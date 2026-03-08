# utils/chat_history.py
# Server-side chat history persistence using DynamoDB
# Uses existing chat_sessions table with 'hist:{farmer_id}' partition key
# so no new tables or IAM changes are needed.

import boto3
import os
import json
import logging
import time

logger = logging.getLogger()

SESSIONS_TABLE = os.environ.get('DYNAMODB_SESSIONS_TABLE', 'chat_sessions')
MAX_MESSAGES_PER_SESSION = 100  # 50 user + 50 assistant = 50 interactions
MAX_SESSIONS_PER_FARMER = 20  # Auto-evict oldest when exceeded
SESSION_TTL_DAYS = 30  # Auto-expire session blobs after 30 days

_dynamodb = None
_table = None


def _get_table():
    global _dynamodb, _table
    if _table is None:
        _dynamodb = boto3.resource('dynamodb')
        _table = _dynamodb.Table(SESSIONS_TABLE)
    return _table


def list_sessions(farmer_id):
    """
    List all chat sessions for a farmer.
    Returns list of session metadata (no messages).
    """
    if not farmer_id or farmer_id == 'anonymous':
        return []

    table = _get_table()
    pk = f'hist:{farmer_id}'

    try:
        resp = table.query(
            KeyConditionExpression='session_id = :pk',
            ExpressionAttributeValues={':pk': pk},
            ProjectionExpression='#ts, sid, preview, message_count, created_at, updated_at',
            ExpressionAttributeNames={'#ts': 'timestamp'},
        )
        sessions = []
        for item in resp.get('Items', []):
            sessions.append({
                'id': item.get('sid', ''),
                'preview': item.get('preview', 'New chat'),
                'messageCount': int(item.get('message_count', 0)),
                'createdAt': int(item.get('created_at', 0)),
                'lastTimestamp': int(item.get('updated_at', 0)),
            })
        # Sort by most recent first
        sessions.sort(key=lambda s: s['lastTimestamp'], reverse=True)
        return sessions
    except Exception as e:
        logger.error(f'list_sessions error: {e}')
        return []


def get_session_messages(farmer_id, session_id):
    """
    Get all messages for a specific chat session.
    """
    if not farmer_id or farmer_id == 'anonymous':
        return []

    table = _get_table()
    pk = f'hist:{farmer_id}'

    try:
        resp = table.get_item(
            Key={'session_id': pk, 'timestamp': session_id}
        )
        item = resp.get('Item')
        if not item:
            return []

        messages_json = item.get('messages', '[]')
        if isinstance(messages_json, str):
            return json.loads(messages_json)
        return messages_json
    except Exception as e:
        logger.error(f'get_session_messages error: {e}')
        return []


def save_session(farmer_id, session_id, messages, preview=None):
    """
    Save/update a chat session with all its messages.
    """
    if not farmer_id or farmer_id == 'anonymous':
        return False
    if not session_id or not messages:
        return False

    table = _get_table()
    pk = f'hist:{farmer_id}'
    now = int(time.time() * 1000)

    # Derive preview from first user message if not provided
    if not preview:
        first_user = next((m for m in messages if m.get('role') == 'user'), None)
        preview = (first_user.get('content', '')[:60] if first_user else 'New chat')

    # Get existing created_at or use now
    created_at = now
    try:
        existing = table.get_item(
            Key={'session_id': pk, 'timestamp': session_id},
            ProjectionExpression='created_at'
        )
        if existing.get('Item'):
            created_at = int(existing['Item'].get('created_at', now))
    except Exception:
        pass

    # Trim messages to max
    trimmed = messages[-MAX_MESSAGES_PER_SESSION:]

    # TTL: auto-expire session blobs after SESSION_TTL_DAYS
    ttl_epoch = int(time.time()) + (SESSION_TTL_DAYS * 86400)

    try:
        table.put_item(Item={
            'session_id': pk,
            'timestamp': session_id,
            'sid': session_id,
            'farmer_id': farmer_id,
            'messages': json.dumps(trimmed, ensure_ascii=False),
            'preview': preview,
            'message_count': len(trimmed),
            'created_at': created_at,
            'updated_at': now,
            'ttl': ttl_epoch,  # DynamoDB TTL — auto-delete old sessions
        })

        # ── Session count limit: evict oldest sessions if too many ──
        _enforce_session_limit(table, pk, farmer_id)

        return True
    except Exception as e:
        logger.error(f'save_session error: {e}')
        return False


def _enforce_session_limit(table, pk, farmer_id):
    """Delete oldest sessions if farmer exceeds MAX_SESSIONS_PER_FARMER.
    Keeps the most recent sessions, evicts the oldest by created_at."""
    try:
        resp = table.query(
            KeyConditionExpression='session_id = :pk',
            ExpressionAttributeValues={':pk': pk},
            ProjectionExpression='#ts, created_at, sid',
            ExpressionAttributeNames={'#ts': 'timestamp'},
        )
        items = resp.get('Items', [])
        if len(items) <= MAX_SESSIONS_PER_FARMER:
            return  # Under limit, nothing to do

        # Sort by created_at ascending (oldest first)
        items.sort(key=lambda x: int(x.get('created_at', 0)))
        to_delete = items[:len(items) - MAX_SESSIONS_PER_FARMER]

        for item in to_delete:
            table.delete_item(
                Key={'session_id': pk, 'timestamp': item['timestamp']}
            )
            logger.info(f'Evicted old session {item.get("sid","?")} for farmer {farmer_id}')
    except Exception as e:
        logger.warning(f'_enforce_session_limit error (non-fatal): {e}')


def delete_session(farmer_id, session_id):
    """
    Delete a chat session fully:
    - session metadata row under hist:{farmer_id}
    - all message rows under session_id partition
    """
    if not farmer_id or farmer_id == 'anonymous':
        return {
            'deleted': False,
            'deleted_history': 0,
            'deleted_messages': 0,
        }
    if not session_id:
        return {
            'deleted': False,
            'deleted_history': 0,
            'deleted_messages': 0,
        }

    table = _get_table()
    hist_pk = f'hist:{farmer_id}'
    deleted_history = 0
    deleted_messages = 0

    try:
        # Delete history/session metadata row
        table.delete_item(
            Key={'session_id': hist_pk, 'timestamp': session_id}
        )
        deleted_history = 1

        # Delete all per-message rows for this chat session
        last_evaluated_key = None
        while True:
            query_kwargs = {
                'KeyConditionExpression': 'session_id = :sid',
                'ExpressionAttributeValues': {':sid': session_id},
                'ProjectionExpression': '#ts',
                'ExpressionAttributeNames': {'#ts': 'timestamp'},
            }
            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key

            resp = table.query(**query_kwargs)
            items = resp.get('Items', [])
            for item in items:
                ts = item.get('timestamp')
                if ts is None:
                    continue
                table.delete_item(Key={'session_id': session_id, 'timestamp': ts})
                deleted_messages += 1

            last_evaluated_key = resp.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        return {
            'deleted': True,
            'deleted_history': deleted_history,
            'deleted_messages': deleted_messages,
        }
    except Exception as e:
        logger.error(f'delete_session error: {e}')
        return {
            'deleted': False,
            'deleted_history': deleted_history,
            'deleted_messages': deleted_messages,
        }


def rename_session(farmer_id, session_id, new_title):
    """
    Rename a chat session's preview/title.
    Uses UpdateItem to only modify the preview field without touching messages.
    """
    if not farmer_id or farmer_id == 'anonymous':
        return False
    if not session_id or not new_title:
        return False

    table = _get_table()
    pk = f'hist:{farmer_id}'

    # Sanitize: strip whitespace, limit to 80 chars
    clean_title = new_title.strip()[:80]
    if not clean_title:
        return False

    try:
        table.update_item(
            Key={'session_id': pk, 'timestamp': session_id},
            UpdateExpression='SET preview = :p, updated_at = :u',
            ExpressionAttributeValues={
                ':p': clean_title,
                ':u': int(time.time() * 1000),
            },
        )
        return True
    except Exception as e:
        logger.error(f'rename_session error: {e}')
        return False
