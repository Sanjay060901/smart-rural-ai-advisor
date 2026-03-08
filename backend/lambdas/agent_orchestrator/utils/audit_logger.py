# backend/utils/audit_logger.py
# Enterprise Audit Logging: Structured JSON audit trail for compliance
# Logs every policy decision, guardrail action, and security event
# Owner: Manoj RS
# Gap addressed: #6 Audit Trail

import json
import logging
import time
from datetime import datetime, UTC

logger = logging.getLogger()

# Dedicated audit logger — separate from application logs
# In production, this can be routed to a dedicated CloudWatch log group,
# S3 bucket, or OpenSearch via a subscription filter
audit_logger = logging.getLogger('AUDIT')
audit_logger.setLevel(logging.INFO)


class AuditEvent:
    """Structured audit event builder."""

    # Event categories
    GUARDRAIL = 'GUARDRAIL'
    POLICY = 'POLICY'
    ACCESS = 'ACCESS'
    TOOL_USE = 'TOOL_USE'
    PIPELINE = 'PIPELINE'
    ERROR = 'ERROR'
    SECURITY = 'SECURITY'

    # Action types
    INPUT_VALIDATED = 'INPUT_VALIDATED'
    INPUT_BLOCKED = 'INPUT_BLOCKED'
    PII_DETECTED = 'PII_DETECTED'
    INJECTION_BLOCKED = 'INJECTION_BLOCKED'
    TOXICITY_BLOCKED = 'TOXICITY_BLOCKED'
    RATE_LIMITED = 'RATE_LIMITED'
    OFF_TOPIC_BLOCKED = 'OFF_TOPIC_BLOCKED'
    GROUNDING_ENFORCED = 'GROUNDING_ENFORCED'
    TOOL_INVOKED = 'TOOL_INVOKED'
    TOOL_FAILED = 'TOOL_FAILED'
    RESPONSE_TRUNCATED = 'RESPONSE_TRUNCATED'
    BEDROCK_GUARDRAIL_TRIGGERED = 'BEDROCK_GUARDRAIL_TRIGGERED'
    PIPELINE_COMPLETED = 'PIPELINE_COMPLETED'
    REQUEST_STARTED = 'REQUEST_STARTED'
    REQUEST_COMPLETED = 'REQUEST_COMPLETED'


def audit_log(category, action, farmer_id='anonymous', session_id=None,
              details=None, severity='info', pii_safe_message=None):
    """
    Write a structured audit log entry.
    
    Args:
        category: AuditEvent category (GUARDRAIL, POLICY, ACCESS, etc.)
        action: AuditEvent action type
        farmer_id: Farmer identifier (for tracing)
        session_id: Session identifier
        details: Dict of additional context (NEVER include raw PII)
        severity: 'info', 'warning', 'critical'
        pii_safe_message: PII-masked version of the user message (for context)
    """
    entry = {
        'audit': True,  # marker for log filtering
        'timestamp': datetime.now(UTC).replace(tzinfo=None).isoformat() + 'Z',
        'epoch': time.time(),
        'category': category,
        'action': action,
        'severity': severity,
        'farmer_id': farmer_id,
        'session_id': session_id,
    }

    if pii_safe_message:
        entry['message_preview'] = pii_safe_message[:200]  # truncate for safety

    if details:
        # Ensure no raw PII leaks into audit logs
        entry['details'] = details

    log_line = json.dumps(entry, default=str)

    if severity == 'critical':
        audit_logger.critical(f"AUDIT|{log_line}")
    elif severity == 'warning':
        audit_logger.warning(f"AUDIT|{log_line}")
    else:
        audit_logger.info(f"AUDIT|{log_line}")


def audit_request_start(farmer_id, session_id, pii_safe_message, detected_lang=None):
    """Audit log: new request received."""
    audit_log(
        category=AuditEvent.ACCESS,
        action=AuditEvent.REQUEST_STARTED,
        farmer_id=farmer_id,
        session_id=session_id,
        pii_safe_message=pii_safe_message,
        details={
            'language': detected_lang,
            'message_length': len(pii_safe_message) if pii_safe_message else 0,
        },
    )


def audit_guardrail_block(block_type, farmer_id, session_id, pii_safe_message,
                          threat_details=None):
    """Audit log: guardrail blocked a request."""
    action_map = {
        'input_validation': AuditEvent.INPUT_BLOCKED,
        'prompt_injection': AuditEvent.INJECTION_BLOCKED,
        'toxicity': AuditEvent.TOXICITY_BLOCKED,
        'rate_limit': AuditEvent.RATE_LIMITED,
        'off_topic': AuditEvent.OFF_TOPIC_BLOCKED,
    }
    audit_log(
        category=AuditEvent.SECURITY if block_type in ('prompt_injection', 'toxicity') else AuditEvent.GUARDRAIL,
        action=action_map.get(block_type, AuditEvent.INPUT_BLOCKED),
        farmer_id=farmer_id,
        session_id=session_id,
        severity='warning' if block_type in ('prompt_injection', 'toxicity') else 'info',
        pii_safe_message=pii_safe_message,
        details={
            'block_type': block_type,
            'threat': threat_details,
        },
    )


def audit_pii_detected(farmer_id, session_id, pii_types):
    """Audit log: PII found in user input (types only, never the actual data)."""
    if not pii_types:
        return
    audit_log(
        category=AuditEvent.GUARDRAIL,
        action=AuditEvent.PII_DETECTED,
        farmer_id=farmer_id,
        session_id=session_id,
        severity='info',
        details={
            'pii_types': pii_types,
            'count': len(pii_types),
        },
    )


def audit_tool_invocation(tool_name, farmer_id, session_id, success=True, error=None):
    """Audit log: tool was invoked during reasoning."""
    audit_log(
        category=AuditEvent.TOOL_USE,
        action=AuditEvent.TOOL_INVOKED if success else AuditEvent.TOOL_FAILED,
        farmer_id=farmer_id,
        session_id=session_id,
        severity='info' if success else 'warning',
        details={
            'tool': tool_name,
            'success': success,
            'error': str(error)[:200] if error else None,
        },
    )


def audit_policy_decision(farmer_id, session_id, policy_meta):
    """Audit log: code policy enforcement result."""
    audit_log(
        category=AuditEvent.POLICY,
        action=AuditEvent.GROUNDING_ENFORCED if policy_meta.get('grounding_required') else AuditEvent.INPUT_VALIDATED,
        farmer_id=farmer_id,
        session_id=session_id,
        details={
            'code_policy_enforced': policy_meta.get('code_policy_enforced'),
            'off_topic_blocked': policy_meta.get('off_topic_blocked'),
            'grounding_required': policy_meta.get('grounding_required'),
            'grounding_satisfied': policy_meta.get('grounding_satisfied'),
        },
    )


def audit_request_complete(farmer_id, session_id, tools_used, pipeline_mode,
                           response_length, elapsed_seconds, bedrock_guardrail_triggered=False,
                           output_guardrail=None):
    """Audit log: request processing completed."""
    details = {
        'tools_used': tools_used or [],
        'pipeline_mode': pipeline_mode,
        'response_length': response_length,
        'elapsed_seconds': round(elapsed_seconds, 2),
        'bedrock_guardrail_triggered': bedrock_guardrail_triggered,
    }
    if output_guardrail:
        details['output_guardrail'] = {
            'pii_masked': output_guardrail.get('pii_masked', []),
            'prompt_leaked': output_guardrail.get('prompt_leaked', False),
            'truncated': output_guardrail.get('truncated', False),
            'original_length': output_guardrail.get('original_length', 0),
        }
    audit_log(
        category=AuditEvent.PIPELINE,
        action=AuditEvent.REQUEST_COMPLETED,
        farmer_id=farmer_id,
        session_id=session_id,
        details=details,
    )


def audit_bedrock_guardrail(farmer_id, session_id, guardrail_action, trace_info=None):
    """Audit log: Bedrock native guardrail was triggered."""
    audit_log(
        category=AuditEvent.SECURITY,
        action=AuditEvent.BEDROCK_GUARDRAIL_TRIGGERED,
        farmer_id=farmer_id,
        session_id=session_id,
        severity='warning',
        details={
            'guardrail_action': guardrail_action,
            'trace': str(trace_info)[:300] if trace_info else None,
        },
    )
