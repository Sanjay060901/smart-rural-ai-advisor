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
import unicodedata
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None
polly = boto3.client('polly', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('polly')
s3 = boto3.client('s3', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('s3')
cloudwatch = boto3.client('cloudwatch', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('cloudwatch')

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

# Feature flags for reliability improvements (default: OFF)
ENABLE_GTTS_EXPONENTIAL_BACKOFF = os.environ.get('ENABLE_GTTS_EXPONENTIAL_BACKOFF', 'false').lower() == 'true'
ENABLE_EXTENDED_AUDIO_EXPIRY = os.environ.get('ENABLE_EXTENDED_AUDIO_EXPIRY', 'false').lower() == 'true'
ENABLE_VOICE_VALIDATION = os.environ.get('ENABLE_VOICE_VALIDATION', 'false').lower() == 'true'
ENABLE_S3_VALIDATION = os.environ.get('ENABLE_S3_VALIDATION', 'false').lower() == 'true'
ENABLE_TTS_LIST_FORMATTING = os.environ.get('ENABLE_TTS_LIST_FORMATTING', 'false').lower() == 'true'
ENABLE_GTTS_DEPENDENCY_CHECK = os.environ.get('ENABLE_GTTS_DEPENDENCY_CHECK', 'true').lower() == 'true'

_gtts_dependency_ok = None


def _emit_gtts_dependency_metric(is_missing):
    try:
        cloudwatch.put_metric_data(
            Namespace='SmartRuralAI/TTS',
            MetricData=[
                {
                    'MetricName': 'GTTSDependencyMissing',
                    'Dimensions': [
                        {
                            'Name': 'FunctionName',
                            'Value': os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown'),
                        }
                    ],
                    'Value': 1.0 if is_missing else 0.0,
                    'Unit': 'Count',
                }
            ],
        )
    except Exception as metric_err:
        logger.warning(f"Unable to publish gTTS dependency metric: {metric_err}")


def _validate_gtts_dependency_once():
    global _gtts_dependency_ok

    if _gtts_dependency_ok is not None:
        return _gtts_dependency_ok

    if not USE_GTTS or not ENABLE_GTTS_DEPENDENCY_CHECK:
        _gtts_dependency_ok = True
        return _gtts_dependency_ok

    try:
        from gtts import gTTS as _gTTS  # noqa: F401
        _gtts_dependency_ok = True
        _emit_gtts_dependency_metric(is_missing=False)
        return _gtts_dependency_ok
    except Exception as dep_err:
        _gtts_dependency_ok = False
        logger.error(f"gTTS dependency check failed at startup: {dep_err}")
        _emit_gtts_dependency_metric(is_missing=True)
        return _gtts_dependency_ok


_validate_gtts_dependency_once()

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

POLLY_CHUNK_MAX_CHARS = max(500, int(os.environ.get('POLLY_CHUNK_MAX_CHARS', '2400')))
GTTS_CHUNK_MAX_CHARS = max(300, int(os.environ.get('GTTS_CHUNK_MAX_CHARS', '900')))


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
        ordinals = {
            '1': 'First, ',
            '2': 'Second, ',
            '3': 'Third, ',
            '4': 'Fourth, ',
            '5': 'Fifth, ',
        }

        def _replace_numbered(match):
            number = match.group(1)
            return ordinals.get(number, f"Point {number}, ")

        s = re.sub(r'^(\d+)\.\s+', _replace_numbered, s, flags=re.MULTILINE)
    else:
        # Remove numbered list prefixes that look odd in speech: "1. " → ""
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


def _prepare_text_for_tts(text):
    """Strip markdown for TTS without truncating content."""
    cleaned = _strip_markdown_for_tts(text)
    cleaned = unicodedata.normalize('NFC', cleaned)
    return cleaned


def _split_text_for_tts(text, chunk_max_chars):
    """Split text into chunks without dropping content."""
    normalized = (text or '').strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_max_chars:
        return [normalized]

    chunks = []
    current = ''

    def _flush_current():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ''

    paragraphs = [p.strip() for p in re.split(r'\n+', normalized) if p.strip()]
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_max_chars:
            candidate = f"{current}\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= chunk_max_chars:
                current = candidate
            else:
                _flush_current()
                current = paragraph
            continue

        sentences = [s.strip() for s in re.split(r'(?<=[\.!\?\u0964\u0965])\s+', paragraph) if s.strip()]
        for sentence in sentences:
            if len(sentence) <= chunk_max_chars:
                candidate = f"{current} {sentence}".strip() if current else sentence
                if len(candidate) <= chunk_max_chars:
                    current = candidate
                else:
                    _flush_current()
                    current = sentence
                continue

            words = sentence.split(' ')
            for word in words:
                if not word:
                    continue
                if len(word) > chunk_max_chars:
                    _flush_current()
                    start = 0
                    while start < len(word):
                        chunks.append(word[start:start + chunk_max_chars])
                        start += chunk_max_chars
                    continue

                candidate = f"{current} {word}".strip() if current else word
                if len(candidate) <= chunk_max_chars:
                    current = candidate
                else:
                    _flush_current()
                    current = word

        _flush_current()

    _flush_current()
    return chunks


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
    chunks = _split_text_for_tts(safe_text, POLLY_CHUNK_MAX_CHARS)
    total_chunks = len(chunks)
    if total_chunks > 1:
        logger.info(f'Polly chunking enabled: total_chunks={total_chunks}, total_chars={len(safe_text)}')

    merged_audio = io.BytesIO()
    for idx, chunk in enumerate(chunks, 1):
        logger.info(f'Polly request: chunk={idx}/{total_chunks}, chars={len(chunk)}, lang={language_code}')
        response = polly.synthesize_speech(
            Text=chunk,
            OutputFormat='mp3',
            VoiceId=selected_voice,
            Engine='neural',
            LanguageCode=POLLY_LANG_MAP.get(language_code, 'en-IN')
        )
        merged_audio.write(response['AudioStream'].read())

    return _upload_audio_bytes(merged_audio.getvalue())


def _gtts_tts_chunk(chunk_text, language_code, chunk_index=1, total_chunks=1):
    """Generate one gTTS MP3 chunk with retry."""
    if not _validate_gtts_dependency_once():
        raise RuntimeError('gTTS dependency missing in Lambda package; redeploy with SAM build')

    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError('gTTS not installed in Lambda package')

    last_error = None
    for attempt in range(1, GTTS_RETRY_ATTEMPTS + 1):
        try:
            logger.info(
                f'gTTS request: chunk={chunk_index}/{total_chunks}, chars={len(chunk_text)}, '
                f'lang={language_code}, attempt={attempt}/{GTTS_RETRY_ATTEMPTS}'
            )
            tts = gTTS(text=chunk_text, lang=language_code, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as err:
            last_error = err
            logger.warning(
                f'gTTS attempt failed: chunk={chunk_index}/{total_chunks}, lang={language_code}, '
                f'attempt={attempt}/{GTTS_RETRY_ATTEMPTS}, '
                f'error_type={type(err).__name__}, error={err}'
            )
            if attempt < GTTS_RETRY_ATTEMPTS:
                if os.environ.get('ENABLE_GTTS_EXPONENTIAL_BACKOFF', 'false').lower() == 'true':
                    delay = GTTS_RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
                    jitter = delay * random.uniform(-0.25, 0.25)
                    time.sleep(max(0.1, delay + jitter))
                else:
                    time.sleep(GTTS_RETRY_BACKOFF_SEC * attempt)

    raise RuntimeError(
        f'gTTS failed after {GTTS_RETRY_ATTEMPTS} attempts '
        f'(chunk={chunk_index}/{total_chunks}, lang={language_code}, '
        f'error_type={type(last_error).__name__}): {last_error}'
    )


def _gtts_tts(safe_text, language_code, time_budget_sec=None):
    """Free Google Translate TTS. No API key. Supports all major Indian languages."""
    chunks = _split_text_for_tts(safe_text, GTTS_CHUNK_MAX_CHARS)
    if not chunks:
        return None

    total_chunks = len(chunks)
    if total_chunks > 1:
        logger.info(f'gTTS chunking enabled: total_chunks={total_chunks}, total_chars={len(safe_text)}')

    merged_audio = io.BytesIO()
    start_time = time.time()
    processed_chars = 0
    completed_all_chunks = True

    for idx, chunk in enumerate(chunks, 1):
        if idx > 1 and time_budget_sec and (time.time() - start_time) >= time_budget_sec:
            completed_all_chunks = False
            logger.warning(
                f'gTTS partial cutoff reached before chunk {idx}/{total_chunks}: '
                f'elapsed={time.time() - start_time:.2f}s budget={time_budget_sec}s'
            )
            break

        chunk_audio = _gtts_tts_chunk(chunk, language_code, chunk_index=idx, total_chunks=total_chunks)
        merged_audio.write(chunk_audio)
        processed_chars += len(chunk)

        if idx < total_chunks and time_budget_sec and (time.time() - start_time) >= time_budget_sec:
            completed_all_chunks = False
            logger.warning(
                f'gTTS partial cutoff reached after chunk {idx}/{total_chunks}: '
                f'elapsed={time.time() - start_time:.2f}s budget={time_budget_sec}s'
            )
            break

    if processed_chars == 0:
        return None

    upload_result = _upload_audio_bytes(merged_audio.getvalue())
    if isinstance(upload_result, dict):
        upload_result['partial_audio'] = not completed_all_chunks
        upload_result['processed_chars'] = processed_chars
        upload_result['total_chars'] = len(safe_text)
    return upload_result


def text_to_speech(text, language_code='en', voice_id=None, return_metadata=False, gtts_time_budget_sec=None):
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
    was_truncated = False
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
                try:
                    result = _gtts_tts(safe_text, language_code, time_budget_sec=gtts_time_budget_sec)
                except Exception as gtts_err:
                    tts_error = f"gTTS error ({language_code}): {gtts_err}"
                    logger.warning(tts_error)
            else:
                tts_error = f"gTTS disabled by USE_GTTS for language={language_code}"
                logger.warning(tts_error)
        else:
            tts_error = f"No TTS engine configured for language={language_code}"
            logger.warning(tts_error)


        # Unpack result — _upload_audio_bytes now returns {'url': ..., 'key': ...}
        if isinstance(result, dict):
            audio_url = result.get('url')
            audio_key = result.get('key')
        else:
            audio_url = result
            audio_key = None

        if not audio_url and not tts_error:
            tts_error = f"TTS produced no audio for language={language_code}"

        if return_metadata:
            partial_audio = bool(result.get('partial_audio', False)) if isinstance(result, dict) else False
            processed_chars = result.get('processed_chars') if isinstance(result, dict) else None
            total_chars = result.get('total_chars') if isinstance(result, dict) else None
            return {
                'audio_url': audio_url,
                'audio_key': audio_key,
                'truncated': was_truncated,
                'error': tts_error,
                'partial_audio': partial_audio,
                'processed_chars': processed_chars,
                'total_chars': total_chars,
            }
        return audio_url

    except Exception as e:
        tts_error = f"TTS fatal error: {e}"
        print(tts_error)
        if return_metadata:
            return {
                'audio_url': None,
                'audio_key': None,
                'truncated': was_truncated,
                'error': tts_error,
            }
        return None
