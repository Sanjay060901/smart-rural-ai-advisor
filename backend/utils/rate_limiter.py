# backend/utils/rate_limiter.py
# Enterprise Rate Limiting: Per-session + per-farmer request throttling
# Uses DynamoDB for serverless, distributed rate tracking
# Owner: Manoj RS
# Gap addressed: #3 Rate Limiting

import boto3
import os
import logging
import time
from datetime import datetime, UTC

logger = logging.getLogger()

# ── Configuration ──
# Limits are generous for real farmers but block abuse
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.environ.get('RATE_LIMIT_RPM', '15'))
RATE_LIMIT_REQUESTS_PER_HOUR = int(os.environ.get('RATE_LIMIT_RPH', '120'))
RATE_LIMIT_DAILY_MAX = int(os.environ.get('RATE_LIMIT_DAILY', '500'))

# DynamoDB table for rate tracking (reuse chat_sessions or create dedicated)
RATE_LIMIT_TABLE = os.environ.get('DYNAMODB_RATE_LIMIT_TABLE', 'rate_limits')
ENABLE_RATE_LIMIT_TTL = os.environ.get('ENABLE_RATE_LIMIT_TTL', 'false').lower() == 'true'

# Lazy-init DynamoDB resource (avoid cold-start cost if rate limiting disabled)
_dynamodb = None
_rate_table = None
RATE_LIMITING_ENABLED = os.environ.get('ENABLE_RATE_LIMITING', 'true').lower() == 'true'


def _rate_update_parts(ttl_epoch, now_iso):
    if ENABLE_RATE_LIMIT_TTL:
        return (
            'SET hit_count = if_not_exists(hit_count, :zero) + :inc, ttl_epoch = :ttl, updated_at = :now',
            {':zero': 0, ':inc': 1, ':ttl': ttl_epoch, ':now': now_iso},
        )
    return (
        'SET hit_count = if_not_exists(hit_count, :zero) + :inc, updated_at = :now',
        {':zero': 0, ':inc': 1, ':now': now_iso},
    )


def _get_rate_table():
    """Lazy-initialize DynamoDB table for rate limiting."""
    global _dynamodb, _rate_table
    if _rate_table is None:
        _dynamodb = boto3.resource('dynamodb')
        _rate_table = _dynamodb.Table(RATE_LIMIT_TABLE)
    return _rate_table


def check_rate_limit(session_id, farmer_id='anonymous'):
    """
    Check if the session/farmer has exceeded rate limits.
    Uses a sliding window counter stored in DynamoDB.
    
    Returns: {
        'allowed': bool,
        'reason': str or None,           # why blocked
        'remaining_rpm': int,             # requests left this minute
        'remaining_rph': int,             # requests left this hour  
        'retry_after_seconds': int or None,  # when to retry
    }
    """
    if not RATE_LIMITING_ENABLED:
        return {
            'allowed': True,
            'reason': None,
            'remaining_rpm': RATE_LIMIT_REQUESTS_PER_MINUTE,
            'remaining_rph': RATE_LIMIT_REQUESTS_PER_HOUR,
            'retry_after_seconds': None,
        }

    now = time.time()
    now_iso = datetime.now(UTC).replace(tzinfo=None).isoformat()
    minute_key = f"{farmer_id}#{int(now // 60)}"
    hour_key = f"{farmer_id}#{int(now // 3600)}"
    day_key = f"{farmer_id}#{datetime.now(UTC).strftime('%Y-%m-%d')}"

    try:
        table = _get_rate_table()

        # Atomic increment for per-minute counter
        minute_update_expr, minute_attrs = _rate_update_parts(int(now) + 120, now_iso)
        minute_resp = table.update_item(
            Key={'rate_key': minute_key, 'window': 'minute'},
            UpdateExpression=minute_update_expr,
            ExpressionAttributeValues=minute_attrs,
            ReturnValues='UPDATED_NEW',
        )
        minute_count = int(minute_resp['Attributes']['hit_count'])

        if minute_count > RATE_LIMIT_REQUESTS_PER_MINUTE:
            seconds_left = 60 - int(now % 60)
            logger.warning(
                f"RATE LIMIT: minute limit exceeded | farmer={farmer_id} | "
                f"count={minute_count}/{RATE_LIMIT_REQUESTS_PER_MINUTE}"
            )
            return {
                'allowed': False,
                'reason': f'Rate limit exceeded: {RATE_LIMIT_REQUESTS_PER_MINUTE} requests per minute. Please wait.',
                'remaining_rpm': 0,
                'remaining_rph': max(0, RATE_LIMIT_REQUESTS_PER_HOUR - minute_count),
                'retry_after_seconds': seconds_left,
            }

        # Atomic increment for per-hour counter
        hour_update_expr, hour_attrs = _rate_update_parts(int(now) + 7200, now_iso)
        hour_resp = table.update_item(
            Key={'rate_key': hour_key, 'window': 'hour'},
            UpdateExpression=hour_update_expr,
            ExpressionAttributeValues=hour_attrs,
            ReturnValues='UPDATED_NEW',
        )
        hour_count = int(hour_resp['Attributes']['hit_count'])

        if hour_count > RATE_LIMIT_REQUESTS_PER_HOUR:
            seconds_left = 3600 - int(now % 3600)
            logger.warning(
                f"RATE LIMIT: hourly limit exceeded | farmer={farmer_id} | "
                f"count={hour_count}/{RATE_LIMIT_REQUESTS_PER_HOUR}"
            )
            return {
                'allowed': False,
                'reason': f'Hourly limit of {RATE_LIMIT_REQUESTS_PER_HOUR} requests exceeded. Please try after some time.',
                'remaining_rpm': max(0, RATE_LIMIT_REQUESTS_PER_MINUTE - minute_count),
                'remaining_rph': 0,
                'retry_after_seconds': min(seconds_left, 300),  # cap at 5 min message
            }

        # Atomic increment for daily counter
        day_update_expr, day_attrs = _rate_update_parts(int(now) + 172800, now_iso)
        day_resp = table.update_item(
            Key={'rate_key': day_key, 'window': 'day'},
            UpdateExpression=day_update_expr,
            ExpressionAttributeValues=day_attrs,
            ReturnValues='UPDATED_NEW',
        )
        day_count = int(day_resp['Attributes']['hit_count'])

        if day_count > RATE_LIMIT_DAILY_MAX:
            logger.warning(
                f"RATE LIMIT: daily limit exceeded | farmer={farmer_id} | "
                f"count={day_count}/{RATE_LIMIT_DAILY_MAX}"
            )
            return {
                'allowed': False,
                'reason': f'Daily limit of {RATE_LIMIT_DAILY_MAX} requests exceeded. Please try again tomorrow.',
                'remaining_rpm': max(0, RATE_LIMIT_REQUESTS_PER_MINUTE - minute_count),
                'remaining_rph': max(0, RATE_LIMIT_REQUESTS_PER_HOUR - hour_count),
                'retry_after_seconds': None,
            }

        return {
            'allowed': True,
            'reason': None,
            'remaining_rpm': max(0, RATE_LIMIT_REQUESTS_PER_MINUTE - minute_count),
            'remaining_rph': max(0, RATE_LIMIT_REQUESTS_PER_HOUR - hour_count),
            'retry_after_seconds': None,
        }

    except Exception as e:
        # Fail closed on rate-limit persistence errors to avoid bypass under infra faults
        logger.error(f"Rate limiter error (failing closed): {str(e)}")
        return {
            'allowed': False,
            'reason': 'Rate limiting service temporarily unavailable. Please retry shortly.',
            'remaining_rpm': 0,
            'remaining_rph': 0,
            'retry_after_seconds': 30,
        }
