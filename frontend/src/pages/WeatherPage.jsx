// src/pages/WeatherPage.jsx

import { useState, useEffect, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useLanguage } from '../contexts/LanguageContext';
import { useFarmer } from '../contexts/FarmerContext';
import { getDistrictName } from '../i18n/districtTranslations';
import { WeatherSkeleton } from '../components/SkeletonLoader';
import { apiFetch } from '../utils/apiFetch';
import ScrollPill from '../components/ScrollPill';
import config from '../config';
import { cleanLocationName, toApiName, toDistrictMapName } from '../utils/locationUtils';

// Inline SVG map pin — zero network requests, resolution-independent
const MARKER_SVG = encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41">' +
    '<path d="M12.5 0C5.6 0 0 5.6 0 12.5 0 21.9 12.5 41 12.5 41S25 21.9 25 12.5C25 5.6 19.4 0 12.5 0zm0 18.8a6.3 6.3 0 110-12.6 6.3 6.3 0 010 12.6z" fill="#2563EB" stroke="#1E40AF"/>' +
    '</svg>'
);
const MARKER_URL = `data:image/svg+xml,${MARKER_SVG}`;
const defaultIcon = new L.Icon({
    iconUrl: MARKER_URL,
    iconRetinaUrl: MARKER_URL,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
});
L.Marker.prototype.options.icon = defaultIcon;

// Major Indian cities for quick selection
const INDIA_CITIES = [
    { name: 'Delhi', lat: 28.6139, lng: 77.2090 },
    { name: 'Mumbai', lat: 19.0760, lng: 72.8777 },
    { name: 'Chennai', lat: 13.0827, lng: 80.2707 },
    { name: 'Kolkata', lat: 22.5726, lng: 88.3639 },
    { name: 'Bangalore', lat: 12.9716, lng: 77.5946 },
    { name: 'Hyderabad', lat: 17.3850, lng: 78.4867 },
    { name: 'Ahmedabad', lat: 23.0225, lng: 72.5714 },
    { name: 'Pune', lat: 18.5204, lng: 73.8567 },
    { name: 'Jaipur', lat: 26.9124, lng: 75.7873 },
    { name: 'Lucknow', lat: 26.8467, lng: 80.9462 },
    { name: 'Chandigarh', lat: 30.7333, lng: 76.7794 },
    { name: 'Bhopal', lat: 23.2599, lng: 77.4126 },
    { name: 'Patna', lat: 25.6093, lng: 85.1376 },
    { name: 'Thiruvananthapuram', lat: 8.5241, lng: 76.9366 },
    { name: 'Guwahati', lat: 26.1445, lng: 91.7362 },
    { name: 'Bhubaneswar', lat: 20.2961, lng: 85.8245 },
    { name: 'Raipur', lat: 21.2514, lng: 81.6296 },
    { name: 'Ranchi', lat: 23.3441, lng: 85.3096 },
    { name: 'Coimbatore', lat: 11.0168, lng: 76.9558 },
    { name: 'Visakhapatnam', lat: 17.6868, lng: 83.2185 },
    { name: 'Salem', lat: 11.6643, lng: 78.1460 },
    { name: 'Madurai', lat: 9.9252, lng: 78.1198 },
    { name: 'Trichy', lat: 10.7905, lng: 78.7047 },
];

/* Map click handler component */
function MapClickHandler({ onMapClick }) {
    useMapEvents({
        click(e) {
            onMapClick(e.latlng.lat, e.latlng.lng);
        },
    });
    return null;
}

/* Fly map to a given position when it changes */
function MapFlyTo({ lat, lng }) {
    const map = useMap();
    useEffect(() => {
        if (lat && lng) {
            map.flyTo([lat, lng], 10, { duration: 1.2 });
        }
    }, [lat, lng, map]);
    return null;
}

// OpenWeatherMap condition translations
const CONDITION_MAP = {
    'en-IN': {},
    'ta-IN': { 'clear sky':'தெளிவான வானம்','few clouds':'சில மேகங்கள்','scattered clouds':'சிதறிய மேகங்கள்','broken clouds':'உடைந்த மேகங்கள்','overcast clouds':'மூடிய மேகங்கள்','light rain':'லேசான மழை','moderate rain':'மிதமான மழை','heavy intensity rain':'கனமழை','very heavy rain':'மிகக் கனமழை','extreme rain':'தீவிர மழை','light intensity drizzle':'லேசான தூறல்','drizzle':'தூறல்','thunderstorm':'இடியுடன் கூடிய மழை','thunderstorm with light rain':'லேசான மழையுடன் இடி','thunderstorm with rain':'மழையுடன் இடி','thunderstorm with heavy rain':'கனமழையுடன் இடி','mist':'மூடுபனி','haze':'புகைமூட்டம்','fog':'அடர் பனி','smoke':'புகை','dust':'தூசு','sand':'மணல்','tornado':'சூறாவளி','squalls':'புயல்காற்று','snow':'பனி','light snow':'லேசான பனி' },
    'hi-IN': { 'clear sky':'साफ़ आसमान','few clouds':'कुछ बादल','scattered clouds':'बिखरे बादल','broken clouds':'टूटे बादल','overcast clouds':'घने बादल','light rain':'हल्की बारिश','moderate rain':'मध्यम बारिश','heavy intensity rain':'भारी बारिश','very heavy rain':'बहुत भारी बारिश','extreme rain':'अत्यधिक बारिश','light intensity drizzle':'हल्की बूंदाबांदी','drizzle':'बूंदाबांदी','thunderstorm':'आंधी-तूफान','thunderstorm with light rain':'हल्की बारिश के साथ तूफान','thunderstorm with rain':'बारिश के साथ तूफान','thunderstorm with heavy rain':'भारी बारिश के साथ तूफान','mist':'धुंध','haze':'कुहासा','fog':'कोहरा','smoke':'धुआं','dust':'धूल','sand':'रेत','tornado':'बवंडर','squalls':'तेज़ हवाएं','snow':'बर्फ','light snow':'हल्की बर्फ' },
    'te-IN': { 'clear sky':'నిర్మలమైన ఆకాశం','few clouds':'కొన్ని మేఘాలు','scattered clouds':'చెదురుమదురు మేఘాలు','broken clouds':'విరిగిన మేఘాలు','overcast clouds':'మేఘావృతం','light rain':'తేలిక వర్షం','moderate rain':'మోస్తరు వర్షం','heavy intensity rain':'భారీ వర్షం','very heavy rain':'చాలా భారీ వర్షం','light intensity drizzle':'తేలిక జల్లు','drizzle':'జల్లు','thunderstorm':'ఉరుములతో తుఫాను','mist':'పొగమంచు','haze':'మసక','fog':'దట్టమైన పొగమంచు','smoke':'పొగ','dust':'ధూళి' },
    'kn-IN': { 'clear sky':'ನಿರ್ಮಲ ಆಕಾಶ','few clouds':'ಕೆಲವು ಮೋಡಗಳು','scattered clouds':'ಚದುರಿದ ಮೋಡಗಳು','broken clouds':'ಒಡೆದ ಮೋಡಗಳು','overcast clouds':'ಮೋಡ ಕವಿದ','light rain':'ಹಗುರ ಮಳೆ','moderate rain':'ಮಧ್ಯಮ ಮಳೆ','heavy intensity rain':'ಭಾರೀ ಮಳೆ','drizzle':'ತುಂತುರು','thunderstorm':'ಗುಡುಗು ಮಳೆ','mist':'ಮಂಜು','haze':'ಮಬ್ಬು','fog':'ದಟ್ಟ ಮಂಜು','smoke':'ಹೊಗೆ','dust':'ಧೂಳು' },
    'ml-IN': { 'clear sky':'തെളിഞ്ഞ ആകാശം','few clouds':'ചില മേഘങ്ങൾ','scattered clouds':'ചിതറിയ മേഘങ്ങൾ','broken clouds':'ഭാഗിക മേഘാവൃതം','overcast clouds':'മേഘാവൃതം','light rain':'നേരിയ മഴ','moderate rain':'മിതമായ മഴ','heavy intensity rain':'കനത്ത മഴ','drizzle':'ചാറ്റൽ മഴ','thunderstorm':'ഇടിമഴ','mist':'മൂടൽമഞ്ഞ്','haze':'മങ്ങൽ','fog':'കടുത്ത മൂടൽമഞ്ഞ്','smoke':'പുക','dust':'പൊടി' },
    'bn-IN': { 'clear sky':'পরিষ্কার আকাশ','few clouds':'কিছু মেঘ','scattered clouds':'বিক্ষিপ্ত মেঘ','broken clouds':'ভাঙা মেঘ','overcast clouds':'মেঘাচ্ছন্ন','light rain':'হালকা বৃষ্টি','moderate rain':'মাঝারি বৃষ্টি','heavy intensity rain':'ভারী বৃষ্টি','drizzle':'গুঁড়ি গুঁড়ি বৃষ্টি','thunderstorm':'বজ্রঝড়','mist':'কুয়াশা','haze':'ধোঁয়াশা','fog':'ঘন কুয়াশা','smoke':'ধোঁয়া','dust':'ধুলো' },
    'mr-IN': { 'clear sky':'स्वच्छ आकाश','few clouds':'थोडे ढग','scattered clouds':'विखुरलेले ढग','broken clouds':'तुटलेले ढग','overcast clouds':'ढगाळ','light rain':'हलका पाऊस','moderate rain':'मध्यम पाऊस','heavy intensity rain':'जोरदार पाऊस','drizzle':'रिमझिम','thunderstorm':'वादळी पाऊस','mist':'धुके','haze':'कुहरा','fog':'दाट धुके','smoke':'धूर','dust':'धूळ' },
    'gu-IN': { 'clear sky':'સ્વચ્છ આકાશ','few clouds':'થોડા વાદળો','scattered clouds':'વિખરાયેલા વાદળો','broken clouds':'તૂટેલા વાદળો','overcast clouds':'વાદળછાયું','light rain':'હળવો વરસાદ','moderate rain':'મધ્યમ વરસાદ','heavy intensity rain':'ભારે વરસાદ','drizzle':'ઝરમર','thunderstorm':'વીજળી સાથે વરસાદ','mist':'ઝાકળ','haze':'ધૂંધ','fog':'ગાઢ ધુમ્મસ','smoke':'ધુમાડો','dust':'ધૂળ' },
    'pa-IN': { 'clear sky':'ਸਾਫ਼ ਅਸਮਾਨ','few clouds':'ਕੁਝ ਬੱਦਲ','scattered clouds':'ਖਿੱਲਰੇ ਬੱਦਲ','broken clouds':'ਟੁੱਟੇ ਬੱਦਲ','overcast clouds':'ਬੱਦਲਵਾਈ','light rain':'ਹਲਕੀ ਬਾਰਿਸ਼','moderate rain':'ਦਰਮਿਆਨੀ ਬਾਰਿਸ਼','heavy intensity rain':'ਭਾਰੀ ਬਾਰਿਸ਼','drizzle':'ਫੁਹਾਰ','thunderstorm':'ਗਰਜ ਨਾਲ ਮੀਂਹ','mist':'ਧੁੰਦ','haze':'ਕੋਹਰਾ','fog':'ਸੰਘਣੀ ਧੁੰਦ','smoke':'ਧੂੰਆਂ','dust':'ਧੂੜ' },
    'or-IN': { 'clear sky':'ସ୍ୱଚ୍ଛ ଆକାଶ','few clouds':'କିଛି ମେଘ','scattered clouds':'ବିଖଣ୍ଡିତ ମେଘ','broken clouds':'ଭଗ୍ନ ମେଘ','overcast clouds':'ମେଘାଚ୍ଛନ୍ନ','light rain':'ହାଲକା ବର୍ଷା','moderate rain':'ମଧ୍ୟମ ବର୍ଷା','heavy intensity rain':'ଭାରି ବର୍ଷା','drizzle':'ଝିରିଝିରି','thunderstorm':'ବଜ୍ରପାତ ସହ ବର୍ଷା','mist':'କୁହୁଡ଼ି','haze':'ଧୂଆଁ','fog':'ଘନ କୁହୁଡ଼ି','smoke':'ଧୂଆଁ','dust':'ଧୂଳି' },
    'as-IN': { 'clear sky':'পৰিষ্কাৰ আকাশ','few clouds':'কিছু ডাৱৰ','scattered clouds':'সিঁচৰতি ডাৱৰ','broken clouds':'ভঙা ডাৱৰ','overcast clouds':'ডাৱৰীয়া','light rain':'লঘু বৰষুণ','moderate rain':'মধ্যমীয়া বৰষুণ','heavy intensity rain':'ভাৰী বৰষুণ','drizzle':'টোপালটোপাল','thunderstorm':'ঢেৰেকনি','mist':'কুঁৱলী','haze':'ধোঁৱা-কুঁৱলী','fog':'ডাঠ কুঁৱলী','smoke':'ধোঁৱা','dust':'ধূলি' },
    'ur-IN': { 'clear sky':'صاف آسمان','few clouds':'کچھ بادل','scattered clouds':'بکھرے بادل','broken clouds':'ٹوٹے بادل','overcast clouds':'ابر آلود','light rain':'ہلکی بارش','moderate rain':'معتدل بارش','heavy intensity rain':'بھاری بارش','drizzle':'بوندا باندی','thunderstorm':'آندھی طوفان','mist':'دھند','haze':'کہر','fog':'گہری دھند','smoke':'دھواں','dust':'گرد' },
};

function translateCondition(desc, lang) {
    if (!desc) return '';
    const map = CONDITION_MAP[lang];
    if (!map) return desc;
    const lower = desc.toLowerCase();
    return map[lower] || desc;
}

function WeatherPage() {
    const { language, t } = useLanguage();
    const {
        farmerProfile,
        authReady,
        resolvedLocation,
    } = useFarmer();

    // Avoid premature Chennai fallback before profile finishes restoring.
    const hasProfileLocation = !!(farmerProfile?.district || farmerProfile?.state);
    const canUseFallback = authReady && !hasProfileLocation;
    const profileLocation = resolvedLocation || (canUseFallback ? 'Chennai' : '');
    const initialCoords = { lat: 22.5, lng: 82.0 };

    const [locationEn, setLocationEn] = useState(profileLocation || ''); // English name for API
    const [locationDisplay, setLocationDisplay] = useState(getDistrictName(profileLocation || '', language)); // translated for UI
    const [weather, setWeather] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [markerPos, setMarkerPos] = useState({ lat: initialCoords.lat, lng: initialCoords.lng });
    const [clickedPlace, setClickedPlace] = useState(profileLocation || ''); // English internally
    const [flyTarget, setFlyTarget] = useState(null);

    // Autocomplete state
    const [suggestions, setSuggestions] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const debounceRef = useRef(null);
    const searchBoxRef = useRef(null);
    const scrollRef = useRef(null);

    // Helper: set both English + display name together
    const setLocationBoth = useCallback((engName) => {
        setLocationEn(engName);
        setLocationDisplay(getDistrictName(engName, language));
    }, [language]);

    const fetchWeather = async (loc, coords) => {
        if (!loc || loc === 'Loading...') return;
        setLoading(true);
        setError(null);
        setWeather(null);
        try {
            // Normalize district name to API-friendly name (e.g. Kancheepuram → Kanchipuram)
            const apiLoc = toApiName(loc);
            // Pass lat/lon only when explicitly known (map click/city pick).
            // For profile-based lookups, location name is sufficient.
            const latlon = coords || null;
            const qs = latlon ? `?lat=${latlon.lat}&lon=${latlon.lng || latlon.lon}` : '';
            const res = await apiFetch(`/weather/${encodeURIComponent(apiLoc)}${qs}`);
            const data = await res.json();
            
            if (!res.ok) {
                // API returned an error
                const errorMsg = data.message || `API returned ${res.status}`;
                if (import.meta.env.DEV) console.error('Weather API error:', errorMsg);
                setError(t('weatherFetchError') + ': ' + errorMsg);
                setLoading(false);
                return;
            }
            
            if (data.status === 'success' && data.data) {
                setWeather(data.data);
            } else if (data.current) {
                setWeather(data);
            } else {
                if (import.meta.env.DEV) console.error('Unexpected weather data format:', data);
                setError(t('weatherNoData'));
            }
        } catch (err) {
            if (import.meta.env.DEV) console.error('Weather fetch error:', err);
            // More specific error messages
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
                setError(t('weatherFetchError') + ': Network error. Please check your connection.');
            } else if (err.name === 'AbortError') {
                setError(t('weatherFetchError') + ': Request timeout. Please try again.');
            } else {
                setError(t('weatherFetchError') + ': ' + err.message);
            }
            setWeather(null);
        }
        setLoading(false);
    };

    // Reverse geocode lat/lng to place name using Nominatim
    const reverseGeocode = useCallback(async (lat, lng) => {
        try {
            const res = await fetch(
                `${config.NOMINATIM_BASE_URL}/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10&addressdetails=1`,
                { headers: { 'Accept-Language': 'en' } }
            );
            const data = await res.json();
            const addr = data.address;
            const raw = addr.city || addr.town || addr.village || addr.county || addr.state_district || addr.state || 'Unknown';
            const cleaned = cleanLocationName(raw);
            // Map Nominatim name back to DISTRICT_MAP canonical name for translations
            // e.g. "Kanchipuram" → "Kancheepuram" so getDistrictName() finds the entry
            return toDistrictMapName(cleaned);
        } catch {
            return `${lat.toFixed(2)},${lng.toFixed(2)}`;
        }
    }, []);

    const handleMapClick = useCallback(async (lat, lng) => {
        setMarkerPos({ lat, lng });
        setFlyTarget(null); // don't fly on click — user already clicked the spot
        setClickedPlace('Loading...');
        setLocationDisplay('...');
        const placeName = await reverseGeocode(lat, lng);
        setClickedPlace(placeName);
        setLocationBoth(placeName);
        fetchWeather(placeName, { lat, lng });
    }, [reverseGeocode, setLocationBoth]);

    const handleCityClick = useCallback((city) => {
        setMarkerPos({ lat: city.lat, lng: city.lng });
        setFlyTarget({ lat: city.lat, lng: city.lng });
        setClickedPlace(city.name);
        setLocationBoth(city.name);
        fetchWeather(city.name, { lat: city.lat, lng: city.lng });
    }, [setLocationBoth]);

    const handleSearch = async () => {
        if (!locationDisplay.trim()) return;
        // Use English name if available, else use what user typed
        const searchTerm = locationEn || cleanLocationName(locationDisplay.trim());
        setShowSuggestions(false);
        setSuggestions([]);
        setClickedPlace(searchTerm);
        setLocationBoth(searchTerm);
        // Forward geocode first, then pass coordinates to weather fetch
        const coords = await forwardGeocode(searchTerm);
        fetchWeather(searchTerm, coords);
    };

    // Forward geocode: get lat/lng, fly map there, and return coords for weather fetch
    const forwardGeocode = useCallback(async (query) => {
        // Normalize district name for better Nominatim results
        // e.g. "Kancheepuram" → "Kanchipuram", "Bangalore Urban" → "Bengaluru"
        const apiQuery = toApiName(query);
        try {
            const res = await fetch(
                `${config.NOMINATIM_BASE_URL}/search?format=json&q=${encodeURIComponent(apiQuery)},India&limit=1&addressdetails=1`,
                { headers: { 'Accept-Language': 'en' } }
            );
            const results = await res.json();
            if (results.length > 0) {
                const { lat, lon } = results[0];
                const latN = parseFloat(lat);
                const lngN = parseFloat(lon);
                setMarkerPos({ lat: latN, lng: lngN });
                setFlyTarget({ lat: latN, lng: lngN });
                return { lat: latN, lng: lngN };
            }
            // If API name failed, try original name as fallback
            if (apiQuery !== query) {
                const res2 = await fetch(
                    `${config.NOMINATIM_BASE_URL}/search?format=json&q=${encodeURIComponent(query)},India&limit=1&addressdetails=1`,
                    { headers: { 'Accept-Language': 'en' } }
                );
                const results2 = await res2.json();
                if (results2.length > 0) {
                    const { lat, lon } = results2[0];
                    const latN = parseFloat(lat);
                    const lngN = parseFloat(lon);
                    setMarkerPos({ lat: latN, lng: lngN });
                    setFlyTarget({ lat: latN, lng: lngN });
                    return { lat: latN, lng: lngN };
                }
            }
        } catch { /* ignore geocode failure */ }
        return null;
    }, []);

    // Autocomplete: debounced forward geocode search as user types
    const handleLocationInput = useCallback((value) => {
        setLocationDisplay(value);
        setLocationEn(''); // user is typing freely, clear English mapping
        if (debounceRef.current) clearTimeout(debounceRef.current);
        if (!value.trim() || value.trim().length < 2) {
            setSuggestions([]);
            setShowSuggestions(false);
            return;
        }
        debounceRef.current = setTimeout(async () => {
            try {
                const res = await fetch(
                    `${config.NOMINATIM_BASE_URL}/search?format=json&q=${encodeURIComponent(value)},India&limit=5&addressdetails=1`,
                    { headers: { 'Accept-Language': 'en' } }
                );
                const results = await res.json();
                const items = results
                    .filter(r => r.lat && r.lon)
                    .map(r => ({
                        name: toDistrictMapName(cleanLocationName(r.address?.city || r.address?.town || r.address?.village || r.address?.county || r.address?.state_district || r.display_name.split(',')[0])),
                        display: r.display_name.length > 60 ? r.display_name.substring(0, 60) + '…' : r.display_name,
                        lat: parseFloat(r.lat),
                        lng: parseFloat(r.lon),
                    }));
                // Deduplicate by name
                const seen = new Set();
                const unique = items.filter(i => {
                    if (seen.has(i.name)) return false;
                    seen.add(i.name);
                    return true;
                });
                setSuggestions(unique);
                setShowSuggestions(unique.length > 0);
            } catch {
                setSuggestions([]);
                setShowSuggestions(false);
            }
        }, 350);
    }, []);

    const handleSuggestionClick = useCallback((s) => {
        setClickedPlace(s.name);
        setLocationBoth(s.name);
        setMarkerPos({ lat: s.lat, lng: s.lng });
        setFlyTarget({ lat: s.lat, lng: s.lng });
        setSuggestions([]);
        setShowSuggestions(false);
        fetchWeather(s.name, { lat: s.lat, lng: s.lng });
    }, [setLocationBoth]);

    // Close suggestions on outside click
    useEffect(() => {
        const handler = (e) => {
            if (searchBoxRef.current && !searchBoxRef.current.contains(e.target)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Track whether user has manually interacted (search, click, city pick)
    const userOverrodeRef = useRef(false);
    const prevProfileLocRef = useRef(profileLocation);

    // Wrap user-initiated actions to set the override flag
    const handleMapClickWrapped = useCallback(async (lat, lng) => {
        userOverrodeRef.current = true;
        return handleMapClick(lat, lng);
    }, [handleMapClick]);

    const handleCityClickWrapped = useCallback((city) => {
        userOverrodeRef.current = true;
        return handleCityClick(city);
    }, [handleCityClick]);

    const handleSearchWrapped = async () => {
        userOverrodeRef.current = true;
        return handleSearch();
    };

    const handleSuggestionClickWrapped = useCallback((s) => {
        userOverrodeRef.current = true;
        return handleSuggestionClick(s);
    }, [handleSuggestionClick]);

    useEffect(() => {
        if (!profileLocation) return;
        // Skip if user manually picked a location (search, map click, city button)
        if (userOverrodeRef.current) return;
        // Skip if profileLocation hasn't changed (avoids duplicate fetches)
        if (prevProfileLocRef.current === profileLocation) return;
        prevProfileLocRef.current = profileLocation;

        // Re-run when profileLocation upgrades from 'Chennai' fallback → real profile/GPS value
        setLocationBoth(profileLocation);
        setClickedPlace(profileLocation);
        // Geocode district name first to get coordinates, then fetch weather with coords
        (async () => {
            const coords = await forwardGeocode(profileLocation);
            fetchWeather(profileLocation, coords);
        })();
    }, [profileLocation]);

    // Initial fetch on mount (uses whatever profileLocation is at mount time)
    useEffect(() => {
        if (!profileLocation) return;
        // Geocode district name first to get coordinates, then fetch weather with coords
        (async () => {
            const coords = await forwardGeocode(profileLocation);
            fetchWeather(profileLocation, coords);
        })();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Re-translate display name when language changes
    useEffect(() => {
        if (locationEn) {
            setLocationDisplay(getDistrictName(locationEn, language));
        }
    }, [language]); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <div className="weather-page">
            <div className="page-header">
                <h2>🌤️ {t('weatherTitle')}</h2>
                <p>{t('weatherSubtitle')}</p>
            </div>

            <div className="weather-page-scroll" ref={scrollRef}>

            {/* Map + Search Section */}
            <div className="weather-map-section">
                {/* Interactive Map */}
                <div className="weather-map-container">
                    <MapContainer
                        center={[22.5, 82.0]}
                        zoom={5}
                        className="weather-map"
                        scrollWheelZoom={true}
                        preferCanvas={true}
                        zoomSnap={0.5}
                        wheelDebounceTime={100}
                    >
                        <TileLayer
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
                            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
                            subdomains="abcd"
                            maxZoom={20}
                            keepBuffer={4}
                            updateWhenZooming={false}
                            updateWhenIdle={true}
                        />
                        <MapClickHandler onMapClick={handleMapClickWrapped} />
                        {flyTarget && <MapFlyTo lat={flyTarget.lat} lng={flyTarget.lng} />}
                        <Marker position={[markerPos.lat, markerPos.lng]}>
                            <Popup>
                                <strong>📍 {getDistrictName(clickedPlace, language)}</strong>
                            </Popup>
                        </Marker>
                    </MapContainer>
                    <p className="map-hint">👆 {t('weatherMapHint')}</p>
                </div>

                {/* Quick Cities + Search */}
                <div className="weather-sidebar">
                    {/* Search with autocomplete */}
                    <div className="weather-search-box" ref={searchBoxRef} style={{ position: 'relative' }}>
                        <div className="search-bar" style={{ flex: 1 }}>
                            <span className="search-icon">🔍</span>
                            <input
                                type="text"
                                value={locationDisplay}
                                onChange={(e) => handleLocationInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSearchWrapped()}
                                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                                placeholder={t('weatherSearch')}
                                autoComplete="off"
                            />
                        </div>
                        <button type="button" onClick={handleSearchWrapped} className="send-btn" style={{ borderRadius: '12px', padding: '0 20px', height: 'auto', alignSelf: 'stretch' }}>
                            {t('search')}
                        </button>
                        {/* Autocomplete dropdown */}
                        {showSuggestions && suggestions.length > 0 && (
                            <div className="weather-autocomplete-dropdown">
                                {suggestions.map((s, i) => (
                                    <div
                                        key={i}
                                        className="weather-autocomplete-item"
                                        onClick={() => handleSuggestionClickWrapped(s)}
                                    >
                                        <span className="autocomplete-name">📍 {getDistrictName(s.name, language)}</span>
                                        <span className="autocomplete-detail">{s.display}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Quick city buttons */}
                    <h4 className="weather-cities-title">📍 {t('weatherQuickSelect')}</h4>
                    <div className="weather-cities-grid">
                        {INDIA_CITIES.map((city) => (
                            <button
                                key={city.name}
                                className={`weather-city-btn ${clickedPlace === city.name ? 'active' : ''}`}
                                onClick={() => handleCityClickWrapped(city)}
                            >
                                {getDistrictName(city.name, language)}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Selected location */}
            {clickedPlace && !loading && (
                <div className="weather-location-badge">
                    📍 {t('weatherShowingFor')}: <strong>{getDistrictName(clickedPlace, language)}</strong>
                </div>
            )}

            {loading && <WeatherSkeleton />}

            {error && !loading && (
                <div className="alert" style={{ marginBottom: '18px', background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: '12px', padding: '14px 18px' }}>
                    ⚠️ {error}
                </div>
            )}

            {/* Stats */}
            {weather?.current && !loading && (
                <div className="stat-grid">
                    <div className="stat-card">
                        <span className="stat-icon">🌡️</span>
                        <div className="stat-value">{weather.current.temp_celsius}°C</div>
                        <div className="stat-label">{t('weatherTemp')}</div>
                    </div>
                    <div className="stat-card">
                        <span className="stat-icon">💧</span>
                        <div className="stat-value">{weather.current.humidity}%</div>
                        <div className="stat-label">{t('weatherHumidity')}</div>
                    </div>
                    <div className="stat-card">
                        <span className="stat-icon">🌧️</span>
                        <div className="stat-value">{weather.current.rain_mm || '0'} mm</div>
                        <div className="stat-label">{t('weatherRainfall')}</div>
                    </div>
                    <div className="stat-card">
                        <span className="stat-icon">💨</span>
                        <div className="stat-value">{weather.current.wind_speed_kmh} km/h</div>
                        <div className="stat-label">{t('weatherWind')}</div>
                    </div>
                </div>
            )}

            {weather?.current?.description && !loading && (
                <div className="alert alert-info" style={{ marginTop: '18px' }}>
                    ☁️ <strong>{t('weatherCondition')}:</strong>&nbsp;{translateCondition(weather.current.description, language)}
                </div>
            )}

            {/* Farming Advisory */}
            {weather?.current && !loading && (() => {
                const temp = weather.current.temp_celsius || 0;
                const humidity = weather.current.humidity || 0;
                const rain = weather.current.rain_mm || 0;
                const parts = [];
                if (humidity > 80) parts.push(t('advHighHumidity'));
                if (temp > 38) parts.push(t('advExtremeHeat'));
                if (rain > 10) parts.push(t('advHeavyRain'));
                if (parts.length === 0) parts.push(t('advNormal'));
                return (
                    <div className="card" style={{ marginTop: '18px', borderLeft: '4px solid var(--primary)' }}>
                        <h3>🌾 {t('weatherAdvisory')}</h3>
                        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>{parts.join(' ')}</p>
                    </div>
                );
            })()}

            {/* 5-Day Forecast */}
            {weather?.forecast?.length > 0 && !loading && (
                <div style={{ marginTop: '24px' }}>
                    <h3 style={{ marginBottom: '14px', fontSize: '18px', fontWeight: 600 }}>
                        📅 {t('weatherForecast')}
                    </h3>
                    <div className="forecast-grid">
                        {weather.forecast.map((day, i) => (
                            <div key={i} className="forecast-card">
                                <strong>{day.date}</strong>
                                <p>🌡️ {day.temp_min}–{day.temp_max}°C</p>
                                <p>☁️ {translateCondition(day.description, language)}</p>
                                <p>🌧️ {day.rain_probability}% {t('weatherRainChance')}</p>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            </div>{/* end weather-page-scroll */}
            <ScrollPill scrollRef={scrollRef} />
        </div>
    );
}

export default WeatherPage;
