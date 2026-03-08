# backend/lambdas/weather_lookup/handler.py
# Lambda Tool: OpenWeatherMap integration
# Owner: Manoj RS
# Endpoint: GET /weather/{location}
# See: Detailed_Implementation_Guide.md Section 9

import json
import os
import logging
import re
import socket
import base64
import urllib.request
import urllib.error
import urllib.parse
import boto3
from utils.response_helper import success_response, error_response
from utils.cors_helper import handle_cors_preflight

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY', '')
OPENWEATHER_API_KEY_SECRET_ARN = os.environ.get('OPENWEATHER_API_KEY_SECRET_ARN', '')
OPENWEATHER_BASE = 'https://api.openweathermap.org/data/2.5'

_secrets_client = None
_cached_openweather_api_key = None

# Feature flag: coordinate validation (default: OFF) — Bug 1.7
ENABLE_COORDINATE_VALIDATION = os.environ.get('ENABLE_COORDINATE_VALIDATION', 'false').lower() == 'true'

# Feature flag: enforce HTTPS weather API scheme consistently (default: OFF) — Bug 1.26
ENABLE_HTTPS_WEATHER_API = os.environ.get('ENABLE_HTTPS_WEATHER_API', 'false').lower() == 'true'
ENABLE_UNIFIED_CORS = os.environ.get('ENABLE_UNIFIED_CORS', 'false').lower() == 'true'


def _openweather_base_url():
    if os.environ.get('ENABLE_HTTPS_WEATHER_API', 'false').lower() == 'true':
        return OPENWEATHER_BASE.replace('http://', 'https://')
    return OPENWEATHER_BASE


def _coordinate_validation_enabled():
    return os.environ.get('ENABLE_COORDINATE_VALIDATION', 'false').lower() == 'true'


def _resolve_openweather_api_key():
    global _secrets_client, _cached_openweather_api_key

    if _cached_openweather_api_key:
        return _cached_openweather_api_key

    secret_arn = OPENWEATHER_API_KEY_SECRET_ARN
    if secret_arn:
        try:
            if _secrets_client is None:
                _secrets_client = boto3.client('secretsmanager')

            response = _secrets_client.get_secret_value(SecretId=secret_arn)
            secret_string = response.get('SecretString')
            if not secret_string and response.get('SecretBinary'):
                secret_string = base64.b64decode(response['SecretBinary']).decode('utf-8')

            candidate_key = None
            if secret_string:
                try:
                    parsed = json.loads(secret_string)
                    if isinstance(parsed, dict):
                        candidate_key = (
                            parsed.get('OPENWEATHER_API_KEY')
                            or parsed.get('openweather_api_key')
                            or parsed.get('api_key')
                            or parsed.get('key')
                        )
                    elif isinstance(parsed, str):
                        candidate_key = parsed
                except json.JSONDecodeError:
                    candidate_key = secret_string.strip()

            if candidate_key and candidate_key != 'CHANGE_ME':
                _cached_openweather_api_key = candidate_key
                logger.info('Using OpenWeather API key from Secrets Manager')
                return _cached_openweather_api_key

            logger.warning('OpenWeather secret is present but empty/invalid; falling back to environment variable')
        except Exception as exc:
            logger.warning(f'Failed to retrieve OpenWeather API key from Secrets Manager; falling back to env var. Error: {str(exc)}')

    if OPENWEATHER_API_KEY and OPENWEATHER_API_KEY != 'CHANGE_ME':
        _cached_openweather_api_key = OPENWEATHER_API_KEY
        return _cached_openweather_api_key

    return ''

# ── Security: Input validation constants ──
MAX_LOCATION_LENGTH = 100
LOCATION_PATTERN = re.compile(r'^[\w\s\-\.,\'()]+$', re.UNICODE)

# Common India district/city spelling variants across data sources
# Maps district names (from DISTRICT_MAP) to city names that OpenWeatherMap recognises
LOCATION_ALIASES = {
    # Spelling variants
    'Viluppuram': 'Villupuram',
    'Villupuram': 'Viluppuram',
    # Bangalore / Bengaluru variants
    'Bangalore Urban': 'Bengaluru',
    'Bangalore Rural': 'Bengaluru',
    'Bengaluru Urban': 'Bengaluru',
    'Bengaluru Rural': 'Bengaluru',
    # Andhra Pradesh districts → district HQ cities
    'East Godavari': 'Kakinada',
    'West Godavari': 'Eluru',
    'YSR Kadapa': 'Kadapa',
    'Sri Potti Sriramulu Nellore': 'Nellore',
    'Spsr Nellore': 'Nellore',
    'Alluri Sitharama Raju': 'Paderu',
    'Dr. B.R. Ambedkar Konaseema': 'Amalapuram',
    'NTR': 'Vijayawada',
    'Palnadu': 'Narasaraopet',
    'Bapatla': 'Bapatla',
    'Anakapalli': 'Visakhapatnam',
    'Kakinada': 'Kakinada',
    'Annamayya': 'Kadapa',
    'Sri Sathya Sai': 'Puttaparthi',
    'Tirupati': 'Tirupati',
    # Telangana districts → district HQ cities
    'Medchal-Malkajgiri': 'Secunderabad',
    'Ranga Reddy': 'Hyderabad',
    'Hanumakonda': 'Warangal',
    'Sangareddy': 'Sangareddy',
    'Jayashankar Bhupalpally': 'Warangal',
    'Jogulamba Gadwal': 'Gadwal',
    'Komaram Bheem': 'Asifabad',
    'Komaram Bheem Asifabad': 'Asifabad',
    'Bhadradri Kothagudem': 'Kothagudem',
    'Yadadri Bhuvanagiri': 'Bhongir',
    'Rajanna Sircilla': 'Karimnagar',
    'Narayanpet': 'Mahbubnagar',
    'Mahabubnagar': 'Mahbubnagar',
    'Nagarkurnool': 'Nalgonda',
    'Wanaparthy': 'Mahbubnagar',
    'Peddapalli': 'Peddapalli',
    'Mancherial': 'Mancherial',
    'Jagtial': 'Jagtial',
    'Jangaon': 'Jangaon',
    'Siddipet': 'Siddipet',
    'Medak': 'Medak',
    'Mahabubabad': 'Mahabubabad',
    'Mulugu': 'Warangal',
    'Suryapet': 'Suryapet',
    'Vikarabad': 'Vikarabad',
    'Kamareddy': 'Nizamabad',
    # Tamil Nadu districts
    'Chengalpattu': 'Chengalpattu',
    'Kancheepuram': 'Kanchipuram',
    'Kanchipuram': 'Kanchipuram',
    'Tiruvallur': 'Tiruvallur',
    'Villupuram': 'Villupuram',
    'Tiruvannamalai': 'Tiruvannamalai',
    'Kallakurichi': 'Villupuram',
    'Ranipet': 'Vellore',
    'Tirupattur': 'Vellore',
    'Mayiladuthurai': 'Mayiladuthurai',
    'Tenkasi': 'Tenkasi',
    'Krishnagiri': 'Krishnagiri',
    'The Nilgiris': 'Ooty',
    'Ramanathapuram': 'Ramanathapuram',
    'Sivaganga': 'Sivaganga',
    'Virudhunagar': 'Virudhunagar',
    'Ariyalur': 'Ariyalur',
    'Perambalur': 'Tiruchirappalli',
    'Tiruppur': 'Tiruppur',
    'Namakkal': 'Namakkal',
    'Karur': 'Karur',
    'Nagapattinam': 'Nagapattinam',
    'Thanjavur': 'Thanjavur',
    'Cuddalore': 'Cuddalore',
    # Karnataka districts
    'Dakshina Kannada': 'Mangalore',
    'Uttara Kannada': 'Karwar',
    'Hassan': 'Hassan',
    'Ramanagara': 'Bengaluru',
    'Chikkamagaluru': 'Chikmagalur',
    'Chikkaballapur': 'Kolar',
    'Kolar': 'Kolar',
    'Kodagu': 'Madikeri',
    'Yadgir': 'Yadgir',
    'Koppal': 'Koppal',
    'Haveri': 'Haveri',
    'Gadag': 'Gadag',
    'Chamarajanagar': 'Mysore',
    'Mandya': 'Mandya',
    'Tumakuru': 'Tumkur',
    'Chitradurga': 'Chitradurga',
    'Davanagere': 'Davangere',
    'Udupi': 'Udupi',
    # Kerala districts
    'Thiruvananthapuram': 'Thiruvananthapuram',
    'Ernakulam': 'Kochi',
    'Pathanamthitta': 'Pathanamthitta',
    'Alappuzha': 'Alappuzha',
    'Kottayam': 'Kottayam',
    'Idukki': 'Idukki',
    'Wayanad': 'Kalpetta',
    'Kasaragod': 'Kasaragod',
    'Kannur': 'Kannur',
    'Malappuram': 'Malappuram',
    # West Bengal districts
    'South 24 Parganas': 'Baruipur',
    'North 24 Parganas': 'Barasat',
    'Purba Medinipur': 'Tamluk',
    'Paschim Medinipur': 'Kharagpur',
    'Purba Bardhaman': 'Bardhaman',
    'Paschim Bardhaman': 'Asansol',
    'Uttar Dinajpur': 'Raiganj',
    'Dakshin Dinajpur': 'Balurghat',
    'Jhargram': 'Jhargram',
    'Kalimpong': 'Kalimpong',
    'Alipurduar': 'Alipurduar',
    'Cooch Behar': 'Koch Bihar',
    # Maharashtra districts
    'Palghar': 'Palghar',
    'Raigad': 'Alibag',
    'Sindhudurg': 'Ratnagiri',
    'Ratnagiri': 'Ratnagiri',
    'Beed': 'Beed',
    'Washim': 'Washim',
    'Hingoli': 'Hingoli',
    'Gadchiroli': 'Chandrapur',
    'Gondia': 'Gondia',
    'Wardha': 'Wardha',
    # Assam districts
    'Kamrup Metropolitan': 'Guwahati',
    'Kamrup': 'Amingaon',
    'Cachar': 'Silchar',
    'Dibrugarh': 'Dibrugarh',
    'Nagaon': 'Nagaon',
    'Sonitpur': 'Tezpur',
    'Jorhat': 'Jorhat',
    'Tinsukia': 'Tinsukia',
    'Barpeta': 'Barpeta',
    'Darrang': 'Mangaldoi',
    'Goalpara': 'Goalpara',
    'Karimganj': 'Karimganj',
    # Bihar districts
    'Purba Champaran': 'Motihari',
    'Pashchim Champaran': 'Bettiah',
    'Begusarai': 'Begusarai',
    'Samastipur': 'Samastipur',
    'Vaishali': 'Hajipur',
    'Saran': 'Chapra',
    'East Champaran': 'Motihari',
    'West Champaran': 'Bettiah',
    # Gujarat districts
    'Kachchh': 'Bhuj',
    'Kutch': 'Bhuj',
    # Rajasthan districts
    'Sri Ganganagar': 'Ganganagar',
    # Odisha districts
    'Khordha': 'Bhubaneswar',
    'Cuttack': 'Cuttack',
    'Ganjam': 'Berhampur',
    'Jagatsinghpur': 'Jagatsinghpur',
    'Kendrapara': 'Kendrapara',
    'Jajpur': 'Jajpur',
    'Mayurbhanj': 'Baripada',
    'Sundargarh': 'Rourkela',
    # Punjab districts
    'Sahibzada Ajit Singh Nagar': 'Mohali',
    'S.A.S. Nagar': 'Mohali',
    'SAS Nagar': 'Mohali',
    # Madhya Pradesh districts
    'Shahdol': 'Shahdol',
    'Hoshangabad': 'Hoshangabad',
    'Narmadapuram': 'Hoshangabad',
    # Puducherry / Pondicherry
    'Puducherry': 'Pondicherry',
    'Pondicherry': 'Pondicherry',
    'Karaikal': 'Karaikal',
    'Mahe': 'Mahe',
    'Yanam': 'Yanam',
}


def _http_get_json(url, timeout=8):
    """HTTP GET JSON using stdlib only (no third-party dependency)."""
    req = urllib.request.Request(url, headers={'User-Agent': 'smart-rural-ai-weather/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # OpenWeather returns structured JSON on 4xx/5xx — parse and return it
        try:
            body = e.read().decode('utf-8')
            return json.loads(body)
        except Exception:
            raise


def _validate_location(location):
    """Validate and sanitize location input. Returns (clean_location, error_msg)."""
    if not location or not location.strip():
        return None, 'Location is required'
    location = location.strip()[:MAX_LOCATION_LENGTH]
    # Block obvious injection attempts
    if any(ch in location for ch in ['<', '>', '{', '}', '|', ';', '`', '$', '\\']):
        return None, 'Invalid characters in location name'
    return location, None


def _validate_coordinates(lat, lon):
    """Validate latitude/longitude ranges. Returns (is_valid, error_message)."""
    if not _coordinate_validation_enabled():
        return True, None

    try:
        if lat not in (None, ''):
            lat_f = float(lat)
            if not (-90 <= lat_f <= 90):
                return False, f"Invalid latitude: {lat}. Must be between -90 and 90."
        if lon not in (None, ''):
            lon_f = float(lon)
            if not (-180 <= lon_f <= 180):
                return False, f"Invalid longitude: {lon}. Must be between -180 and 180."
        return True, None
    except (TypeError, ValueError):
        return False, 'Invalid coordinate format. Must be numeric.'

def clean_location(name):
    """Strip administrative suffixes that confuse weather APIs."""
    if not name:
        return name
    import urllib.parse
    name = urllib.parse.unquote(name)  # decode %20 etc.
    name = re.sub(
        r'\b(Tahsil|Tehsil|Block|Mandal|Taluk[ua]?|Sub-?district|District|Division|'
        r'Sub-?Division|Municipality|Corporation|Cantonment|Nagar Panchayat|Town|'
        r'Circle|Range|Panchayat|Samiti|Gram|Assembly|Constituency|Revenue|Hobli|Firka|'
        r'Community Development)\b',
        '', name, flags=re.IGNORECASE
    )
    return re.sub(r'\s{2,}', ' ', name).strip()


def _get_location_candidates(location):
    """Return ordered location candidates for weather lookup retries."""
    candidates = [location]
    alias = LOCATION_ALIASES.get(location)
    if alias:
        candidates.append(alias)
    # Heuristic fallback: common double-letter variation (e.g., Viluppuram/Villupuram)
    if 'll' in location:
        candidates.append(location.replace('ll', 'l'))
    elif 'l' in location:
        candidates.append(location.replace('l', 'll', 1))

    # Preserve order while removing duplicates/empties
    seen = set()
    ordered = []
    for cand in candidates:
        if cand and cand not in seen:
            ordered.append(cand)
            seen.add(cand)
    return ordered


def _normalize_cod(payload):
    """Normalize OpenWeather 'cod' values (can be int or str) to int when possible."""
    if not isinstance(payload, dict):
        return None
    cod = payload.get('cod')
    if isinstance(cod, int):
        return cod
    if isinstance(cod, str):
        try:
            return int(cod)
        except ValueError:
            return None
    return None


def lambda_handler(event, context):
    """
    Fetches current weather + 5-day forecast for a given location.
    Called by orchestrator Lambda or directly via API Gateway.
    Response shape matches API contract in Section 2b.
    """
    try:
        headers = event.get('headers') or {}
        origin = headers.get('origin') or headers.get('Origin')

        # CORS preflight: return immediately (do not run weather logic)
        if event.get('httpMethod') == 'OPTIONS':
            if ENABLE_UNIFIED_CORS:
                return handle_cors_preflight(origin=origin, methods='GET,POST,OPTIONS')
            return success_response({}, message='OK', origin=origin)

        # Handle API Gateway call
        if 'parameters' in event:
            # Legacy Bedrock format (fallback)
            params = {p['name']: p['value'] for p in event['parameters']}
            location = params.get('location', 'Chennai')
        else:
            # Called via API Gateway
            location = event.get('pathParameters', {}).get('location', 'Chennai')

        # Extract optional lat/lon from query params (fallback for unknown cities)
        qsp = event.get('queryStringParameters') or {}
        lat = qsp.get('lat')
        lon = qsp.get('lon')

        # Bug 1.7: explicit coordinate validation behind feature flag
        if _coordinate_validation_enabled() and (lat is not None or lon is not None):
            valid_coords, coord_err = _validate_coordinates(lat, lon)
            if not valid_coords:
                logger.warning(f"Coordinate validation failed: {coord_err}")
                return error_response(coord_err, 400, origin=origin)

        # Security: validate location input
        location, val_err = _validate_location(location)
        if val_err:
            return error_response(val_err, 400, origin=origin)

        # Existing behavior path (legacy): sanitize invalid coords by dropping them
        if lat:
            try:
                lat_f = float(lat)
                if not (-90 <= lat_f <= 90):
                    lat = None
            except (ValueError, TypeError):
                lat = None
        if lon:
            try:
                lon_f = float(lon)
                if not (-180 <= lon_f <= 180):
                    lon = None
            except (ValueError, TypeError):
                lon = None

        # Clean administrative suffixes (e.g. "Igatpuri Subdistrict" -> "Igatpuri")
        location = clean_location(location)
        logger.info(f"Cleaned location: {location}")

        resolved_openweather_api_key = _resolve_openweather_api_key()
        if not resolved_openweather_api_key:
            logger.error("OPENWEATHER_API_KEY not configured")
            return error_response('OpenWeather API key not configured', 500, origin=origin)

        # Current weather with retry logic and spelling-variant candidates
        location_candidates = _get_location_candidates(location)
        max_retries = 2
        current = None
        matched_location = location

        for candidate in location_candidates:
            current_params = urllib.parse.urlencode({
                'q': f'{candidate},IN',
                'appid': resolved_openweather_api_key,
                'units': 'metric',
            })
            current_url = f"{_openweather_base_url()}/weather?{current_params}"
            for attempt in range(max_retries):
                try:
                    logger.info(f"Fetching current weather for {candidate} (attempt {attempt + 1}/{max_retries})")
                    current = _http_get_json(current_url, timeout=8)
                    current_cod = _normalize_cod(current)

                    if current_cod == 200:
                        matched_location = candidate
                        break
                    elif current_cod == 429:
                        logger.warning(f"Rate limit hit for {candidate}")
                        if attempt < max_retries - 1:
                            import time
                            time.sleep(1)
                            continue
                    else:
                        logger.warning(f"OpenWeather miss for {candidate}: {current.get('message', 'Unknown')}")
                        break
                except (TimeoutError, socket.timeout, urllib.error.URLError):
                    logger.warning(f"Timeout on attempt {attempt + 1} for {candidate}")
                    if attempt == max_retries - 1:
                        raise
                except Exception as e:
                    logger.error(f"Request error on attempt {attempt + 1} for {candidate}: {str(e)}")
                    if attempt == max_retries - 1:
                        raise

            if current and _normalize_cod(current) == 200:
                break

        # If city name lookup failed and we have lat/lon, retry with coordinates
        if (not current or _normalize_cod(current) != 200) and lat and lon:
            logger.info(f"City name '{location}' not found, falling back to lat={lat}, lon={lon}")
            coord_params = urllib.parse.urlencode({
                'lat': lat,
                'lon': lon,
                'appid': resolved_openweather_api_key,
                'units': 'metric',
            })
            coord_url = f"{_openweather_base_url()}/weather?{coord_params}"
            try:
                coord_data = _http_get_json(coord_url, timeout=8)
                if _normalize_cod(coord_data) == 200:
                    current = coord_data
                    logger.info(f"Coordinate fallback succeeded for {location}")
            except Exception as e:
                logger.warning(f"Coordinate fallback also failed: {str(e)}")

        current_cod = _normalize_cod(current)
        if not current or current_cod != 200:
            error_msg = current.get('message', 'Unknown error') if current else 'No response'
            logger.error(f"Failed to get weather for {location}: {error_msg}")
            if current_cod == 401:
                return error_response(
                    "Weather provider authentication failed. Please verify OpenWeather API key configuration.",
                    502,
                    origin=origin,
                )
            if current_cod == 429:
                return error_response(
                    "Weather provider rate limit reached. Please try again shortly.",
                    503,
                    origin=origin,
                )
            if current_cod == 404:
                return error_response(
                    f"Weather data not available for '{location}'. Please check the location name and try again.",
                    404,
                    origin=origin,
                )

            # Security: never expose raw provider error details to client
            return error_response(
                "Weather service is temporarily unavailable. Please try again.",
                502,
                origin=origin,
            )

        # 5-day forecast with retry — use coordinates if city name failed earlier
        if lat and lon and current.get('coord'):
            forecast_params = urllib.parse.urlencode({
                'lat': lat,
                'lon': lon,
                'appid': resolved_openweather_api_key,
                'units': 'metric',
                'cnt': 40,
            })
            forecast_url = f"{_openweather_base_url()}/forecast?{forecast_params}"
        else:
            forecast_params = urllib.parse.urlencode({
                'q': f'{matched_location},IN',
                'appid': resolved_openweather_api_key,
                'units': 'metric',
                'cnt': 40,
            })
            forecast_url = f"{_openweather_base_url()}/forecast?{forecast_params}"
        
        forecast_raw = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching forecast for {location} (attempt {attempt + 1}/{max_retries})")
                forecast_raw = _http_get_json(forecast_url, timeout=8)
                if _normalize_cod(forecast_raw) == 200:
                    break
            except (TimeoutError, socket.timeout, urllib.error.URLError):
                logger.warning(f"Forecast timeout on attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    # Continue without forecast if it fails
                    forecast_raw = {'list': []}
                    break
            except Exception as e:
                logger.error(f"Forecast error on attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    forecast_raw = {'list': []}
                    break

        # Build response matching API contract field names
        weather_data = {
            "location": matched_location,
            "current": {
                "temp_celsius": current.get("main", {}).get("temp"),
                "humidity": current.get("main", {}).get("humidity"),
                "description": current.get("weather", [{}])[0].get("description", ""),
                "wind_speed_kmh": round(
                    (current.get("wind", {}).get("speed", 0)) * 3.6, 1
                ),  # m/s → km/h
                "rain_mm": current.get("rain", {}).get("1h", 0)
            },
            "forecast": [],
            "farming_advisory": ""
        }

        # Aggregate to daily forecast (group by date)
        daily = {}
        for item in forecast_raw.get("list", []):
            date = item.get("dt_txt", "")[:10]  # "2026-02-27"
            temp = item.get("main", {}).get("temp", 0)
            if date not in daily:
                daily[date] = {"temps": [], "descriptions": [], "rain": 0}
            daily[date]["temps"].append(temp)
            daily[date]["descriptions"].append(
                item.get("weather", [{}])[0].get("description", "")
            )
            daily[date]["rain"] += item.get("rain", {}).get("3h", 0)

        for date, info in list(daily.items())[:5]:  # Cap at 5 days
            weather_data["forecast"].append({
                "date": date,
                "temp_min": round(min(info["temps"]), 1),
                "temp_max": round(max(info["temps"]), 1),
                "description": max(
                    set(info["descriptions"]),
                    key=info["descriptions"].count
                ),
                "rain_probability": min(
                    100, int((info["rain"] / 5) * 100)
                )  # rough estimate
            })

        # Simple farming advisory based on conditions
        temp = weather_data["current"]["temp_celsius"] or 0
        humidity = weather_data["current"]["humidity"] or 0
        rain = weather_data["current"]["rain_mm"] or 0
        advisories = []
        if humidity > 80:
            advisories.append(
                "High humidity — risk of fungal infections. Monitor crops."
            )
        if temp > 38:
            advisories.append(
                "Extreme heat — ensure adequate irrigation."
            )
        if rain > 10:
            advisories.append(
                "Heavy rain expected — avoid pesticide spraying today."
            )
        if not advisories:
            advisories.append(
                "Conditions are normal. Good day for regular farm activities."
            )
        weather_data["farming_advisory"] = " ".join(advisories)

        logger.info(
            f"Weather for {location}: {weather_data['current']['temp_celsius']}°C"
        )

        return success_response(weather_data)

    except (TimeoutError, socket.timeout, urllib.error.URLError):
        logger.error(f"Weather API timeout for {location}")
        return error_response("Weather service timed out. Please try again.", 504)
    except Exception as e:
        logger.error(f"Weather error: {str(e)}", exc_info=True)
        # Security: never expose internal error details to client
        return error_response("Weather service is temporarily unavailable. Please try again.", 500)
