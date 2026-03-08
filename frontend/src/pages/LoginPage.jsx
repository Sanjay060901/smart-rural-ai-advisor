// src/pages/LoginPage.jsx
// Cognito-authenticated login — phone + PIN for rural farmers
// Sign-up: phone + name + profile + PIN → auto-confirmed → JWT tokens
// Sign-in: phone + PIN → JWT tokens

import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { useFarmer } from '../contexts/FarmerContext';
import config from '../config';
import { CROP_KEYS, CROP_VALUES_EN, SOIL_KEYS, SOIL_VALUES_EN, DISTRICT_MAP } from '../i18n/translations';
import { getDistrictName } from '../i18n/districtTranslations';
import { apiFetch } from '../utils/apiFetch';
// State options with translation keys for localized display
const STATE_OPTION_OBJECTS = [
    { value: 'Andhra Pradesh', key: 'stateAP' },
    { value: 'Arunachal Pradesh', key: 'stateAR' },
    { value: 'Assam', key: 'stateAS' },
    { value: 'Bihar', key: 'stateBR' },
    { value: 'Chhattisgarh', key: 'stateCG' },
    { value: 'Goa', key: 'stateGA' },
    { value: 'Gujarat', key: 'stateGJ' },
    { value: 'Haryana', key: 'stateHR' },
    { value: 'Himachal Pradesh', key: 'stateHP' },
    { value: 'Jharkhand', key: 'stateJH' },
    { value: 'Karnataka', key: 'stateKA' },
    { value: 'Kerala', key: 'stateKL' },
    { value: 'Madhya Pradesh', key: 'stateMP' },
    { value: 'Maharashtra', key: 'stateMH' },
    { value: 'Manipur', key: 'stateMN' },
    { value: 'Meghalaya', key: 'stateML' },
    { value: 'Mizoram', key: 'stateMZ' },
    { value: 'Nagaland', key: 'stateNL' },
    { value: 'Odisha', key: 'stateOD' },
    { value: 'Puducherry', key: 'statePY' },
    { value: 'Punjab', key: 'statePB' },
    { value: 'Rajasthan', key: 'stateRJ' },
    { value: 'Sikkim', key: 'stateSK' },
    { value: 'Tamil Nadu', key: 'stateTN' },
    { value: 'Telangana', key: 'stateTS' },
    { value: 'Tripura', key: 'stateTR' },
    { value: 'Uttar Pradesh', key: 'stateUP' },
    { value: 'Uttarakhand', key: 'stateUK' },
    { value: 'West Bengal', key: 'stateWB' },
];

function LoginPage() {
    const { t, language, setLanguage } = useLanguage();
    const { signUpAndLogin, signInWithPin, checkPhoneExists } = useFarmer();

    // Restore registration form from sessionStorage on refresh
    const saved = (() => {
        try {
            const raw = JSON.parse(sessionStorage.getItem('reg_form') || '{}');
            // Discard stale data from older versions that had pre-filled defaults
            if (raw._v !== 2) { sessionStorage.removeItem('reg_form'); return {}; }
            return raw;
        } catch { return {}; }
    })();

    const [phone, setPhone] = useState(saved.phone || '');
    const [pin, setPin] = useState(''); // never persist PIN
    const [name, setName] = useState(saved.name || '');
    const [mode, setMode] = useState(saved.mode === 'new' ? 'new' : 'welcome');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');

    // Forgot PIN flow state
    const [otpCode, setOtpCode] = useState('');
    const [newPin, setNewPin] = useState('');
    const [confirmPin, setConfirmPin] = useState('');
    const [otpDestination, setOtpDestination] = useState('');
    const [regOtpCode, setRegOtpCode] = useState('');
    const [regDemoOtp, setRegDemoOtp] = useState('');
    const [forgotDemoOtp, setForgotDemoOtp] = useState('');

    // Registration form fields
    const [regState, setRegState] = useState(saved.regState || '');
    const [regDistrict, setRegDistrict] = useState(saved.regDistrict || '');
    const [regCrops, setRegCrops] = useState(saved.regCrops || []);
    const [regSoilType, setRegSoilType] = useState(saved.regSoilType || '');
    const [regLandSize, setRegLandSize] = useState(saved.regLandSize || '');
    const [regLanguage, setRegLanguage] = useState(saved.regLanguage || '');

    // Persist registration form to sessionStorage
    useEffect(() => {
        if (mode === 'new') {
            sessionStorage.setItem('reg_form', JSON.stringify({
                _v: 2, phone, name, mode, regState, regDistrict, regCrops,
                regSoilType, regLandSize, regLanguage
            }));
        }
    }, [mode, phone, name, regState, regDistrict, regCrops, regSoilType, regLandSize, regLanguage]);

    const clearRegForm = useCallback(() => {
        sessionStorage.removeItem('reg_form');
    }, []);

    const isValidPhone = phone.replace(/\D/g, '').length >= 10;
    const isValidPin = pin.length >= 6;

    const handleCropToggle = (crop) => {
        setRegCrops(prev =>
            prev.includes(crop) ? prev.filter(c => c !== crop) : [...prev, crop]
        );
    };

    const getRegistrationProfileData = () => ({
        name: name.trim(),
        state: regState.trim(),
        district: regDistrict.trim(),
        crops: regCrops,
        soil_type: regSoilType,
        land_size_acres: parseFloat(regLandSize) || 0,
        language: regLanguage,
    });

    // ── Sign up new farmer: send OTP first ──
    const handleNewSignup = async () => {
        if (!isValidPhone) { setError(t('loginInvalidPhone')); return; }
        if (!name.trim()) { setError(t('loginNameRequired')); return; }
        if (!isValidPin) { setError(t('loginPinRequired')); return; }
        if (!regState) { setError(t('loginSelectState')); return; }
        if (!regDistrict) { setError(t('loginSelectDistrict')); return; }
        if (regCrops.length === 0) { setError(t('loginSelectCrop')); return; }
        if (!regLandSize || parseFloat(regLandSize) <= 0) { setError(t('loginEnterLand')); return; }
        if (!regSoilType) { setError(t('loginSelectSoilType') || 'Please select soil type.'); return; }
        if (!regLanguage) { setError(t('loginSelectLanguage') || 'Please select language.'); return; }
        setLoading(true);
        setError('');
        try {
            const cleanPhone = phone.replace(/\D/g, '').slice(-10);
            const res = await apiFetch('/otp/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: cleanPhone }),
            });
            const data = await res.json();
            if (!res.ok || data?.status === 'error') {
                throw new Error(data?.message || data?.error || t('otpSendFailed'));
            }

            setRegDemoOtp(data?.demo_otp || '');
            setRegOtpCode('');
            setOtpDestination(data?.phone_masked || `+91 ${cleanPhone}`);
            setMode('register-verify');
            setError('');
        } catch (err) {
            const msg = err?.message || '';
            if (msg.includes('UsernameExistsException') || msg.includes('already exists')) {
                setError(t('loginAlreadyRegistered'));
            } else {
                setError(msg || t('loginError'));
            }
        }
        setLoading(false);
    };

    // ── Registration: verify OTP then create account ──
    const handleRegisterVerify = async () => {
        if (!regOtpCode || regOtpCode.length !== 6) {
            setError(t('otpIncomplete') || 'Please enter the 6-digit OTP');
            return;
        }

        setLoading(true);
        setError('');
        try {
            const cleanPhone = phone.replace(/\D/g, '').slice(-10);
            const verifyRes = await apiFetch('/otp/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: cleanPhone, otp: regOtpCode }),
            });
            const verifyData = await verifyRes.json();
            if (!verifyRes.ok || verifyData?.status === 'error') {
                throw new Error(verifyData?.message || verifyData?.error || t('forgotPinInvalidOtp'));
            }

            const profileData = getRegistrationProfileData();
            await signUpAndLogin(cleanPhone, pin, name.trim(), profileData);
            clearRegForm();
            if (regLanguage !== language) {
                setLanguage(regLanguage, { persist: true });
            }
        } catch (err) {
            setError(err?.message || t('loginError'));
        }
        setLoading(false);
    };

    // ── Forgot PIN: send OTP (prototype backend flow) ──
    const handleForgotPin = async () => {
        if (!isValidPhone) { setError(t('loginInvalidPhone')); return; }
        setLoading(true);
        setError('');
        try {
            const cleanPhone = phone.replace(/\D/g, '').slice(-10);
            const res = await apiFetch('/otp/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: cleanPhone }),
            });
            const data = await res.json();
            if (!res.ok || data?.status === 'error') {
                throw new Error(data?.message || data?.error || t('otpSendFailed'));
            }

            setForgotDemoOtp(data?.demo_otp || '');
            setOtpDestination(data?.phone_masked || `+91 ${cleanPhone}`);
            setMode('reset-pin');
            setError('');
        } catch (err) {
            const msg = err?.message || '';
            setError(msg || t('loginError'));
        }
        setLoading(false);
    };

    // ── Reset PIN: verify OTP + set new PIN (prototype backend flow) ──
    const handleResetPin = async () => {
        if (!otpCode.trim()) { setError(t('forgotPinOtpRequired')); return; }
        if (newPin.length < 6) { setError(t('loginPinRequired')); return; }
        if (newPin !== confirmPin) { setError(t('forgotPinMismatch')); return; }
        setLoading(true);
        setError('');
        try {
            const cleanPhone = phone.replace(/\D/g, '').slice(-10);
            const res = await apiFetch('/pin/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: cleanPhone,
                    otp: otpCode.trim(),
                    new_pin: newPin,
                }),
            });
            const data = await res.json();
            if (!res.ok || data?.status === 'error') {
                throw new Error(data?.message || data?.error || t('forgotPinInvalidOtp'));
            }

            setMode('returning');
            setPin('');
            setOtpCode('');
            setNewPin('');
            setConfirmPin('');
            setForgotDemoOtp('');
            setSuccessMsg(t('forgotPinSuccess'));
        } catch (err) {
            const msg = err?.message || '';
            if (msg.includes('Incorrect OTP') || msg.includes('Invalid verification') || msg.includes('code')) {
                setError(t('forgotPinInvalidOtp'));
            } else if (msg.includes('ExpiredCodeException') || msg.includes('expired')) {
                setError(t('forgotPinExpiredOtp'));
            } else {
                setError(msg || t('loginError'));
            }
        }
        setLoading(false);
    };

    // ── Sign in returning farmer ──
    const handleSignIn = async () => {
        if (!isValidPhone) { setError(t('loginInvalidPhone')); return; }
        if (!isValidPin) { setError(t('loginPinRequired')); return; }
        setLoading(true);
        setError('');
        try {
            await signInWithPin(phone, pin);
            const savedLanguage = localStorage.getItem('app_language');
            if (savedLanguage) {
                setLanguage(savedLanguage, { persist: true });
            }
        } catch (err) {
            const msg = err?.message || '';
            if (msg.includes('UserNotFoundException') || msg.includes('does not exist')) {
                setMode('not-found');
                setError('');
            } else if (msg.includes('NotAuthorizedException') || msg.includes('Incorrect')) {
                setError(t('loginWrongPin'));
            } else {
                setError(msg || t('loginError'));
            }
        }
        setLoading(false);
    };

    return (
        <div className="login-page">
            <div className="login-container">
                {/* Language selector - only show on welcome screen */}
                {mode === 'welcome' && (
                    <div className="login-lang">
                        <span>🌐</span>
                        <select value={language} onChange={(e) => setLanguage(e.target.value, { persist: false })}>
                            {Object.entries(config.LANGUAGES).map(([code, lang]) => (
                                <option key={code} value={code}>{lang.name}</option>
                            ))}
                        </select>
                    </div>
                )}

                {mode === 'register-verify' && (
                    <div className="login-form">
                        <h2>{t('otpVerifyTitle')}</h2>
                        <p className="login-form-hint">
                            {t('otpEnterCode')} {otpDestination || `+91 ${phone}`}
                        </p>
                        {!!regDemoOtp && (
                            <div className="login-success" style={{ marginBottom: '10px' }}>
                                🔐 {t('otpDemoLabel')}: <strong>{regDemoOtp}</strong>
                            </div>
                        )}
                        <div className="login-form-group">
                            <label>{t('forgotPinOtpLabel') || 'OTP'}</label>
                            <input
                                type="text"
                                className="form-input"
                                maxLength={6}
                                value={regOtpCode}
                                onChange={(e) => setRegOtpCode(e.target.value.replace(/\D/g, ''))}
                                placeholder={t('forgotPinOtpPlaceholder') || 'Enter 6-digit OTP'}
                                autoFocus
                            />
                        </div>
                        {error && <div className="login-error">{error}</div>}
                        <button
                            className="login-btn login-btn-primary"
                            onClick={handleRegisterVerify}
                            disabled={loading || regOtpCode.length !== 6}
                        >
                            {loading ? '⏳ ...' : `✅ ${t('otpVerifyRegister')}`}
                        </button>
                        <button
                            className="login-btn login-btn-secondary"
                            onClick={handleNewSignup}
                            disabled={loading}
                        >
                            🔁 {t('otpResend') || 'Resend Code'}
                        </button>
                        <button
                            className="login-btn login-btn-back"
                            onClick={() => { setMode('new'); setError(''); setRegOtpCode(''); setRegDemoOtp(''); }}
                        >
                            ← {t('loginBack')}
                        </button>
                    </div>
                )}

                {/* Logo */}
                <div className="login-logo">
                    <span className="login-logo-icon">🌾</span>
                    <h1>{t('appName')}</h1>
                    <p className="login-tagline">{t('tagline')}</p>
                </div>

                {mode === 'welcome' && (
                    <div className="login-welcome">
                        <div className="login-welcome-art">
                            <div className="login-feature">🌤️ {t('loginFeatureWeather')}</div>
                            <div className="login-feature">🌱 {t('loginFeatureCrop')}</div>
                            <div className="login-feature">📋 {t('loginFeatureSchemes')}</div>
                            <div className="login-feature">🎤 {t('loginFeatureVoice')}</div>
                        </div>
                        <button className="login-btn login-btn-primary" onClick={() => setMode('new')}>
                            🚀 {t('loginNewFarmer')}
                        </button>
                        <button className="login-btn login-btn-secondary" onClick={() => setMode('returning')}>
                            🔄 {t('loginReturningFarmer')}
                        </button>
                    </div>
                )}

                {mode === 'new' && (
                    <div className="login-form login-form-register">
                        <h2>{t('loginCreateProfile')}</h2>

                        {/* Phone */}
                        <div className="login-form-group">
                            <label>{t('loginPhoneLabel')} <span className="required-star">*</span></label>
                            <div className="login-phone-input">
                                <span className="login-phone-prefix">+91</span>
                                <input
                                    type="tel"
                                    maxLength={10}
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                                    placeholder={t('loginPhonePlaceholder')}
                                    autoFocus
                                />
                            </div>
                        </div>

                        {/* Name */}
                        <div className="login-form-group">
                            <label>{t('profileName')} <span className="required-star">*</span></label>
                            <input
                                type="text"
                                className="form-input"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder={t('profileNamePlaceholder')}
                            />
                        </div>

                        {/* PIN */}
                        <div className="login-form-group">
                            <label>{t('loginPinLabel')} <span className="required-star">*</span></label>
                            <input
                                type="password"
                                className="form-input"
                                maxLength={20}
                                value={pin}
                                onChange={(e) => setPin(e.target.value)}
                                placeholder={t('loginPinPlaceholder')}
                            />
                            <span className="login-form-hint-small">{t('loginPinHint')}</span>
                        </div>

                        {/* State & District */}
                        <div className="login-form-row">
                            <div className="login-form-group">
                                <label>{t('profileState')} <span className="required-star">*</span></label>
                                <select className="form-input" value={regState}
                                    onChange={(e) => { setRegState(e.target.value); setRegDistrict(''); }}>
                                    <option value="" disabled>{t('selectState') || 'Select state...'}</option>
                                    {STATE_OPTION_OBJECTS.map(s => <option key={s.value} value={s.value}>{t(s.key)}</option>)}
                                </select>
                            </div>
                            <div className="login-form-group">
                                <label>{t('profileDistrict')} <span className="required-star">*</span></label>
                                <select className="form-input" value={regDistrict}
                                    onChange={(e) => setRegDistrict(e.target.value)}>
                                    <option value="" disabled>{t('loginSelectDistrict')}</option>
                                    {(DISTRICT_MAP[regState] || []).map(d =>
                                        <option key={d} value={d}>{getDistrictName(d, language)}</option>
                                    )}
                                </select>
                            </div>
                        </div>

                        {/* Crops */}
                        <div className="login-form-group">
                            <label>{t('profileCrops')} <span className="required-star">*</span></label>
                            <div className="crop-chips crop-chips-compact">
                                {CROP_KEYS.map((key, i) => (
                                    <button
                                        key={key}
                                        type="button"
                                        className={`crop-chip ${regCrops.includes(CROP_VALUES_EN[i]) ? 'selected' : ''}`}
                                        onClick={() => handleCropToggle(CROP_VALUES_EN[i])}
                                    >
                                        {t(key)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Soil Type, Land Size, Language */}
                        <div className="login-form-row login-form-row-3">
                            <div className="login-form-group">
                                <label>{t('profileSoilType')} <span className="required-star">*</span></label>
                                <select className="form-input" value={regSoilType}
                                    onChange={(e) => setRegSoilType(e.target.value)}>
                                    <option value="" disabled>{t('selectSoilType') || 'Select soil type...'}</option>
                                    {SOIL_KEYS.map((key, i) =>
                                        <option key={key} value={SOIL_VALUES_EN[i]}>{t(key)}</option>
                                    )}
                                </select>
                            </div>
                            <div className="login-form-group">
                                <label>{t('profileLandSize')} <span className="required-star">*</span></label>
                                <input className="form-input" type="number" value={regLandSize}
                                    min="0" step="0.5"
                                    onChange={(e) => setRegLandSize(e.target.value)}
                                    placeholder="0" />
                            </div>
                            <div className="login-form-group">
                                <label>{t('profileLanguage')} <span className="required-star">*</span></label>
                                <select className="form-input" value={regLanguage}
                                    onChange={(e) => setRegLanguage(e.target.value)}>
                                    <option value="" disabled>{t('selectLanguage') || 'Select language...'}</option>
                                    {Object.entries(config.LANGUAGES).map(([code, lang]) =>
                                        <option key={code} value={code}>{lang.name}</option>
                                    )}
                                </select>
                            </div>
                        </div>

                        {error && <div className="login-error">{error}</div>}
                        <button
                            className="login-btn login-btn-primary"
                            onClick={handleNewSignup}
                            disabled={loading || !isValidPhone || !name.trim() || !isValidPin || !regState || !regDistrict || regCrops.length === 0 || !regLandSize || !regSoilType || !regLanguage}
                        >
                            {loading ? '⏳ ...' : `✅ ${t('loginStart')}`}
                        </button>
                        <button className="login-btn login-btn-back" onClick={() => { setMode('welcome'); setError(''); clearRegForm(); }}>
                            ← {t('loginBack')}
                        </button>
                    </div>
                )}

                {mode === 'returning' && (
                    <div className="login-form">
                        <h2>{t('loginWelcomeBack')}</h2>
                        <p className="login-form-hint">{t('loginEnterPhonePin')}</p>
                        <div className="login-form-group">
                            <label>{t('loginPhoneLabel')}</label>
                            <div className="login-phone-input">
                                <span className="login-phone-prefix">+91</span>
                                <input
                                    type="tel"
                                    maxLength={10}
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                                    placeholder={t('loginPhonePlaceholder')}
                                    autoFocus
                                />
                            </div>
                        </div>
                        <div className="login-form-group">
                            <label>{t('loginPinLabel')}</label>
                            <input
                                type="password"
                                className="form-input"
                                maxLength={20}
                                value={pin}
                                onChange={(e) => setPin(e.target.value)}
                                placeholder={t('loginPinPlaceholder')}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && isValidPhone && isValidPin && !loading) {
                                        handleSignIn();
                                    }
                                }}
                            />
                        </div>
                        {successMsg && <div className="login-success">{successMsg}</div>}
                        {error && (
                            <div className="login-error">
                                {error}
                                {error === t('loginNotRegistered') && (
                                    <button
                                        className="login-error-link"
                                        onClick={() => { setMode('new'); setError(''); }}
                                    >
                                        → {t('loginNewFarmer')}
                                    </button>
                                )}
                            </div>
                        )}
                        <button
                            className="login-btn login-btn-primary"
                            onClick={handleSignIn}
                            disabled={loading || !isValidPhone || !isValidPin}
                        >
                            {loading ? '⏳ ...' : `🔓 ${t('loginSignIn')}`}
                        </button>
                        <button
                            className="login-btn-link login-forgot-pin"
                            onClick={() => { setMode('forgot-pin'); setError(''); setSuccessMsg(''); }}
                        >
                            🔑 {t('forgotPinLink')}
                        </button>
                        <button className="login-btn login-btn-back" onClick={() => { setMode('welcome'); setError(''); setSuccessMsg(''); }}>
                            ← {t('loginBack')}
                        </button>
                    </div>
                )}

                {mode === 'forgot-pin' && (
                    <div className="login-form">
                        <h2>🔑 {t('forgotPinTitle')}</h2>
                        <p className="login-form-hint">{t('forgotPinHintEmail') || t('forgotPinHint')}</p>
                        <div className="login-form-group">
                            <label>{t('loginPhoneLabel')}</label>
                            <div className="login-phone-input">
                                <span className="login-phone-prefix">+91</span>
                                <input
                                    type="tel"
                                    maxLength={10}
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                                    placeholder={t('loginPhonePlaceholder')}
                                    autoFocus
                                />
                            </div>
                        </div>
                        {error && <div className="login-error">{error}</div>}
                        <button
                            className="login-btn login-btn-primary"
                            onClick={handleForgotPin}
                            disabled={loading || !isValidPhone}
                        >
                            {loading ? '⏳ ...' : `📲 ${t('forgotPinSendOtp')}`}
                        </button>
                        <button className="login-btn login-btn-back" onClick={() => { setMode('returning'); setError(''); }}>
                            ← {t('loginBack')}
                        </button>
                    </div>
                )}

                {mode === 'reset-pin' && (
                    <div className="login-form">
                        <h2>🔐 {t('forgotPinResetTitle')}</h2>
                        <p className="login-form-hint">
                            📧 {t('forgotPinOtpSentEmail') || t('forgotPinOtpSent')}
                            {otpDestination && <strong style={{ display: 'block', marginTop: '6px', fontSize: '15px', letterSpacing: '0.5px' }}>✉️ {otpDestination}</strong>}
                        </p>
                        {!!forgotDemoOtp && (
                            <div className="login-success" style={{ marginBottom: '10px' }}>
                                🔐 {t('otpDemoLabel')}: <strong>{forgotDemoOtp}</strong>
                            </div>
                        )}
                        <div className="login-form-group">
                            <label>{t('forgotPinOtpLabel')}</label>
                            <input
                                type="text"
                                className="form-input"
                                maxLength={6}
                                value={otpCode}
                                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                                placeholder={t('forgotPinOtpPlaceholder')}
                                autoFocus
                            />
                        </div>
                        <div className="login-form-group">
                            <label>{t('forgotPinNewLabel')}</label>
                            <input
                                type="password"
                                className="form-input"
                                maxLength={20}
                                value={newPin}
                                onChange={(e) => setNewPin(e.target.value)}
                                placeholder={t('forgotPinNewPlaceholder')}
                            />
                        </div>
                        <div className="login-form-group">
                            <label>{t('forgotPinConfirmLabel')}</label>
                            <input
                                type="password"
                                className="form-input"
                                maxLength={20}
                                value={confirmPin}
                                onChange={(e) => setConfirmPin(e.target.value)}
                                placeholder={t('forgotPinConfirmPlaceholder')}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && otpCode.length >= 4 && newPin.length >= 6 && !loading) {
                                        handleResetPin();
                                    }
                                }}
                            />
                        </div>
                        {error && <div className="login-error">{error}</div>}
                        <button
                            className="login-btn login-btn-primary"
                            onClick={handleResetPin}
                            disabled={loading || !otpCode.trim() || newPin.length < 6 || !confirmPin}
                        >
                            {loading ? '⏳ ...' : `✅ ${t('forgotPinResetBtn')}`}
                        </button>
                        <button className="login-btn login-btn-back" onClick={() => { setMode('forgot-pin'); setError(''); setOtpCode(''); setNewPin(''); setConfirmPin(''); }}>
                            ← {t('loginBack')}
                        </button>
                    </div>
                )}

                {mode === 'not-found' && (
                    <div className="login-form">
                        <div className="login-not-found-card">
                            <div className="login-not-found-icon">🔍</div>
                            <h2>{t('loginNotFoundTitle')}</h2>
                            <p className="login-not-found-msg">
                                {t('loginNotFoundMsg').replace('{phone}', phone || '...')}
                            </p>
                            <button
                                className="login-btn login-btn-primary"
                                onClick={() => { setMode('new'); setError(''); setPin(''); }}
                            >
                                🚀 {t('loginNotFoundCreate')}
                            </button>
                            <button
                                className="login-btn login-btn-secondary"
                                onClick={() => { setMode('returning'); setError(''); setPin(''); }}
                            >
                                🔄 {t('loginNotFoundRetry')}
                            </button>
                            <button className="login-btn login-btn-back" onClick={() => { setMode('welcome'); setError(''); setPhone(''); setPin(''); }}>
                                ← {t('loginBack')}
                            </button>
                        </div>
                    </div>
                )}

                <div className="login-footer">
                    <p>📞 {t('helpline')}</p>
                </div>
            </div>
        </div>
    );
}

export default LoginPage;
