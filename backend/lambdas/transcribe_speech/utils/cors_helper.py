import os


def get_cors_headers(origin=None, methods='GET,POST,PUT,DELETE,OPTIONS'):
    allowed_origin = origin or os.environ.get('ALLOWED_ORIGIN', 'https://d80ytlzsrax1n.cloudfront.net')
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': allowed_origin,
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        'Access-Control-Allow-Methods': methods,
    }


def handle_cors_preflight(origin=None, methods='GET,POST,PUT,DELETE,OPTIONS'):
    return {
        'statusCode': 200,
        'headers': get_cors_headers(origin, methods=methods),
        'body': '',
    }