# backend/utils/dynamodb_helper.py
# DynamoDB operations for farmer_profiles and chat_sessions tables
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 12

import boto3
import os
import logging
import time as _time
from datetime import datetime, UTC

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
PROFILES_TABLE = os.environ.get('DYNAMODB_PROFILES_TABLE', 'farmer_profiles')
SESSIONS_TABLE = os.environ.get('DYNAMODB_SESSIONS_TABLE', 'chat_sessions')

# TTL: chat messages auto-expire after this many days (DynamoDB TTL attribute = 'ttl')
CHAT_TTL_DAYS = int(os.environ.get('CHAT_TTL_DAYS', '30'))

profiles_table = dynamodb.Table(PROFILES_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)


def get_farmer_profile(farmer_id):
    """Retrieve farmer profile by ID. Returns dict or None."""
    try:
        response = profiles_table.get_item(Key={'farmer_id': farmer_id})
        return response.get('Item')
    except Exception as e:
        logger.error(f"DynamoDB get profile error: {e}")
        return None


def put_farmer_profile(farmer_id, profile_data):
    """Create or update farmer profile. Returns True on success."""
    try:
        item = {
            'farmer_id': farmer_id,
            **profile_data,
            'updated_at': datetime.now(UTC).replace(tzinfo=None).isoformat()
        }
        profiles_table.put_item(Item=item)
        return True
    except Exception as e:
        logger.error(f"DynamoDB put profile error: {e}")
        return False


def save_chat_message(session_id, role, message, language='en', farmer_id=None, message_en=None):
    """Save a single chat message to session history.
    Includes a TTL epoch so DynamoDB auto-deletes old messages after CHAT_TTL_DAYS.
    When language != 'en', also stores message_en (English version) for pipeline context.
    """
    try:
        timestamp = datetime.now(UTC).replace(tzinfo=None).isoformat()
        ttl_epoch = int(_time.time()) + (CHAT_TTL_DAYS * 86400)
        item = {
            'session_id': session_id,
            'timestamp': timestamp,
            'role': role,  # 'user' or 'assistant'
            'message': message,
            'language': language,
            'ttl': ttl_epoch,  # DynamoDB TTL attribute — auto-expire
        }
        if farmer_id:
            item['farmer_id'] = farmer_id
        # Store English version alongside local language for better pipeline context
        if message_en and language and language != 'en':
            item['message_en'] = message_en
        sessions_table.put_item(Item=item)
        return True
    except Exception as e:
        logger.error(f"DynamoDB save chat error: {e}")
        return False


def get_session_message_count(session_id):
    """Return the number of messages stored for a session.
    Uses Select='COUNT' for efficiency — doesn't transfer item data."""
    try:
        response = sessions_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('session_id').eq(session_id),
            Select='COUNT',
        )
        return response.get('Count', 0)
    except Exception as e:
        logger.error(f"DynamoDB count error: {e}")
        return 0


def get_chat_history(session_id, limit=40):
    """Retrieve the most recent chat messages for a session (sorted oldest→newest).

    DynamoDB Query with ScanIndexForward=False returns newest first, then we
    reverse so callers always receive chronological order (oldest→newest).
    This ensures we always get the *latest* N messages, not the first N ever stored.
    """
    try:
        response = sessions_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('session_id').eq(session_id),
            ScanIndexForward=False,  # Newest first so Limit grabs the tail
            Limit=limit
        )
        items = response.get('Items', [])
        # Reverse back to chronological order (oldest → newest)
        items.reverse()
        return items
    except Exception as e:
        logger.error(f"DynamoDB get chat history error: {e}")
        return []
