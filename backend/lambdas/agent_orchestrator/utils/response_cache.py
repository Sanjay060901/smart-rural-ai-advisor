# backend/lambdas/agent_orchestrator/utils/response_cache.py
# Session-aware response cache using DynamoDB chat_sessions table
# Avoids re-running the Bedrock converse() call for repeated/similar queries
# Owner: Manoj RS
#
# Cache key = hash(normalized_query + location + crop + season)
# Stored in chat_sessions table with PK "cache:{hash}" to avoid new tables/IAM.
# TTL-aware: weather=1h, crop=6h, schemes=12h, general=3h

import hashlib
import json
import logging
import os
import time
from datetime import datetime, UTC

import boto3

logger = logging.getLogger()

dynamodb = boto3.resource('dynamodb')
SESSIONS_TABLE = os.environ.get('DYNAMODB_SESSIONS_TABLE', 'chat_sessions')
_table = dynamodb.Table(SESSIONS_TABLE)

# TTL per query category (seconds)
CACHE_TTL = {
    'weather': 3600,       # 1 hour  — weather changes
    'crop': 21600,         # 6 hours — crop advice is stable
    'pest': 21600,         # 6 hours
    'irrigation': 21600,   # 6 hours
    'schemes': 43200,      # 12 hours — schemes rarely change
    'general': 10800,      # 3 hours
}


def _normalize_query(text):
    """Lowercase, strip, collapse whitespace for consistent hashing."""
    if not text:
        return ''
    import re
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    from datetime import datetime, UTC
    # Remove punctuation for fuzzy matching
    t = re.sub(r'[^\w\s]', '', t)
    return t.strip()


def _detect_category(query_text, intents=None):
    """Detect the cache category from intents or query keywords."""
    if intents:
        for cat in ('weather', 'pest', 'irrigation', 'crop', 'schemes'):
            if cat in intents:
                return cat
    q = (query_text or '').lower()
    if any(w in q for w in ('weather', 'rain', 'temperature', 'forecast', 'monsoon')):
        return 'weather'
    if any(w in q for w in ('pest', 'disease', 'insect', 'fungus', 'spray', 'yellow leaves')):
        return 'pest'
    if any(w in q for w in ('irrigation', 'water', 'drip', 'sprinkler')):
        return 'irrigation'
    if any(w in q for w in ('crop', 'seed', 'sowing', 'fertilizer', 'harvest', 'variety')):
        return 'crop'
    if any(w in q for w in ('scheme', 'subsidy', 'loan', 'insurance', 'pm-kisan', 'yojana')):
        return 'schemes'
    return 'general'


def _build_cache_key(query_text, location=None, crop=None, season=None):
    """Build a deterministic cache key from query + context."""
    parts = [
        _normalize_query(query_text),
        (location or '').lower().strip(),
        (crop or '').lower().strip(),
        (season or '').lower().strip(),
    ]
    raw = '|'.join(parts)
    h = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
    return f"cache:{h}"


def get_cached_response(query_text, location=None, crop=None, season=None, intents=None):
    """
    Look up a cached response for this query signature.
    Returns dict with {reply, reply_en, tools_used, sources, ...} or None on miss.
    """
    cache_key = _build_cache_key(query_text, location, crop, season)
    try:
        resp = _table.get_item(Key={
            'session_id': cache_key,
            'timestamp': 'cached',
        })
        item = resp.get('Item')
        if not item:
            logger.info(f"Cache MISS: {cache_key}")
            return None

        # Check TTL
        expires_at = float(item.get('expires_at', 0))
        if time.time() > expires_at:
            logger.info(f"Cache EXPIRED: {cache_key}")
            return None

        # Deserialize
        cached = json.loads(item.get('response_data', '{}'))
        cached['_cache_hit'] = True
        cached['_cache_key'] = cache_key
        logger.info(f"Cache HIT: {cache_key} (category={item.get('category','?')})")
        return cached

    except Exception as e:
        logger.warning(f"Cache lookup error: {e}")
        return None


def cache_response(query_text, location, crop, season, response_data, intents=None):
    """
    Store a response in the cache. Fire-and-forget — errors are logged but not raised.
    response_data: dict with keys like reply, reply_en, tools_used, sources, etc.
    """
    cache_key = _build_cache_key(query_text, location, crop, season)
    category = _detect_category(query_text, intents)
    ttl = CACHE_TTL.get(category, CACHE_TTL['general'])

    try:
        ttl_epoch = int(time.time() + ttl)
        item = {
            'session_id': cache_key,
            'timestamp': 'cached',
            'category': category,
            'response_data': json.dumps(response_data, default=str),
            'query_normalized': _normalize_query(query_text)[:200],
            'location': (location or '')[:100],
            'crop': (crop or '')[:50],
            'season': (season or '')[:20],
            'created_at': datetime.now(UTC).replace(tzinfo=None).isoformat(),
            'expires_at': str(ttl_epoch),
            'ttl_seconds': ttl,
            'ttl': ttl_epoch,  # DynamoDB TTL attribute — auto-delete expired cache entries
        }
        _table.put_item(Item=item)
        logger.info(f"Cache STORED: {cache_key} (category={category}, ttl={ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache store error: {e}")
        return False
