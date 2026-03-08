// src/hooks/useGeolocation.js
// Browser Geolocation API hook — reverse geocodes GPS → place name
// Priority: GPS (primary) → Profile location (secondary) → Explicit mention (tertiary)

import { useState, useEffect, useCallback, useRef } from 'react';
import config from '../config';
import { cleanLocationName } from '../utils/locationUtils';

const GPS_LOCATION_KEY = 'sra_gps_location';
const GPS_COORDS_KEY = 'sra_gps_coords';
const GPS_TIMESTAMP_KEY = 'sra_gps_timestamp';
const GPS_PERMISSION_KEY = 'sra_gps_permission'; // 'granted' | 'denied' | 'prompt'

// Cache GPS for 30 minutes (farmer doesn't move much)
const GPS_CACHE_MS = 30 * 60 * 1000;

/**
 * Reverse geocode lat/lng → English place name using Nominatim (free, no API key)
 */
async function reverseGeocode(lat, lng) {
    try {
        const res = await fetch(
            `${config.NOMINATIM_BASE_URL}/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10&addressdetails=1`,
            { headers: { 'Accept-Language': 'en' } }
        );
        const data = await res.json();
        const addr = data.address;
        const raw = addr.city || addr.town || addr.village || addr.county
            || addr.state_district || addr.state || 'Unknown';
        return cleanLocationName(raw);
    } catch {
        return null;
    }
}

/**
 * Hook: useGeolocation()
 * 
 * Returns:
 *   gpsLocation   — place name string (e.g. "Coimbatore") or null
 *   gpsCoords     — { lat, lng } or null
 *   gpsStatus     — 'idle' | 'requesting' | 'granted' | 'denied' | 'unavailable'
 *   gpsError      — error message or null
 *   requestGps()  — trigger permission request
 *   refreshGps()  — force re-fetch GPS
 *   clearGps()    — clear stored GPS data
 */
export function useGeolocation() {
    const [gpsLocation, setGpsLocation] = useState(() => {
        try { return localStorage.getItem(GPS_LOCATION_KEY) || null; } catch { return null; }
    });
    const [gpsCoords, setGpsCoords] = useState(() => {
        try {
            const stored = localStorage.getItem(GPS_COORDS_KEY);
            return stored ? JSON.parse(stored) : null;
        } catch { return null; }
    });
    const [gpsStatus, setGpsStatus] = useState(() => {
        try { return localStorage.getItem(GPS_PERMISSION_KEY) || 'idle'; } catch { return 'idle'; }
    });
    const [gpsError, setGpsError] = useState(null);
    const requestingRef = useRef(false);

    // Check if cached GPS is still fresh
    const isCacheFresh = useCallback(() => {
        try {
            const ts = parseInt(localStorage.getItem(GPS_TIMESTAMP_KEY) || '0');
            return Date.now() - ts < GPS_CACHE_MS;
        } catch { return false; }
    }, []);

    // Store GPS data in localStorage
    const persistGps = useCallback((location, coords) => {
        try {
            localStorage.setItem(GPS_LOCATION_KEY, location);
            localStorage.setItem(GPS_COORDS_KEY, JSON.stringify(coords));
            localStorage.setItem(GPS_TIMESTAMP_KEY, String(Date.now()));
            localStorage.setItem(GPS_PERMISSION_KEY, 'granted');
        } catch { /* quota exceeded */ }
    }, []);

    // Core GPS fetch
    const fetchGps = useCallback(() => {
        if (requestingRef.current) return;
        if (!navigator.geolocation) {
            setGpsStatus('unavailable');
            setGpsError('Geolocation not supported');
            return;
        }

        requestingRef.current = true;
        setGpsStatus('requesting');
        setGpsError(null);

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const { latitude, longitude } = position.coords;
                const coords = { lat: latitude, lng: longitude };
                setGpsCoords(coords);

                // Reverse geocode
                const placeName = await reverseGeocode(latitude, longitude);
                if (placeName) {
                    setGpsLocation(placeName);
                    persistGps(placeName, coords);
                    setGpsStatus('granted');
                } else {
                    // Use raw coords as fallback display
                    const fallback = `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`;
                    setGpsLocation(fallback);
                    persistGps(fallback, coords);
                    setGpsStatus('granted');
                }
                requestingRef.current = false;
            },
            (error) => {
                requestingRef.current = false;
                switch (error.code) {
                    case error.PERMISSION_DENIED:
                        setGpsStatus('denied');
                        setGpsError('Location permission denied');
                        try { localStorage.setItem(GPS_PERMISSION_KEY, 'denied'); } catch {}
                        break;
                    case error.POSITION_UNAVAILABLE:
                        setGpsStatus('unavailable');
                        setGpsError('Location unavailable');
                        break;
                    case error.TIMEOUT:
                        setGpsStatus('unavailable');
                        setGpsError('Location request timed out');
                        break;
                    default:
                        setGpsStatus('unavailable');
                        setGpsError('Unknown location error');
                }
            },
            {
                enableHighAccuracy: false, // coarse is fine for city-level
                timeout: 10000,
                maximumAge: GPS_CACHE_MS,
            }
        );
    }, [persistGps]);

    // Public: request GPS (user-triggered, e.g. on login)
    const requestGps = useCallback(() => {
        fetchGps();
    }, [fetchGps]);

    // Public: force refresh GPS (ignores cache)
    const refreshGps = useCallback(() => {
        try {
            localStorage.removeItem(GPS_TIMESTAMP_KEY);
        } catch {}
        fetchGps();
    }, [fetchGps]);

    // Public: clear GPS data (on logout)
    const clearGps = useCallback(() => {
        setGpsLocation(null);
        setGpsCoords(null);
        setGpsStatus('idle');
        setGpsError(null);
        try {
            localStorage.removeItem(GPS_LOCATION_KEY);
            localStorage.removeItem(GPS_COORDS_KEY);
            localStorage.removeItem(GPS_TIMESTAMP_KEY);
            localStorage.removeItem(GPS_PERMISSION_KEY);
        } catch {}
    }, []);

    // Auto-refresh if cache is stale and previously granted
    useEffect(() => {
        if (gpsStatus === 'granted' && !isCacheFresh()) {
            fetchGps();
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    return {
        gpsLocation,
        gpsCoords,
        gpsStatus,
        gpsError,
        requestGps,
        refreshGps,
        clearGps,
    };
}
