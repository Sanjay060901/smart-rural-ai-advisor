# backend/lambdas/agent_orchestrator/handler.py
# Main Lambda: API Gateway → Amazon Bedrock (direct converse API) → Format Response
# Owner: Manoj RS
# Endpoints: POST /chat, POST /voice
# See: Detailed_Implementation_Guide.md Section 9

import json
import uuid
import boto3
import logging
import os
import re
import unicodedata
import time as _time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# API Gateway hard timeout is 29s. We must return before that.
API_GW_TIMEOUT_SEC = 29
TTS_TIME_BUDGET_SEC = 18  # skip Polly TTS if elapsed > this
ASYNC_GTTS_TIME_BUDGET_SEC = float(os.environ.get('ASYNC_GTTS_TIME_BUDGET_SEC', '24'))

# Feature-page session prefixes: pre-structured prompts that
# use a single direct Bedrock call (fast path).
FAST_PATH_PREFIXES = ('crop-recommend-', 'soil-analysis-', 'farm-calendar-', 'price-advisory', 'pest-advisory', 'schemes-')

from utils.response_helper import success_response, error_response
from utils.translate_helper import detect_and_translate, translate_response, normalize_language_code, needs_localization_retry
from utils.polly_helper import text_to_speech, refresh_audio_url
from utils.dynamodb_helper import save_chat_message, save_chat_messages_batch, get_farmer_profile, get_chat_history, get_session_message_count

# Enterprise Guardrails (Gaps #1-#4, #6-#7)
from utils.guardrails import run_all_guardrails, mask_pii_in_log, run_output_guardrails
from utils.rate_limiter import check_rate_limit
from utils.chat_history import list_sessions, get_session_messages, save_session, delete_session as delete_chat_session, rename_session as rename_chat_session
from utils.response_cache import get_cached_response, cache_response
from utils.cors_helper import handle_cors_preflight, get_cors_headers
from utils.audit_logger import (
    audit_request_start, audit_guardrail_block, audit_pii_detected,
    audit_tool_invocation, audit_policy_decision, audit_request_complete,
    audit_bedrock_guardrail,
)

ENFORCE_CODE_POLICY = os.environ.get('ENFORCE_CODE_POLICY', 'true').lower() == 'true'

# ── Bedrock Guardrail (Gap #5: AWS-native content/PII/topic filtering) ──
BEDROCK_GUARDRAIL_ID = os.environ.get('BEDROCK_GUARDRAIL_ID', '')
BEDROCK_GUARDRAIL_VERSION = os.environ.get('BEDROCK_GUARDRAIL_VERSION', '')

def _guardrail_config():
    """Return guardrailConfig dict for Bedrock converse() if guardrail is set up."""
    if BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION:
        return {
            'guardrailIdentifier': BEDROCK_GUARDRAIL_ID,
            'guardrailVersion': BEDROCK_GUARDRAIL_VERSION,
        }
    return None

FOUNDATION_MODEL = os.environ.get('FOUNDATION_MODEL', 'apac.amazon.nova-pro-v1:0')
FOUNDATION_MODEL_LITE = os.environ.get('FOUNDATION_MODEL_LITE', 'global.amazon.nova-2-lite-v1:0')
HYBRID_LOCALIZATION_ENABLED = os.environ.get('HYBRID_LOCALIZATION_ENABLED', 'false').lower() == 'true'
STRIP_LOCAL_MARKDOWN_SYMBOLS = os.environ.get('STRIP_LOCAL_MARKDOWN_SYMBOLS', 'true').lower() == 'true'
LAMBDA_WEATHER = os.environ.get('LAMBDA_WEATHER', '')
LAMBDA_CROP = os.environ.get('LAMBDA_CROP', '')
LAMBDA_SCHEMES = os.environ.get('LAMBDA_SCHEMES', '')
LAMBDA_PROFILE = os.environ.get('LAMBDA_PROFILE', '')

REQUIRED_ENV_VARS = (
    'LAMBDA_WEATHER',
    'LAMBDA_CROP',
    'LAMBDA_SCHEMES',
    'LAMBDA_PROFILE',
)


def _validate_required_env_vars():
    """Validate required runtime environment variables at startup."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        logger.error(
            "Startup env validation failed. Missing required env vars: %s. "
            "Set these Lambda environment variables before production traffic.",
            ', '.join(missing),
        )
    return missing


STARTUP_ENV_MISSING = _validate_required_env_vars()

# Feature flag: Timeout protection (default: OFF)
ENABLE_TIMEOUT_PROTECTION = os.environ.get('ENABLE_TIMEOUT_PROTECTION', 'false').lower() == 'true'
TIMEOUT_BUFFER_MS = int(os.environ.get('TIMEOUT_BUFFER_MS', '5000'))  # 5 seconds before API Gateway timeout

# Feature flag: Tool execution timeout (default: OFF) — Bug 1.2
ENABLE_TOOL_TIMEOUT = os.environ.get('ENABLE_TOOL_TIMEOUT', 'false').lower() == 'true'
TOOL_EXECUTION_TIMEOUT_SEC = int(os.environ.get('TOOL_EXECUTION_TIMEOUT_SEC', '25'))

# Feature flag: Thread-safe parallel tool execution (default: OFF) — Bug 1.5
ENABLE_THREAD_SAFE_TOOLS = os.environ.get('ENABLE_THREAD_SAFE_TOOLS', 'false').lower() == 'true'

# Feature flag: Model fallback control (default: OFF) — Bug 1.4
ENABLE_MODEL_FALLBACK = os.environ.get('ENABLE_MODEL_FALLBACK', 'false').lower() == 'true'

# Feature flags: medium/low reliability improvements (default: OFF)
ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
ENABLE_BACKOFF_JITTER = os.environ.get('ENABLE_BACKOFF_JITTER', 'false').lower() == 'true'
ENABLE_MODEL_VALIDATION = os.environ.get('ENABLE_MODEL_VALIDATION', 'false').lower() == 'true'
ENABLE_TOOL_INVOCATION_TIMEOUT = os.environ.get('ENABLE_TOOL_INVOCATION_TIMEOUT', 'false').lower() == 'true'
ENABLE_TOOL_METRICS = os.environ.get('ENABLE_TOOL_METRICS', 'false').lower() == 'true'
ENABLE_UNIFIED_CORS = os.environ.get('ENABLE_UNIFIED_CORS', 'false').lower() == 'true'


def _pool_config():
    if not ENABLE_CONNECTION_POOLING:
        return None
    return Config(max_pool_connections=25)


_POOL_CONFIG = _pool_config()


def _check_timeout_approaching(context):
    """
    Check if Lambda is approaching API Gateway timeout.
    Returns: (is_approaching: bool, remaining_ms: int)
    """
    # Read flag dynamically to support testing
    enable_protection = os.environ.get('ENABLE_TIMEOUT_PROTECTION', 'false').lower() == 'true'
    if not enable_protection:
        return False, None
    
    buffer_ms = int(os.environ.get('TIMEOUT_BUFFER_MS', '5000'))
    remaining_ms = context.get_remaining_time_in_millis()
    is_approaching = remaining_ms < buffer_ms
    return is_approaching, remaining_ms


def _timeout_fallback_response(language='en'):
    """
    Generate graceful timeout fallback response.
    Returns: dict with reply and timeout_fallback flag
    """
    messages = {
        'en': 'Your request is taking longer than expected to process. Please try again with a simpler question.',
        'hi': 'आपका अनुरोध संसाधित होने में अपेक्षा से अधिक समय ले रहा है। कृपया एक सरल प्रश्न के साथ पुनः प्रयास करें।',
    }
    
    message = messages.get(language, messages['en'])
    
    return {
        'reply': message,
        'audio_url': None,
        'timeout_fallback': True
    }


def _timeout_http_response(session_id, language='en'):
    """HTTP response payload for graceful timeout fallback."""
    fallback = _timeout_fallback_response(language)
    return {
        'statusCode': 200,
        'headers': get_cors_headers(methods='GET,POST,OPTIONS'),
        'body': json.dumps({
            'reply': fallback['reply'],
            'reply_en': fallback['reply'],
            'detected_language': language,
            'tools_used': [],
            'audio_url': fallback['audio_url'],
            'audio_key': None,
            'session_id': session_id,
            'mode': 'bedrock-direct',
            'timeout_fallback': fallback['timeout_fallback'],
        })
    }


# Bedrock Runtime client for direct model invocation (converse API with tool use)
_REGION = os.environ.get('AWS_REGION', 'ap-south-1')
bedrock_rt = boto3.client('bedrock-runtime', region_name=_REGION, config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('bedrock-runtime', region_name=_REGION)
lambda_client = boto3.client('lambda', region_name=_REGION, config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('lambda', region_name=_REGION)
if ENABLE_TOOL_INVOCATION_TIMEOUT:
    _lambda_timeout_config = Config(read_timeout=30, connect_timeout=5, max_pool_connections=25 if ENABLE_CONNECTION_POOLING else 10)
    lambda_invoke_client = boto3.client('lambda', region_name=_REGION, config=_lambda_timeout_config)
else:
    lambda_invoke_client = lambda_client
cloudwatch_client = boto3.client('cloudwatch', region_name=_REGION, config=_POOL_CONFIG) if (ENABLE_TOOL_METRICS and _POOL_CONFIG) else (boto3.client('cloudwatch', region_name=_REGION) if ENABLE_TOOL_METRICS else None)
logger.info(f"Mode: Direct Bedrock converse() | Model: {FOUNDATION_MODEL}")


AGRI_POLICY_KEYWORDS = {
    # General farming
    'crop', 'farming', 'farm', 'farmer', 'agriculture', 'agri', 'cultivat', 'horticulture',
    'organic', 'permaculture', 'agroforestry', 'intercrop', 'rotation', 'mulch', 'compost',
    'nursery', 'greenhouse', 'polyhouse', 'terrace', 'dryland', 'rainfed', 'plantation',
    # Weather
    'weather', 'rain', 'rainfall', 'monsoon', 'temperature', 'humidity', 'forecast',
    'drought', 'flood', 'frost', 'heatwave', 'fog', 'wind', 'climate', 'season',
    # Soil & land
    'soil', 'clay', 'loam', 'sandy', 'black soil', 'red soil', 'alluvial', 'laterite',
    'ph', 'salinity', 'alkaline', 'acidic', 'nutrient', 'micronutrient', 'zinc',
    'land', 'acre', 'hectare', 'field', 'plot',
    # Planting
    'seed', 'sowing', 'planting', 'transplant', 'spacing', 'variety', 'hybrid',
    'germination', 'seedling', 'nursery', 'grafting', 'propagation',
    # Growing
    'irrigation', 'water', 'watering', 'drip', 'sprinkler', 'furrow', 'canal', 'borewell',
    'well', 'tube well', 'pump', 'tds',
    'fertilizer', 'manure', 'urea', 'dap', 'npk', 'potash', 'nitrogen', 'phosphorus',
    'growth', 'flowering', 'fruiting', 'tillering', 'weeding', 'thinning', 'pruning',
    # Harvest & post-harvest
    'harvest', 'yield', 'production', 'threshing', 'drying', 'milling',
    'store', 'storage', 'warehouse', 'godown', 'cold storage', 'shelf life',
    'aflatoxin', 'moisture', 'spoilage', 'rotting', 'preservation',
    # Pests & diseases
    'pest', 'disease', 'fungus', 'insect', 'spray', 'blight', 'wilt', 'rot',
    'infestation', 'nematode', 'mite', 'borer', 'aphid', 'caterpillar', 'termite',
    'virus', 'bacteria', 'rust', 'smut', 'mosaic', 'leaf curl', 'mildew',
    'yellow', 'brown', 'spotting', 'curling', 'wilting', 'dying',
    'pesticide', 'fungicide', 'herbicide', 'insecticide', 'neem', 'bio-control',
    'treatment', 'remedy', 'medicine', 'cure', 'prevention', 'ipm',
    # Schemes & market
    'scheme', 'subsidy', 'loan', 'insurance', 'pm-kisan', 'kisan', 'yojana', 'pmfby',
    'kcc', 'credit card', 'msp', 'market', 'mandi', 'price', 'apmc', 'e-nam',
    'procurement', 'trade', 'export', 'profit', 'income', 'cost', 'budget',
    'government', 'benefit', 'grant', 'pension', 'ration',
    # Crop names (all 35 from crop_data.csv)
    'rice', 'paddy', 'wheat', 'cotton', 'sugarcane', 'maize', 'corn',
    'groundnut', 'peanut', 'soybean', 'soya', 'banana', 'coconut',
    'tomato', 'onion', 'potato', 'millet', 'ragi', 'bajra', 'jowar', 'sorghum',
    'chilli', 'pepper', 'mango', 'brinjal', 'eggplant', 'turmeric', 'ginger',
    'black gram', 'urad', 'mustard', 'sunflower', 'sesame', 'til',
    'jute', 'lentil', 'masoor', 'barley', 'okra', 'bhindi', 'lady finger',
    'pomegranate', 'guava', 'papaya', 'castor', 'safflower', 'chickpea', 'chana',
    'green gram', 'moong', 'toor', 'arhar', 'pigeon pea', 'pulses',
    'vegetable', 'fruit', 'spice', 'oilseed', 'fibre', 'cereal',
    'tea', 'coffee', 'rubber', 'cardamom', 'pepper', 'cinnamon', 'clove',
    'grape', 'apple', 'orange', 'citrus', 'watermelon', 'cucumber', 'carrot',
    'cabbage', 'cauliflower', 'pea', 'bean', 'drumstick', 'moringa',
    'mushroom', 'flower', 'jasmine', 'marigold', 'rose',
    # Seasons
    'kharif', 'rabi', 'zaid', 'summer', 'winter',
    # Livestock
    'cattle', 'dairy', 'goat', 'poultry', 'chicken', 'sheep', 'pig', 'fish',
    'aquaculture', 'pisciculture', 'sericulture', 'silkworm', 'beekeeping', 'honey',
    'fodder', 'feed', 'milk', 'egg', 'meat', 'wool',
    # Equipment & techniques
    'tractor', 'plough', 'sprayer', 'harvester', 'sickle', 'thresher',
    'drone', 'sensor', 'precision', 'biogas', 'vermicompost', 'composting',
    'solar', 'renewable', 'processing', 'value addition', 'food processing',
    # Location / general agriculture
    'village', 'district', 'block', 'taluk', 'panchayat', 'mandal',
    'extension', 'krishi', 'vigyan', 'kendra', 'kvk',
    'agriculture office', 'agriculture department',
    'fpo', 'cooperative', 'self-help group', 'shg',
    # Misc farming
    'pollination', 'pollen', 'honey bee', 'beneficial insect',
    'cover crop', 'green manure', 'legume', 'nitrogen fixing',
    'contract farming', 'lease', 'tenant', 'sharecropper',
    'succession', 'land record', 'patta', 'survey',
    # Additional farming terms (aquaponics, hydroponics, nursery, etc.)
    'aquaponics', 'hydroponics', 'nursery', 'greenhouse', 'polyhouse',
    'mulch', 'mulching', 'grafting', 'pruning', 'thinning', 'canopy',
    'intercrop', 'intercropping', 'agroforestry', 'silviculture',
    'fertigation', 'foliar spray', 'micronutrient', 'deficiency',
    'organic farming', 'zbnf', 'jeevamrutha', 'panchagavya',
    'azolla', 'biofertilizer', 'trichoderma', 'pseudomonas',
    'neem cake', 'neem oil', 'bio-agent', 'bio-pesticide',
    'garden', 'kitchen garden', 'backyard', 'terrace garden',
    'staking', 'trellising', 'raised bed', 'seed priming',
    'crop budget', 'crop rotation', 'crop residue',
    'watershed', 'rainwater', 'farm pond', 'bund',
    'silage', 'hay', 'straw', 'husk',
    'drying yard', 'grading', 'packaging', 'cold chain',
    'tissue culture', 'air layering', 'budding', 'marcotting',
    'fym', 'compost', 'nadep', 'pit', 'heap',
}

# ── Off-topic blocklist: catch clearly non-agriculture queries ──
# These override the lenient 3+ word pass rule.
OFF_TOPIC_KEYWORDS = {
    # Entertainment
    'movie', 'movies', 'film', 'films', 'cinema', 'bollywood', 'hollywood',
    'netflix', 'web series', 'tv show', 'song', 'songs', 'music', 'album',
    'actor', 'actress', 'celebrity', 'concert', 'trailer',
    # Politics
    'prime minister', 'president', 'election', 'politician', 'parliament',
    'rajya sabha', 'lok sabha', 'political party', 'bjp', 'congress', 'minister',
    'chief minister', 'mla', 'mp ',  # trailing space to avoid matching 'msp'
    # Sports
    'cricket', 'football', 'soccer', 'tennis', 'ipl', 'world cup', 'match score',
    'hockey', 'olympics', 'batting', 'bowling', 'goal', 'fifa',
    # Technology (non-farm)
    'iphone', 'android', 'laptop', 'computer', 'software', 'hack', 'hacking',
    'programming', 'coding', 'gaming', 'video game', 'playstation', 'xbox',
    # General knowledge / trivia
    'capital of', 'population of', 'tallest', 'longest', 'biggest',
    'who invented', 'who discovered', 'who founded', 'who wrote',
    # Travel / lifestyle
    'flight', 'hotel', 'tourism', 'restaurant', 'recipe', 'cooking',
    'fashion', 'makeup', 'hairstyle',
    # Education (non-farm)
    'exam result', 'jee', 'neet', 'upsc', 'ssc', 'board exam',
    # Misc clearly off-topic
    'stock market', 'share price', 'cryptocurrency', 'bitcoin', 'forex',
    'lottery', 'gambling', 'bet ', 'betting',
}

SAFE_CHITCHAT = {'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay',
                 'good morning', 'good evening', 'good afternoon', 'good night',
                 'bye', 'goodbye', 'namaste', 'vanakkam', 'namaskar'}


def _is_greeting_or_chitchat(text):
    """Return True if the message is a simple greeting/chitchat with no farming intent."""
    normalized = (text or '').lower().strip().rstrip('!?.,')
    if not normalized:
        return False
    return normalized in SAFE_CHITCHAT


def _greeting_response(farmer_context=None):
    """Generate a short, friendly greeting. Skips the Bedrock converse() call."""
    name = ''
    if farmer_context and farmer_context.get('name'):
        name = f" {farmer_context['name'].split()[0]}"  # first name only
    return (
        f"Hello{name}! 👋 Welcome to Smart Rural AI Advisor.\n\n"
        f"I can help you with:\n"
        f"• **Crop advice** — what to plant, fertilizers, irrigation\n"
        f"• **Weather updates** — rain, temperature, forecasts\n"
        f"• **Pest & disease help** — symptoms, treatment, prevention\n"
        f"• **Government schemes** — PM-KISAN, subsidies, insurance\n"
        f"• **Market prices** — MSP, mandi rates\n\n"
        f"Just type your question or use the feature pages above!"
    )


def _sanitize_user_message(text):
    cleaned = (text or '').strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', cleaned)
    cleaned = re.sub(r'([,.;:!?()\-])\1{2,}', r'\1', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def _normalize_translated_agri_terms(text):
    """Fix common translation artifacts for key agriculture season terms."""
    normalized = str(text or '')
    if not normalized:
        return normalized

    replacements = [
        (r'\bcardiff\b', 'kharif'),
        (r'\bharif\b', 'kharif'),
        (r'\bkhariff\b', 'kharif'),
        (r'\brabby\b', 'rabi'),
        (r'\brabbi\b', 'rabi'),
        (r'\bzaad\b', 'zaid'),
        (r'\bzaidh\b', 'zaid'),
    ]
    for pattern, repl in replacements:
        normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)
    return normalized


def _resolve_reply_language(preferred_language, detected_language, raw_user_message, enforce_preferred=False):
    """Resolve reply language with a single source of truth.

    If the client provides/stores a preferred language, always honor it.
    This avoids per-turn drift where detected input language overrides user settings.
    """
    preferred = normalize_language_code(preferred_language, default='en') if preferred_language else None
    if preferred:
        return preferred
    return normalize_language_code(detected_language, default='en')


def _contains_indic_chars(text):
    if not text:
        return False
    return bool(re.search(r'[\u0900-\u0D7F]', text))


def _is_on_topic_query(text):
    normalized = (text or '').lower().strip()
    if not normalized:
        return True
    if normalized in SAFE_CHITCHAT:
        return True
    if _contains_indic_chars(normalized):
        return True

    # ── Priority 1: Multi-word off-topic phrases (most specific → check first) ──
    # Phrases like "stock market", "prime minister", "web series" are unambiguous
    # and must override single-word AGRI matches (e.g. "market" in AGRI).
    off_topic_phrases = [kw for kw in OFF_TOPIC_KEYWORDS if ' ' in kw]
    if any(phrase in normalized for phrase in off_topic_phrases):
        logger.info(f"Off-topic blocked (phrase): matched in '{normalized[:80]}'")
        return False

    # ── Priority 2: AGRI keyword match ──
    if any(keyword in normalized for keyword in AGRI_POLICY_KEYWORDS):
        return True

    # ── Priority 3: Single-word off-topic keywords (after AGRI to avoid false positives) ──
    off_topic_singles = [kw for kw in OFF_TOPIC_KEYWORDS if ' ' not in kw]
    if any(keyword in normalized for keyword in off_topic_singles):
        logger.info(f"Off-topic blocked (single): matched in '{normalized[:80]}'")
        return False

    # Lenient fallback: if the query has 3+ words, let it through —
    # the Bedrock model is better at deciding relevance than a keyword list.
    # Only block very short off-topic inputs (1-2 words) that don't match any keyword.
    word_count = len(normalized.split())
    if word_count >= 3:
        logger.info(f"On-topic lenient pass: {word_count} words, no keyword match")
        return True
    return False



# Generic query patterns: educational, definitional, or broad questions that
# do NOT benefit from personalizing with the farmer's profile/location/crops.
GENERIC_QUERY_PATTERNS = [
    r'^what\s+is\b', r'^what\s+are\b', r'^define\b', r'^explain\b',
    r'^how\s+does\b', r'^how\s+is\b', r'^how\s+do\b', r'^how\s+are\b',
    r'^who\s+is\b', r'^who\s+are\b', r'^when\s+is\b', r'^when\s+was\b',
    r'^where\s+is\b', r'^where\s+are\b', r'^why\s+is\b', r'^why\s+do\b',
    r'^tell\s+me\s+about\b', r'^meaning\s+of\b', r'^difference\s+between\b',
    r'^types\s+of\b', r'^list\b.*\btypes\b', r'^advantages\b', r'^benefits\s+of\b',
    r'^history\s+of\b', r'^overview\s+of\b',
    r'\bwhat\s+is\s+msp\b', r'\bwhat\s+is\s+pm.kisan\b',
    r'\bhow\s+to\s+apply\b', r'\bhow\s+to\s+register\b',
    r'\bgeneral\b.*\binformation\b', r'\bgeneral\b.*\bknowledge\b',
]

# Specific query indicators: phrases that signal the farmer wants advice
# personalized to THEIR situation, land, location, or crops.
SPECIFIC_QUERY_INDICATORS = [
    r'\bmy\s+(farm|crop|land|soil|field|area|village|district|state)\b',
    r'\bfor\s+my\b', r'\bin\s+my\s+area\b', r'\bmy\s+region\b',
    r'\bshould\s+i\b', r'\bcan\s+i\b', r'\bwhat\s+should\s+i\b',
    r'\brecommend\s+for\b', r'\bsuggest\s+for\b', r'\badvise\s+me\b',
    r'\bbest\s+crop\s+for\b', r'\bwhich\s+crop\b', r'\bwhich\s+variety\b',
    r'\bwhat\s+to\s+(grow|plant|sow)\b', r'\bcurrent\s+weather\b',
    r'\bweather\s+(in|at|for|today)\b', r'\bforecast\b',
]


def _is_generic_query(english_text):
    """Determine if the query is generic/educational (True) vs specific/personalized (False).
    Generic queries should NOT be personalized with farmer profile data."""
    text = (english_text or '').lower().strip()
    if not text:
        return False
    # If it matches specific indicators, it's NOT generic
    for pattern in SPECIFIC_QUERY_INDICATORS:
        if re.search(pattern, text):
            return False
    # If it matches generic patterns, it IS generic
    for pattern in GENERIC_QUERY_PATTERNS:
        if re.search(pattern, text):
            return True
    # Default: not generic (assume farmer wants personalized advice)
    return False


def _is_open_crop_recommendation_query(english_text):
    """True when user asks open-ended crop suitability (no specific crop requested)."""
    text = (english_text or '').lower().strip()
    if not text:
        return False

    patterns = [
        r'\bwhich\s+crops?\s+(are\s+)?suitable\b',
        r'\bwhat\s+crops?\s+(can|should)\s+i\s+grow\b',
        r'\bbest\s+crops?\s+for\s+(my|this)\s+(soil|location|area|region)\b',
        r'\bwhich\s+crops?\s+for\s+(my|this)\s+(soil|location|area|region)\b',
        r'\bsuitable\s+crops?\s+for\s+(my|this)\s+(soil|location|area|region)\b',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _is_profile_crop_specific_query(english_text):
    """True when user explicitly asks about their own crop(s) and expects profile personalization."""
    text = (english_text or '').lower().strip()
    if not text:
        return False

    patterns = [
        r'\bmy\s+crop\b',
        r'\bmy\s+crops\b',
        r'\bfor\s+my\s+crop\b',
        r'\bfor\s+my\s+crops\b',
        r'\bbest\s+season\s+to\s+grow\s+my\s+crops\b',
        r'\bseason\s+for\s+my\s+crops\b',
        r'\bwhen\s+should\s+i\s+grow\s+my\s+crops\b',
        r'\bmy\s+crop\s+season\b',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _off_topic_response():
    return (
        "I can help only with agriculture and rural livelihood topics, such as crops, pests, weather, "
        "irrigation, market prices, and government schemes. Please ask a farming-related question."
    )


def _requires_grounded_tools(intents):
    required = {'weather', 'crop', 'pest', 'schemes', 'profile'}
    return bool(set(intents or []) & required)


def _grounding_prompt_for_intents(intents):
    intent_set = set(intents or [])
    if 'weather' in intent_set:
        return "Please share your location (village/town/city) so I can fetch a weather update."
    if 'pest' in intent_set:
        return "Please share your crop, location, and visible symptoms so I can give a reliable pest advisory."
    if 'crop' in intent_set:
        return "Please share your location, season, and crop preference so I can give a reliable crop advisory."
    if 'schemes' in intent_set:
        return "Please share your state and farmer category so I can find relevant government schemes."
    if 'profile' in intent_set:
        return "Please share your farmer ID or profile details so I can give profile-based advice."
    return (
        "Please share your crop, location, season, and symptoms so I can provide a reliable advisory."
    )


def _strip_sources_line(text):
    """Remove any 'Sources: ...' line from the text (agent.py may have added it).
    Returns (cleaned_text, extracted_sources_str_or_None)."""
    if not text:
        return text, None
    match = re.search(r'\n\s*Sources:\s*(.+)$', text)
    if match:
        return text[:match.start()].rstrip(), match.group(1).strip()
    return text, None


def _build_sources_line(tools_used):
    """Build a sources attribution string from tool names (never translated)."""
    if not tools_used:
        return None
    tool_labels = {
        'get_weather': 'WeatherFunction(OpenWeather)',
        'get_crop_advisory': 'CropAdvisoryFunction(KB)',
        'get_pest_alert': 'CropAdvisoryFunction(Pest Tool)',
        'search_schemes': 'GovtSchemesFunction',
        'get_farmer_profile': 'FarmerProfileFunction',
    }
    unique_tools = list(dict.fromkeys(tools_used))
    source_list = [tool_labels.get(tool, tool) for tool in unique_tools]
    return ', '.join(source_list)


def _append_sources(reply_en, tools_used):
    """Append sources line to English text. Only used for reply_en field."""
    text = (reply_en or '').strip()
    if not text or not tools_used:
        return text

    # Strip any existing sources line first (avoid duplicates from agent.py)
    text, _ = _strip_sources_line(text)

    sources = _build_sources_line(tools_used)
    if sources:
        return f"{text}\n\nSources: {sources}"
    return text


def _apply_code_policy(user_query_en, intents, result_text, tools_used, original_query=None, farmer_context=None, is_generic=False):
    policy_meta = {
        'code_policy_enforced': ENFORCE_CODE_POLICY,
        'off_topic_blocked': False,
        'grounding_required': _requires_grounded_tools(intents) and not is_generic,
        'grounding_satisfied': bool(tools_used) or is_generic,
    }

    if not ENFORCE_CODE_POLICY:
        return result_text, tools_used, policy_meta

    if not (_is_on_topic_query(user_query_en) or _is_on_topic_query(original_query)):
        policy_meta['off_topic_blocked'] = True
        return _off_topic_response(), [], policy_meta

    cleaned_tools = list(dict.fromkeys(tools_used or []))
    text = (result_text or '').strip()

    if not text:
        text = "I need a bit more farm context to provide a reliable advisory."

    is_warmup_or_runtime_msg = any(token in text.lower() for token in [
        'warming up',
        'runtime initialization',
        'please try again in a minute',
        'runtimeclienterror',
        'timeout',
        'error processing',
        'error calling model',
        'apologize',
    ])

    # If it's a runtime error/warm-up message, pass it through instead of masking
    if is_warmup_or_runtime_msg:
        logger.info(f"Runtime message detected (passing through): {text[:200]}")
        return text, cleaned_tools, policy_meta

    # Check if farmer_context provides enough grounding data already
    # (profile has state/crops — no need to ask user again)
    _has_profile_context = (
        farmer_context
        and (farmer_context.get('state') or farmer_context.get('district'))
    )

    if policy_meta['grounding_required'] and not cleaned_tools:
        # If the AI already generated a substantive response (>100 chars when
        # profile context exists, >200 chars otherwise), allow it through —
        # the query + profile context already had enough data.
        substantive_threshold = 100 if _has_profile_context else 200
        if len(text) > substantive_threshold:
            logger.info(f"Grounding: no tools but response is substantive ({len(text)} chars, "
                        f"threshold={substantive_threshold}, has_profile={_has_profile_context}) — passing through")
            policy_meta['grounding_satisfied'] = True
        elif _has_profile_context and len(text) > 40:
            # Profile context gives us location/crops — even shorter responses
            # are likely grounded in the context prefix the model received
            logger.info(f"Grounding: farmer profile context available, response {len(text)} chars — passing through")
            policy_meta['grounding_satisfied'] = True
        else:
            policy_meta['grounding_satisfied'] = False
            text = _grounding_prompt_for_intents(intents)

    text = _append_sources(text, cleaned_tools)

    if len(text) > 7000:
        text = text[:7000].rsplit(' ', 1)[0] + '...'

    return text, cleaned_tools, policy_meta


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DIRECT BEDROCK CONVERSE API (primary invocation path)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIRECT_SYSTEM_PROMPT = """You are the Smart Rural AI Advisor — a warm, friendly agricultural assistant for Indian farmers.
You combine 5 cognitive roles: Understanding, Reasoning, Fact-Checking, Communication, and Memory.
Speak like a helpful neighbor, not a machine. Be conversational, encouraging, and practical.

CRITICAL RULES:
1. Use tools for EVERY weather, crop, pest, irrigation, or scheme query — NEVER guess data
2. Always ground answers in real tool outputs
3. Keep advice practical, region-specific, and season-aware
4. Be culturally sensitive to Indian farming practices — use relatable examples
5. If data is unavailable, say so honestly
6. For irrigation/water queries, always call get_crop_advisory with query_type='irrigation' — the Knowledge Base has detailed water tables, drip/sprinkler guides, and crop water needs
7. For pest/disease queries with symptoms (yellow leaves, spots, wilting), always call get_pest_alert — the KB has pesticide guides, dosages, and treatment protocols
8. When farmer context is provided, ALWAYS use it to fill missing parameters (name, state, crop, soil_type) for tool calls — DO NOT ask the farmer for information already in their profile context. NEVER ask for the farmer's name — it is already provided. Address them by name directly.
9. Provide specific numbers: kg/hectare, mm of water, litres/day, days to harvest, etc.
10. CRITICAL: If the farmer's query mentions crops/season/weather but doesn't specify location, and farmer context has state/district — use that location for the tool call. NEVER refuse to answer or ask for location if it's available in the farmer context. If gps_location is in the context, use it as the PRIMARY fallback location. If the farmer explicitly mentions a different location in the current query, ALWAYS use the farmer-mentioned location instead of gps_location/profile location.
11. ANSWER WHAT THE FARMER ASKED with intent-matched depth. Keep most operational replies concise and actionable (typically 120-250 words). Expand only when the user asks for detailed explanation or a full plan. Always include concrete numbers when available (kg/hectare, litres/day, Rs/quintal, mm water, days to harvest). Do NOT add unrelated topics. If the farmer asks 'what crop to grow', answer only crop recommendation unless they explicitly ask for pest/irrigation/fertilizer/schemes.
12. If conversation history is provided, use it for context in follow-up questions. If the farmer asks 'what about pest control?' after a crop recommendation, use the prior crop as context.
13. Write in a warm, human tone — use short sentences, everyday words, and a conversational style. Avoid bullet-point lists unless summarizing multiple items. Sound like a knowledgeable friend, not a textbook.
14. CRITICAL: You have knowledge about ALL major Indian crops — not just rice and wheat. The tool database covers 35+ crops including cotton, sugarcane, maize, groundnut, soybean, banana, coconut, tomato, onion, potato, millets (ragi/bajra/jowar), chilli, mango, brinjal, turmeric, black gram, mustard, sunflower, sesame, jute, lentil, barley, okra, pomegranate, guava, papaya, castor, safflower, chickpea, green gram, toor dal, and more. If the tool returns partial data (e.g., only 2 crops), provide helpful advice for the farmer's requested crop using tool evidence first and general agronomic knowledge second. NEVER say "I only have data for rice and wheat" or "the tool only returned data for X and Y".
15. STRICT SOIL RULE: For soil-type crop recommendation queries (e.g., black soil/red soil), ONLY recommend crops that are explicitly supported by retrieved tool evidence for that soil. Do NOT add extra crops from generic knowledge when soil fit is not evidenced. If evidence is insufficient, say so clearly and ask for soil test details/pH/drainage.
16. STRICT SCHEME SCOPE RULE: For government scheme answers, include only Central schemes plus the farmer's profile state schemes. Never list schemes from other states unless the farmer explicitly asks for cross-state comparison.
17. For topics outside the tool database (e.g., livestock, dairy, sericulture, food processing, biogas), provide practical general advice and recommend the farmer contact their local KVK (Krishi Vigyan Kendra) or agricultural extension service for specialized guidance.
18. RESPONSE FORMAT CONTRACT (STRICT): Return plain Markdown only (no HTML/JSON/code fences unless asked). For multi-item answers (e.g., schemes), use this exact structure:
    ### <Item Name>
    - **Eligibility:** ...
    - **Deadline:** ...
    - **Benefit:** ...
    - **How to apply:** ...
   Keep spacing compact: one blank line between sections, no extra blank lines between bullets. Never output raw placeholders like [object Object].
19. For pest/disease queries based only on text symptoms, NEVER present a single diagnosis as certain. Use cautious wording: "likely" / "possibly", include 2-3 differential possibilities, and list quick confirmation cues (what to check on leaf/stem/fruit).
20. Give exact pesticide/fungicide dose only when tool evidence strongly matches a specific disease/pest; otherwise provide safe immediate steps first (remove infected parts, moisture control, field hygiene) and ask for a photo or additional symptoms to confirm.
21. Do NOT use definitive labels/headings like "This is X disease" or a standalone disease name as the final diagnosis unless there is explicit confirmation evidence (clear photo/lab/field confirmation). For symptom-only cases, format as "Most likely possibilities" and "How to confirm first" before any treatment details.

CROP REFERENCE (key data for quick lookup — use alongside tool results):
Rice: Kharif, 120-150d, clay loam pH5.5-6.5, NPK 120:60:40, yield 3.5-5.0t/ha, MSP ₹2300/q
Wheat: Rabi, 110-140d, loam pH6.0-7.5, NPK 120-150:40-60:40-60, yield 3.0-6.5t/ha, MSP ₹2275/q
Cotton: Kharif, 140-180d, black soil pH6.0-8.0, drip/furrow, yield 1.5-3.0t/ha, MSP ₹7020/q
Sugarcane: Annual, 300-450d, clay loam pH6.0-8.0, flood/drip, yield 60-120t/ha, MSP ₹3150/q
Maize: Kharif+Rabi, 90-120d, loam pH5.5-7.5, yield 2.5-9.0t/ha, MSP ₹2090/q
Groundnut: Kharif, 100-130d, sandy loam pH6.0-7.0, yield 1.0-4.0t/ha, MSP ₹6377/q
Soybean: Kharif, 100-140d, loam pH6.0-7.5, yield 1.0-3.0t/ha, MSP ₹4600/q
Banana: Perennial, 270-420d, loam pH5.5-7.0, drip, yield 30-50t/ha
Coconut: Perennial, loam pH5.0-8.0, drip/basin, 50-100 nuts/palm/yr, MSP ₹10860/q
Tomato: Rabi+Kharif, 90-140d, sandy loam pH6.0-7.5, drip, yield 20-40t/ha
Onion: Rabi, 110-150d, loam pH6.0-7.5, drip, yield 10-30t/ha
Potato: Rabi, 90-130d, loam pH5.0-7.0, drip/furrow, yield 15-40t/ha
Ragi: Kharif, 70-110d, red soil pH5.5-7.5, rainfed, yield 1.0-4.0t/ha, MSP ₹3846/q
Toor: Kharif, 140-180d, loam pH6.0-7.5, rainfed, yield 0.6-2.5t/ha, MSP ₹7000/q
Chilli: Kharif+Rabi, 120-150d, loam pH6.0-7.0, drip, yield 3-12t/ha
Turmeric: Kharif, 210-270d, loam pH4.5-7.5, drip, yield 8-15t/ha
Mustard: Rabi, 90-120d, loam pH6.5-8.0, sprinkler, yield 1.0-3.0t/ha, MSP ₹5650/q

MSP LOOKUP RULE: For MSP (Minimum Support Price) and market price queries, FIRST refer to the CROP REFERENCE data above — it contains current MSP rates for all major crops. You do NOT need to call search_schemes for MSP data. Provide the MSP value directly from CROP REFERENCE along with any additional context from get_crop_advisory if needed.


MULTI-TOPIC QUERIES (CRITICAL): When the farmer asks about MULTIPLE topics in one message (e.g., pest + weather + MSP + schemes), you MUST:
1. Address ALL topics mentioned — do NOT ignore any part of the question
2. Keep EACH topic section focused but thorough (5-8 sentences) — cover ALL topics with adequate detail
3. Structure your response with clear ### headings for each topic (e.g., ### Pest Issue, ### Weather, ### MSP, ### Government Schemes)
4. For pest/disease in multi-topic: give the likely cause, one key treatment, and one organic option — NOT the full diagnosis
5. For weather in multi-topic: give current temp, condition, and 1-2 day forecast — NOT the full week
6. For schemes in multi-topic: list 2-3 most relevant schemes with ONE line each — NOT full eligibility details
7. For MSP in multi-topic: give the exact price/quintal value from CROP REFERENCE — one line
This ensures ALL parts of the farmer's question get answered within the response limit.

You have access to tools for weather lookup, crop advisory (including irrigation), pest alerts, government schemes, and farmer profiles.
Always call the relevant tool first, then synthesize the response from tool data."""

DIRECT_TOOLS = [
    {
        "toolSpec": {
            "name": "get_weather",
            "description": "Get current weather for a location in India. Returns temperature, humidity, rainfall, wind, and forecast.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City or village name in India (e.g., 'Coimbatore', 'Pune')"},
                        "days": {"type": "integer", "description": "Number of forecast days (1-7)", "default": 3}
                    },
                    "required": ["location"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "get_crop_advisory",
            "description": "Get crop recommendations, growing advice, varieties, fertilizer schedules, irrigation guidance, and MSP (Minimum Support Price) data from the Knowledge Base. Use query_type='irrigation' specifically for water requirements, irrigation scheduling, drip/sprinkler methods, and water management queries. Also use for MSP, market price, mandi rate queries.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Farmer's location (district/state)"},
                        "crop": {"type": "string", "description": "Crop name (e.g., 'Rice', 'Cotton')"},
                        "season": {"type": "string", "description": "Season: kharif, rabi, or summer"},
                        "soil_type": {"type": "string", "description": "Soil type (e.g., 'Clay', 'Loam', 'Red soil')"},
                        "query_type": {"type": "string", "description": "One of: recommendation, pest, irrigation, general. Use 'irrigation' for water/watering queries."}
                    },
                    "required": ["location"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "search_schemes",
            "description": "Search Indian government agricultural schemes, subsidies, loans, and insurance programs. Do NOT use this for MSP or market price queries — use get_crop_advisory or CROP REFERENCE instead.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for schemes"},
                        "state": {"type": "string", "description": "Indian state name"},
                        "category": {"type": "string", "description": "Category: subsidy, loan, insurance, general"}
                    },
                    "required": ["query"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "get_farmer_profile",
            "description": "Retrieve a farmer's profile including crops, soil type, location, and preferences.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "farmer_id": {"type": "string", "description": "The farmer's ID"}
                    },
                    "required": ["farmer_id"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "get_pest_alert",
            "description": "Get pesticide product guides, pest alerts, disease identification, and treatment recommendations from the Knowledge Base. Use this for: yellow leaves, brown spots, wilting, rotting, insect damage, fungal infections, and any crop health problems. Returns specific pesticide names, dosages, organic alternatives, and prevention methods.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Detailed pest/disease/pesticide query describing symptoms and crop"},
                        "crop": {"type": "string", "description": "Crop name (e.g., Rice, Wheat, Cotton)"},
                        "symptoms": {"type": "string", "description": "Visible symptoms: yellow leaves, brown spots, wilting, holes, etc."},
                        "location": {"type": "string", "description": "Farmer location (state/district)"},
                        "season": {"type": "string", "description": "Current season: kharif, rabi, summer"}
                    },
                    "required": ["query"]
                }
            }
        }
    }
]

# Map tool names to Lambda function names
TOOL_TO_LAMBDA = {
    "get_weather": LAMBDA_WEATHER,
    "get_crop_advisory": LAMBDA_CROP,
    "get_pest_alert": LAMBDA_CROP,
    "search_schemes": LAMBDA_SCHEMES,
    "get_farmer_profile": LAMBDA_PROFILE,
}


def _emit_tool_metric(tool_name, duration_ms, success):
    if not cloudwatch_client:
        return
    try:
        cloudwatch_client.put_metric_data(
            Namespace='SmartRuralAI/Tools',
            MetricData=[
                {
                    'MetricName': 'ToolExecutionDurationMs',
                    'Dimensions': [{'Name': 'ToolName', 'Value': str(tool_name)}],
                    'Value': float(duration_ms),
                    'Unit': 'Milliseconds',
                },
                {
                    'MetricName': 'ToolExecutionSuccess',
                    'Dimensions': [{'Name': 'ToolName', 'Value': str(tool_name)}],
                    'Value': 1.0 if success else 0.0,
                    'Unit': 'Count',
                },
            ],
        )
    except Exception as metric_err:
        logger.warning(f"Tool metric emission failed for {tool_name}: {metric_err}")


def _validated_model_id(model_id):
    if not model_id:
        return FOUNDATION_MODEL
    if not os.environ.get('ENABLE_MODEL_VALIDATION', 'false').lower() == 'true':
        return model_id
    allowed = {FOUNDATION_MODEL, FOUNDATION_MODEL_LITE}
    if model_id not in allowed:
        logger.info(f"Invalid model_id override '{model_id}' rejected; using FOUNDATION_MODEL")
        return FOUNDATION_MODEL
    return model_id


def _execute_tool(tool_name, tool_input):
    """Execute a tool by invoking the corresponding Lambda function."""
    lambda_name = TOOL_TO_LAMBDA.get(tool_name)
    if not lambda_name:
        return {"error": f"Unknown tool: {tool_name}"}

    start_time = _time.time()
    try:
        # Build Lambda payload based on tool
        if tool_name == "get_weather":
            # Weather Lambda reads from pathParameters.location (API Gateway: /weather/{location})
            lambda_payload = {"pathParameters": {"location": tool_input.get("location", "Chennai")}}
        elif tool_name == "get_crop_advisory":
            lambda_payload = {"queryStringParameters": tool_input}
        elif tool_name == "get_pest_alert":
            # Route pest queries to crop advisory Lambda with KB lookup
            lambda_payload = {"queryStringParameters": tool_input}
        elif tool_name == "search_schemes":
            lambda_payload = {"queryStringParameters": tool_input}
        elif tool_name == "get_farmer_profile":
            lambda_payload = {"pathParameters": {"farmerId": tool_input.get("farmer_id", "")}}
        else:
            lambda_payload = {"body": json.dumps(tool_input)}

        response = lambda_invoke_client.invoke(
            FunctionName=lambda_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(lambda_payload).encode(),
        )
        resp_payload = json.loads(response["Payload"].read().decode())

        # Parse Lambda response
        if isinstance(resp_payload, dict) and "body" in resp_payload:
            body = resp_payload["body"]
            if isinstance(body, str):
                try:
                    parsed = json.loads(body)
                    _emit_tool_metric(tool_name, (_time.time() - start_time) * 1000.0, True)
                    return parsed
                except json.JSONDecodeError:
                    _emit_tool_metric(tool_name, (_time.time() - start_time) * 1000.0, True)
                    return {"result": body}
            _emit_tool_metric(tool_name, (_time.time() - start_time) * 1000.0, True)
            return body
        _emit_tool_metric(tool_name, (_time.time() - start_time) * 1000.0, True)
        return resp_payload
    except Exception as e:
        _emit_tool_metric(tool_name, (_time.time() - start_time) * 1000.0, False)
        logger.error(f"Tool execution error ({tool_name}): {str(e)}")
        return {"error": "Tool invocation failed"}


def _is_soil_specific_recommendation_query(user_prompt, tool_input=None):
    """Return True when the request is soil-focused and asks for crop recommendations."""
    ti = tool_input or {}
    text = " ".join([
        str(user_prompt or ''),
        str(ti.get('query') or ''),
        str(ti.get('soil_type') or ''),
    ]).lower()

    soil_terms = (
        'soil', 'black soil', 'red soil', 'alluvial', 'laterite', 'clay', 'loam', 'sandy'
    )
    recommendation_terms = (
        'recommend', 'best crop', 'which crop', 'suitable crop', 'what crop', 'grow'
    )

    has_soil_signal = any(term in text for term in soil_terms) or bool((ti.get('soil_type') or '').strip())
    has_recommend_signal = any(term in text for term in recommendation_terms)
    return has_soil_signal and has_recommend_signal


_INDIA_STATE_UT_NAMES = {
    'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh', 'goa',
    'gujarat', 'haryana', 'himachal pradesh', 'jharkhand', 'karnataka', 'kerala',
    'madhya pradesh', 'maharashtra', 'manipur', 'meghalaya', 'mizoram', 'nagaland',
    'odisha', 'orissa', 'punjab', 'rajasthan', 'sikkim', 'tamil nadu', 'telangana',
    'tripura', 'uttar pradesh', 'uttarakhand', 'west bengal', 'jammu and kashmir',
    'ladakh', 'delhi', 'nct of delhi', 'chandigarh', 'puducherry', 'pondicherry',
    'andaman and nicobar islands', 'daman and diu', 'dadra and nagar haveli',
    'dadra and nagar haveli and daman and diu', 'lakshadweep'
}


def _is_cross_state_scheme_request(user_prompt, farmer_context=None):
    """Return True when query explicitly asks for schemes beyond profile state."""
    text = str(user_prompt or '').lower()
    fc_state = str((farmer_context or {}).get('state') or '').strip().lower()

    explicit_cross_state_phrases = (
        'other state', 'another state', 'across states', 'all states', 'outside my state',
        'compare state', 'state comparison', 'compare schemes'
    )
    if any(p in text for p in explicit_cross_state_phrases):
        return True

    mentioned_states = []
    for state_name in _INDIA_STATE_UT_NAMES:
        if re.search(r'\b' + re.escape(state_name) + r'\b', text):
            mentioned_states.append(state_name)

    if not mentioned_states:
        return False

    # If user names a different state than profile state, treat as explicit cross-state intent.
    if fc_state:
        for state_name in mentioned_states:
            if state_name != fc_state:
                return True

    return False


def _apply_tool_input_policy(tool_name, tool_input, farmer_context=None, user_prompt=''):
    """Apply deterministic constraints to model-generated tool inputs."""
    adjusted = dict(tool_input or {})
    fc = farmer_context or {}

    if tool_name == 'search_schemes':
        farmer_state = str(fc.get('state') or '').strip()
        if farmer_state and not _is_cross_state_scheme_request(user_prompt, fc):
            adjusted['state'] = farmer_state
        if not str(adjusted.get('query') or '').strip():
            adjusted['query'] = 'all'

    if tool_name == 'get_crop_advisory':
        if not str(adjusted.get('soil_type') or '').strip() and str(fc.get('soil_type') or '').strip():
            adjusted['soil_type'] = fc.get('soil_type')

        if not str(adjusted.get('location') or '').strip():
            profile_location = str(fc.get('district') or fc.get('state') or '').strip()
            if profile_location:
                adjusted['location'] = profile_location

        if _is_soil_specific_recommendation_query(user_prompt, adjusted) and not str(adjusted.get('query_type') or '').strip():
            adjusted['query_type'] = 'recommendation'

    return adjusted


def _enforce_tool_result_policy(tool_name, result, farmer_context=None, user_prompt=''):
    """Apply deterministic constraints to tool outputs before model synthesis."""
    if tool_name != 'search_schemes' or not isinstance(result, dict):
        return result

    farmer_state = str((farmer_context or {}).get('state') or '').strip()
    if not farmer_state:
        return result

    if _is_cross_state_scheme_request(user_prompt, farmer_context):
        return result

    payload = result.get('data') if isinstance(result.get('data'), dict) else result
    state_schemes = payload.get('state_schemes')
    if not isinstance(state_schemes, dict):
        return result

    filtered = {
        state_name: schemes
        for state_name, schemes in state_schemes.items()
        if str(state_name).strip().lower() == farmer_state.lower()
    }
    payload['state_schemes'] = filtered
    payload['state_scope_applied'] = farmer_state

    if isinstance(result.get('data'), dict):
        result['data'] = payload
    else:
        result = payload

    return result


_SOIL_GUARD_CROP_ALIASES = {
    'rice': ('rice', 'paddy'),
    'wheat': ('wheat',),
    'cotton': ('cotton',),
    'sugarcane': ('sugarcane',),
    'maize': ('maize', 'corn'),
    'groundnut': ('groundnut', 'peanut'),
    'soybean': ('soybean', 'soya'),
    'banana': ('banana',),
    'coconut': ('coconut',),
    'tomato': ('tomato',),
    'onion': ('onion',),
    'potato': ('potato',),
    'ragi': ('ragi', 'finger millet'),
    'toor': ('toor', 'arhar', 'pigeon pea'),
    'chilli': ('chilli', 'chili'),
    'turmeric': ('turmeric',),
    'mustard': ('mustard',),
    'jowar': ('jowar', 'sorghum'),
    'bajra': ('bajra', 'pearl millet'),
    'black gram': ('black gram', 'urad'),
    'green gram': ('green gram', 'moong'),
    'chickpea': ('chickpea', 'chana'),
    'safflower': ('safflower',),
    'sesame': ('sesame', 'til'),
    'sunflower': ('sunflower',),
    'lentil': ('lentil', 'masoor'),
    'barley': ('barley',),
    'okra': ('okra', 'bhindi'),
    'brinjal': ('brinjal', 'eggplant'),
}


def _extract_soil_evidence_crops(tool_data_log):
    """Extract crop names explicitly present in retrieved advisory_data chunks."""
    logs = tool_data_log or []
    corpus_parts = []
    for entry in logs:
        if entry.get('tool') != 'get_crop_advisory':
            continue
        output = entry.get('output')
        if not isinstance(output, dict):
            continue
        payload = output.get('data') if isinstance(output.get('data'), dict) else output
        advisory_data = payload.get('advisory_data') if isinstance(payload, dict) else None
        if not isinstance(advisory_data, list):
            continue
        for chunk in advisory_data:
            if isinstance(chunk, dict):
                corpus_parts.append(str(chunk.get('content') or ''))

    corpus = ' '.join(corpus_parts).lower()
    allowed = set()
    for canonical, aliases in _SOIL_GUARD_CROP_ALIASES.items():
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', corpus):
                allowed.add(canonical)
                break
    return sorted(allowed)


def _mentioned_crops_in_text(text):
    lowered = str(text or '').lower()
    mentioned = set()
    for canonical, aliases in _SOIL_GUARD_CROP_ALIASES.items():
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', lowered):
                mentioned.add(canonical)
                break
    return mentioned


def _apply_strict_soil_response_guard(result_text, user_query_en, farmer_context=None, tool_data_log=None):
    """Deterministically constrain soil recommendation outputs to evidenced crops only."""
    if not _is_soil_specific_recommendation_query(user_query_en, {}):
        return result_text

    allowed = _extract_soil_evidence_crops(tool_data_log)
    if not allowed:
        location_hint = str((farmer_context or {}).get('district') or (farmer_context or {}).get('state') or '').strip()
        if location_hint:
            return (
                f"I could not find strong soil-specific crop evidence for {location_hint} in the retrieved data. "
                "Please share soil pH, drainage, and season (Kharif/Rabi) or run a soil test so I can give a precise recommendation."
            )
        return (
            "I could not find strong soil-specific crop evidence in the retrieved data. "
            "Please share soil pH, drainage, and season (Kharif/Rabi) so I can give a precise recommendation."
        )

    mentioned = _mentioned_crops_in_text(result_text)
    disallowed = sorted(mentioned - set(allowed))
    if not disallowed:
        return result_text

    allowed_str = ', '.join(sorted(allowed))
    return (
        "Based on currently retrieved soil and location evidence, I can recommend only these crops: "
        f"{allowed_str}.\n\n"
        "I am intentionally not recommending other crops here because their soil-fit evidence was not found in the current data."
    )


def _collect_crop_tool_signals(tool_data_log):
    """Collect deterministic guard signals emitted by crop_advisory tool payloads."""
    signals = {
        'insufficient_evidence': False,
        'evidence_message': '',
        'staleness_warnings': [],
        'scheme_redirect': False,
        'scheme_redirect_message': '',
    }

    for entry in (tool_data_log or []):
        if entry.get('tool') != 'get_crop_advisory':
            continue
        output = entry.get('output')
        if not isinstance(output, dict):
            continue

        payload = output.get('data') if isinstance(output.get('data'), dict) else output
        if not isinstance(payload, dict):
            continue

        if payload.get('insufficient_evidence'):
            signals['insufficient_evidence'] = True
            if not signals['evidence_message']:
                signals['evidence_message'] = str(payload.get('evidence_message') or '').strip()

        freshness = payload.get('freshness') if isinstance(payload.get('freshness'), dict) else {}
        warning = str(freshness.get('staleness_warning') or '').strip()
        if warning:
            signals['staleness_warnings'].append(warning)

        if str(payload.get('source_authority') or '').strip().lower() == 'govt_schemes':
            signals['scheme_redirect'] = True
            if not signals['scheme_redirect_message']:
                signals['scheme_redirect_message'] = str(payload.get('message') or '').strip()

    # Deduplicate warnings while preserving order
    unique = []
    seen = set()
    for warning in signals['staleness_warnings']:
        if warning and warning not in seen:
            unique.append(warning)
            seen.add(warning)
    signals['staleness_warnings'] = unique

    return signals


def _apply_tool_signal_response_guard(result_text, user_query_en, tools_used=None, tool_data_log=None):
    """Apply deterministic final-response guardrails from tool metadata signals."""
    text = str(result_text or '').strip()
    signals = _collect_crop_tool_signals(tool_data_log)

    # If crop tool indicates scheme authority hand-off but scheme tool wasn't used,
    # return deterministic hand-off instead of potentially inconsistent answer.
    if signals['scheme_redirect'] and 'search_schemes' not in set(tools_used or []):
        return (
            signals['scheme_redirect_message']
            or "Please ask your scheme query and I will fetch it from the dedicated government schemes service for accurate eligibility and deadlines."
        )

    if signals['insufficient_evidence']:
        low_confidence_markers = (
            'likely', 'possibly', 'could', 'may', 'insufficient evidence',
            'please share', 'need more details'
        )
        lower_text = text.lower()
        if not any(marker in lower_text for marker in low_confidence_markers):
            prefix = signals['evidence_message'] or (
                "Retrieved evidence confidence is limited for this query. "
                "I will share cautious guidance and you should confirm key details first."
            )
            text = f"{prefix}\n\n{text}" if text else prefix

    if signals['staleness_warnings'] and _is_open_crop_recommendation_query(user_query_en) is False:
        # Append one warning only for potentially time-sensitive replies.
        warning = signals['staleness_warnings'][0]
        if warning.lower() not in text.lower():
            text = f"{text}\n\nNote: {warning}".strip()

    return text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BEDROCK RETRY WITH EXPONENTIAL BACKOFF + MODEL FALLBACK
#  Handles ThrottlingException, ModelTimeoutException gracefully.
#  If the primary model fails after all retries, automatically
#  falls back to the alternate model (Pro ↔ Lite).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_RETRIES = 2  # 1 original + 2 retries = 3 total attempts
RETRY_BASE_DELAY = 0.5  # seconds

# Model fallback mapping: primary → fallback
# Nova Pro ↔ Nova 2 Lite (bidirectional)
MODEL_FALLBACK = {}

def _init_model_fallback():
    """Initialize the fallback map after env vars are loaded."""
    global MODEL_FALLBACK
    MODEL_FALLBACK = {
        FOUNDATION_MODEL: FOUNDATION_MODEL_LITE,
        FOUNDATION_MODEL_LITE: FOUNDATION_MODEL,
    }

_init_model_fallback()


def _bedrock_converse_with_retry(bedrock_client, **kwargs):
    """Wrapper around bedrock_rt.converse() with exponential backoff for throttling.
    After exhausting retries on the primary model, automatically falls back to
    the alternate model (Pro ↔ Lite) for one final attempt.
    Returns the Bedrock response dict, or raises the last exception on exhaustion.
    """
    primary_model = kwargs.get('modelId', '')
    last_exc = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            return bedrock_client.converse(**kwargs)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            retryable = error_code in (
                'ThrottlingException', 'TooManyRequestsException',
                'ServiceUnavailableException', 'ModelTimeoutException',
                'InternalServerException',
            )
            if retryable and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                if os.environ.get('ENABLE_BACKOFF_JITTER', 'false').lower() == 'true':
                    delay = max(0.1, delay * (1 + random.uniform(-0.25, 0.25)))
                logger.warning(
                    f"Bedrock {error_code} (attempt {attempt+1}/{1+MAX_RETRIES}) — "
                    f"retrying in {delay:.1f}s"
                )
                _time.sleep(delay)
                last_exc = e
            else:
                last_exc = e
                break  # exhausted retries — try fallback
        except Exception:
            raise

    # Read flag dynamically so tests and runtime env updates are respected.
    model_fallback_enabled = os.environ.get('ENABLE_MODEL_FALLBACK', 'false').lower() == 'true'

    # ── MODEL FALLBACK (guarded by feature flag) ──
    fallback_model = MODEL_FALLBACK.get(primary_model)
    if model_fallback_enabled and fallback_model and last_exc:
        error_code = ''
        if isinstance(last_exc, ClientError):
            error_code = last_exc.response.get('Error', {}).get('Code', '')
        logger.warning(
            f"Primary model {primary_model} failed ({error_code}) after {1+MAX_RETRIES} attempts — "
            f"falling back to {fallback_model}"
        )
        try:
            fallback_kwargs = {**kwargs, 'modelId': fallback_model}
            response = bedrock_client.converse(**fallback_kwargs)
            logger.info(f"Model fallback SUCCESS: {fallback_model}")
            return response
        except Exception as fb_err:
            logger.error(f"Model fallback ALSO FAILED ({fallback_model}): {fb_err}")
            # Raise the original exception — more informative
            raise last_exc
    elif fallback_model and last_exc and not model_fallback_enabled:
        logger.warning(
            f"Primary model {primary_model} failed after {1+MAX_RETRIES} attempts; "
            "model fallback is DISABLED"
        )

    if last_exc:
        raise last_exc
    raise RuntimeError('_bedrock_converse_with_retry: unreachable')


def _build_conversation_history_context(session_id, limit=40):
    """Retrieve recent chat history from DynamoDB and format for the model.
    Returns a list of Bedrock converse() message dicts (role/content pairs).
    Retrieves up to `limit` recent messages (user+assistant pairs).
    Prefers English (message_en) over local language for pipeline context."""
    if not session_id:
        return []
    try:
        history = get_chat_history(session_id, limit=limit)
        if not history:
            return []
        converse_messages = []
        for item in history:
            role = item.get('role', 'user')
            # Prefer English version for pipeline context (model processes in English)
            text = item.get('message_en') or item.get('message', '')
            if not text or not text.strip():
                continue
            # Truncate long previous messages to save tokens
            if len(text) > 500:
                text = text[:500] + '...'
            # Remove sources line from previous assistant messages
            text = re.sub(r'\n\s*Sources:\s*.+$', '', text, flags=re.MULTILINE).strip()
            # Strip any HTML artifacts from previous messages
            text = re.sub(r'</?span[^>]*>', '', text, flags=re.IGNORECASE).strip()
            if role in ('user', 'assistant') and text:
                converse_messages.append({"role": role, "content": [{"text": text}]})
        return converse_messages
    except Exception as e:
        logger.warning(f"Failed to retrieve chat history: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOL RESULT ENRICHMENT & POST-PROCESSING
#  Fixes the "only rice and wheat" problem at two levels:
#  1) Before: enrich tool results when KB returns wrong crop data
#  2) After : post-process final response to remove remaining bad phrases
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Crop reference for enrichment (subset — most commonly mismatched)
_CROP_REF = {
    'cotton': 'Kharif, 140-180d, NPK 120:60:60, black soil pH6-8, drip/furrow, yield 1.5-3t/ha, MSP ₹7020/q. Common pests: bollworm, whitefly, jassid. Diseases: bacterial blight, grey mildew.',
    'sugarcane': 'Annual, 300-450d, NPK 250:100:120, clay loam pH6-8, flood/drip, yield 60-120t/ha, MSP ₹3150/q. Common pests: shoot borer, top borer, woolly aphid, pyrilla. Diseases: red rot, smut, wilt.',
    'maize': 'Kharif+Rabi, 90-120d, NPK 120:60:40, loam pH5.5-7.5, yield 2.5-9t/ha, MSP ₹2090/q. Common pests: fall armyworm, stem borer, aphid. Diseases: turcicum leaf blight, downy mildew, stalk rot.',
    'groundnut': 'Kharif, 100-130d, NPK 25:50:0, sandy loam pH6-7, yield 1-4t/ha, MSP ₹6377/q. Common pests: leaf miner, white grub, aphid. Diseases: tikka disease, stem rot, collar rot.',
    'soybean': 'Kharif, 100-140d, NPK 30:60:40, loam pH6-7.5, yield 1-3t/ha, MSP ₹4600/q. Common pests: girdle beetle, stem fly. Diseases: yellow mosaic, root rot.',
    'banana': 'Perennial, 270-420d, NPK 200:30:300, loam pH5.5-7, drip, yield 30-50t/ha. Common pests: rhizome weevil, banana aphid. Diseases: panama wilt, sigatoka.',
    'coconut': 'Perennial, loam pH5-8, drip/basin, 50-100 nuts/palm/yr, MSP ₹10860/q. Common pests: rhinoceros beetle, red palm weevil. Diseases: bud rot, leaf blight.',
    'tomato': 'Rabi+Kharif, 90-140d, NPK 120:80:80, sandy loam pH6-7.5, drip, yield 20-40t/ha. Common pests: fruit borer, whitefly. Diseases: early blight, late blight, leaf curl virus.',
    'onion': 'Rabi, 110-150d, NPK 100:50:50, loam pH6-7.5, drip, yield 10-30t/ha. Store in cool, dry, ventilated place at 0-5°C for 6-8 months. Cure bulbs for 2 weeks before storage.',
    'potato': 'Rabi, 90-130d, NPK 150:80:100, loam pH5-7, drip/furrow, yield 15-40t/ha. Common pests: tuber moth, aphid. Diseases: late blight, common scab.',
    'chilli': 'Kharif+Rabi, 120-150d, NPK 120:60:60, loam pH6-7, drip, yield 3-12t/ha. Common pests: thrips, mite, fruit borer. Diseases: leaf curl, anthracnose, dieback.',
    'turmeric': 'Kharif, 210-270d, NPK 60:50:120, loam pH4.5-7.5, drip, yield 8-15t/ha. Common pests: shoot borer, scale insect. Diseases: rhizome rot, leaf spot.',
    'mustard': 'Rabi, 90-120d, NPK 80:40:40, loam pH6.5-8, sprinkler, yield 1-3t/ha, MSP ₹5650/q. Common pests: aphid, painted bug. Diseases: alternaria blight, white rust.',
    'ragi': 'Kharif, 70-110d, NPK 50:40:25, red soil pH5.5-7.5, rainfed, yield 1-4t/ha, MSP ₹3846/q. Common pests: stem borer. Diseases: blast, finger mildew.',
    'toor': 'Kharif, 140-180d, NPK 25:50:0, loam pH6-7.5, rainfed, yield 0.6-2.5t/ha, MSP ₹7000/q. Common pests: pod borer, pod fly. Diseases: wilt, sterility mosaic.',
    'mushroom': 'Indoor cultivation, 30-60d cycles. Oyster/button/milky mushroom. Substrate: paddy straw, wheat straw. Spawn from certified labs. Temperature 20-28°C, humidity 80-90%. Investment ₹50K-2L for small unit. Contact local KVK for training.',
    'jowar': 'Kharif+Rabi, 100-120d, NPK 80:40:40, medium soil pH6-8, rainfed, yield 1-5t/ha, MSP ₹3180/q. Common pests: shoot fly, stem borer. Diseases: grain mold, anthracnose.',
    'bajra': 'Kharif, 70-90d, NPK 60:30:0, sandy soil pH6.5-8, rainfed, yield 1-3t/ha, MSP ₹2500/q. Common pests: shoot fly. Diseases: downy mildew, ergot.',
}


def _canonicalize_alias(value):
    normalized = re.sub(r'\s+', ' ', str(value or '').strip().lower())
    normalized = normalized.replace('_', ' ')
    return normalized.strip()


def _crop_key_aliases(crop_key):
    """Generate stable aliases from crop reference keys to improve soil guard coverage."""
    key = _canonicalize_alias(crop_key)
    if not key:
        return set()

    aliases = {key}
    aliases.add(key.replace('-', ' '))
    aliases.add(key.replace(' ', ''))

    # Handle bracket variants: e.g., "mango (table)" -> "mango"
    aliases.add(re.sub(r'\s*\([^)]*\)', '', key).strip())

    # Support common plural forms conservatively
    if not key.endswith('s'):
        aliases.add(f"{key}s")

    return {a for a in aliases if a}


def _expand_soil_aliases_with_crop_ref(base_aliases, crop_ref):
    expanded = {
        canonical: tuple(sorted({_canonicalize_alias(a) for a in aliases if _canonicalize_alias(a)}))
        for canonical, aliases in (base_aliases or {}).items()
    }

    for crop_key in (crop_ref or {}).keys():
        canonical = _canonicalize_alias(crop_key)
        generated = _crop_key_aliases(crop_key)
        if not canonical:
            continue
        existing = set(expanded.get(canonical, tuple()))
        expanded[canonical] = tuple(sorted(existing | generated))

    return expanded


# Ensure strict soil evidence recognises all crops represented in _CROP_REF.
_SOIL_GUARD_CROP_ALIASES = _expand_soil_aliases_with_crop_ref(_SOIL_GUARD_CROP_ALIASES, _CROP_REF)


def _enrich_tool_result(result, tool_name, tool_input, user_prompt):
    """
    When KB tools return data for crops the farmer didn't ask about,
    add a supplementary note with relevant crop reference data so the
    model doesn't say 'I only have data for rice and wheat.'
    """
    if tool_name not in ('get_crop_advisory', 'get_pest_alert'):
        return result

    # Soil recommendation policy: avoid injecting generic crop-reference data,
    # because it can introduce crops without explicit soil-fit evidence.
    if tool_name == 'get_crop_advisory' and _is_soil_specific_recommendation_query(user_prompt, tool_input):
        if isinstance(result, dict):
            result['_soil_evidence_policy'] = (
                "STRICT_SOIL_EVIDENCE: Recommend only crops explicitly supported in advisory_data for the requested soil. "
                "If evidence is weak or missing, state that and ask for soil test details instead of suggesting unsupported crops."
            )
        return result

    # Determine what crop the farmer asked about
    query_crop = (tool_input.get('crop') or '').lower().strip()
    if not query_crop:
        # Try to extract from prompt
        prompt_lower = user_prompt.lower()
        for crop_name in _CROP_REF:
            if crop_name in prompt_lower:
                query_crop = crop_name
                break

    if not query_crop:
        return result

    # Check if the tool result text mainly talks about rice/wheat
    result_str = json.dumps(result).lower() if isinstance(result, dict) else str(result).lower()
    mentions_requested = query_crop in result_str
    mentions_rice_wheat = ('rice' in result_str or 'wheat' in result_str)

    # If result mentions rice/wheat but NOT the requested crop, enrich
    if mentions_rice_wheat and not mentions_requested and query_crop in _CROP_REF:
        enrichment = {
            '_advisor_note': (
                f"IMPORTANT: The knowledge base returned data about rice/wheat instead of {query_crop}. "
                f"Do NOT tell the farmer you only have rice/wheat data. Instead, use THIS reference data "
                f"about {query_crop} combined with the tool results to give helpful advice: "
                f"{_CROP_REF[query_crop]}. "
                f"Provide practical, actionable advice for {query_crop} using this reference data."
            )
        }
        if isinstance(result, dict):
            result['_enrichment'] = enrichment
        else:
            result = {'original': result, '_enrichment': enrichment}
        logger.info(f"Enriched tool result for {query_crop} (KB returned rice/wheat data)")

    return result


def _post_process_response(text):
    """
    Safety-net post-processing to remove any remaining 'only rice and wheat' type phrases.
    This catches cases where the model ignores the system prompt instruction.
    """
    if not text:
        return text

    # Normalize known agri-term translation artifacts at final output stage.
    text = _normalize_translated_agri_terms(text)

    # Patterns that indicate the model is telling the farmer about tool limitations
    bad_patterns = [
        r'(?:only|just)\s+(?:have|has|got|received|cover[s]?|include[s]?)\s+(?:data|details?|info(?:rmation)?|advice|tips?|updates?)\s+(?:for|about|on|regarding)\s+(?:rice|wheat)',
        r'(?:only|just)\s+(?:cover[s]?|include[s]?)\s+rice\s+and\s+wheat',
        r'(?:tools?|system|database|data|advisory)\s+(?:I\s+(?:have|checked)|(?:only|just))\s+.*?rice\s+and\s+wheat',
        r'the\s+(?:latest|recent|current)\s+(?:tool\s+)?(?:data|updates?|advisory|information)\s+.*?(?:only|just)\s+.*?rice\s+and\s+wheat',
        r'(?:unfortunately|sadly),?\s+(?:the\s+)?(?:information|data|tools?|advisory)\s+.*?(?:doesn.?t|don.?t|did\s*n.?t)\s+(?:cover|include|have)\s+.*?(?:specific|detailed)',
    ]

    text_lower = text.lower()
    needs_fix = False
    for pattern in bad_patterns:
        if re.search(pattern, text_lower):
            needs_fix = True
            break

    # Also check for the literal phrase
    if 'rice and wheat' in text_lower and ('only' in text_lower or 'just' in text_lower):
        needs_fix = True

    if needs_fix:
        logger.info("Post-processing: removing 'only rice/wheat' limitation language from response")
        # Remove sentences that mention the tool limitation
        sentences = re.split(r'(?<=[.!?])\s+', text)
        filtered = []
        for s in sentences:
            s_lower = s.lower()
            if ('rice and wheat' in s_lower and ('only' in s_lower or 'just' in s_lower or 'cover' in s_lower)):
                continue
            if re.search(r'tool[s]?\s+(?:I\s+)?(?:checked|have|received)\s+only', s_lower):
                continue
            if re.search(r"(?:doesn.?t|don.?t|did\s*n.?t)\s+(?:cover|include|have)\s+(?:specific|detailed)\s+(?:data|info|details)", s_lower):
                continue
            filtered.append(s)
        if filtered:
            text = ' '.join(filtered)
        # If everything was filtered, keep original (shouldn't happen)

    return text


def _normalize_output_markdown(text):
    """Normalize model markdown so frontend rendering stays deterministic."""
    if not text:
        return text

    normalized = text.replace('\r\n', '\n')

    # Headings: remove excessive indentation and enforce space after hashes
    normalized = re.sub(r'^[\t ]{2,}(#{1,6}\s*)', r'\1', normalized, flags=re.MULTILINE)
    normalized = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', normalized, flags=re.MULTILINE)

    # Bullet consistency: convert unicode bullets to markdown dashes
    normalized = re.sub(r'^[\t ]*•[\t ]+', '- ', normalized, flags=re.MULTILINE)

    # Compact spacing: collapse 3+ blank lines to 1 blank line
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)

    # Trim trailing spaces line-wise and final body
    normalized = '\n'.join(line.rstrip() for line in normalized.split('\n')).strip()

    return normalized


def _looks_like_symptom_query(text):
    if not text:
        return False
    q = text.lower()
    symptom_terms = [
        'yellow', 'spot', 'spots', 'wilting', 'wilt', 'rot', 'blight',
        'leaf', 'leaves', 'stem', 'fruit', 'disease', 'what disease', 'symptom'
    ]
    return any(term in q for term in symptom_terms)


def _ensure_cautious_pest_response(text, tools_used, user_query_en):
    if not text:
        return text
    used = set(tools_used or [])
    if 'get_pest_alert' not in used:
        return text
    if not _looks_like_symptom_query(user_query_en):
        return text

    lowered = text.lower()
    if 'probable diagnosis' in lowered or 'not a confirmed' in lowered:
        return text

    caution = (
        'Based on symptoms alone, this is a probable diagnosis and not a confirmed one. '
        'Please verify with close leaf/stem/fruit checks or a photo before final treatment.'
    )
    return f"{caution}\n\n{text}"


def _strip_local_markdown_symbols(text, language_code='en'):
    """Sanitize text for frontend and remove markdown symbols for cleaner plain-text UX."""
    if not text:
        return text

    s = text.replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'</?span[^>]*>', '', s, flags=re.IGNORECASE)
    s = s.replace('\uFFFD', '')

    _lang = normalize_language_code(language_code or 'en', default='en')
    _is_indic = _lang in {'ta', 'te', 'kn', 'ml', 'mr', 'bn', 'gu', 'pa', 'or', 'as', 'ur', 'hi'}
    if _is_indic:
        s = re.sub(r'[\u200b\ufeff]', '', s)
    else:
        s = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', s)

    filtered = []
    for ch in s:
        if ch in ('\n', '\t'):
            filtered.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in {'Cc', 'Cs', 'Co', 'Cn'}:
            continue
        filtered.append(ch)
    s = ''.join(filtered)

    def _normalize_local_units_and_artifacts(value, lang, is_indic):
        out = value or ''

        def _format_number_for_text(num_value):
            if abs(num_value - round(num_value)) < 1e-9:
                return str(int(round(num_value)))
            return f"{num_value:.2f}".rstrip('0').rstrip('.')

        def _to_quintal_rate(raw_number):
            try:
                base = float((raw_number or '').replace(',', ''))
            except Exception:
                return None
            if base < 0:
                return None
            return _format_number_for_text(base * 100.0)

        canonical_quintal = {
            'ta': 'குவிண்டால்',
            'hi': 'क्विंटल',
            'te': 'క్వింటాల్',
        }.get(lang, 'quintal')

        currency_pat = r'(?:₹|Rs\.?|INR|ரூ\.?|रु\.?|రూ\.?)'
        kg_pat = r'(?:kg|kilo(?:gram)?s?|கிலோ|किलो(?:ग्राम)?|కిలో(?:గ్రాము)?)'
        per_sep = r'(?:/|\bper\b|\bप्रति\b|\bప్రతి\b|க்கு|\bko\b)'

        def _replace_cur_num_per_kg(match):
            cur = match.group('cur')
            num = match.group('num')
            quintal_rate = _to_quintal_rate(num)
            if quintal_rate is None:
                return match.group(0)
            return f"{cur} {quintal_rate}/{canonical_quintal}"

        out = re.sub(
            rf'(?P<cur>{currency_pat})\s*(?P<num>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*{per_sep}\s*{kg_pat}',
            _replace_cur_num_per_kg,
            out,
            flags=re.IGNORECASE,
        )

        if lang == 'ta':
            out = re.sub(r'கு[யவ]ி?ண?்டா?ல்|கு[யவ]ி?ண?்டல்|காயிண்டல்|காயின்டல்|கிண்டல்', 'குவிண்டால்', out)
            out = re.sub(r'கிலோகிராம்|கிலோகிராம்கள்|கிலோ\s*கிராம்', 'கிலோ', out)
        elif lang == 'hi':
            out = re.sub(r'क्विन्टल|क्विंटल', 'क्विंटल', out)
            out = re.sub(r'किलोग्राम|किलो\s*ग्राम', 'किलो', out)
        elif lang == 'te':
            out = re.sub(r'క్వింటల్|క్వింటాళ్|క్వింటా', 'క్వింటాల్', out)
            out = re.sub(r'కిలోగ్రాము|కిలోగ్రాములు|కిలో\s*గ్రాము', 'కిలో', out)

        if is_indic:
            script_ranges = {
                'ta': '\u0B80-\u0BFF',
                'hi': '\u0900-\u097F',
                'te': '\u0C00-\u0C7F',
                'kn': '\u0C80-\u0CFF',
                'ml': '\u0D00-\u0D7F',
                'mr': '\u0900-\u097F',
                'bn': '\u0980-\u09FF',
                'as': '\u0980-\u09FF',
                'gu': '\u0A80-\u0AFF',
                'pa': '\u0A00-\u0A7F',
                'or': '\u0B00-\u0B7F',
                'ur': '\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF',
            }
            rg = script_ranges.get(lang)
            if rg:
                out = re.sub(fr'(?<![A-Za-z])[A-Za-z](?=[{rg}])', '', out)
                out = re.sub(fr'(?<=[{rg}])[A-Za-z](?![A-Za-z])', '', out)
                out = '\n'.join(
                    re.match(r'^[\t ]*', line).group(0) + re.sub(r' {2,}', ' ', line[len(re.match(r'^[\t ]*', line).group(0)):])
                    for line in out.split('\n')
                )

        return out

    if not STRIP_LOCAL_MARKDOWN_SYMBOLS:
        s = _normalize_local_units_and_artifacts(s, _lang, _is_indic)
        s = re.sub(r'\n{3,}', '\n\n', s)
        return '\n'.join(line.rstrip() for line in s.split('\n')).strip()

    lines = s.split('\n')
    numbered_line_re = re.compile(r'^(?P<indent>[\t ]*)(?P<num>\d{1,2})\.\s+(?P<body>.+)$')

    def _renumber_numbered_runs(line_list):
        """Normalize contiguous numbered lists to 1..N so repeated '1.' markers become stable points."""
        output = []
        run_counters = {}

        for raw in line_list:
            m = numbered_line_re.match(raw)
            if not m:
                # Break numbering runs on blank/non-numbered lines.
                if not raw.strip():
                    run_counters.clear()
                output.append(raw)
                continue

            indent = m.group('indent')
            body = m.group('body')
            next_num = run_counters.get(indent, 0) + 1
            run_counters[indent] = next_num
            output.append(f"{indent}{next_num}. {body}")

            # Child indentation should not leak stale counters if parent advances.
            for key in list(run_counters.keys()):
                if len(key) > len(indent) and key.startswith(indent):
                    del run_counters[key]

        return output

    heading_re = re.compile(r'^[\t ]*#{1,6}[\t ]*(.+?)\s*$')
    should_number_headings = (sum(1 for line in lines if heading_re.match(line)) >= 3) and (not _is_indic)
    heading_idx = 0
    cleaned_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            cleaned_lines.append('')
            continue

        heading_match = heading_re.match(line)
        if heading_match:
            heading_text = heading_match.group(1).strip()
            heading_text = heading_text.replace('**', '').replace('*', '').replace('#', '')
            if should_number_headings:
                heading_idx += 1
                cleaned_lines.append(f"{heading_idx}. {heading_text}")
            else:
                cleaned_lines.append(heading_text)
            continue

        line = re.sub(r'^([\t ]*)[•\-\*][\t ]+', r'\1- ', line)
        # Normalize list markers across locales (e.g., 1), 1., 1।, 1۔) to a stable "1. " format.
        line = re.sub(r'^([\t ]*)(\d{1,2})[\)\.\u0964\u0965\u06D4][\t ]+', r'\1\2. ', line)
        line = line.replace('**', '')
        line = line.replace('*', '')
        line = re.sub(r'^([\t ]*)#{1,6}[\t ]*', r'\1', line)
        cleaned_lines.append(line.rstrip())

    s = '\n'.join(cleaned_lines)
    s = '\n'.join(_renumber_numbered_runs(s.split('\n')))
    s = _normalize_local_units_and_artifacts(s, _lang, _is_indic)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return '\n'.join(line.rstrip() for line in s.split('\n')).strip()


def _localize_response_hybrid(text_en, target_lang):
    """Model-first localization with Translate fallback on failure/quality issues."""
    if not text_en:
        return text_en, 'empty'
    if target_lang == 'en':
        return text_en, 'en'
    if not HYBRID_LOCALIZATION_ENABLED:
        return translate_response(text_en, 'en', target_lang), 'translate_only'

    try:
        localize_prompt = (
            f"Translate this agricultural advisory to language code '{target_lang}'. "
            "Keep meaning and numbers exact. Output plain text only. "
            "Do not use markdown symbols like # or *.\n\n"
            f"Advisory:\n{text_en}"
        )

        response = bedrock_rt.converse(
            modelId=FOUNDATION_MODEL_LITE or FOUNDATION_MODEL,
            messages=[{"role": "user", "content": [{"text": localize_prompt}]}],
            inferenceConfig={"temperature": 0.2},
        )
        localized = (
            response.get('output', {})
            .get('message', {})
            .get('content', [{}])[0]
            .get('text', '')
            .strip()
        )
        stop_reason = response.get('stopReason', '')

        if (
            localized
            and len(localized) >= 40
            and 'blocked by our content filters' not in localized.lower()
            and stop_reason != 'content_filtered'
            and not needs_localization_retry(localized, target_lang)
        ):
            return localized, 'model_direct'
    except Exception as loc_err:
        logger.warning(f"Hybrid localization model path failed ({target_lang}): {loc_err}")

    return translate_response(text_en, 'en', target_lang), 'translate_fallback'


def _invoke_bedrock_direct(prompt, farmer_context=None, skip_native_guardrail=False, chat_history=None, model_id=None, lambda_context=None):
    """
    Call Bedrock model directly with tool use (converse API).
    Primary invocation path using Bedrock converse() API with tool use.
    skip_native_guardrail: True for feature-page fast paths (internal prompts
    are code-generated, already screened by application-level guardrails).
    chat_history: list of previous converse() message dicts for conversation memory.
    model_id: optional override — use FOUNDATION_MODEL_LITE for simple queries.
    lambda_context: optional Lambda context for timeout checking.
    Returns: (result_text, tools_used, tool_data_log, guardrail_intervened)
    """
    tools_used = []
    tool_data_log = []  # raw tool results for fact-checking
    guardrail_intervened = False

    # Build messages
    system_prompt = DIRECT_SYSTEM_PROMPT
    if farmer_context:
        system_prompt += f"\n\nFarmer context: {json.dumps(farmer_context)}"

    # Prepend conversation history for follow-up context
    # Bedrock converse() requires:
    #   1. Must start with a user message
    #   2. Alternating user/assistant roles
    #   3. Must end with assistant before we append the new user message
    messages = []
    if chat_history:
        prev_role = None
        for msg in chat_history:
            role = msg.get('role', 'user')
            # Skip consecutive same-role messages to maintain alternation
            if role == prev_role:
                continue
            messages.append(msg)
            prev_role = role
        # Bedrock rule: must START with user message
        while messages and messages[0].get('role') != 'user':
            messages.pop(0)
        # Bedrock rule: must END with assistant so new user message is valid next
        while messages and messages[-1].get('role') == 'user':
            messages.pop()
        if messages:
            logger.info(f"Conversation memory: {len(messages)} prior messages")
    messages.append({"role": "user", "content": [{"text": prompt}]})

    try:
        # Multi-turn tool use loop (max 5 turns)
        for turn in range(5):
            # NEW: Check timeout before each turn
            if ENABLE_TIMEOUT_PROTECTION and lambda_context:
                is_approaching, remaining_ms = _check_timeout_approaching(lambda_context)
                if is_approaching:
                    logger.warning(f"Timeout approaching in turn {turn}: {remaining_ms}ms remaining")
                    return _timeout_fallback_response(), tools_used, tool_data_log, False

            converse_kwargs = {
                "modelId": _validated_model_id(model_id),
                "messages": messages,
                "system": [{"text": system_prompt}],
                "toolConfig": {"tools": DIRECT_TOOLS},
                "inferenceConfig": {"maxTokens": 4096, "temperature": 0.3},
            }
            # Gap #5: Attach Bedrock native guardrail if configured
            # (skipped for feature-page fast paths — their prompts are
            #  code-generated and already passed application guardrails)
            gc = _guardrail_config()
            if gc and not skip_native_guardrail:
                converse_kwargs['guardrailConfig'] = gc

            response = _bedrock_converse_with_retry(bedrock_rt, **converse_kwargs)
            output = response.get("output", {})
            message = output.get("message", {})
            stop_reason = response.get("stopReason", "")

            # Add assistant message to conversation
            messages.append(message)

            # Check if model wants to use a tool
            if stop_reason == "tool_use":
                # Collect all tool_use blocks first
                pending_tools = []
                for block in message.get("content", []):
                    if "toolUse" in block:
                        tool_use = block["toolUse"]
                        pending_tools.append({
                            "name": tool_use["name"],
                            "input": tool_use.get("input", {}),
                            "id": tool_use["toolUseId"],
                        })

                # Enforce deterministic input policy before any tool calls.
                for t in pending_tools:
                    t["input"] = _apply_tool_input_policy(
                        t["name"],
                        t.get("input", {}),
                        farmer_context=farmer_context,
                        user_prompt=prompt,
                    )

                # ── PARALLEL TOOL EXECUTION ──
                # When 2+ tools are requested, run them concurrently (~2x speedup)
                tool_results = []
                if len(pending_tools) >= 2:
                    logger.info(f"Parallel tool execution: {[t['name'] for t in pending_tools]}")

                    # Bug 1.5: thread-safe lock for shared lists
                    _lock = threading.Lock() if ENABLE_THREAD_SAFE_TOOLS else None

                    def _safe_append_tool(name):
                        if _lock:
                            with _lock:
                                tools_used.append(name)
                        else:
                            tools_used.append(name)

                    def _safe_append_log(entry):
                        if _lock:
                            with _lock:
                                tool_data_log.append(entry)
                        else:
                            tool_data_log.append(entry)

                    pool = ThreadPoolExecutor(max_workers=len(pending_tools))
                    try:
                        futures = {
                            pool.submit(_execute_tool, t["name"], t["input"]): t
                            for t in pending_tools
                        }

                        # Bug 1.2: use wait() with timeout instead of as_completed()
                        if ENABLE_TOOL_TIMEOUT:
                            done, not_done = wait(futures.keys(), timeout=TOOL_EXECUTION_TIMEOUT_SEC)

                            # Process completed tools
                            for future in done:
                                t = futures[future]
                                tool_name = t["name"]
                                tool_input = t["input"]
                                tool_id = t["id"]
                                _safe_append_tool(tool_name)
                                try:
                                    result = future.result()
                                    result = _enrich_tool_result(result, tool_name, tool_input, prompt)
                                    result = _enforce_tool_result_policy(tool_name, result, farmer_context, user_prompt=prompt)
                                    _safe_append_log({"tool": tool_name, "input": tool_input, "output": result})
                                    tool_results.append({
                                        "toolResult": {
                                            "toolUseId": tool_id,
                                            "content": [{"json": result}],
                                        }
                                    })
                                except Exception as e:
                                    logger.error(f"Tool {tool_name} result error: {str(e)}")
                                    tool_results.append({
                                        "toolResult": {
                                            "toolUseId": tool_id,
                                            "content": [{"json": {"error": f"Tool execution failed: {str(e)}"}}],
                                        }
                                    })

                            # Handle timed-out tools
                            for future in not_done:
                                t = futures[future]
                                tool_name = t["name"]
                                tool_id = t["id"]
                                logger.error(f"Tool {tool_name} TIMED OUT after {TOOL_EXECUTION_TIMEOUT_SEC}s")
                                _safe_append_tool(f"{tool_name}_TIMEOUT")
                                _emit_tool_metric(tool_name, TOOL_EXECUTION_TIMEOUT_SEC * 1000.0, False)
                                tool_results.append({
                                    "toolResult": {
                                        "toolUseId": tool_id,
                                        "content": [{"json": {
                                            "error": f"Tool execution timed out after {TOOL_EXECUTION_TIMEOUT_SEC} seconds",
                                            "tool": tool_name,
                                            "timeout": True,
                                        }}],
                                    }
                                })
                                future.cancel()
                        else:
                            # Original code path: no timeout
                            for future in as_completed(futures):
                                t = futures[future]
                                tool_name = t["name"]
                                tool_input = t["input"]
                                tool_id = t["id"]
                                _safe_append_tool(tool_name)
                                result = future.result()
                                result = _enrich_tool_result(result, tool_name, tool_input, prompt)
                                result = _enforce_tool_result_policy(tool_name, result, farmer_context, user_prompt=prompt)
                                _safe_append_log({"tool": tool_name, "input": tool_input, "output": result})
                                tool_results.append({
                                    "toolResult": {
                                        "toolUseId": tool_id,
                                        "content": [{"json": result}],
                                    }
                                })
                    finally:
                        if ENABLE_TOOL_TIMEOUT:
                            pool.shutdown(wait=False, cancel_futures=True)
                        else:
                            pool.shutdown(wait=True)
                else:
                    # Single tool — execute directly (no thread overhead)
                    for t in pending_tools:
                        tool_name = t["name"]
                        tool_input = t["input"]
                        tool_id = t["id"]
                        logger.info(f"Direct Bedrock tool call: {tool_name}({json.dumps(tool_input)[:100]})")
                        tools_used.append(tool_name)
                        result = _execute_tool(tool_name, tool_input)
                        result = _enrich_tool_result(result, tool_name, tool_input, prompt)
                        result = _enforce_tool_result_policy(tool_name, result, farmer_context, user_prompt=prompt)
                        tool_data_log.append({"tool": tool_name, "input": tool_input, "output": result})
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_id,
                                "content": [{"json": result}],
                            }
                        })

                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})
                continue

            # Model is done — extract final text
            result_text = ""
            for block in message.get("content", []):
                if "text" in block:
                    result_text += block["text"]

            if stop_reason == "guardrail_intervened":
                logger.warning(f"Direct Bedrock guardrail INTERVENED — output replaced ({len(result_text)} chars)")
                guardrail_intervened = True
            logger.info(f"Direct Bedrock response: {len(result_text)} chars, tools={tools_used}, stopReason={stop_reason}")
            return result_text, tools_used, tool_data_log, guardrail_intervened

        # Exhausted turns
        return "I'm having trouble processing your request. Please try again.", tools_used, tool_data_log, guardrail_intervened

    except Exception as e:
        logger.error(f"Direct Bedrock invocation error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"I apologize, I encountered an error. Please try again.", [], [], False



def _classify_intents(message_en, original_message=None):
    """Classify intents from English translation AND original Indic text.
    Uses word-boundary matching for English keywords to prevent false positives
    (e.g., 'rain' must not match 'drainage' or 'drains').
    """
    text = (message_en or '').lower()
    orig = (original_message or '').lower()
    combined = text + ' ' + orig
    intents = set()

    def _has_any_keyword(keywords, haystack):
        """Match keywords with word-boundary for Latin text, substring for Indic."""
        for kw in keywords:
            if re.search(r'[\u0900-\u0D7F]', kw):
                # Indic script: substring match (no word boundaries in Devanagari etc.)
                if kw in haystack:
                    return True
            else:
                # Latin/English: word-boundary match to avoid 'rain' ⊂ 'drains'
                if re.search(r'\b' + re.escape(kw) + r'\b', haystack):
                    return True
        return False

    weather_kw = ['weather', 'rain', 'rainfall', 'temperature', 'humidity', 'forecast', 'monsoon', 'mausam',
                  # Tamil/Hindi/Telugu weather words
                  'வானிலை', 'மழை', 'வெப்பநிலை', 'मौसम', 'बारिश', 'तापमान',
                  'వాతావరణం', 'వర్షం', 'ఉష్ణోగ్రత']
    crop_kw = ['crop', 'seed', 'soil', 'fertilizer', 'irrigation', 'yield', 'harvest', 'variety',
               'kharif', 'rabi', 'grow', 'plant', 'sow', 'cultivat',
               'msp', 'minimum support price', 'market price', 'price', 'mandi', 'procurement',
               # Tamil crop words
               'பயிர்', 'விதை', 'மண்', 'உரம்', 'நெல்', 'நிலம்', 'வளர்', 'விவசாய',
               # Hindi crop words
               'फसल', 'बीज', 'मिट्टी', 'खाद', 'उगा', 'खेती',
               # Telugu crop words
               'పంట', 'విత్తనం', 'నేల', 'ఎరువు', 'వ్యవసాయ']
    pest_kw = ['pest', 'disease', 'fungus', 'insect', 'blight', 'spot', 'rot', 'spray', 'infestation',
               'yellow', 'brown', 'wilt', 'curling', 'dying', 'damage', 'attack', 'infection',
               'fungicide', 'pesticide', 'medicine', 'treatment', 'cure', 'leaves turning',
               # Tamil pest/symptom words
               'பூச்சி', 'நோய்', 'கீடம்', 'மஞ்சள்', 'மருந்து', 'தெளிக்க', 'தெளி',
               'பழுப்பு', 'வாடி', 'அழுகல்', 'இலைகள்',
               # Hindi pest/symptom words
               'कीट', 'रोग', 'पीला', 'पीले', 'दवा', 'छिड़काव', 'फफूंद', 'कीटनाशक',
               'भूरा', 'मुरझा', 'सड़',
               # Telugu pest/symptom words
               'పురుగు', 'వ్యాధి', 'పసుపు', 'మందు', 'స్ప్రే', 'ఆకులు',
               'గోధుమ', 'వాడి', 'కుళ్ళు']
    schemes_kw = ['scheme', 'subsidy', 'loan', 'insurance', 'pm-kisan', 'government', 'yojana', 'benefit',
                  # Tamil/Hindi/Telugu scheme words
                  'திட்டம்', 'மானியம்', 'கடன்', 'योजना', 'सब्सिडी', 'ऋण',
                  'పథకం', 'రాయితీ', 'రుణం']
    profile_kw = ['profile', 'my farm', 'my details', 'my crop', 'my soil', 'my state', 'my district']

    if _has_any_keyword(weather_kw, combined):
        intents.add('weather')
    if _has_any_keyword(crop_kw, combined):
        intents.add('crop')
    if _has_any_keyword(pest_kw, combined):
        intents.add('pest')
    if _has_any_keyword(schemes_kw, combined):
        intents.add('schemes')
    if _has_any_keyword(profile_kw, combined):
        intents.add('profile')

    return list(intents)


def _build_tool_first_prompt(message_en, intents, farmer_context=None):
    """Force tool-first behavior for known intents to reduce empty/non-grounded replies."""
    text = (message_en or '').strip()
    if not text:
        return text

    intent_order = ['pest', 'weather', 'irrigation', 'crop', 'schemes', 'profile']
    selected = [i for i in intent_order if i in (intents or [])]
    if not selected:
        return text

    # Limit to 3 intents max to avoid API Gateway timeout (29s)
    if len(selected) > 3:
        logger.warning(f"Too many intents ({len(selected)}), trimming to top 3: {selected[:3]}")
        selected = selected[:3]

    tool_map = {
        'pest': 'get_pest_alert',
        'weather': 'get_weather',
        'irrigation': 'get_crop_advisory',
        'crop': 'get_crop_advisory',
        'schemes': 'search_schemes',
        'profile': 'get_farmer_profile',
    }
    required_tools = [tool_map[i] for i in selected if i in tool_map]
    first_tool = required_tools[0]

    context_hint = ""
    if farmer_context:
        known = []
        if farmer_context.get('state'):
            known.append(f"state={farmer_context['state']}")
        if farmer_context.get('district'):
            known.append(f"district={farmer_context['district']}")
        if farmer_context.get('soil_type'):
            known.append(f"soil_type={farmer_context['soil_type']}")
        if farmer_context.get('crops'):
            known.append(f"crops={', '.join(farmer_context['crops'])}")
        if known:
            context_hint = f"Known farmer context: {'; '.join(known)}."

    # For irrigation intent, add specific instruction
    irrigation_hint = ""
    if 'irrigation' in selected:
        irrigation_hint = (
            "For the irrigation query, call get_crop_advisory with query_type='irrigation' "
            "and include the crop name, location, and soil_type in the parameters. "
            "The Knowledge Base has detailed irrigation schedules, water requirements, "
            "drip/sprinkler/flood methods, and crop water need tables.\n"
        )

    routing = (
        "[ROUTING POLICY - STRICT]\n"
        f"Detected intents: {', '.join(selected)}.\n"
        f"You MUST call this tool first: {first_tool}.\n"
        f"Then use these tools as needed: {', '.join(required_tools)}.\n"
        "Do not answer with generic text before at least one tool call.\n"
        "If required parameters are missing, make a best-effort call with available context first, "
        "then ask only the minimum missing fields.\n"
        f"{irrigation_hint}"
        f"{context_hint}\n"
        "[/ROUTING POLICY]\n\n"
    )
    return routing + text


def lambda_handler(event, context):
    """
    Main orchestrator — full flow:
    1. Detect language → translate to English
    2. Invoke Bedrock converse() with tool routing
    3. Translate response back to farmer's language
    4. Generate Polly audio
    5. Return {reply, reply_en, detected_language, tools_used, audio_url, session_id}
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        if ENABLE_UNIFIED_CORS:
            return handle_cors_preflight(methods='GET,POST,OPTIONS')
        return success_response({}, message='OK')

    # Correlation ID for end-to-end request tracing across CloudWatch logs
    _request_id = getattr(context, 'aws_request_id', str(uuid.uuid4())[:8])
    logger.info(f"[{_request_id}] Handler invoked")

    try:
        body = json.loads(event.get('body', '{}'))

        # ── Chat History API (DB-backed, cross-device sync) ──
        action = body.get('action')
        if action:
            hist_farmer = body.get('farmer_id', '')
            hist_session = body.get('session_id', '')
            if action == 'list_sessions':
                sessions = list_sessions(hist_farmer)
                return success_response({'sessions': sessions}, message='Sessions loaded')
            elif action == 'get_session':
                msgs = get_session_messages(hist_farmer, hist_session)
                return success_response({'messages': msgs}, message='Messages loaded')
            elif action == 'save_session':
                msgs = body.get('messages', [])
                preview = body.get('preview', None)
                ok = save_session(hist_farmer, hist_session, msgs, preview)
                return success_response({'saved': ok}, message='Session saved' if ok else 'Save failed')
            elif action == 'delete_session':
                delete_result = delete_chat_session(hist_farmer, hist_session)
                deleted = bool(delete_result.get('deleted')) if isinstance(delete_result, dict) else bool(delete_result)
                payload = delete_result if isinstance(delete_result, dict) else {'deleted': deleted}
                return success_response(payload, message='Session deleted' if deleted else 'Delete failed')
            elif action == 'rename_session':
                new_title = body.get('title', '').strip()
                if not new_title:
                    return error_response('title is required', 400)
                ok = rename_chat_session(hist_farmer, hist_session, new_title)
                return success_response({'renamed': ok, 'title': new_title[:80]}, message='Session renamed' if ok else 'Rename failed')

        # ── Fast path: Refresh an expired audio presigned URL ──
        refresh_key = body.get('refresh_audio_key')
        if refresh_key:
            fresh_url = refresh_audio_url(refresh_key)
            if fresh_url:
                return success_response({'audio_url': fresh_url, 'audio_key': refresh_key},
                                        message='Audio URL refreshed')
            return error_response('Audio file not found', 404)

        # ── Fast path: Async TTS generation (called separately by frontend) ──
        generate_tts = body.get('generate_tts')
        if generate_tts:
            tts_text = body.get('tts_text', '')
            tts_lang = body.get('tts_language', 'en')
            tts_farmer_id = body.get('farmer_id', 'anonymous')
            if tts_farmer_id and tts_farmer_id != 'anonymous':
                tts_profile = get_farmer_profile(tts_farmer_id)
                if tts_profile and tts_profile.get('language'):
                    tts_lang = tts_profile.get('language')
            if not tts_text:
                return error_response('tts_text is required', 400)
            try:
                tts_lang_norm = normalize_language_code(tts_lang, default='en')
                gtts_budget = ASYNC_GTTS_TIME_BUDGET_SEC if tts_lang_norm not in ('en', 'hi') else None
                polly_result = text_to_speech(
                    tts_text,
                    tts_lang,
                    return_metadata=True,
                    gtts_time_budget_sec=gtts_budget,
                )
                if isinstance(polly_result, dict):
                    if not polly_result.get('audio_url'):
                        _tts_err = polly_result.get('error') or f'No audio generated for language={tts_lang}'
                        logger.warning(f'Async TTS unavailable: {_tts_err}')
                        return error_response('Audio is temporarily unavailable. Please try again.', 503)
                    return success_response({
                        'audio_url': polly_result.get('audio_url'),
                        'audio_key': polly_result.get('audio_key'),
                        'truncated': polly_result.get('truncated', False),
                        'partial_audio': polly_result.get('partial_audio', False),
                        'processed_chars': polly_result.get('processed_chars'),
                        'total_chars': polly_result.get('total_chars'),
                    }, message='TTS generated')
                if not polly_result:
                    _tts_err = f'No audio generated for language={tts_lang}'
                    logger.warning(f'Async TTS unavailable: {_tts_err}')
                    return error_response('Audio is temporarily unavailable. Please try again.', 503)
                return success_response({'audio_url': polly_result}, message='TTS generated')
            except Exception as tts_err:
                logger.warning(f'Async TTS failed: {tts_err}')
                return error_response('TTS generation failed', 500)

        user_message = body.get('message', '')
        session_id = body.get('session_id', str(uuid.uuid4()))
        farmer_id = body.get('farmer_id', 'anonymous')
        idempotency_token = body.get('idempotency_token')
        language = body.get('language', None)
        profile = get_farmer_profile(farmer_id) if farmer_id != 'anonymous' else None
        profile_language = None
        if profile and profile.get('language'):
            profile_language = normalize_language_code(profile.get('language'), default='en')
        # Client language is authoritative (frontend now sends persisted app_language).
        # Profile language is a fallback when client language is not present.
        effective_preferred_language = language or profile_language
        if profile_language and language:
            requested_language = normalize_language_code(language, default='en')
            if requested_language != profile_language:
                logger.info(
                    f"Language override for farmer {farmer_id}: requested={requested_language}, profile={profile_language}"
                )
        # GPS location sent from frontend (browser Geolocation API)
        gps_location = body.get('gps_location', None)  # e.g. "Coimbatore"
        gps_coords = body.get('gps_coords', None)      # e.g. {"lat": 11.01, "lng": 76.95}

        # Ensure session ID is long enough for Bedrock session tracking
        if len(session_id) < 33:
            session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, session_id))

        _t_start = _time.time()
        _is_feature_page = any(session_id.startswith(p) or body.get('session_id', '').startswith(p) for p in FAST_PATH_PREFIXES)
        logger.info(f'Session {session_id} | feature_page={_is_feature_page}')

        if not user_message or not user_message.strip():
            return error_response('Message is required', 400)

        # Early timeout check before any additional processing/guardrails/tooling
        is_approaching, remaining_ms = _check_timeout_approaching(context)
        if is_approaching:
            logger.warning(f"Timeout approaching early in request: {remaining_ms}ms remaining, returning fallback")
            requested_lang = normalize_language_code(effective_preferred_language or 'en', default='en')
            return _timeout_http_response(session_id, requested_lang)

        # ── Chat session message limit ──
        # Cap at 50 user interactions per session (100 messages = 50 user + 50 assistant).
        # Beyond this:
        # - Context quality degrades (model only reads last 6 anyway)
        # - DynamoDB item accumulation becomes wasteful
        # - Forces fresh context for complex new topics
        MAX_MESSAGES_PER_SESSION = 100
        if not _is_feature_page:
            msg_count = get_session_message_count(session_id)
            if msg_count >= MAX_MESSAGES_PER_SESSION:
                logger.info(f'Session {session_id} reached message limit ({msg_count}/{MAX_MESSAGES_PER_SESSION})')
                return success_response({
                    'reply': (
                        "This chat has reached its message limit. "
                        "To keep our conversations helpful and accurate, please start a new chat. "
                        "Your chat history is saved and you can review it anytime!"
                    ),
                    'reply_en': (
                        "This chat has reached its message limit. "
                        "To keep our conversations helpful and accurate, please start a new chat. "
                        "Your chat history is saved and you can review it anytime!"
                    ),
                    'detected_language': 'en',
                    'tools_used': [],
                    'audio_url': None,
                    'audio_key': None,
                    'session_id': session_id,
                    'session_full': True,
                    'message_count': msg_count,
                    'message_limit': MAX_MESSAGES_PER_SESSION,
                    'mode': 'bedrock-direct',
                    'policy': {
                        'code_policy_enforced': True,
                        'session_limit_reached': True,
                    },
                }, message='Session message limit reached', language='en')

        # ══════ ENTERPRISE GUARDRAILS (Pre-processing) ══════
        # Gap #1 (PII), #2 (Injection), #4 (Input Length), #7 (Toxicity)
        guardrail_result = run_all_guardrails(user_message)
        pii_safe_msg = guardrail_result.get('pii_masked_message', user_message[:200])

        if not guardrail_result['passed']:
            block_type = guardrail_result['blocked_reason']
            block_response = guardrail_result['blocked_response']
            audit_guardrail_block(
                block_type=block_type,
                farmer_id=farmer_id,
                session_id=session_id,
                pii_safe_message=pii_safe_msg,
                threat_details=guardrail_result.get('threat_details'),
            )
            return success_response({
                'reply': block_response,
                'reply_en': block_response,
                'detected_language': 'en',
                'tools_used': [],
                'audio_url': None,
                'audio_key': None,
                'session_id': session_id,
                'mode': 'bedrock-direct',
                'policy': {
                    'code_policy_enforced': True,
                    'guardrail_blocked': True,
                    'block_type': block_type,
                },
            }, message='Guardrail blocked', language='en')

        # Log PII detection (types only, never raw data)
        if guardrail_result['pii_detected']:
            audit_pii_detected(farmer_id, session_id, guardrail_result['pii_detected'])

        # Gap #3: Rate limiting
        rate_result = check_rate_limit(session_id, farmer_id)
        if not rate_result['allowed']:
            audit_guardrail_block(
                block_type='rate_limit',
                farmer_id=farmer_id,
                session_id=session_id,
                pii_safe_message=pii_safe_msg,
                threat_details={'reason': rate_result['reason']},
            )
            return success_response({
                'reply': rate_result['reason'],
                'reply_en': rate_result['reason'],
                'detected_language': 'en',
                'tools_used': [],
                'audio_url': None,
                'audio_key': None,
                'session_id': session_id,
                'mode': 'bedrock-direct',
                'policy': {
                    'code_policy_enforced': True,
                    'rate_limited': True,
                    'retry_after_seconds': rate_result.get('retry_after_seconds'),
                },
            }, message='Rate limited', language='en')

        user_message = _sanitize_user_message(guardrail_result['sanitized_message'])

        # Second empty check after sanitization (sanitizer may strip everything)
        if not user_message or not user_message.strip():
            return error_response('Message is required', 400)

        # Gap #6: Audit log — request start (PII-safe)
        audit_request_start(farmer_id, session_id, pii_safe_msg)
        logger.info(f"Query from farmer {farmer_id}: {pii_safe_msg}")

        # --- Step 1: Detect language & translate to English ---
        detection = detect_and_translate(user_message, target_language='en')
        detected_lang = _resolve_reply_language(
            effective_preferred_language,
            detection.get('detected_language', 'en'),
            user_message,
        )
        english_message = _normalize_translated_agri_terms(
            detection.get('translated_text', user_message)
        )
        # Keep a clean copy of the English translation (before farmer context prefix)
        # for storing in chat history and cache key building
        _clean_english_msg = english_message
        intents = _classify_intents(english_message, original_message=user_message)

        # If user speaks in an Indic language but no specific intents detected,
        # default to 'crop' (most common farmer query) so it gets routed to a tool
        # Check if this is a generic/educational query
        _query_is_generic = _is_generic_query(english_message)

        if not intents and _contains_indic_chars(user_message):
            if _query_is_generic:
                logger.info("Indic generic query — answering without tool routing")
                intents = ['general']
            else:
                logger.info("Indic-language query with no detected intents — defaulting to 'crop' intent")
                intents = ['crop']

        on_topic = _is_on_topic_query(english_message) or _is_on_topic_query(user_message)
        if ENFORCE_CODE_POLICY and not on_topic:
            policy_reply_en = _off_topic_response()
            translated_policy_reply = (
                translate_response(policy_reply_en, 'en', detected_lang)
                if detected_lang and detected_lang != 'en'
                else policy_reply_en
            )
            translated_policy_reply = _strip_local_markdown_symbols(translated_policy_reply, detected_lang)

            audio_url = None
            audio_key = None
            polly_text_truncated = False
            try:
                polly_result = text_to_speech(
                    translated_policy_reply,
                    detected_lang or 'en',
                    return_metadata=True,
                )
                if isinstance(polly_result, dict):
                    audio_url = polly_result.get('audio_url')
                    audio_key = polly_result.get('audio_key')
                    polly_text_truncated = bool(polly_result.get('truncated', False))
                else:
                    audio_url = polly_result
            except Exception as polly_err:
                logger.warning(f"Polly audio failed (non-fatal): {polly_err}")

            save_chat_messages_batch([
                {
                    'session_id': session_id,
                    'role': 'user',
                    'message': user_message,
                    'language': detected_lang,
                    'message_en': _clean_english_msg if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:policy:user" if idempotency_token else None,
                },
                {
                    'session_id': session_id,
                    'role': 'assistant',
                    'message': translated_policy_reply,
                    'language': detected_lang,
                    'message_en': policy_reply_en if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:policy:assistant" if idempotency_token else None,
                },
            ])

            return success_response({
                'reply': translated_policy_reply,
                'reply_en': policy_reply_en,
                'detected_language': detected_lang,
                'tools_used': [],
                'audio_url': audio_url,
                'audio_key': audio_key,
                'polly_text_truncated': polly_text_truncated,
                'session_id': session_id,
                'mode': 'bedrock-direct',
                'policy': {
                    'code_policy_enforced': True,
                    'off_topic_blocked': True,
                    'grounding_required': False,
                    'grounding_satisfied': True,
                },
            }, message='Policy-safe advisory generated', language=detected_lang)

        # --- Step 2: Enrich with farmer profile (optional) ---
        farmer_context = None
        if profile:
            farmer_context = {
                'name': profile.get('name', ''),
                'state': profile.get('state', ''),
                'crops': profile.get('crops', []),
                'soil_type': profile.get('soil_type', ''),
                'district': profile.get('district', ''),
            }
            # GPS location priority: GPS > profile district > profile state
            # If frontend sent GPS-detected location, inject as the primary location
            if gps_location:
                farmer_context['gps_location'] = gps_location
                logger.info(f"GPS location from frontend: {gps_location}")
            if gps_coords:
                farmer_context['gps_lat'] = gps_coords.get('lat')
                farmer_context['gps_lng'] = gps_coords.get('lng')

            # Build context prefix — use GPS location if available, else profile district/state
            active_location = gps_location or farmer_context['district'] or farmer_context['state']
            if _query_is_generic:
                logger.info("Generic query detected — NOT injecting farmer profile into prompt")
                # Keep farmer_context available for tools but don't prepend to message
            else:
                context_prefix = (
                    f"[Farmer context: {farmer_context['name']}, "
                    f"Location={active_location}, State={farmer_context['state']}, "
                    f"Crops={farmer_context['crops']}, Soil={farmer_context['soil_type']}] "
                )
                english_message = context_prefix + english_message
                logger.info("Specific query — injected farmer profile into prompt")
        elif gps_location:
            # No profile but we have GPS — create minimal context
            farmer_context = {
                'name': '', 'state': '', 'crops': [], 'soil_type': '', 'district': '',
                'gps_location': gps_location,
            }
            if gps_coords:
                farmer_context['gps_lat'] = gps_coords.get('lat')
                farmer_context['gps_lng'] = gps_coords.get('lng')
            context_prefix = f"[Farmer GPS location: {gps_location}] "
            english_message = context_prefix + english_message
            logger.info(f"GPS location (no profile): {gps_location}")

        # For open-ended crop suitability queries, do not bias with stored profile crops.
        # Keep location/soil context, but remove crops from model/tool context.
        model_farmer_context = farmer_context
        _is_open_crop_query = _is_open_crop_recommendation_query(_clean_english_msg)
        _is_specific_profile_crop_query = _is_profile_crop_specific_query(_clean_english_msg)
        if _query_is_generic:
            model_farmer_context = None
            logger.info("Generic query — removed farmer context from model invocation")
        elif _is_open_crop_query and not _is_specific_profile_crop_query and farmer_context:
            model_farmer_context = dict(farmer_context)
            model_farmer_context['crops'] = []
            logger.info("Open crop recommendation query — removed profile crops from model context")
        elif _is_specific_profile_crop_query and farmer_context:
            logger.info("Specific profile-crop query — retaining profile crops in model context")

        # --- Step 2b: Greeting shortcut (skip Bedrock call for "hi", "hello", etc.) ---
        _raw_en = detection.get('translated_text', user_message)
        if _is_greeting_or_chitchat(_raw_en) and not intents:
            logger.info(f"Greeting shortcut: '{_raw_en}' — skipping pipeline")
            result_text = _greeting_response(farmer_context)
            tools_used = []
            policy_meta = {
                'code_policy_enforced': True,
                'off_topic_blocked': False,
                'grounding_required': False,
                'grounding_satisfied': True,
                'greeting_shortcut': True,
            }

            # Translate if needed
            if detected_lang and detected_lang != 'en':
                translated_reply = translate_response(result_text, 'en', detected_lang)
            else:
                translated_reply = result_text
            translated_reply = _strip_local_markdown_symbols(translated_reply, detected_lang)

            # Quick TTS
            audio_url = None
            audio_key = None
            audio_pending = False
            polly_text_truncated = False
            _lang = detected_lang or 'en'
            if _lang not in ('en', 'hi'):
                audio_pending = True
            else:
                try:
                    polly_result = text_to_speech(translated_reply, _lang, return_metadata=True)
                    if isinstance(polly_result, dict):
                        audio_url = polly_result.get('audio_url')
                        audio_key = polly_result.get('audio_key')
                        polly_text_truncated = bool(polly_result.get('truncated', False))
                    else:
                        audio_url = polly_result
                except Exception as polly_err:
                    logger.warning(f"Polly audio failed (non-fatal): {polly_err}")

            save_chat_messages_batch([
                {
                    'session_id': session_id,
                    'role': 'user',
                    'message': user_message,
                    'language': detected_lang,
                    'farmer_id': farmer_id,
                    'message_en': _clean_english_msg if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:greet:user" if idempotency_token else None,
                },
                {
                    'session_id': session_id,
                    'role': 'assistant',
                    'message': translated_reply,
                    'language': detected_lang,
                    'farmer_id': farmer_id,
                    'message_en': result_text if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:greet:assistant" if idempotency_token else None,
                },
            ])

            _total_elapsed = _time.time() - _t_start
            logger.info(f'Greeting shortcut completed in {_total_elapsed:.1f}s')
            audit_request_complete(
                farmer_id=farmer_id, session_id=session_id,
                tools_used=[], pipeline_mode='greeting',
                response_length=len(translated_reply), elapsed_seconds=_total_elapsed,
                bedrock_guardrail_triggered=False,
            )
            return success_response({
                'reply': translated_reply,
                'reply_en': result_text,
                'detected_language': detected_lang,
                'tools_used': [],
                'sources': None,
                'audio_url': audio_url,
                'audio_key': audio_key,
                'audio_pending': audio_pending,
                'polly_text_truncated': polly_text_truncated,
                'session_id': session_id,
                'mode': 'bedrock-direct',
                'pipeline_mode': 'greeting',
                'policy': policy_meta,
            }, message='Greeting response', language=detected_lang)

        # --- Step 3: Invoke AI Agent ---
        pipeline_meta_extra = {}

        # ══════ RESPONSE CACHE CHECK ══════
        # If the same query (normalized) was answered recently, return cached result instantly.
        # Cache key = hash(query + location + crop + season). TTL varies by category.
        _fc = farmer_context or {}
        _cache_location = _fc.get('gps_location') or _fc.get('district') or _fc.get('state') or ''
        _cache_crop = (_fc.get('crops') or [''])[0] if isinstance(_fc.get('crops'), list) else str(_fc.get('crops', ''))
        _raw_en_for_cache = detection.get('translated_text', user_message)

        cached = get_cached_response(_raw_en_for_cache, _cache_location, _cache_crop, intents=intents) if not _query_is_generic else None
        if cached:
            logger.info(f"CACHE HIT — returning cached response (key={cached.get('_cache_key')})")
            # Use cached English reply
            result_text_en = cached.get('reply_en', '')
            cached_tools = cached.get('tools_used', [])
            cached_sources = cached.get('sources')

            # Translate if needed
            if detected_lang and detected_lang != 'en':
                translated_reply, _cache_localization_mode = _localize_response_hybrid(result_text_en, detected_lang)
                # Defensive: strip any leftover HTML artifacts from translation
                translated_reply = re.sub(r'</?span[^>]*>', '', translated_reply, flags=re.IGNORECASE)
            else:
                translated_reply = result_text_en
                _cache_localization_mode = 'en'
            translated_reply = _strip_local_markdown_symbols(translated_reply, detected_lang)

            # TTS
            audio_url = None
            audio_key = None
            audio_pending = False
            polly_text_truncated = False
            _lang = detected_lang or 'en'
            if _lang not in ('en', 'hi'):
                audio_pending = True
            else:
                _elapsed_cache = _time.time() - _t_start
                if _elapsed_cache < TTS_TIME_BUDGET_SEC:
                    try:
                        polly_result = text_to_speech(translated_reply, _lang, return_metadata=True)
                        if isinstance(polly_result, dict):
                            audio_url = polly_result.get('audio_url')
                            audio_key = polly_result.get('audio_key')
                            polly_text_truncated = bool(polly_result.get('truncated', False))
                        else:
                            audio_url = polly_result
                    except Exception as polly_err:
                        logger.warning(f"Polly TTS failed (cached, non-fatal): {polly_err}")

            save_chat_messages_batch([
                {
                    'session_id': session_id,
                    'role': 'user',
                    'message': user_message,
                    'language': detected_lang,
                    'farmer_id': farmer_id,
                    'message_en': _raw_en_for_cache if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:cache:user" if idempotency_token else None,
                },
                {
                    'session_id': session_id,
                    'role': 'assistant',
                    'message': translated_reply,
                    'language': detected_lang,
                    'farmer_id': farmer_id,
                    'message_en': result_text_en if detected_lang != 'en' else None,
                    'idempotency_token': f"{idempotency_token}:cache:assistant" if idempotency_token else None,
                },
            ])

            _total_elapsed = _time.time() - _t_start
            logger.info(f'Cache hit response in {_total_elapsed:.1f}s')
            audit_request_complete(
                farmer_id=farmer_id, session_id=session_id,
                tools_used=cached_tools, pipeline_mode='cache_hit',
                response_length=len(translated_reply), elapsed_seconds=_total_elapsed,
                bedrock_guardrail_triggered=False,
            )
            return success_response({
                'reply': translated_reply,
                'reply_en': result_text_en,
                'detected_language': detected_lang,
                'tools_used': cached_tools,
                'sources': cached_sources,
                'audio_url': audio_url,
                'audio_key': audio_key,
                'audio_pending': audio_pending,
                'polly_text_truncated': polly_text_truncated,
                'session_id': session_id,
                'mode': 'bedrock-direct',
                'pipeline_mode': 'cache_hit',
                'localization_mode': _cache_localization_mode,
                'policy': {
                    'code_policy_enforced': True,
                    'off_topic_blocked': False,
                    'grounding_required': False,
                    'grounding_satisfied': True,
                    'cache_hit': True,
                },
            }, message='Cached advisory', language=detected_lang)

        # Save user message EARLY (before Bedrock) — prevents data loss on timeout
        save_chat_message(session_id, 'user', user_message, detected_lang, farmer_id=farmer_id,
                message_en=_raw_en_for_cache if detected_lang != 'en' else None,
                idempotency_token=f"{idempotency_token}:user:early" if idempotency_token else None)

        # Retrieve conversation history for follow-up context (chat pages only, not feature pages)
        chat_history = []
        if not _is_feature_page:
            chat_history = _build_conversation_history_context(session_id, limit=40)
            if chat_history:
                logger.info(f"Loaded {len(chat_history)} prior messages for conversation memory")

        if _is_feature_page:
            # FAST PATH: feature pages use single direct Bedrock call
            # skip_native_guardrail=True because these prompts are code-generated
            # (not raw user text) and already passed application-level guardrails.
            logger.info(f'FAST PATH for feature page (elapsed {_time.time()-_t_start:.1f}s)')
            
            # Check timeout before expensive Bedrock operation
            is_approaching, remaining_ms = _check_timeout_approaching(context)
            if is_approaching:
                logger.warning(f"Timeout approaching: {remaining_ms}ms remaining, returning fallback")
                return _timeout_http_response(session_id, detected_lang)
            
            routed_prompt = _build_tool_first_prompt(english_message, intents, farmer_context)
            result_text, tools_used, tool_data_log, _gr_intervened = _invoke_bedrock_direct(
                routed_prompt, model_farmer_context, skip_native_guardrail=True, lambda_context=context
            )

        else:
            # Standard chat: direct Bedrock converse() with tool routing
            logger.info(f"Direct Bedrock converse() | intents={intents}")
            
            # Check timeout before expensive Bedrock operation
            is_approaching, remaining_ms = _check_timeout_approaching(context)
            if is_approaching:
                logger.warning(f"Timeout approaching: {remaining_ms}ms remaining, returning fallback")
                return _timeout_http_response(session_id, detected_lang)
            
            routed_prompt = _build_tool_first_prompt(
                english_message,
                intents,
                model_farmer_context,
            )
            result_text, tools_used, tool_data_log, _gr_intervened = _invoke_bedrock_direct(
                routed_prompt, model_farmer_context, chat_history=chat_history, lambda_context=context
            )

        # Clean up model thinking tags (Claude emits <thinking>...</thinking>)
        result_text = re.sub(r'<thinking>.*?</thinking>\s*', '', result_text, flags=re.DOTALL)
        result_text = result_text.strip()

        # Audit: log each tool invoked during this request
        for _tn in tools_used:
            audit_tool_invocation(_tn, farmer_id, session_id, success=True)

        # Guard: if agent returned garbled/empty content, provide a fallback
        # Remove punctuation/spaces and check if any real text remains
        _stripped = re.sub(r'[\s\(\)\,\.\?\!\;\:\-\[\]\{\}\"\']+', '', result_text)
        if len(_stripped) < 10:
            logger.warning(f"Agent returned near-empty/garbled response: {repr(result_text[:100])}")
            result_text = (
                "I couldn't get a complete answer right now. "
                "Please share more details like your crop, location, and season so I can help better."
            )
            tools_used = []

        if _is_feature_page:
            # Feature pages (soil-analysis, crop-recommend, farm-calendar) send
            # self-contained prompts with all context embedded — never replace
            # the model response with a grounding prompt asking for more data.
            policy_meta = {
                'code_policy_enforced': True,
                'off_topic_blocked': False,
                'grounding_required': False,
                'grounding_satisfied': True,
                'feature_page': True,
            }
        else:
            result_text, tools_used, policy_meta = _apply_code_policy(
                english_message,
                intents,
                result_text,
                tools_used,
                original_query=user_message,
                farmer_context=farmer_context,
                is_generic=_query_is_generic,
            )

        # Gap #6: Audit policy decision
        audit_policy_decision(farmer_id, session_id, policy_meta)

        # Post-process: remove any "only rice and wheat" limitation language
        result_text = _post_process_response(result_text)
        result_text = _apply_strict_soil_response_guard(
            result_text,
            english_message,
            farmer_context=farmer_context,
            tool_data_log=tool_data_log,
        )
        result_text = _apply_tool_signal_response_guard(
            result_text,
            english_message,
            tools_used=tools_used,
            tool_data_log=tool_data_log,
        )
        result_text = _normalize_output_markdown(result_text)
        result_text = _ensure_cautious_pest_response(result_text, tools_used, _raw_en_for_cache)

        logger.info(f"Agent response: {mask_pii_in_log(result_text[:200])}... tools={tools_used}")

        # --- Step 4: Translate response to farmer's language ---
        # Strip sources line BEFORE translation so function names don't get garbled
        text_for_translation, _ = _strip_sources_line(result_text)
        sources_line = _build_sources_line(tools_used)

        if detected_lang and detected_lang != 'en':
            translated_reply, localization_mode = _localize_response_hybrid(text_for_translation, detected_lang)
            # Defensive: strip any leftover HTML artifacts from translation
            translated_reply = re.sub(r'</?span[^>]*>', '', translated_reply, flags=re.IGNORECASE)
        else:
            translated_reply = text_for_translation
            localization_mode = 'en'
        translated_reply = _strip_local_markdown_symbols(translated_reply, detected_lang)

        # Re-append sources in English AFTER translation only to reply_en (debug)
        # Do NOT append sources to translated_reply — frontend shows sources separately
        if sources_line:
            result_text = f"{text_for_translation}\n\nSources: {sources_line}"

        # ══════ CACHE STORE (fire-and-forget) ══════
        # Store the English response for future cache hits on similar queries.
        try:
            cache_response(
                _raw_en_for_cache, _cache_location, _cache_crop, None,
                {
                    'reply_en': text_for_translation,
                    'tools_used': tools_used,
                    'sources': sources_line,
                },
                intents=intents,
            )
        except Exception as _cache_err:
            logger.warning(f"Cache store failed (non-fatal): {_cache_err}")

        # --- Step 4b: Output guardrails (PII leakage, prompt leakage, length cap) ---
        output_guard = run_output_guardrails(translated_reply, context={
            'farmer_id': farmer_id, 'session_id': session_id,
        })
        if output_guard['modified']:
            translated_reply = output_guard['text']
            logger.info(
                f"Output guardrail applied | pii={output_guard['pii_masked']} "
                f"prompt_leak={output_guard['prompt_leaked']} truncated={output_guard['truncated']}"
            )

        # --- Step 5: Generate TTS audio ---
        # Polly (en/hi) is fast (~1-2s) → generate inline.
        # gTTS (ta/te/kn/...) is slow (~15-25s) → defer to async call from frontend.
        _elapsed = _time.time() - _t_start
        audio_url = None
        audio_key = None
        audio_pending = False
        polly_text_truncated = False

        _lang = detected_lang or 'en'
        _needs_gtts = _lang not in ('en', 'hi')

        if _needs_gtts:
            # Defer gTTS to a separate frontend call — return text immediately
            audio_pending = True
            logger.info(f'Deferring gTTS({_lang}) to async call — elapsed {_elapsed:.1f}s')
        elif _elapsed > TTS_TIME_BUDGET_SEC:
            logger.warning(f'Skipping Polly TTS - elapsed {_elapsed:.1f}s > {TTS_TIME_BUDGET_SEC}s budget')
        else:
            try:
                polly_result = text_to_speech(
                    translated_reply,
                    _lang,
                    return_metadata=True,
                )
                if isinstance(polly_result, dict):
                    audio_url = polly_result.get('audio_url')
                    audio_key = polly_result.get('audio_key')
                    polly_text_truncated = bool(polly_result.get('truncated', False))
                else:
                    audio_url = polly_result
                logger.info(f'Polly TTS completed in {_time.time()-_t_start-_elapsed:.1f}s, audio={bool(audio_url)}')
            except Exception as polly_err:
                logger.warning(f"Polly audio failed (non-fatal): {polly_err}")

        # --- Step 6: Save chat history ---
        # User message was already saved before Step 3 (early save for durability)
        save_chat_message(session_id, 'assistant', translated_reply, detected_lang, farmer_id=farmer_id,
                message_en=text_for_translation if detected_lang != 'en' else None,
                idempotency_token=f"{idempotency_token}:assistant:final" if idempotency_token else None)

        # --- Step 7: Return response (matches API contract) ---
        _total_elapsed = _time.time() - _t_start
        logger.info(f'Total handler time: {_total_elapsed:.1f}s | feature_page={_is_feature_page} | audio={bool(audio_url)}')

        # Gap #6: Audit request completion
        if _gr_intervened:
            audit_bedrock_guardrail(farmer_id, session_id, 'output_blocked')
        audit_request_complete(
            farmer_id=farmer_id,
            session_id=session_id,
            tools_used=tools_used,
            pipeline_mode='direct' if not _is_feature_page else 'fast_path',
            response_length=len(translated_reply or ''),
            elapsed_seconds=_total_elapsed,
            bedrock_guardrail_triggered=_gr_intervened,
            output_guardrail=output_guard if output_guard.get('modified') else None,
        )

        return success_response({
            'reply': translated_reply,
            'reply_en': result_text,
            'detected_language': detected_lang,
            'tools_used': tools_used,
            'sources': sources_line or None,
            'audio_url': audio_url,
            'audio_key': audio_key,
            'audio_pending': audio_pending,
            'polly_text_truncated': polly_text_truncated,
            'session_id': session_id,
            'mode': 'bedrock-direct',
            'localization_mode': localization_mode,
            'pipeline_mode': 'direct',
            'pipeline': pipeline_meta_extra if pipeline_meta_extra else None,
            'policy': policy_meta,
        }, message='Advisory generated successfully', language=detected_lang)

    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return error_response('An internal error occurred. Please try again.', 500)
