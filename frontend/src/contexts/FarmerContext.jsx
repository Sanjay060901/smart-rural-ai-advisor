// src/contexts/FarmerContext.jsx
// Shared farmer identity — Cognito-authenticated, single source of truth
// Phone + PIN auth via AWS Cognito, JWT tokens on every API call

import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import config from '../config';
import * as cognitoAuth from '../services/cognitoAuth';
import { apiFetch } from '../utils/apiFetch';

const FarmerContext = createContext();

const FARMER_ID_KEY = 'farmer_id';
const FARMER_PHONE_KEY = 'farmer_phone';
const FARMER_NAME_KEY = 'farmer_name';
const APP_LANGUAGE_KEY = 'app_language';

export function FarmerProvider({ children }) {
    const [farmerId, setFarmerIdState] = useState(() => localStorage.getItem(FARMER_ID_KEY) || null);
    const [farmerPhone, setFarmerPhoneState] = useState(() => localStorage.getItem(FARMER_PHONE_KEY) || '');
    const [farmerName, setFarmerNameState] = useState(() => localStorage.getItem(FARMER_NAME_KEY) || '');
    const [farmerProfile, setFarmerProfile] = useState(null);
    const [isLoggedIn, setIsLoggedIn] = useState(() => !!localStorage.getItem(FARMER_ID_KEY));
    const [authReady, setAuthReady] = useState(false); // true once Cognito session checked
    const [needsEmailVerification, setNeedsEmailVerification] = useState(false);

    // Geolocation is intentionally disabled: location is sourced from profile only.
    const gpsLocation = null;
    const gpsCoords = null;
    const gpsStatus = 'disabled';
    const gpsError = null;
    const requestGps = useCallback(() => {}, []);
    const refreshGps = useCallback(() => {}, []);

    // On mount: restore Cognito session if it exists
    useEffect(() => {
        let didFinish = false;
        const restoreSession = async () => {
            try {
                // Race getSession against a 3-second timeout so the app
                // never gets stuck on a white screen if Cognito SDK hangs
                const session = await Promise.race([
                    cognitoAuth.getSession(),
                    new Promise(resolve => setTimeout(() => resolve(null), 3000)),
                ]);
                if (didFinish) return; // timeout already fired
                if (session && session.idToken) {
                    // Cognito session is valid — restore login state
                    const phone = session.phone?.replace('+91', '') || '';
                    const id = `ph_${phone}`;
                    localStorage.setItem(FARMER_ID_KEY, id);
                    localStorage.setItem(FARMER_PHONE_KEY, phone);
                    setFarmerIdState(id);
                    setFarmerPhoneState(phone);
                    setIsLoggedIn(true);
                    if (session.name) {
                        setFarmerNameState(session.name);
                        localStorage.setItem(FARMER_NAME_KEY, session.name);
                    }
                } else if (localStorage.getItem(FARMER_ID_KEY)) {
                    // No valid Cognito session but local storage has login — clear it
                    localStorage.removeItem(FARMER_ID_KEY);
                    localStorage.removeItem(FARMER_PHONE_KEY);
                    localStorage.removeItem(FARMER_NAME_KEY);
                    localStorage.removeItem(APP_LANGUAGE_KEY);
                    setFarmerIdState(null);
                    setFarmerPhoneState('');
                    setFarmerNameState('');
                    setIsLoggedIn(false);
                }
            } catch { /* no session */ }
            didFinish = true;
            setAuthReady(true);
        };
        restoreSession();
    }, []);

    // Load profile from DynamoDB when logged in (uses auth headers)
    useEffect(() => {
        if (!farmerId || !authReady) return;
        const loadProfile = async () => {
            try {
                const res = await apiFetch(`/profile/${farmerId}`);
                const data = await res.json();
                if (data.data) {
                    setFarmerProfile(data.data);
                }
                if (data.data && data.data.name) {
                    setFarmerNameState(data.data.name);
                    localStorage.setItem(FARMER_NAME_KEY, data.data.name);
                }
            } catch { /* offline — use cached name */ }
        };
        loadProfile();
    }, [farmerId, authReady]);

    /**
     * Check if a phone number is already registered (has a profile with a name).
     * Returns the profile data if exists, or null if not registered.
     */
    const checkPhoneExists = useCallback(async (phone) => {
        const cleanPhone = phone.replace(/\D/g, '').slice(-10);
        const id = `ph_${cleanPhone}`;
        try {
            const res = await apiFetch(`/profile/${id}`);
            const data = await res.json();
            if (data.data && data.data.name) {
                return data.data; // registered user
            }
        } catch { /* offline */ }
        return null; // not registered
    }, []);

    /**
     * Sign up a new farmer via Cognito + create DynamoDB profile.
     * @param {string} phone - 10-digit phone
     * @param {string} pin - 6+ char PIN
     * @param {string} name - Farmer name
     * @param {object} profileData - Full profile data
     * @param {string} [email] - Optional email for PIN recovery
     * @returns {Promise<object>} tokens
     */
    const signUpAndLogin = useCallback(async (phone, pin, name, profileData, email) => {
        const cleanPhone = phone.replace(/\D/g, '').slice(-10);
        const id = `ph_${cleanPhone}`;

        // 1. Sign up in Cognito (auto-confirmed via Pre-SignUp trigger)
        //    If username already exists but no DynamoDB profile exists, treat it as
        //    an orphaned Cognito user from an interrupted signup and clean it up.
        try {
            await cognitoAuth.signUp(cleanPhone, pin, name, email);
        } catch (signUpErr) {
            const msg = signUpErr?.message || '';
            if (msg.includes('UsernameExistsException') || msg.includes('already exists')) {
                let profileExists = false;
                try {
                    const res = await apiFetch(`/profile/${id}`);
                    const data = await res.json();
                    profileExists = !!(data?.data && data.data.name);
                } catch {
                    profileExists = true; // fail safe: never auto-delete on network error
                }

                if (profileExists) {
                    throw signUpErr;
                }

                // Orphaned Cognito user (no profile) → delete and retry signup once
                await apiFetch(`/profile/${id}`, { method: 'DELETE' });
                await cognitoAuth.signUp(cleanPhone, pin, name, email);
            } else {
                throw signUpErr;
            }
        }

        // 2. Sign in to get JWT tokens
        const tokens = await cognitoAuth.signIn(cleanPhone, pin);

        // 3. Set local state
        localStorage.setItem(FARMER_ID_KEY, id);
        localStorage.setItem(FARMER_PHONE_KEY, cleanPhone);
        localStorage.setItem(FARMER_NAME_KEY, name);
        setFarmerIdState(id);
        setFarmerPhoneState(cleanPhone);
        setFarmerNameState(name);
        setIsLoggedIn(true);

        // 3.5 If email was provided, trigger email verification
        if (email && email.trim()) {
            setNeedsEmailVerification(true);
            try {
                await cognitoAuth.sendEmailVerificationCode();
            } catch { /* may fail if already verified */ }
        }

        // 4. Create DynamoDB profile (now with auth token)
        const newProfile = profileData || {
            name, language: 'en-IN', state: '', district: '',
            crops: [], soil_type: '', land_size_acres: 0
        };
        if (!newProfile.name) newProfile.name = name;
        if (!String(newProfile.state || '').trim()) {
            throw new Error('State is required');
        }
        if (!String(newProfile.district || '').trim()) {
            throw new Error('District is required');
        }
        try {
            await apiFetch(`/profile/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newProfile),
            });
        } catch { /* will save later */ }
        setFarmerProfile(newProfile);
        if (newProfile?.language) {
            localStorage.setItem(APP_LANGUAGE_KEY, newProfile.language);
        }

        return tokens;
    }, []);

    /**
     * Sign in an existing farmer via Cognito.
     * @param {string} phone - 10-digit phone
     * @param {string} pin - PIN/password
     * @returns {Promise<object>} tokens
     */
    const signInWithPin = useCallback(async (phone, pin) => {
        const cleanPhone = phone.replace(/\D/g, '').slice(-10);
        const id = `ph_${cleanPhone}`;

        // 1. Cognito sign-in
        const tokens = await cognitoAuth.signIn(cleanPhone, pin);

        // 2. Set local state
        localStorage.setItem(FARMER_ID_KEY, id);
        localStorage.setItem(FARMER_PHONE_KEY, cleanPhone);
        setFarmerIdState(id);
        setFarmerPhoneState(cleanPhone);
        setIsLoggedIn(true);

        // 3. Load profile from DynamoDB
        try {
            const res = await apiFetch(`/profile/${id}`);
            const data = await res.json();
            if (data.data) {
                setFarmerProfile(data.data);
            }
            if (data.data && data.data.name) {
                setFarmerNameState(data.data.name);
                localStorage.setItem(FARMER_NAME_KEY, data.data.name);
            }
            if (data.data?.language) {
                localStorage.setItem(APP_LANGUAGE_KEY, data.data.language);
            }
        } catch { /* offline */ }

        return tokens;
    }, []);

    // Resolved location: profile district/state only
    const resolvedLocation = farmerProfile?.district
        || farmerProfile?.state
        || null;

    const resolvedCoords = null;

    // ── Logout ──
    const logout = useCallback(() => {
        cognitoAuth.signOut();
        localStorage.removeItem(FARMER_ID_KEY);
        localStorage.removeItem(FARMER_PHONE_KEY);
        localStorage.removeItem(FARMER_NAME_KEY);
        localStorage.removeItem(APP_LANGUAGE_KEY);
        localStorage.removeItem('last_activity');
        setFarmerIdState(null);
        setFarmerPhoneState('');
        setFarmerNameState('');
        setFarmerProfile(null);
        setIsLoggedIn(false);
    }, []);

    /**
     * Permanently delete this farmer's account:
     * 1. Delete DynamoDB profile
     * 2. Delete Cognito user
     * 3. Clear local state (logout)
     */
    const deleteAccount = useCallback(async () => {
        const id = farmerId;
        // 1. Delete profile from DynamoDB
        try {
            await apiFetch(`/profile/${id}`, { method: 'DELETE' });
        } catch { /* may already be gone */ }

        // 2. Delete user from Cognito
        try {
            await cognitoAuth.deleteUser();
        } catch { /* force logout anyway */ }

        // 3. Clear local state
        logout();
    }, [farmerId, logout]);

    // ── Idle timeout: auto-logout after 30 minutes of inactivity ──
    // Tracks mouse, keyboard, touch, and scroll events to detect user activity.
    // If no activity for IDLE_TIMEOUT_MS, the user is logged out automatically.
    // Also checks Cognito session validity every 5 minutes as a safety net.
    const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
    const SESSION_CHECK_MS = 5 * 60 * 1000; // check every 5 minutes
    const lastActivityRef = useRef(Date.now());
    const sessionCheckRef = useRef(null);
    const idleCheckRef = useRef(null);

    // Track user activity — update last activity timestamp
    useEffect(() => {
        if (!isLoggedIn) return;

        const updateActivity = () => {
            lastActivityRef.current = Date.now();
            // Persist to localStorage so tab reopens can detect staleness
            try { localStorage.setItem('last_activity', String(Date.now())); } catch { /* ignore */ }
        };

        const events = ['mousedown', 'keydown', 'touchstart', 'scroll', 'mousemove'];
        // Throttle: only update once per 30 seconds to avoid perf overhead
        let throttleTimer = null;
        const throttledUpdate = () => {
            if (throttleTimer) return;
            updateActivity();
            throttleTimer = setTimeout(() => { throttleTimer = null; }, 30000);
        };

        events.forEach(evt => window.addEventListener(evt, throttledUpdate, { passive: true }));
        updateActivity(); // set initial timestamp

        return () => {
            events.forEach(evt => window.removeEventListener(evt, throttledUpdate));
            if (throttleTimer) clearTimeout(throttleTimer);
        };
    }, [isLoggedIn]);

    // Periodic checks: idle timeout + Cognito session validity
    useEffect(() => {
        if (!isLoggedIn) {
            if (sessionCheckRef.current) clearInterval(sessionCheckRef.current);
            if (idleCheckRef.current) clearInterval(idleCheckRef.current);
            return;
        }

        // Check idle timeout every 60 seconds
        idleCheckRef.current = setInterval(() => {
            const elapsed = Date.now() - lastActivityRef.current;
            if (elapsed > IDLE_TIMEOUT_MS) {
                if (import.meta.env.DEV) console.warn(`[Session] Idle for ${Math.round(elapsed / 60000)} min — logging out`);
                logout();
            }
        }, 60 * 1000);

        // Check Cognito session every 5 minutes (refresh token safety net)
        const checkSession = async () => {
            try {
                const session = await cognitoAuth.getSession();
                if (!session || !session.idToken) {
                    if (import.meta.env.DEV) console.warn('[Session] Cognito session expired — logging out');
                    logout();
                }
            } catch {
                if (import.meta.env.DEV) console.warn('[Session] Cognito session check failed — logging out');
                logout();
            }
        };
        sessionCheckRef.current = setInterval(checkSession, SESSION_CHECK_MS);

        return () => {
            if (sessionCheckRef.current) clearInterval(sessionCheckRef.current);
            if (idleCheckRef.current) clearInterval(idleCheckRef.current);
        };
    }, [isLoggedIn, logout]);

    // On mount/tab-reopen: check if last activity was too long ago
    useEffect(() => {
        if (!isLoggedIn) return;
        try {
            const stored = localStorage.getItem('last_activity');
            if (stored) {
                const elapsed = Date.now() - parseInt(stored, 10);
                if (elapsed > IDLE_TIMEOUT_MS) {
                    if (import.meta.env.DEV) console.warn(`[Session] Tab reopened after ${Math.round(elapsed / 60000)} min idle — logging out`);
                    logout();
                }
            }
        } catch { /* ignore */ }
    }, [isLoggedIn, logout]);

    const updateProfile = useCallback((profile) => {
        setFarmerProfile(profile);
        if (profile?.name) {
            setFarmerNameState(profile.name);
            localStorage.setItem(FARMER_NAME_KEY, profile.name);
        }
    }, []);

    return (
        <FarmerContext.Provider value={{
            farmerId,
            farmerPhone,
            farmerName,
            farmerProfile,
            isLoggedIn,
            authReady,
            checkPhoneExists,
            signUpAndLogin,
            signInWithPin,
            logout,
            deleteAccount,
            updateProfile,
            needsEmailVerification,
            setNeedsEmailVerification,
            // GPS location
            gpsLocation,
            gpsCoords,
            gpsStatus,
            gpsError,
            requestGps,
            refreshGps,
            resolvedLocation,
            resolvedCoords,
        }}>
            {children}
        </FarmerContext.Provider>
    );
}

export function useFarmer() {
    const ctx = useContext(FarmerContext);
    if (!ctx) throw new Error('useFarmer must be used within FarmerProvider');
    return ctx;
}
