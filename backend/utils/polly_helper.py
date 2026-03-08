# backend/utils/polly_helper.py
# Amazon Polly text-to-speech helper
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 11

import boto3
import os
import uuid
import io
import re
import time
import random
import logging
from botocore.config import Config

logger = logging.getLogger()

ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None
polly = boto3.client('polly', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('polly')
s3 = boto3.client('s3', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('s3')

S3_BUCKET = os.environ.get('S3_KNOWLEDGE_BUCKET', 'smart-rural-ai-knowledge-base')

LANGUAGE_ALIASES = {
    'en-in': 'en',
    'en-us': 'en',
    'hi-in': 'hi',
    'ta-in': 'ta',
    'te-in': 'te',
    'kn-in': 'kn',
    'ml-in': 'ml',
    'mr-in': 'mr',
    'bn-in': 'bn',
    'gu-in': 'gu',
    'pa-in': 'pa',
    'or-in': 'or',
    'as-in': 'as',
    'ur-in': 'ur',
}

# Language → Polly voice mapping
# Polly has Hindi + English (Indian) neural voices.
# Tamil/Telugu fall back to Hindi voice (Kajal).
VOICE_MAP = {
    'en': 'Kajal',    # English Indian Neural
    'hi': 'Kajal',    # Hindi Neural
}

# Language code for Polly (LanguageCode parameter)
POLLY_LANG_MAP = {
    'en': 'en-IN',
    'hi': 'hi-IN',
}

POLLY_NATIVE_LANGS = {'en', 'hi'}

# gTTS: free Google Translate TTS – supports ta, te, kn, ml, mr, bn, gu, pa etc.
# No API key needed. Used as primary path for non-Polly languages.
GTTS_SUPPORTED_LANGS = {'ta', 'te', 'kn', 'ml', 'mr', 'bn', 'gu', 'pa', 'or', 'as', 'ur'}
USE_GTTS = os.environ.get('USE_GTTS', 'true').lower() == 'true'
GTTS_RETRY_ATTEMPTS = max(1, int(os.environ.get('GTTS_RETRY_ATTEMPTS', '3')))
GTTS_RETRY_BACKOFF_SEC = float(os.environ.get('GTTS_RETRY_BACKOFF_SEC', '0.6'))
ENABLE_GTTS_EXPONENTIAL_BACKOFF = os.environ.get('ENABLE_GTTS_EXPONENTIAL_BACKOFF', 'false').lower() == 'true'
ENABLE_EXTENDED_AUDIO_EXPIRY = os.environ.get('ENABLE_EXTENDED_AUDIO_EXPIRY', 'false').lower() == 'true'
ENABLE_VOICE_VALIDATION = os.environ.get('ENABLE_VOICE_VALIDATION', 'false').lower() == 'true'
ENABLE_S3_VALIDATION = os.environ.get('ENABLE_S3_VALIDATION', 'false').lower() == 'true'
ENABLE_TTS_LIST_FORMATTING = os.environ.get('ENABLE_TTS_LIST_FORMATTING', 'false').lower() == 'true'

if ENABLE_S3_VALIDATION:
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        logger.info(f"S3 bucket validated for Polly audio uploads: {S3_BUCKET}")
    except Exception as bucket_err:
        logger.warning(f"S3 bucket validation failed for '{S3_BUCKET}': {bucket_err}")


def normalize_language_code(language_code, default='en'):
    normalized = (language_code or '').strip().lower().replace('_', '-')
    if not normalized:
        return default
    return LANGUAGE_ALIASES.get(normalized, normalized)

MAX_POLLY_TEXT_LENGTH = 2800


def _strip_markdown_for_tts(text):
    """Remove markdown formatting, emojis, and special chars that TTS reads aloud."""
    if not text:
        return text
    s = text
    # Remove markdown headings: ### heading → heading
    s = re.sub(r'^#{1,6}\s*', '', s, flags=re.MULTILINE)
    # Remove bold: **text** → text
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    # Remove italic: *text* → text
    s = re.sub(r'\*(.+?)\*', r'\1', s)
    # Remove bullet markers at start of line: - item or • item → item
    s = re.sub(r'^[\s]*[\-•]\s+', '', s, flags=re.MULTILINE)
    if os.environ.get('ENABLE_TTS_LIST_FORMATTING', 'false').lower() == 'true':
        has_indic_script = bool(re.search(r'[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F]', s))
        ordinals = {
            '1': 'First, ',
            '2': 'Second, ',
            '3': 'Third, ',
            '4': 'Fourth, ',
            '5': 'Fifth, ',
        }

        def _replace_numbered(match):
            number = match.group(1)
            if has_indic_script:
                return f"{number}. "
            return ordinals.get(number, f"Point {number}, ")

        s = re.sub(r'^(\d+)\.\s+', _replace_numbered, s, flags=re.MULTILINE)
    else:
        s = re.sub(r'^\d+\.\s+', '', s, flags=re.MULTILINE)
    # Remove common emojis (Unicode blocks for emoji)
    s = re.sub(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', '', s)
    # Remove other special chars: |, ~, `, >, ===
    s = re.sub(r'[\|~`>]', '', s)
    s = re.sub(r'={3,}', '', s)
    s = re.sub(r'-{3,}', '', s)
    # Collapse multiple newlines/spaces
    s = re.sub(r'\n{3,}', '\n\n', s)
    s = re.sub(r'  +', ' ', s)
    return s.strip()


def _truncate_text(text, max_length):
    """Truncate text to max_length, breaking at a word boundary."""
    normalized = (text or '').strip()
    if len(normalized) <= max_length:
        return normalized
    truncated = normalized[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > int(max_length * 0.7):
        truncated = truncated[:last_space]
    return f"{truncated}..."


def _prepare_text_for_tts(text, max_length=MAX_POLLY_TEXT_LENGTH):
    """Strip markdown and truncate for TTS."""
    cleaned = _strip_markdown_for_tts(text)
    return _truncate_text(cleaned, max_length)


def _upload_audio_bytes(audio_bytes):
    audio_key = f"audio/{uuid.uuid4()}.mp3"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=audio_key,
        Body=audio_bytes,
        ContentType='audio/mpeg'
    )

    expiry_seconds = 7200 if os.environ.get('ENABLE_EXTENDED_AUDIO_EXPIRY', 'false').lower() == 'true' else 3600
    presigned = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': S3_BUCKET, 'Key': audio_key},
        ExpiresIn=expiry_seconds
    )
    return {'url': presigned, 'key': audio_key}


def refresh_audio_url(audio_key):
    """Generate a fresh presigned URL for an existing audio file."""
    if not audio_key or not audio_key.startswith('audio/'):
        return None
    try:
        # Verify the file exists
        s3.head_object(Bucket=S3_BUCKET, Key=audio_key)
        expiry_seconds = 7200 if os.environ.get('ENABLE_EXTENDED_AUDIO_EXPIRY', 'false').lower() == 'true' else 3600
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': audio_key},
            ExpiresIn=expiry_seconds
        )
    except Exception:
        return None


def _polly_tts(safe_text, language_code, voice_id=None):
    selected_voice = voice_id or VOICE_MAP.get(language_code, 'Kajal')
    if os.environ.get('ENABLE_VOICE_VALIDATION', 'false').lower() == 'true' and voice_id and voice_id not in VOICE_MAP.values():
        logger.warning(f"Invalid voice_id '{voice_id}' received; using mapped/default voice")
        selected_voice = VOICE_MAP.get(language_code, 'Kajal')
    response = polly.synthesize_speech(
        Text=safe_text,
        OutputFormat='mp3',
        VoiceId=selected_voice,
        Engine='neural',
        LanguageCode=POLLY_LANG_MAP.get(language_code, 'en-IN')
    )
    return _upload_audio_bytes(response['AudioStream'].read())


def _gtts_tts(safe_text, language_code):
    """Free Google Translate TTS. No API key. Supports all major Indian languages."""
    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError('gTTS not installed in Lambda package')

    last_error = None
    for attempt in range(1, GTTS_RETRY_ATTEMPTS + 1):
        try:
            print(f'gTTS: {len(safe_text)} chars for lang={language_code}, attempt={attempt}/{GTTS_RETRY_ATTEMPTS}')
            tts = gTTS(text=safe_text, lang=language_code, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return _upload_audio_bytes(buf.read())
        except Exception as err:
            last_error = err
            if attempt < GTTS_RETRY_ATTEMPTS:
                if os.environ.get('ENABLE_GTTS_EXPONENTIAL_BACKOFF', 'false').lower() == 'true':
                    delay = GTTS_RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
                    jitter = delay * random.uniform(-0.25, 0.25)
                    time.sleep(max(0.1, delay + jitter))
                else:
                    time.sleep(GTTS_RETRY_BACKOFF_SEC * attempt)

    raise RuntimeError(f'gTTS failed after {GTTS_RETRY_ATTEMPTS} attempts: {last_error}')


def text_to_speech(text, language_code='en', voice_id=None, return_metadata=False):
    """
    Convert text to speech using Amazon Polly or gTTS.

    Args:
        text: The text to convert
        language_code: 'en' for English, 'hi' for Hindi, 'ta' for Tamil
        voice_id: Specific Polly voice (auto-selected if None)
        return_metadata: If True, returns {'audio_url': ..., 'audio_key': ..., 'truncated': ...}

    Returns:
        Presigned S3 URL (default), or metadata dict if return_metadata=True
    """
    language_code = normalize_language_code(language_code, default='en')

    safe_text = _prepare_text_for_tts(text)
    was_truncated = (text or '').strip() != safe_text
    if not safe_text:
        if return_metadata:
            return {'audio_url': None, 'audio_key': None, 'truncated': False}
        return None

    tts_error = None

    try:
        result = None  # will be {'url': ..., 'key': ...} or None

        if language_code in POLLY_NATIVE_LANGS:
            result = _polly_tts(safe_text, language_code, voice_id=voice_id)
        elif language_code in GTTS_SUPPORTED_LANGS:
            if USE_GTTS:
                # gTTS has built-in retry logic - let it raise exception if all retries fail
                result = _gtts_tts(safe_text, language_code)
            else:
                tts_error = f"gTTS disabled by USE_GTTS for language={language_code}"
                logger.warning(tts_error)
        else:
            tts_error = f"No TTS engine configured for language={language_code}"
            logger.warning(tts_error)


        # Unpack result — _upload_audio_bytes now returns {'url': ..., 'key': ...}
        audio_url = None
        audio_key = None
        
        if result:
            if isinstance(result, dict):
                audio_url = result.get('url')
                audio_key = result.get('key')
            else:
                audio_url = result
                audio_key = None

        if not audio_url and not tts_error:
            tts_error = f"TTS produced no audio for language={language_code}"

        if return_metadata:
            return {
                'audio_url': audio_url,
                'audio_key': audio_key,
                'truncated': was_truncated,
                'error': tts_error,
            }
        return audio_url

    except Exception as e:
        # Only catch unexpected errors - gTTS/Polly errors should propagate
        logger.error(f"TTS fatal error: {e}")
        if return_metadata:
            return {
                'audio_url': None,
                'audio_key': None,
                'truncated': was_truncated,
                'error': str(e),
            }
        # Re-raise the exception so caller knows TTS failed
        raise
