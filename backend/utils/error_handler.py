# backend/utils/error_handler.py
# Centralized error handling and logging
# Owner: Manoj RS
# See: Detailed_Implementation_Guide.md Section 9

import json
import logging
import traceback
from utils.response_helper import error_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle_errors(func):
    """Decorator that wraps Lambda handlers with error handling."""
    def wrapper(event, context):
        try:
            logger.info(f"Lambda invoked: {context.function_name}")
            logger.info(f"Event: {json.dumps(event)}")
            return func(event, context)
        except KeyError as e:
            logger.error(f"Missing required field: {e}")
            return error_response("Missing required request field.", 400)
        except Exception as e:
            logger.error(f"Unhandled error: {str(e)}")
            logger.error(traceback.format_exc())
            return error_response("Internal server error. Please try again.", 500)
    return wrapper
