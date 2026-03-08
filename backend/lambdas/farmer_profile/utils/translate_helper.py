# backend/utils/translate_helper.py
# Amazon Translate helper for multilingual support
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 12

import boto3

translate = boto3.client('translate')

# Supported languages (must match frontend config.js)
SUPPORTED_LANGUAGES = ["en", "hi", "ta", "te", "kn", "ml", "mr", "bn", "gu", "pa", "or", "as", "ur"]

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

# Language code reference:
# Tamil: 'ta'    | Telugu: 'te'   | Hindi: 'hi'
# English: 'en'  | Kannada: 'kn'  | Malayalam: 'ml'
# Marathi: 'mr'  | Bengali: 'bn'


def normalize_language_code(language_code, default='en'):
    normalized = (language_code or '').strip().lower().replace('_', '-')
    if not normalized:
        return default
    normalized = LANGUAGE_ALIASES.get(normalized, normalized)
    return normalized if normalized in SUPPORTED_LANGUAGES else default


def detect_and_translate(text, target_language='en'):
    """
    Auto-detect source language and translate to target.

    Args:
        text: Input text in any supported language
        target_language: Language code to translate to ('en', 'ta', 'hi', 'te')

    Returns:
        dict with detected_language, translated_text, target_language
    """
    normalized_target = normalize_language_code(target_language, default='en')
    try:
        response = translate.translate_text(
            Text=text,
            SourceLanguageCode='auto',  # Auto-detect!
            TargetLanguageCode=normalized_target
        )

        return {
            'detected_language': normalize_language_code(response['SourceLanguageCode'], default='en'),
            'translated_text': response['TranslatedText'],
            'target_language': normalized_target
        }

    except Exception as e:
        print(f"Translate error: {e}")
        # Fallback: return original text assuming English
        return {
            'detected_language': 'en',
            'translated_text': text,
            'target_language': normalized_target
        }


def _strip_html_artifacts(text):
    """Remove any <span translate="no">...</span> tags and other HTML artifacts from output."""
    import re
    # Strip well-formed <span translate="no">...</span>
    text = re.sub(r'<span\s+translate\s*=\s*["\']?no["\']?\s*>(.*?)</span>', r'\1', text, flags=re.DOTALL | re.IGNORECASE)
    # Strip broken/partial span tags that translation may garble
    text = re.sub(r'</?span[^>]*>', '', text, flags=re.IGNORECASE)
    # Strip stray HTML entities that might leak
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#\d+;', '', text)
    return text.strip()


def _is_garbled_translation(original, translated):
    """Detect if a translation is garbled/degraded.
    Returns True if the translation appears to be garbage output."""
    import re
    if not translated or not translated.strip():
        return True
    # Check length ratio: translated should be within 0.1x to 6x of original
    ratio = len(translated) / max(len(original), 1)
    if ratio < 0.1 or ratio > 6.0:
        return True
    # Check for excessive punctuation (>70% non-alpha)
    alpha_chars = sum(1 for c in translated if c.isalpha())
    if len(translated) > 30 and alpha_chars / max(len(translated), 1) < 0.25:
        return True
    # Check for repetition loops: same 8+ char substring repeated 5+ times
    if len(translated) > 100:
        for chunk_len in (15, 10, 8):
            for i in range(0, min(len(translated) - chunk_len, 200)):
                chunk = translated[i:i + chunk_len]
                if chunk.strip() and translated.count(chunk) >= 5:
                    return True
    return False


# Localized "Translation unavailable" message for each supported language
_TRANSLATION_UNAVAILABLE = {
    'hi': '(अनुवाद उपलब्ध नहीं है — अंग्रेज़ी में दिखा रहे हैं)\n\n',
    'ta': '(மொழிபெயர்ப்பு கிடைக்கவில்லை — ஆங்கிலத்தில் காட்டுகிறோம்)\n\n',
    'te': '(అనువాదం అందుబాటులో లేదు — ఆంగ్లంలో చూపిస్తున్నాము)\n\n',
    'kn': '(ಅನುವಾದ ಲಭ್ಯವಿಲ್ಲ — ಆಂಗ್ಲದಲ್ಲಿ ತೋರಿಸಲಾಗುತ್ತಿದೆ)\n\n',
    'ml': '(വിവർത്തനം ലഭ്യമല്ല — ഇംഗ്ലീഷിൽ കാണിക്കുന്നു)\n\n',
    'mr': '(भाषांतर उपलब्ध नाही — इंग्रजीत दाखवत आहोत)\n\n',
    'bn': '(অনুবাদ পাওয়া যায়নি — ইংরেজিতে দেখানো হচ্ছে)\n\n',
    'gu': '(અનુવાદ ઉપલબ્ધ નથી — અંગ્રેજીમાં બતાવી રહ્યા છીએ)\n\n',
    'pa': '(ਅਨੁਵਾਦ ਉਪਲਬਧ ਨਹੀਂ — ਅੰਗਰੇਜ਼ੀ ਵਿੱਚ ਦਿਖਾ ਰਹੇ ਹਾਂ)\n\n',
    'or': '(ଅନୁବାଦ ଉପಲବ୍ଧ ନାହିଁ — ଇଂରାଜୀରେ ଦେଖାଉଛୁ)\n\n',
    'as': '(অনুবাদ উপলব্ধ নহয় — ইংৰাজীত দেখুৱাইছো)\n\n',
    'ur': '(ترجمہ دستیاب نہیں — انگریزی میں دکھا رہے ہیں)\n\n',
}


def translate_response(text, source_language='en', target_language='ta'):
    """
    Translate AI response from English to farmer's language.
    Preserves markdown formatting markers using token-based protection.
    Detects garbled translations and falls back to English with a localized disclaimer.
    """
    normalized_source = normalize_language_code(source_language, default='en')
    normalized_target = normalize_language_code(target_language, default='en')

    if normalized_source == normalized_target:
        return text

    import re

    # Token-based markdown protection: replace markers with unique tokens
    # that AWS Translate will pass through unchanged (no HTML needed)
    _TOKEN_MAP = [
        # Order matters: longest/most specific patterns first
        (re.compile(r'^(#{1,4})\s+', re.MULTILINE), r'MKTK_H\1MKTK_HE '),        # ### heading
        (re.compile(r'\*\*(.+?)\*\*'), r'MKTK_BS\1MKTK_BE'),                       # **bold**
        (re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)'), r'MKTK_IS\1MKTK_IE'),  # *italic*
        (re.compile(r'^(\s*)[\-•]\s+', re.MULTILINE), r'\1MKTK_BL '),              # - bullet
        (re.compile(r'^(\s*\d+)\.\s+', re.MULTILINE), r'\1MKTK_NL '),              # 1. numbered
        (re.compile(r'(₹[\d,\.]+)'), r'MKTK_CS\1MKTK_CE'),                         # ₹1,234
    ]

    _RESTORE_MAP = [
        ('MKTK_BS', '**'), ('MKTK_BE', '**'),
        ('MKTK_IS', '*'), ('MKTK_IE', '*'),
        ('MKTK_BL', '- '),
        ('MKTK_NL', '. '),
        ('MKTK_CS', ''), ('MKTK_CE', ''),
    ]

    def _protect_markdown(t):
        """Replace markdown markers with pass-through tokens before translation."""
        for pattern, replacement in _TOKEN_MAP:
            t = pattern.sub(replacement, t)
        return t

    def _restore_markdown(t):
        """Restore markdown markers from tokens after translation."""
        # Restore heading tokens: MKTK_H###MKTK_HE → ###
        t = re.sub(r'MKTK_H(#{1,4})MKTK_HE\s*', r'\1 ', t)
        # Restore all other tokens
        for token, marker in _RESTORE_MAP:
            t = t.replace(token, marker)
        # Clean up any remaining MKTK tokens that got garbled
        t = re.sub(r'MKTK_\w+', '', t)
        return t

    def _do_translate_protected(source_text):
        """Translate with token-based markdown protection."""
        protected = _protect_markdown(source_text)
        response = translate.translate_text(
            Text=protected,
            SourceLanguageCode=normalized_source,
            TargetLanguageCode=normalized_target,
        )
        result = _restore_markdown(response['TranslatedText'])
        # Strip any stray HTML artifacts
        result = _strip_html_artifacts(result)
        return result

    def _do_translate_plain(source_text):
        """Plain text translation (fallback — no markdown protection)."""
        response = translate.translate_text(
            Text=source_text,
            SourceLanguageCode=normalized_source,
            TargetLanguageCode=normalized_target,
        )
        result = response['TranslatedText']
        # Defensive: strip any HTML that might leak
        result = _strip_html_artifacts(result)
        return result

    # Attempt 1: Token-protected translation (preserves markdown)
    try:
        translated = _do_translate_protected(text)
        if not _is_garbled_translation(text, translated):
            return translated
        print(f"Garbled protected translation detected, retrying plain text")
    except Exception as e:
        print(f"Protected translate error: {e}, retrying plain text")

    # Attempt 2: Plain text translation (no markdown protection)
    try:
        translated = _do_translate_plain(text)
        if not _is_garbled_translation(text, translated):
            return translated
        print(f"Garbled plain-text translation detected, falling back to English")
    except Exception as e2:
        print(f"Plain text translate error: {e2}, falling back to English")

    # Attempt 3: Fall back to English with localized disclaimer
    disclaimer = _TRANSLATION_UNAVAILABLE.get(normalized_target, '')
    return disclaimer + text
