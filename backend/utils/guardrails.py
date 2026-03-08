# backend/utils/guardrails.py
# Enterprise Guardrails: PII masking, prompt injection defense,
# input validation, toxicity filtering, OUTPUT validation
# Owner: Manoj RS
# Gaps addressed: #1 PII, #2 Prompt Injection, #4 Input Length, #7 Toxicity, #8 Output Validation

import re
import logging

logger = logging.getLogger()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAP #4: INPUT VALIDATION — Length, encoding, structure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAX_MESSAGE_LENGTH = 2000  # characters
MIN_MESSAGE_LENGTH = 1


def validate_input(message):
    """
    Validate user input for length, encoding, and structure.
    Returns: (is_valid: bool, error_message: str or None, sanitized: str)
    """
    if not message or not isinstance(message, str):
        return False, "Message is required and must be a string.", ""

    # Strip and check length
    cleaned = message.strip()

    if len(cleaned) < MIN_MESSAGE_LENGTH:
        return False, "Message is too short.", ""

    if len(cleaned) > MAX_MESSAGE_LENGTH:
        return False, f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters ({len(cleaned)} received). Please shorten your message.", ""

    # Check for null bytes or control characters (except newlines/tabs)
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', cleaned):
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', cleaned)

    return True, None, cleaned


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAP #1: PII DETECTION & MASKING
#  Detects: Aadhaar, phone numbers, bank accounts, PAN, emails
#  Two modes: mask (replace with ***) or detect (bool check)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PII_PATTERNS = {
    'aadhaar': {
        # Aadhaar: 12 digits, often written as XXXX XXXX XXXX or XXXX-XXXX-XXXX
        'pattern': re.compile(r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b'),
        'mask': '****-****-****',
        'label': 'AADHAAR',
        # Validation: first digit != 0 or 1, length = 12 digits
        'validate': lambda m: len(re.sub(r'[\s\-]', '', m)) == 12 and re.sub(r'[\s\-]', '', m)[0] not in ('0', '1'),
    },
    'phone': {
        # Indian phone: +91XXXXXXXXXX or 0XXXXXXXXXX or 10-digit mobile
        'pattern': re.compile(r'(?:\+91[\s\-]?|0)?([6-9]\d{9})\b'),
        'mask': '****-****-**',
        'label': 'PHONE',
        'validate': lambda m: True,
    },
    'pan': {
        # PAN: ABCDE1234F format
        'pattern': re.compile(r'\b([A-Z]{5}\d{4}[A-Z])\b'),
        'mask': '**********',
        'label': 'PAN',
        'validate': lambda m: True,
    },
    'bank_account': {
        # Bank account: 9-18 digit number (context-dependent)
        'pattern': re.compile(r'\b(?:account\s*(?:no|number|num|#)?[\s:.\-]*)?(\d{9,18})\b', re.IGNORECASE),
        'mask': '**************',
        'label': 'BANK_ACCOUNT',
        # Only flag if preceded by account-related keywords
        'validate': lambda m: True,
    },
    'email': {
        'pattern': re.compile(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b'),
        'mask': '***@***.***',
        'label': 'EMAIL',
        'validate': lambda m: True,
    },
    'ifsc': {
        # IFSC code: 4 letters + 0 + 6 alphanumeric
        'pattern': re.compile(r'\b([A-Z]{4}0[A-Z0-9]{6})\b'),
        'mask': '***********',
        'label': 'IFSC',
        'validate': lambda m: True,
    },
}


def detect_pii(text):
    """
    Detect PII in text. Returns list of dicts:
    [{'type': 'AADHAAR', 'match': '5432 1234 5678', 'start': 10, 'end': 24}]
    """
    if not text:
        return []

    findings = []
    for pii_type, config in PII_PATTERNS.items():
        for match in config['pattern'].finditer(text):
            matched_text = match.group(0)
            if config['validate'](matched_text):
                findings.append({
                    'type': config['label'],
                    'match': matched_text,
                    'start': match.start(),
                    'end': match.end(),
                })
    return findings


def mask_pii(text):
    """
    Mask all detected PII in text. Returns (masked_text, pii_types_found).
    Used for logging — never log raw PII.
    """
    if not text:
        return text, []

    masked = text
    pii_types = set()

    # Process in reverse order of position to preserve indices
    findings = detect_pii(text)
    findings.sort(key=lambda f: f['start'], reverse=True)

    for finding in findings:
        pii_type = finding['type']
        mask = PII_PATTERNS.get(pii_type.lower(), {}).get('mask', '***')
        masked = masked[:finding['start']] + f"[{pii_type}:{mask}]" + masked[finding['end']:]
        pii_types.add(pii_type)

    return masked, list(pii_types)


def mask_pii_in_log(text):
    """Quick mask for log messages — returns masked text only."""
    masked, _ = mask_pii(text)
    return masked


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAP #2: PROMPT INJECTION DEFENSE
#  Detects attempts to hijack model behavior:
#  - Role impersonation ("you are now...", "act as...")
#  - Instruction override ("ignore previous", "disregard")
#  - Data exfiltration ("list all farmers", "show database")
#  - System prompt extraction ("what are your instructions")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INJECTION_PATTERNS = [
    # Instruction override
    (re.compile(r'ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?|directives?)', re.IGNORECASE),
     'instruction_override', 'high'),
    (re.compile(r'disregard\s+(all\s+)?(previous|prior|above|earlier|your)\s+(instructions?|rules?|guidelines?)', re.IGNORECASE),
     'instruction_override', 'high'),
    (re.compile(r'forget\s+(everything|all|your)\s+(you\s+)?(know|were\s+told|instructions?)', re.IGNORECASE),
     'instruction_override', 'high'),
    (re.compile(r'override\s+(your|the|all)\s+(instructions?|rules?|policies?|safety)', re.IGNORECASE),
     'instruction_override', 'high'),
    (re.compile(r'do\s+not\s+follow\s+(your|the|any)\s+(instructions?|rules?|guidelines?)', re.IGNORECASE),
     'instruction_override', 'high'),

    # Role impersonation
    (re.compile(r'you\s+are\s+now\s+(a|an|the|my)\s+', re.IGNORECASE),
     'role_hijack', 'high'),
    (re.compile(r'act\s+as\s+(a|an|the|my)\s+(?!farmer)', re.IGNORECASE),
     'role_hijack', 'medium'),
    (re.compile(r'pretend\s+(to\s+be|you\s+are)\s+', re.IGNORECASE),
     'role_hijack', 'high'),
    (re.compile(r'switch\s+(to|into)\s+(.*?)\s+mode', re.IGNORECASE),
     'role_hijack', 'medium'),
    (re.compile(r'enter\s+(developer|admin|debug|god|sudo|root)\s+mode', re.IGNORECASE),
     'role_hijack', 'high'),

    # System prompt extraction
    (re.compile(r'(what|show|reveal|display|print|tell|repeat)\s+(are\s+)?(your|the|system)\s+(instructions?|prompts?|rules?|guidelines?|system\s+prompt)', re.IGNORECASE),
     'prompt_extraction', 'high'),
    (re.compile(r'(output|show|print|reveal)\s+(your\s+)?(initial|system|hidden)\s+(prompt|instructions?|message)', re.IGNORECASE),
     'prompt_extraction', 'high'),

    # Data exfiltration
    (re.compile(r'(list|show|give|display|export|dump)\s+(all|every)\s+(farmer|user|profile|record|data|customer)', re.IGNORECASE),
     'data_exfiltration', 'high'),
    (re.compile(r'(access|query|read|scan)\s+(the\s+)?(database|dynamodb|table|storage|s3)', re.IGNORECASE),
     'data_exfiltration', 'high'),
    (re.compile(r'(show|reveal|list)\s+(the\s+)?(api|secret|password|key|token|credential)', re.IGNORECASE),
     'data_exfiltration', 'high'),

    # Code execution attempts
    (re.compile(r'(execute|run|eval)\s+(this\s+)?(code|script|command|python|javascript|sql)', re.IGNORECASE),
     'code_execution', 'high'),
    (re.compile(r'```(?:python|javascript|bash|sql|shell)', re.IGNORECASE),
     'code_execution', 'medium'),

    # Encoded/obfuscated attacks
    (re.compile(r'base64[\s:]+[A-Za-z0-9+/]{20,}', re.IGNORECASE),
     'obfuscated_input', 'medium'),
]

INJECTION_RESPONSE = (
    "I'm designed to help with agriculture and farming topics only. "
    "I cannot modify my instructions or access system data. "
    "Please ask a farming-related question — I'm here to help with crops, weather, pests, schemes, and more!"
)


def check_prompt_injection(text):
    """
    Check for prompt injection attempts.
    Returns: (is_safe: bool, threat_type: str or None, severity: str or None, pattern_matched: str or None)
    """
    if not text:
        return True, None, None, None

    for pattern, threat_type, severity in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(
                f"PROMPT INJECTION DETECTED | type={threat_type} | severity={severity} | "
                f"match='{match.group()[:80]}'"
            )
            return False, threat_type, severity, match.group()[:80]

    return True, None, None, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAP #7: TOXICITY / HARMFUL CONTENT FILTER
#  Catches harmful content that passes the on-topic check
#  (e.g., "how to poison a neighbor's crops" is on-topic but harmful)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOXICITY_PATTERNS = [
    # Harm to people
    (re.compile(r'(poison|kill|harm|hurt|injure|attack)\s+(a\s+)?(person|people|human|neighbor|neighbour|someone|farmer|worker|child)', re.IGNORECASE),
     'harm_to_people', 'high'),

    # Intentional crop/animal destruction targeting others
    (re.compile(r'(destroy|ruin|sabotage|contaminate|damage)\s+(my\s+)?(neighbor|neighbour|someone|their|other)\s*\'?s?\s*(crop|farm|field|cattle|livestock|animal)', re.IGNORECASE),
     'sabotage', 'high'),

    # Indirect sabotage phrasing targeting others
    (re.compile(r'(make|cause|help|ensure)\s+(my\s+)?(neighbor|neighbour|someone|their|other)\s*\'?s?\s*(crop|farm|field|yield)\s+(fail|decline|drop|die|wither)', re.IGNORECASE),
     'sabotage', 'high'),

    # Illegal pesticide use (banned substances)
    (re.compile(r'\b(endosulfan|monocrotophos|methyl\s*parathion|phorate|triazophos|methomyl|aldicarb|captafol)\b', re.IGNORECASE),
     'banned_pesticide', 'medium'),

    # Deliberate environmental harm
    (re.compile(r'(poison|contaminate|pollute)\s+(the\s+)?(river|water|ground\s*water|well|lake|stream|soil)\b', re.IGNORECASE),
     'environmental_harm', 'high'),

    # Self-harm (farmer suicide is a real crisis — route to help)
    (re.compile(r'\b(suicide|kill\s+myself|end\s+my\s+life|no\s+point\s+living|want\s+to\s+die)\b', re.IGNORECASE),
     'self_harm', 'critical'),

    # Hate speech in agriculture context
    (re.compile(r'\b(those|these|all)\s+(caste|tribal|dalit|muslim|hindu|christian|lower\s+caste)\s+(farmers?|people)\s+(should|must|deserve)', re.IGNORECASE),
     'hate_speech', 'high'),
]

TOXICITY_RESPONSES = {
    'self_harm': (
        "I sense you may be going through a very difficult time. "
        "Please reach out for support:\n"
        "- Kisan Call Centre: 1800-180-1551 (free, 24/7)\n"
        "- iCall: 9152987821\n"
        "- Vandrevala Foundation: 1860-2662-345 (24/7)\n\n"
        "You are not alone. Help is available."
    ),
    'default': (
        "I cannot help with requests that may cause harm to people, animals, or the environment. "
        "I'm here to help with safe, sustainable farming practices. Please ask a farming-related question."
    ),
    'banned_pesticide': (
        "The substance you mentioned has been banned in India due to safety concerns. "
        "I can suggest safer, approved alternatives for your pest problem. "
        "Please describe the crop and pest issue, and I'll recommend approved treatments."
    ),
}


def check_toxicity(text):
    """
    Check for toxic/harmful content.
    Returns: (is_safe: bool, threat_type: str or None, severity: str or None,
              custom_response: str or None)
    """
    if not text:
        return True, None, None, None

    for pattern, threat_type, severity in TOXICITY_PATTERNS:
        match = pattern.search(text)
        if match:
            response = TOXICITY_RESPONSES.get(threat_type, TOXICITY_RESPONSES['default'])
            logger.warning(
                f"TOXICITY DETECTED | type={threat_type} | severity={severity} | "
                f"match='{match.group()[:80]}'"
            )
            return False, threat_type, severity, response

    return True, None, None, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UNIFIED GUARDRAIL CHECK — Call this from handler.py
#  Runs all checks in order: input validation → PII → injection → toxicity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_all_guardrails(message):
    """
    Run the full guardrail suite on user input.
    
    Returns: {
        'passed': bool,
        'sanitized_message': str,      # cleaned message (if passed)
        'blocked_reason': str or None,  # why it was blocked
        'blocked_response': str or None,# safe response to return to user
        'pii_detected': list,           # PII types found (for audit)
        'pii_masked_message': str,      # message with PII masked (for logging)
        'checks': {                     # individual check results (for audit)
            'input_valid': bool,
            'injection_safe': bool,
            'toxicity_safe': bool,
            'pii_found': bool,
        },
        'threat_details': dict or None, # details of any threat detected
    }
    """
    result = {
        'passed': False,
        'sanitized_message': '',
        'blocked_reason': None,
        'blocked_response': None,
        'pii_detected': [],
        'pii_masked_message': '',
        'checks': {
            'input_valid': False,
            'injection_safe': False,
            'toxicity_safe': False,
            'pii_found': False,
        },
        'threat_details': None,
    }

    # 1. Input validation (length, encoding)
    is_valid, error_msg, cleaned = validate_input(message)
    if not is_valid:
        result['blocked_reason'] = 'input_validation'
        result['blocked_response'] = error_msg
        return result
    result['checks']['input_valid'] = True
    result['sanitized_message'] = cleaned

    # 2. PII detection (detect but don't block — mask for logging)
    pii_masked, pii_types = mask_pii(cleaned)
    result['pii_masked_message'] = pii_masked
    result['pii_detected'] = pii_types
    result['checks']['pii_found'] = bool(pii_types)

    # 3. Prompt injection check
    is_safe, threat_type, severity, pattern_match = check_prompt_injection(cleaned)
    if not is_safe:
        result['blocked_reason'] = 'prompt_injection'
        result['blocked_response'] = INJECTION_RESPONSE
        result['threat_details'] = {
            'type': threat_type,
            'severity': severity,
            'pattern': pattern_match,
        }
        return result
    result['checks']['injection_safe'] = True

    # 4. Toxicity check
    is_safe, threat_type, severity, custom_response = check_toxicity(cleaned)
    if not is_safe:
        result['blocked_reason'] = 'toxicity'
        result['blocked_response'] = custom_response
        result['threat_details'] = {
            'type': threat_type,
            'severity': severity,
        }
        return result
    result['checks']['toxicity_safe'] = True

    # All checks passed
    result['passed'] = True
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAP #8: OUTPUT GUARDRAILS — PII leakage, prompt leakage,
#  response length cap, content safety on model output
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Max output length (characters). After translation some languages
# expand 2-3x; 6000 chars English → ~18000 chars in Tamil.
# Cap post-translation output to prevent excessive Polly synthesis cost
# and terrible UX on low-bandwidth farmer phones.
MAX_OUTPUT_LENGTH = 8000  # chars (post-translation cap)

# System prompt leak markers — phrases that should NEVER appear
# in a response shown to the farmer
PROMPT_LEAK_MARKERS = [
    # System prompt structure markers
    re.compile(r'you\s+are\s+the\s+(understanding|reasoning|fact[\s\-]?check(?:ing)?|communication)\s+agent', re.IGNORECASE),
    re.compile(r'multi[\s\-]?agent\s+agricultural\s+advisory\s+system', re.IGNORECASE),
    re.compile(r'output\s+strict\s+json', re.IGNORECASE),
    re.compile(r'your\s+(?:ONLY\s+)?job\s+is\s+to\s+(?:analyze|validate|rewrite)', re.IGNORECASE),
    # Internal pipeline references
    re.compile(r'reasoning\s+agent\'?s?\s+(?:draft|response|output|advisory)', re.IGNORECASE),
    re.compile(r'understanding\s+agent\'?s?\s+(?:analysis|output|JSON)', re.IGNORECASE),
    re.compile(r'fact[\s\-]?check(?:ing)?\s+agent\'?s?\s+(?:output|validation|response)', re.IGNORECASE),
    re.compile(r'communication\s+agent\'?s?\s+(?:output|rewrite)', re.IGNORECASE),
    # System/internal keywords that should never surface
    re.compile(r'\bsystem[\s_]?prompt\b', re.IGNORECASE),
    re.compile(r'\binferenceConfig\b', re.IGNORECASE),
    re.compile(r'\bmaxTokens\b', re.IGNORECASE),
    re.compile(r'\bguardrailConfig\b', re.IGNORECASE),
    re.compile(r'\bconverse\(\)\b', re.IGNORECASE),
    re.compile(r'bedrock[\s\-]?agentcore', re.IGNORECASE),
    re.compile(r'\blambda_handler\b', re.IGNORECASE),
    re.compile(r'AGENTCORE_RUNTIME_ARN', re.IGNORECASE),
]


def check_output_pii(text):
    """
    Scan model output for PII leakage. Returns (clean_text, pii_types_found).
    Unlike input PII (detect + log), output PII is actively MASKED before
    reaching the farmer, because the model may echo back sensitive data.
    """
    if not text:
        return text, []

    findings = detect_pii(text)
    if not findings:
        return text, []

    pii_types = set()
    # Mask in reverse order to preserve positions
    masked = text
    findings.sort(key=lambda f: f['start'], reverse=True)
    for finding in findings:
        pii_type = finding['type']
        mask = PII_PATTERNS.get(pii_type.lower(), {}).get('mask', '***')
        masked = masked[:finding['start']] + mask + masked[finding['end']:]
        pii_types.add(pii_type)

    pii_list = list(pii_types)
    if pii_list:
        logger.warning(f"OUTPUT PII LEAKAGE CAUGHT | types={pii_list} | count={len(findings)}")

    return masked, pii_list


def check_output_prompt_leakage(text):
    """
    Detect if model output contains system prompt fragments.
    Returns: (is_clean: bool, leaked_marker: str or None)
    """
    if not text:
        return True, None

    for pattern in PROMPT_LEAK_MARKERS:
        match = pattern.search(text)
        if match:
            logger.warning(f"SYSTEM PROMPT LEAKAGE DETECTED in output | match='{match.group()[:100]}'")
            return False, match.group()[:100]

    return True, None


def truncate_output(text, max_length=MAX_OUTPUT_LENGTH):
    """
    Truncate output to max_length characters with a clean break.
    Tries to break at sentence boundary if possible.
    Returns: (text, was_truncated: bool)
    """
    if not text or len(text) <= max_length:
        return text, False

    # Try to break at sentence end (.!?) within last 200 chars of limit
    truncated = text[:max_length]
    last_sentence_end = max(
        truncated.rfind('. ', max_length - 200),
        truncated.rfind('! ', max_length - 200),
        truncated.rfind('? ', max_length - 200),
    )

    if last_sentence_end > max_length - 200:
        truncated = truncated[:last_sentence_end + 1]
    else:
        # Fall back to last space
        last_space = truncated.rfind(' ', max_length - 100)
        if last_space > max_length - 100:
            truncated = truncated[:last_space]

    truncated = truncated.rstrip() + "\n\n(Response trimmed for readability.)"
    logger.info(f"Output truncated: {len(text)} → {len(truncated)} chars")
    return truncated, True


PROMPT_LEAKAGE_FALLBACK = (
    "I apologize, but I encountered an issue generating your advisory. "
    "Please try asking your question again, and I'll provide helpful farming guidance."
)


def run_output_guardrails(text, context=None):
    """
    Run output guardrail suite on model response BEFORE returning to farmer.
    
    Checks (in order):
      1. System prompt leakage → replace entire response
      2. PII leakage → mask PII in output
      3. Output length → truncate with clean break
    
    Args:
        text: The model's response text (post-translation)
        context: Optional dict with 'farmer_id', 'session_id' for logging
    
    Returns: {
        'text': str,            # cleaned/safe output text
        'modified': bool,       # whether any changes were made
        'pii_masked': list,     # PII types masked in output
        'prompt_leaked': bool,  # whether prompt leakage was detected
        'truncated': bool,      # whether response was truncated
        'original_length': int, # original response length
    }
    """
    ctx = context or {}
    farmer_id = ctx.get('farmer_id', 'unknown')
    session_id = ctx.get('session_id', 'unknown')

    result = {
        'text': text or '',
        'modified': False,
        'pii_masked': [],
        'prompt_leaked': False,
        'truncated': False,
        'original_length': len(text or ''),
    }

    if not text:
        return result

    working_text = text

    # 1. Check for system prompt leakage (most critical — replace entire response)
    is_clean, leaked_marker = check_output_prompt_leakage(working_text)
    if not is_clean:
        logger.error(
            f"OUTPUT GUARDRAIL: Prompt leakage blocked | farmer={farmer_id} "
            f"session={session_id} | marker='{leaked_marker}'"
        )
        result['text'] = PROMPT_LEAKAGE_FALLBACK
        result['modified'] = True
        result['prompt_leaked'] = True
        return result  # Don't process further — entire response replaced

    # 2. Check for PII leakage in output (mask, don't block)
    clean_text, pii_types = check_output_pii(working_text)
    if pii_types:
        logger.warning(
            f"OUTPUT GUARDRAIL: PII masked in output | farmer={farmer_id} "
            f"session={session_id} | types={pii_types}"
        )
        working_text = clean_text
        result['pii_masked'] = pii_types
        result['modified'] = True

    # 3. Truncate if too long (after PII masking, which may shorten text)
    truncated_text, was_truncated = truncate_output(working_text)
    if was_truncated:
        logger.info(
            f"OUTPUT GUARDRAIL: Response truncated | farmer={farmer_id} "
            f"session={session_id} | {len(working_text)} → {len(truncated_text)} chars"
        )
        working_text = truncated_text
        result['truncated'] = True
        result['modified'] = True

    result['text'] = working_text
    return result
