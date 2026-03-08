# backend/lambdas/crop_advisory/handler.py
# Lambda Tool: Crop + Pest + Irrigation advisory
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 9

import json
import boto3
import os
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple
from botocore.config import Config
from utils.response_helper import success_response, error_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None
bedrock_kb = boto3.client('bedrock-agent-runtime', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('bedrock-agent-runtime')
KB_ID = os.environ.get('BEDROCK_KB_ID', '')

# Feature flag: KB retry on throttling (default: OFF) — Bug 1.6
ENABLE_KB_RETRY = os.environ.get('ENABLE_KB_RETRY', 'false').lower() == 'true'
KB_RETRY_MAX_ATTEMPTS = int(os.environ.get('KB_RETRY_MAX_ATTEMPTS', '3'))
KB_RETRY_BASE_DELAY = float(os.environ.get('KB_RETRY_BASE_DELAY', '1.0'))

# Retrieval quality gates
KB_RETRIEVAL_TOP_K = int(os.environ.get('KB_RETRIEVAL_TOP_K', '8'))
KB_RETRIEVAL_MAX_CHUNKS = int(os.environ.get('KB_RETRIEVAL_MAX_CHUNKS', '5'))
KB_MIN_SCORE = float(os.environ.get('KB_MIN_SCORE', '0.35'))
KB_MIN_GOOD_CHUNKS = int(os.environ.get('KB_MIN_GOOD_CHUNKS', '2'))
ENABLE_KB_QUERY_REWRITE = os.environ.get('ENABLE_KB_QUERY_REWRITE', 'true').lower() == 'true'
FRESHNESS_STALE_AFTER_YEARS = int(os.environ.get('FRESHNESS_STALE_AFTER_YEARS', '1'))

# ── Security: Input validation ──
MAX_FIELD_LENGTH = 200
MAX_QUERY_LENGTH = 500

def _sanitize_field(value, max_len=MAX_FIELD_LENGTH):
    """Sanitize a text field: strip, truncate, remove dangerous chars."""
    if not value:
        return ''
    value = str(value).strip()[:max_len]
    # Remove characters that could be used for injection
    value = re.sub(r'[<>{}\[\]|;`$\\]', '', value)
    return value

def _check_injection(text):
    """Check for prompt, SQL, and command injection patterns in user input."""
    if not text:
        return False
    lower = text.lower()
    INJECTION_PATTERNS = [
        # Prompt injection
        r'ignore\s+(all\s+)?previous\s+instructions',
        r'you\s+are\s+now\s+a',
        r'system\s*prompt',
        r'act\s+as\s+(a\s+)?',
        r'new\s+instructions?\s*:',
        r'forget\s+(your|all)\s+',
        r'override\s+',
        r'repeat\s+the\s+above',
        r'what\s+(is|are)\s+your\s+(instructions|rules|prompt)',
        # SQL injection
        r'\bunion\s+select\b',
        r'\bdrop\s+table\b',
        r'\bdelete\s+from\b',
        r'\binsert\s+into\b',
        r'\bupdate\s+\w+\s+set\b',
        r'\bselect\s+.+\s+from\b',
        r"'\s*or\s*'?[0-9a-z_]+'?\s*=\s*'?[0-9a-z_]+'?",
        r'--\s*$',
        # Command injection
        r'&&',
        r'\|\|',
        r'\b(?:cmd\.exe|powershell|bash|sh)\b\s*(?:-c|/c|-enc)?',
        r'\b(?:rm\s+-rf|wget\s+http|curl\s+http|nc\s+-e|chmod\s+\+x)\b',
    ]
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            logger.warning(f"Injection pattern detected: {pattern}")
            return True
    return False


def _kb_retrieve_with_retry(bedrock_kb_client, **kwargs):
    """Call Bedrock KB retrieve with optional throttling retry."""
    retry_enabled = os.environ.get('ENABLE_KB_RETRY', 'false').lower() == 'true'
    if not retry_enabled:
        return bedrock_kb_client.retrieve(**kwargs)

    max_attempts = int(os.environ.get('KB_RETRY_MAX_ATTEMPTS', '3'))
    base_delay = float(os.environ.get('KB_RETRY_BASE_DELAY', '1.0'))

    last_error = None
    for attempt in range(max_attempts):
        try:
            response = bedrock_kb_client.retrieve(**kwargs)
            if attempt > 0:
                logger.info(f"KB retrieve succeeded on attempt {attempt + 1}/{max_attempts}")
            return response
        except Exception as exc:
            err_name = exc.__class__.__name__
            msg = str(exc)
            is_throttled = 'ThrottlingException' in err_name or 'ThrottlingException' in msg
            if is_throttled and attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"KB throttled (attempt {attempt + 1}/{max_attempts}), retrying in {delay:.1f}s"
                )
                time.sleep(delay)
                last_error = exc
                continue
            last_error = exc
            raise

    if last_error:
        raise last_error
    raise RuntimeError("_kb_retrieve_with_retry: unreachable")


def _sanitize_retrieval_item(item: Dict[str, Any]) -> Dict[str, Any]:
    content = str((item.get('content') or {}).get('text') or '')
    content = re.sub(r'<[^>]+>', '', content)
    score = float(item.get('score', 0) or 0)
    source = ((item.get('location') or {}).get('s3Location') or {}).get('uri', '')
    return {
        'content': content[:2000],
        'score': score,
        'source': source,
    }


def _apply_retrieval_quality_gate(
    retrieval_results: List[Dict[str, Any]],
    min_score: float,
    max_chunks: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sanitized = [_sanitize_retrieval_item(item) for item in (retrieval_results or [])]
    sorted_items = sorted(sanitized, key=lambda x: x.get('score', 0), reverse=True)
    good = [item for item in sorted_items if item.get('score', 0) >= min_score]
    selected = good[:max_chunks]
    metrics = {
        'raw_count': len(retrieval_results or []),
        'sanitized_count': len(sanitized),
        'good_count': len(good),
        'selected_count': len(selected),
        'min_score': min_score,
        'max_score': (sorted_items[0].get('score', 0) if sorted_items else 0),
    }
    return selected, metrics


def _rewrite_search_query_for_recall(search_query: str, query_type: str, crop: str) -> str:
    base = (search_query or '').strip()
    if not base:
        base = 'crop advisory india farming'
    qtype = (query_type or '').strip().lower()
    crop_hint = f"{crop} " if crop else ''
    if qtype == 'irrigation':
        return f"{crop_hint}irrigation schedule water requirement india best practices"
    if qtype == 'pest':
        return f"{crop_hint}pest disease symptoms diagnosis treatment india"
    return f"{crop_hint}crop advisory soil season recommendation india best practices"


def _extract_year_tokens(text: str) -> List[int]:
    years: List[int] = []
    if not text:
        return years

    # Matches: 2025, 2025-26, 2025-2026
    for match in re.finditer(r'\b(20\d{2})(?:\s*[-/]\s*(\d{2}|20\d{2}))?\b', text):
        start = int(match.group(1))
        years.append(start)
        end_raw = match.group(2)
        if end_raw:
            if len(end_raw) == 2:
                end = int(str(start)[:2] + end_raw)
            else:
                end = int(end_raw)
            years.append(end)

    return sorted(set(years))


def _is_time_sensitive_query(search_query: str, query_type: str) -> bool:
    text = f"{search_query or ''} {query_type or ''}".lower()
    return bool(re.search(r'\b(msp|price|market|mandi|scheme|subsidy|deadline|last date|current|latest|season|today|this year)\b', text))


def _build_freshness_metadata(search_query: str, query_type: str, advisory_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_year = datetime.now(UTC).year
    corpus = '\n'.join(str(item.get('content') or '') for item in (advisory_data or []))
    years = _extract_year_tokens(corpus)
    latest_year = max(years) if years else None
    time_sensitive = _is_time_sensitive_query(search_query, query_type)

    stale = False
    warning = ''
    if time_sensitive and latest_year is not None:
        stale = (current_year - latest_year) >= FRESHNESS_STALE_AFTER_YEARS
        if stale:
            warning = (
                "Some retrieved references appear older than the current season/year. "
                "Please verify latest MSP/scheme deadlines with official portals before final action."
            )
    elif time_sensitive and latest_year is None:
        warning = (
            "Time-sensitive guidance requested, but retrieved chunks did not include clear year markers. "
            "Please verify latest official rates and deadlines."
        )

    return {
        'current_year': current_year,
        'time_sensitive_query': time_sensitive,
        'detected_years': years,
        'latest_detected_year': latest_year,
        'stale_reference_detected': stale,
        'staleness_warning': warning,
    }


def _is_scheme_intent_query(text: str) -> bool:
    normalized = str(text or '').lower()
    # Keep MSP/market queries in crop tool path; redirect only true scheme intents.
    if re.search(r'\b(msp|market price|mandi|procurement price)\b', normalized):
        return False
    return bool(
        re.search(
            r'\b(scheme|subsidy|loan|insurance|eligibility|pm[- ]?kisan|pmfby|kcc|rythu|kalia|aif|pmksy|soil health card)\b',
            normalized,
        )
    )


def lambda_handler(event, context):
    """
    Retrieves crop advisory from Bedrock Knowledge Base.
    Called by orchestrator Lambda via direct invocation.
    Handles operations: get_crop_advisory, get_pest_alert, get_irrigation_advice.
    """
    try:
        # Support both Bedrock agent format (parameters[]) and
        # orchestrator invocation format (queryStringParameters{})
        if 'parameters' in event and isinstance(event['parameters'], list):
            params = {p['name']: p['value'] for p in event['parameters']}
        elif event.get('queryStringParameters'):
            params = event['queryStringParameters']
        elif event.get('body'):
            params = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            params = {}

        query = _sanitize_field(params.get('query', ''), MAX_QUERY_LENGTH)
        crop = _sanitize_field(params.get('crop', ''))
        state = _sanitize_field(params.get('state', ''))
        season = _sanitize_field(params.get('season', ''))
        soil_type = _sanitize_field(params.get('soil_type', ''))
        symptoms = _sanitize_field(params.get('symptoms', ''))
        location = _sanitize_field(params.get('location', ''))
        query_type = _sanitize_field(params.get('query_type', ''))

        # Security: check for prompt injection
        combined_input = f"{query} {crop} {state} {symptoms} {location}"
        if _check_injection(combined_input):
            return error_response("I can only help with agriculture-related queries. Please rephrase your question.", 400)

        # Source authority guard: scheme details should come from govt_schemes/search_schemes.
        scheme_text = " ".join([query, crop, state, location, query_type])
        if _is_scheme_intent_query(scheme_text):
            return success_response(
                {
                    'query': query,
                    'advisory_data': [],
                    'source_authority': 'govt_schemes',
                    'redirect_tool': 'search_schemes',
                    'message': (
                        'Government scheme details are served from the dedicated schemes service to keep data consistent. '
                        'Use search_schemes for eligibility, benefits, deadlines, and application steps.'
                    ),
                }
            )

        # Build a natural language search query for better KB vector retrieval
        # Natural language queries work much better than pipe-separated keywords
        if query_type == 'irrigation' or 'irrigation' in (query or '').lower() or 'water' in (query or '').lower():
            # Irrigation-specific query
            nl_parts = []
            if crop:
                nl_parts.append(f"{crop} irrigation water requirement schedule")
            if location or state:
                nl_parts.append(f"in {location or state}")
            if soil_type:
                nl_parts.append(f"for {soil_type} soil")
            if season:
                nl_parts.append(f"during {season} season")
            nl_parts.append("drip sprinkler flood irrigation method water need per day")
            if query:
                nl_parts.append(query)
            search_query = " ".join(nl_parts)
        elif symptoms or 'pest' in (query_type or '').lower():
            # Pest/disease query
            nl_parts = []
            if crop:
                nl_parts.append(f"{crop}")
            if symptoms:
                nl_parts.append(f"showing {symptoms}")
            if state or location:
                nl_parts.append(f"in {state or location}")
            if season:
                nl_parts.append(f"during {season}")
            nl_parts.append("pest disease treatment pesticide spray prevention")
            if query:
                nl_parts.append(query)
            search_query = " ".join(nl_parts)
        else:
            # General crop advisory — use natural language format
            nl_parts = []
            if query:
                nl_parts.append(query)
            if crop:
                nl_parts.append(f"{crop} crop advisory varieties fertilizer yield")
            if state or location:
                nl_parts.append(f"in {state or location}")
            if season:
                nl_parts.append(f"during {season} season")
            if soil_type:
                nl_parts.append(f"for {soil_type} soil")
            search_query = " ".join(nl_parts) if nl_parts else "crop advisory recommendations India farming"

        if not KB_ID:
            msg = 'Bedrock Knowledge Base ID not configured'
            return error_response(msg, 500)

        # Query Knowledge Base with natural language query
        response = _kb_retrieve_with_retry(
            bedrock_kb,
            knowledgeBaseId=KB_ID,
            retrievalQuery={'text': search_query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': KB_RETRIEVAL_TOP_K
                }
            }
        )

        raw_results = response.get('retrievalResults', [])
        results, quality = _apply_retrieval_quality_gate(
            raw_results,
            min_score=KB_MIN_SCORE,
            max_chunks=KB_RETRIEVAL_MAX_CHUNKS,
        )

        used_fallback_query = False
        fallback_query = ''

        # If quality is weak, retry with a broader recall-oriented query.
        if ENABLE_KB_QUERY_REWRITE and quality['good_count'] < KB_MIN_GOOD_CHUNKS:
            used_fallback_query = True
            fallback_query = _rewrite_search_query_for_recall(search_query, query_type, crop)
            logger.info(
                "KB quality gate retry: good_count=%s < min_good=%s; fallback query=%s",
                quality['good_count'],
                KB_MIN_GOOD_CHUNKS,
                fallback_query,
            )
            fallback_response = _kb_retrieve_with_retry(
                bedrock_kb,
                knowledgeBaseId=KB_ID,
                retrievalQuery={'text': fallback_query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': KB_RETRIEVAL_TOP_K
                    }
                }
            )
            fallback_results, fallback_quality = _apply_retrieval_quality_gate(
                fallback_response.get('retrievalResults', []),
                min_score=KB_MIN_SCORE,
                max_chunks=KB_RETRIEVAL_MAX_CHUNKS,
            )
            # Keep the better set by good_count then max_score.
            if (
                fallback_quality['good_count'] > quality['good_count']
                or (
                    fallback_quality['good_count'] == quality['good_count']
                    and fallback_quality['max_score'] > quality['max_score']
                )
            ):
                results = fallback_results
                quality = fallback_quality

        result_data = {
            'query': search_query,
            'crop': crop,
            'state': state,
            'season': season,
            'advisory_data': results,
            'retrieval_quality': {
                'used_fallback_query': used_fallback_query,
                'fallback_query': fallback_query,
                **quality,
            },
        }

        result_data['freshness'] = _build_freshness_metadata(search_query, query_type, results)

        if quality['good_count'] < KB_MIN_GOOD_CHUNKS:
            # Deterministic signal to orchestrator/model to avoid over-confident responses.
            result_data['insufficient_evidence'] = True
            result_data['evidence_message'] = (
                "Retrieved knowledge confidence is low for this query. "
                "Provide only cautious high-level guidance and ask for missing specifics "
                "(crop, location, soil type, season, or symptom details) before giving precise recommendations."
            )

        return success_response(result_data)

    except Exception as e:
        logger.error(f"Crop advisory error: {str(e)}", exc_info=True)
        # Security: never expose internal error details
        return error_response("Crop advisory service is temporarily unavailable. Please try again.", 500)
