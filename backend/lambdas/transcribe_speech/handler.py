# backend/lambdas/transcribe_speech/handler.py
# Fallback voice handler: Amazon Transcribe (Firefox fallback)
# Owner: Manoj RS
# Endpoint: POST /transcribe
# See: Detailed_Implementation_Guide.md Section 12

import json
import boto3
import base64
import uuid
import time
import os
import logging
from botocore.config import Config
from utils.response_helper import success_response, error_response
from utils.cors_helper import handle_cors_preflight

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENABLE_CONNECTION_POOLING = os.environ.get('ENABLE_CONNECTION_POOLING', 'false').lower() == 'true'
ENABLE_UNIFIED_CORS = os.environ.get('ENABLE_UNIFIED_CORS', 'false').lower() == 'true'
_POOL_CONFIG = Config(max_pool_connections=25) if ENABLE_CONNECTION_POOLING else None
transcribe = boto3.client('transcribe', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('transcribe')
s3 = boto3.client('s3', config=_POOL_CONFIG) if _POOL_CONFIG else boto3.client('s3')

BUCKET = os.environ.get('S3_KNOWLEDGE_BUCKET', 'smart-rural-ai-knowledge-base')

# Map frontend language codes to Amazon Transcribe language codes
# See: https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html
LANGUAGE_MAP = {
    'en-IN': 'en-IN',   # English (Indian)
    'en-US': 'en-US',   # English (US)
    'hi-IN': 'hi-IN',   # Hindi
    'ta-IN': 'ta-IN',   # Tamil
    'te-IN': 'te-IN',   # Telugu
    'kn-IN': 'kn-IN',   # Kannada
    'ml-IN': 'ml-IN',   # Malayalam
    'bn-IN': 'bn-IN',   # Bengali
    'mr-IN': 'mr-IN',   # Marathi
    'gu-IN': 'gu-IN',   # Gujarati
    'pa-IN': 'pa-IN',   # Punjabi (Gurmukhi)
    'or-IN': 'or-IN',   # Odia
    'ab-IN': 'ab-IN',   # Fallback
}

# Languages not supported by Amazon Transcribe — fall back to Hindi
UNSUPPORTED_LANGUAGES = {'as-IN', 'ur-IN'}


def _generate_job_id():
    """Generate a collision-resistant transcription job ID."""
    return f"voice-{uuid.uuid4().hex}"


def lambda_handler(event, context):
    """
    Receives base64-encoded audio, sends to Amazon Transcribe,
    returns transcribed text. Used as fallback for non-Chrome browsers.
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        if ENABLE_UNIFIED_CORS:
            return handle_cors_preflight(methods='POST,OPTIONS')
        return success_response({}, message='OK')

    try:
        body = json.loads(event.get('body', '{}'))
        audio_base64 = body.get('audio')
        language = body.get('language', 'ta-IN')
        audio_format = body.get('format', 'audio/webm')  # mime type from frontend

        if not audio_base64:
            return error_response('No audio provided', 400)

        # Detect file extension and Transcribe MediaFormat from mime type
        FORMAT_MAP = {
            'audio/webm': ('webm', 'webm'),
            'audio/webm;codecs=opus': ('webm', 'webm'),
            'audio/ogg': ('ogg', 'ogg'),
            'audio/ogg;codecs=opus': ('ogg', 'ogg'),
            'audio/mp3': ('mp3', 'mp3'),
            'audio/mpeg': ('mp3', 'mp3'),
            'audio/wav': ('wav', 'wav'),
            'audio/flac': ('flac', 'flac'),
            'audio/mp4': ('mp4', 'mp4'),
        }
        file_ext, media_format = FORMAT_MAP.get(audio_format, ('webm', 'webm'))

        # Handle unsupported languages by falling back to Hindi
        if language in UNSUPPORTED_LANGUAGES:
            logger.info(f"Language {language} not supported by Transcribe, falling back to hi-IN")
            language = 'hi-IN'

        # Decode audio and upload to S3 (Transcribe reads from S3)
        audio_bytes = base64.b64decode(audio_base64)
        job_id = _generate_job_id()
        s3_key = f"audio-uploads/{job_id}.{file_ext}"

        s3.put_object(
            Bucket=BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType=audio_format.split(';')[0]  # strip codecs param
        )

        # Start transcription job
        transcribe_language = LANGUAGE_MAP.get(language, 'ta-IN')

        transcribe_params = {
            'TranscriptionJobName': job_id,
            'Media': {'MediaFileUri': f's3://{BUCKET}/{s3_key}'},
            'LanguageCode': transcribe_language,
            'OutputBucketName': BUCKET,
            'OutputKey': f'transcriptions/{job_id}.json'
        }
        # Only set MediaFormat if we have a known mapping; otherwise let Transcribe auto-detect
        if media_format:
            transcribe_params['MediaFormat'] = media_format

        transcribe.start_transcription_job(**transcribe_params)

        # Poll for completion (max 45 seconds)
        for _ in range(45):
            status = transcribe.get_transcription_job(
                TranscriptionJobName=job_id
            )
            job_status = status['TranscriptionJob']['TranscriptionJobStatus']

            if job_status == 'COMPLETED':
                # Read the transcription result from S3
                result = s3.get_object(
                    Bucket=BUCKET,
                    Key=f'transcriptions/{job_id}.json'
                )
                transcript_data = json.loads(result['Body'].read().decode('utf-8'))
                transcript = transcript_data['results']['transcripts'][0]['transcript']

                # Cleanup: delete audio and transcription files
                _cleanup(s3_key, job_id)

                return success_response({'transcript': transcript})

            elif job_status == 'FAILED':
                logger.error(f"Transcription failed: {status}")
                _cleanup(s3_key, job_id)
                return error_response('Transcription failed. Please try again.', 500)

            time.sleep(1)  # Wait 1 second before polling again

        _cleanup(s3_key, job_id)
        return error_response('Transcription timed out. Please try again.', 504)

    except Exception as e:
        logger.error(f"Transcribe error: {str(e)}", exc_info=True)
        return error_response('Speech transcription failed. Please try again.', 500)


def _cleanup(s3_key, job_id):
    """Best-effort cleanup of S3 audio and transcription artifacts."""
    try:
        s3.delete_object(Bucket=BUCKET, Key=s3_key)
    except Exception:
        pass
    try:
        s3.delete_object(Bucket=BUCKET, Key=f'transcriptions/{job_id}.json')
    except Exception:
        pass
