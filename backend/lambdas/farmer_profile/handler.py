# backend/lambdas/farmer_profile/handler.py
# Lambda Tool: Farmer profile management (DynamoDB)
# Owner: Manoj RS
# Endpoints: GET /profile/{farmerId}, PUT /profile/{farmerId}
#            POST /otp/send, POST /otp/verify
# See: Detailed_Implementation_Guide.md Section 11

import json
import boto3
import os
import logging
import secrets
import re
import time
from datetime import datetime, UTC
from decimal import Decimal
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from utils.cors_helper import get_cors_headers, handle_cors_preflight

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Security: Input validation constants ──
MAX_NAME_LENGTH = 100
MAX_FIELD_LENGTH = 200
MAX_CROPS = 20
MAX_LAND_SIZE = 10000  # acres
PHONE_PATTERN = re.compile(r'^\d{10,15}$')
FARMER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]{1,64}$')
CANONICAL_FARMER_ID_PATTERN = re.compile(r'^ph_[6-9]\d{9}$')

ALLOWED_PROFILE_FIELDS = {
    'name', 'state', 'district', 'crops', 'soil_type',
    'land_size_acres', 'language', 'created_at', 'farmer_id'
}

def _sanitize_text(value, max_len=MAX_FIELD_LENGTH):
    """Sanitize a text field: strip, truncate, remove dangerous chars."""
    if not value:
        return ''
    value = str(value).strip()[:max_len]
    value = re.sub(r'[<>{}\[\]|;`$\\]', '', value)
    return value

def _validate_phone(phone):
    """Validate and clean phone number. Returns (clean_phone, error_msg)."""
    if not phone:
        return None, 'Phone number is required'
    phone = re.sub(r'[\s\-\+]', '', str(phone))
    # Extract last 10 digits (Indian phone)
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) < 10:
        return None, 'Invalid phone number'
    clean = digits_only[-10:]
    if not re.match(r'^[6-9]\d{9}$', clean):
        return None, 'Invalid Indian phone number'
    return clean, None


def _mask_phone(phone_value):
    """Mask phone for API responses: 9876543210 -> 987***10."""
    if phone_value is None:
        return None
    digits = re.sub(r'\D', '', str(phone_value))
    if len(digits) < 5:
        return '***'
    return f"{digits[:3]}***{digits[-2:]}"


def _mask_profile_phone_fields(profile):
    """Return a copy of profile with sensitive phone fields masked."""
    if not isinstance(profile, dict):
        return profile

    masked = dict(profile)
    for field in ('phone', 'phone_number', 'mobile', 'phone_normalized'):
        if field in masked and masked[field] is not None:
            masked[field] = _mask_phone(masked[field])
    return masked


def _extract_phone_from_farmer_id(farmer_id):
    value = str(farmer_id or '').strip()
    if not CANONICAL_FARMER_ID_PATTERN.match(value):
        return None
    return value[3:]


def _normalize_phone_from_item(item):
    for field in ('phone_normalized', 'phone', 'phone_number', 'mobile'):
        raw = item.get(field)
        if raw is None:
            continue
        digits = re.sub(r'\D', '', str(raw))
        if len(digits) >= 10:
            candidate = digits[-10:]
            if re.match(r'^[6-9]\d{9}$', candidate):
                return candidate

    fid = str(item.get('farmer_id', '')).strip()
    if CANONICAL_FARMER_ID_PATTERN.match(fid):
        return fid[3:]

    return None


def _find_conflicting_profile_ids(clean_phone, current_farmer_id):
    conflicts = set()
    scan_kwargs = {
        'ProjectionExpression': 'farmer_id, phone, phone_normalized, phone_number, mobile',
        'FilterExpression': (
            Attr('phone_normalized').eq(clean_phone)
            | Attr('phone').eq(clean_phone)
            | Attr('phone_number').eq(clean_phone)
            | Attr('mobile').eq(clean_phone)
            | Attr('farmer_id').contains(clean_phone)
        )
    }

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            item_farmer_id = str(item.get('farmer_id', '')).strip()
            if not item_farmer_id or item_farmer_id == current_farmer_id:
                continue
            if _normalize_phone_from_item(item) == clean_phone:
                conflicts.add(item_farmer_id)

        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    return sorted(conflicts)


class DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types in JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return super().default(obj)


def convert_decimals(obj):
    """Recursively convert Decimal values to int/float for JSON safety."""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return obj


ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
ENABLE_FARMER_ID_VALIDATION = os.environ.get('ENABLE_FARMER_ID_VALIDATION', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None

dynamodb = boto3.resource('dynamodb', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp', region_name=os.environ.get('AWS_REGION', 'ap-south-1'), config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('cognito-idp', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
table = dynamodb.Table(os.environ.get('DYNAMODB_PROFILES_TABLE', 'farmer_profiles'))
otp_table = dynamodb.Table(os.environ.get('DYNAMODB_OTP_TABLE', 'otp_codes'))

COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
STAGE = os.environ.get('STAGE', 'prod')

ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', 'https://d80ytlzsrax1n.cloudfront.net')
ENABLE_UNIFIED_CORS = os.environ.get('ENABLE_UNIFIED_CORS', 'false').lower() == 'true'
CORS_HEADERS = get_cors_headers(ALLOWED_ORIGIN, methods='GET,PUT,POST,DELETE,OPTIONS') if ENABLE_UNIFIED_CORS else {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,PUT,POST,DELETE,OPTIONS'
}


def _error_body(message, language='en'):
    """Canonical error envelope with legacy `error` compatibility field."""
    return {
        'status': 'error',
        'data': None,
        'message': message,
        'language': language,
        'error': message,
    }

OTP_EXPIRY_SECONDS = 300  # 5 minutes
ENABLE_DEMO_OTP = os.environ.get('ENABLE_DEMO_OTP', 'false').lower() == 'true'


def lambda_handler(event, context):
    """Handle profile CRUD and OTP send/verify."""
    try:
        method = event.get('httpMethod', 'GET')
        path = event.get('path', '')

        # Handle CORS preflight
        if method == 'OPTIONS':
            if ENABLE_UNIFIED_CORS:
                return handle_cors_preflight(ALLOWED_ORIGIN, methods='GET,PUT,POST,DELETE,OPTIONS')
            return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

        # OTP endpoints
        if path == '/otp/send' and method == 'POST':
            body = json.loads(event.get('body', '{}'))
            return send_otp(body)
        elif path == '/otp/verify' and method == 'POST':
            body = json.loads(event.get('body', '{}'))
            return verify_otp(body)
        elif path == '/pin/reset' and method == 'POST':
            body = json.loads(event.get('body', '{}'))
            return reset_pin(body)

        # Profile endpoints
        farmer_id = event.get('pathParameters', {}).get('farmerId')

        if not farmer_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('Missing farmerId in path'))
            }

        if os.environ.get('ENABLE_FARMER_ID_VALIDATION', 'false').lower() == 'true' and not FARMER_ID_PATTERN.match(str(farmer_id)):
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('Invalid farmerId format'))
            }

        if method == 'GET':
            return get_profile(farmer_id)
        elif method == 'PUT':
            body = json.loads(event.get('body', '{}'))
            return put_profile(farmer_id, body)
        elif method == 'DELETE':
            return delete_profile(farmer_id)
        else:
            return {
                'statusCode': 405,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body(f'Method {method} not allowed'))
            }

    except Exception as e:
        logger.error(f"Profile error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Internal server error'))
        }


def delete_profile(farmer_id):
    """Permanently delete farmer profile from DynamoDB AND Cognito user."""
    errors = []

    # 1. Delete DynamoDB profile
    try:
        table.delete_item(Key={'farmer_id': farmer_id})
        logger.info(f"Deleted DynamoDB profile: {farmer_id}")
    except Exception as e:
        logger.error(f"DynamoDB delete error: {str(e)}", exc_info=True)
        errors.append('Failed to delete profile data')

    # 2. Delete Cognito user (extract phone from farmer_id: ph_XXXXXXXXXX)
    if farmer_id.startswith('ph_'):
        phone = farmer_id[3:]  # strip "ph_"
        cognito_username = f'+91{phone}'
        try:
            cognito.admin_delete_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=cognito_username
            )
            logger.info(f"Deleted Cognito user: {cognito_username}")
        except cognito.exceptions.UserNotFoundException:
            logger.info(f"Cognito user already gone: {cognito_username}")
        except Exception as e:
            logger.error(f"Cognito delete error: {str(e)}", exc_info=True)
            errors.append('Failed to delete authentication record')

    if errors:
        return {
            'statusCode': 207,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'partial',
                'message': 'Profile partially deleted',
                'errors': errors
            })
        }

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'status': 'success',
            'message': 'Profile and account deleted'
        })
    }


def get_profile(farmer_id):
    """Get farmer profile by ID. Returns empty profile if not found."""
    result = table.get_item(Key={'farmer_id': farmer_id})

    if 'Item' in result:
        profile_data = convert_decimals(result['Item'])
        profile_data = _mask_profile_phone_fields(profile_data)
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'success',
                'data': profile_data,
                'message': 'Profile found'
            })
        }
    else:
        blank = {
            'farmer_id': farmer_id,
            'name': '',
            'state': '',
            'district': '',
            'crops': [],
            'soil_type': '',
            'land_size_acres': 0,
            'language': 'ta-IN',
            'created_at': None
        }
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'success',
                'data': blank,
                'message': 'New profile'
            })
        }


def put_profile(farmer_id, body):
    """Create or update farmer profile with schema validation."""
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    canonical_phone = _extract_phone_from_farmer_id(farmer_id)
    if not canonical_phone:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Invalid farmerId format. Expected ph_XXXXXXXXXX'))
        }

    # Security: reject unknown fields (allow only whitelisted)
    body_keys = set(body.keys())

    # ── Partial update: language-only (from language switcher) ──
    if body_keys == {'language'} or body_keys <= {'language', 'farmer_id'}:
        lang = _sanitize_text(body.get('language', 'en-IN'), 10)
        table.update_item(
            Key={'farmer_id': farmer_id},
            UpdateExpression='SET #lang = :language, updated_at = :updated_at',
            ExpressionAttributeNames={'#lang': 'language'},
            ExpressionAttributeValues={
                ':language': lang,
                ':updated_at': now
            }
        )
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'status': 'success', 'message': 'Language updated'})
        }

    # ── Full profile update with validation ──
    # Sanitize all fields
    name = _sanitize_text(body.get('name', ''), MAX_NAME_LENGTH)
    state = _sanitize_text(body.get('state', ''))
    district = _sanitize_text(body.get('district', ''))
    soil_type = _sanitize_text(body.get('soil_type', ''))
    language = _sanitize_text(body.get('language', 'ta-IN'), 10)

    # Mandatory profile location fields
    if not state:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('State is required'))
        }
    if not district:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('District is required'))
        }

    # Validate crops (must be a list of strings, capped)
    raw_crops = body.get('crops', [])
    if not isinstance(raw_crops, list):
        raw_crops = []
    crops = [_sanitize_text(str(c), 50) for c in raw_crops[:MAX_CROPS] if c]

    # Validate land size (must be a reasonable number)
    land_size = body.get('land_size_acres', 0)
    try:
        land_size = float(land_size)
        if land_size < 0 or land_size > MAX_LAND_SIZE:
            land_size = 0
    except (ValueError, TypeError):
        land_size = 0

    # Convert to Decimal for DynamoDB (rejects Python float)
    land_size = Decimal(str(land_size))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    item = {
        'farmer_id': farmer_id,
        'phone': canonical_phone,
        'phone_normalized': canonical_phone,
        'name': name,
        'state': state,
        'district': district,
        'crops': crops,
        'soil_type': soil_type,
        'land_size_acres': land_size,
        'language': language,
        'updated_at': now
    }

    # Use update_item to set created_at only if it doesn't exist (avoids extra get_item)
    # But put_item is simpler for full-profile saves, so we use conditional logic
    # First try to just update updated_at and merge; for simplicity, use put_item
    # with a created_at from the body (frontend can track it) or fallback to now
    item['created_at'] = body.get('created_at', now)

    try:
        conflicting_ids = _find_conflicting_profile_ids(canonical_phone, farmer_id)
    except Exception as e:
        logger.warning(f"Phone uniqueness check skipped (non-fatal): {e}")
        conflicting_ids = []

    if conflicting_ids:
        return {
            'statusCode': 409,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'error',
                'error': 'This phone number is already linked to another profile',
                'conflicting_farmer_ids': conflicting_ids
            })
        }

    # If item already exists, preserve its created_at using an update expression
    try:
        table.update_item(
            Key={'farmer_id': farmer_id},
            UpdateExpression='SET #n = :name, #s = :state, district = :district, crops = :crops, '
                           'soil_type = :soil_type, land_size_acres = :land_size, '
                           '#lang = :language, #phone = :phone, phone_normalized = :phone_normalized, '
                           'updated_at = :updated_at, '
                           'created_at = if_not_exists(created_at, :now)',
            ExpressionAttributeNames={
                '#n': 'name',
                '#s': 'state',
                '#lang': 'language',
                '#phone': 'phone'
            },
            ExpressionAttributeValues={
                ':name': item['name'],
                ':state': item['state'],
                ':district': item['district'],
                ':crops': item['crops'],
                ':soil_type': item['soil_type'],
                ':land_size': land_size,
                ':language': item['language'],
                ':phone': item['phone'],
                ':phone_normalized': item['phone_normalized'],
                ':updated_at': now,
                ':now': now
            }
        )
    except Exception as e:
        logger.error(f"update_item failed, falling back to put_item: {e}")
        table.put_item(Item=item)

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'status': 'success',
            'message': 'Profile saved',
            'data': _mask_profile_phone_fields(convert_decimals(item))
        })
    }


def send_otp(body):
    """Generate OTP and store it for verification (no external delivery providers)."""
    phone = body.get('phone', '')
    clean_phone, phone_err = _validate_phone(phone)
    if phone_err:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body(phone_err))
        }

    otp_code = f"{secrets.randbelow(900000) + 100000:06d}"
    expiry = int(time.time()) + OTP_EXPIRY_SECONDS

    # ── Step 4: Store OTP in DynamoDB ──
    try:
        otp_item = {
            'phone': clean_phone,
            'otp_code': otp_code,
            'expiry_ttl': expiry,
            'created_at': datetime.now(UTC).replace(tzinfo=None).isoformat(),
            'verified': False,
            'sandbox_verification': False
        }
        otp_table.put_item(Item=otp_item)
    except Exception as e:
        logger.error(f"Failed to store OTP: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Failed to generate OTP'))
        }

    # ── Step 5: Build response ──
    # Security: NEVER return the OTP code in the API response
    # The OTP is stored in DynamoDB and verified server-side only
    message = 'OTP generated successfully'

    response_data = {
        'status': 'success',
        'message': message,
        'sms_sent': False,
        'sandbox_verification': False,
        'sms_provider': None,
        'phone_masked': f'+91 {clean_phone[:3]}***{clean_phone[-2:]}'
    }

    # Prototype mode: include generated OTP in response for deterministic testing
    if ENABLE_DEMO_OTP:
        response_data['demo_otp'] = otp_code

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps(response_data)
    }


def verify_otp(body):
    """Verify the OTP entered by the user. Supports both direct SMS and sandbox verification flows."""
    phone = body.get('phone', '')
    entered_otp = str(body.get('otp', '')).strip()

    clean_phone, phone_err = _validate_phone(phone)
    if phone_err:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body(phone_err))
        }
    if not entered_otp or not re.match(r'^\d{6}$', entered_otp):
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Invalid OTP format. Must be 6 digits.'))
        }

    try:
        result = otp_table.get_item(Key={'phone': clean_phone})
        if 'Item' not in result:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('No OTP found. Please request a new one.'))
            }

        item = result['Item']
        expiry = int(item.get('expiry_ttl', 0))
        now = int(time.time())
        if now > expiry:
            # Clean up expired OTP
            otp_table.delete_item(Key={'phone': clean_phone})
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('OTP has expired. Please request a new one.'))
            }

        stored_otp = item.get('otp_code', '')

        if entered_otp != stored_otp:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('Incorrect OTP. Please try again.'))
            }

        # OTP is valid — mark as verified and clean up
        otp_table.delete_item(Key={'phone': clean_phone})

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'success',
                'message': 'OTP verified successfully',
                'verified': True
            })
        }

    except Exception as e:
        logger.error(f"OTP verification error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Verification failed. Please try again.'))
        }


def reset_pin(body):
    """Reset Cognito PIN/password after verifying generated OTP."""
    phone = body.get('phone', '')
    entered_otp = str(body.get('otp', '')).strip()
    new_pin = str(body.get('new_pin', '')).strip()

    clean_phone, phone_err = _validate_phone(phone)
    if phone_err:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body(phone_err))
        }

    if not entered_otp or not re.match(r'^\d{6}$', entered_otp):
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Invalid OTP format. Must be 6 digits.'))
        }

    if len(new_pin) < 6:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('PIN must be at least 6 characters.'))
        }

    try:
        result = otp_table.get_item(Key={'phone': clean_phone})
        item = result.get('Item')
        if not item:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('No OTP found. Please request a new one.'))
            }

        expiry = int(item.get('expiry_ttl', 0))
        if int(time.time()) > expiry:
            otp_table.delete_item(Key={'phone': clean_phone})
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('OTP has expired. Please request a new one.'))
            }

        if entered_otp != item.get('otp_code', ''):
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps(_error_body('Incorrect OTP. Please try again.'))
            }

        username = f'+91{clean_phone}'
        cognito.admin_set_user_password(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
            Password=new_pin,
            Permanent=True
        )

        otp_table.delete_item(Key={'phone': clean_phone})

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'status': 'success', 'message': 'PIN reset successfully'})
        }

    except cognito.exceptions.UserNotFoundException:
        return {
            'statusCode': 404,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('User not found for this phone number.'))
        }
    except Exception as e:
        logger.error(f"PIN reset error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps(_error_body('Failed to reset PIN. Please try again.'))
        }
