# backend/utils/dynamodb_helper.py
# DynamoDB operations for farmer_profiles and chat_sessions tables
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 12

import boto3
import os
import logging
import time as _time
import threading
from datetime import datetime, UTC
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None
dynamodb = boto3.resource('dynamodb', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.resource('dynamodb')
PROFILES_TABLE = os.environ.get('DYNAMODB_PROFILES_TABLE', 'farmer_profiles')
SESSIONS_TABLE = os.environ.get('DYNAMODB_SESSIONS_TABLE', 'chat_sessions')

# TTL: chat messages auto-expire after this many days (DynamoDB TTL attribute = 'ttl')
CHAT_TTL_DAYS = int(os.environ.get('CHAT_TTL_DAYS', '30'))

ENABLE_BATCH_CHAT_WRITES = os.environ.get('ENABLE_BATCH_CHAT_WRITES', 'false').lower() == 'true'
ENABLE_PROFILE_CACHE = os.environ.get('ENABLE_PROFILE_CACHE', 'false').lower() == 'true'
ENABLE_CHAT_IDEMPOTENCY = os.environ.get('ENABLE_CHAT_IDEMPOTENCY', 'false').lower() == 'true'
PROFILE_CACHE_TTL_SEC = int(os.environ.get('PROFILE_CACHE_TTL_SEC', '120'))

_profile_cache = {}
_profile_cache_lock = threading.Lock()


def _idempotency_token_exists(session_id, idempotency_token):
    if not session_id or not idempotency_token:
        return False

    last_evaluated_key = None
    while True:
        query_kwargs = {
            'KeyConditionExpression': boto3.dynamodb.conditions.Key('session_id').eq(session_id),
            'ProjectionExpression': 'idempotency_token',
        }
        if last_evaluated_key:
            query_kwargs['ExclusiveStartKey'] = last_evaluated_key

        response = sessions_table.query(**query_kwargs)
        for item in response.get('Items', []):
            if item.get('idempotency_token') == str(idempotency_token):
                return True

        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            return False

profiles_table = dynamodb.Table(PROFILES_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)


def get_farmer_profile(farmer_id):
    """Retrieve farmer profile by ID. Returns dict or None."""
    cache_enabled = os.environ.get('ENABLE_PROFILE_CACHE', 'false').lower() == 'true'
    if cache_enabled and farmer_id:
        with _profile_cache_lock:
            cached = _profile_cache.get(farmer_id)
        if cached and cached.get('expires_at', 0) > _time.time():
            return cached.get('profile')

    try:
        response = profiles_table.get_item(Key={'farmer_id': farmer_id})
        item = response.get('Item')
        if cache_enabled and farmer_id:
            with _profile_cache_lock:
                _profile_cache[farmer_id] = {
                    'profile': item,
                    'expires_at': _time.time() + PROFILE_CACHE_TTL_SEC,
                }
        return item
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


def save_chat_message(session_id, role, message, language='en', farmer_id=None, message_en=None, idempotency_token=None):
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
        if os.environ.get('ENABLE_CHAT_IDEMPOTENCY', 'false').lower() == 'true' and idempotency_token:
            if _idempotency_token_exists(session_id, idempotency_token):
                logger.info(f"Duplicate chat message skipped for token={idempotency_token}")
                return True
            item['idempotency_token'] = str(idempotency_token)
            sessions_table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(idempotency_token)'
            )
        else:
            sessions_table.put_item(Item=item)
        return True
    except Exception as e:
        if 'ConditionalCheckFailedException' in str(e):
            logger.info(f"Duplicate chat message skipped for token={idempotency_token}")
            return True
        logger.error(f"DynamoDB save chat error: {e}")
        return False


def save_chat_messages_batch(messages):
    """Save multiple chat messages in one operation when batch writes are enabled."""
    if not messages:
        return True

    batch_enabled = os.environ.get('ENABLE_BATCH_CHAT_WRITES', 'false').lower() == 'true'
    if not batch_enabled or len(messages) == 1:
        return all(
            save_chat_message(
                msg.get('session_id'),
                msg.get('role'),
                msg.get('message', ''),
                msg.get('language', 'en'),
                farmer_id=msg.get('farmer_id'),
                message_en=msg.get('message_en'),
                idempotency_token=msg.get('idempotency_token'),
            )
            for msg in messages
        )

    if os.environ.get('ENABLE_CHAT_IDEMPOTENCY', 'false').lower() == 'true':
        return all(
            save_chat_message(
                msg.get('session_id'),
                msg.get('role'),
                msg.get('message', ''),
                msg.get('language', 'en'),
                farmer_id=msg.get('farmer_id'),
                message_en=msg.get('message_en'),
                idempotency_token=msg.get('idempotency_token'),
            )
            for msg in messages
        )

    try:
        for chunk_start in range(0, len(messages), 25):
            chunk = messages[chunk_start:chunk_start + 25]
            with sessions_table.batch_writer() as writer:
                for msg in chunk:
                    timestamp = msg.get('timestamp') or datetime.now(UTC).replace(tzinfo=None).isoformat()
                    ttl_epoch = int(_time.time()) + (CHAT_TTL_DAYS * 86400)
                    item = {
                        'session_id': msg.get('session_id'),
                        'timestamp': timestamp,
                        'role': msg.get('role'),
                        'message': msg.get('message', ''),
                        'language': msg.get('language', 'en'),
                        'ttl': ttl_epoch,
                    }
                    if msg.get('farmer_id'):
                        item['farmer_id'] = msg.get('farmer_id')
                    if msg.get('message_en') and item.get('language') != 'en':
                        item['message_en'] = msg.get('message_en')
                    writer.put_item(Item=item)
        return True
    except Exception as e:
        logger.error(f"DynamoDB batch save chat error: {e}")
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
