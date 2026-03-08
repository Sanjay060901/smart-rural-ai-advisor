# backend/utils/response_helper.py
# Standardized API response envelope
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 6C (Integration Contracts)

import json
import os

# Security: Restrict CORS to known origins
ALLOWED_ORIGINS = [
    os.environ.get('ALLOWED_ORIGIN', 'https://d80ytlzsrax1n.cloudfront.net'),
]

def _get_cors_origin(origin=None):
    """Return the allowed origin or the CloudFront domain as default."""
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    return ALLOWED_ORIGINS[0]


def success_response(data, message="Success", language="en", status_code=200, origin=None):
    """
    Standard success response envelope for API Gateway.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": _get_cors_origin(origin),
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps({
            "status": "success",
            "data": data,
            "message": message,
            "language": language
        })
    }


def error_response(message, status_code=500, language="en", origin=None):
    """
    Standard error response envelope for API Gateway.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": _get_cors_origin(origin),
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps({
            "status": "error",
            "data": None,
            "message": message,
            "language": language
        })
    }

