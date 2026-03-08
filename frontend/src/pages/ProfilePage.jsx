// src/pages/ProfilePage.jsx

import { useState, useEffect, useCallback, useRef } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { useFarmer } from '../contexts/FarmerContext';
import { CROP_KEYS, CROP_VALUES_EN, SOIL_KEYS, SOIL_VALUES_EN, DISTRICT_MAP } from '../i18n/translations';
import { getDistrictName } from '../i18n/districtTranslations';
import LANGUAGES from '../languages';
import { apiFetch } from '../utils/apiFetch';
import * as cognitoAuth from '../services/cognitoAuth';
import ScrollPill from '../components/ScrollPill';

// Delete account confirmation phrase

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

function normalizeProfileData(raw) {
    const data = raw || {};
    const crops = Array.isArray(data.crops)
        ? data.crops.filter(Boolean)
        : (typeof data.crops === 'string'
            ? data.crops.split(',').map(c => c.trim()).filter(Boolean)
            : []);

    return {
        name: typeof data.name === 'string' ? data.name : '',
        state: typeof data.state === 'string' && data.state ? data.state : 'Tamil Nadu',
        district: typeof data.district === 'string' ? data.district : '',
        crops,
        soil_type: typeof data.soil_type === 'string' && data.soil_type ? data.soil_type : 'Alluvial',
        land_size_acres: Number.isFinite(Number(data.land_size_acres)) ? Number(data.land_size_acres) : 0,
        language: typeof data.language === 'string' && data.language ? data.language : 'ta-IN',
    };
}

function ProfilePage() {
    const { t, language, setLanguage } = useLanguage();
    const { farmerId, farmerPhone, updateProfile, deleteAccount } = useFarmer();
    const [profile, setProfile] = useState({
        name: '', state: 'Tamil Nadu', district: '', crops: [],
        soil_type: 'Alluvial', land_size_acres: 0, language: 'ta-IN'
    });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState(null);
    const scrollRef = useRef(null);

    // Change PIN state
    const [oldPin, setOldPin] = useState('');
    const [newPin, setNewPin] = useState('');
    const [confirmNewPin, setConfirmNewPin] = useState('');
    const [pinMessage, setPinMessage] = useState(null);
    const [changingPin, setChangingPin] = useState(false);

    // Delete account
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const safeCrops = Array.isArray(profile.crops) ? profile.crops : [];

    const getLocationValidationError = useCallback((p) => {
        if (!String(p?.state || '').trim()) return t('loginSelectState') || 'Please select state.';
        if (!String(p?.district || '').trim()) return t('loginSelectDistrict') || 'Please select district.';
        return null;
    }, [t]);

    useEffect(() => {
        const loadProfile = async () => {
            try {
                const res = await apiFetch(`/profile/${farmerId}`);
                const data = await res.json();
                if (data.data) setProfile(prev => ({ ...prev, ...normalizeProfileData(data.data) }));
            } catch { /* New user — use defaults */ }
        };
        loadProfile();
    }, [farmerId]);

    const handleCropToggle = (crop) => {
        setProfile(prev => ({
            ...prev,
            crops: (Array.isArray(prev.crops) ? prev.crops : []).includes(crop)
                ? (Array.isArray(prev.crops) ? prev.crops : []).filter(c => c !== crop)
                : [...(Array.isArray(prev.crops) ? prev.crops : []), crop]
        }));
    };

    const handleSave = async () => {
        const locationValidationError = getLocationValidationError(profile);
        if (locationValidationError) {
            setMessage({ type: 'error', text: `❌ ${locationValidationError}` });
            return;
        }
        setSaving(true);
        setMessage(null);
        try {
            await apiFetch(`/profile/${farmerId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(profile)
            });
            updateProfile(profile);
            setLanguage(profile.language, { persist: true });
            setMessage({ type: 'success', text: '✅ ' + t('profileSaved') });
        } catch {
            setMessage({ type: 'error', text: '❌ ' + t('profileSaveFailed') });
        }
        setSaving(false);
    };

    // ── Change PIN handler ──
    const handleChangePin = async () => {
        if (!oldPin) { setPinMessage({ type: 'error', text: '❌ ' + t('changePinOldLabel') }); return; }
        if (newPin.length < 6) { setPinMessage({ type: 'error', text: '❌ ' + t('changePinTooShort') }); return; }
        if (newPin !== confirmNewPin) { setPinMessage({ type: 'error', text: '❌ ' + t('changePinMismatch') }); return; }
        setChangingPin(true);
        setPinMessage(null);
        try {
            await cognitoAuth.changePassword(oldPin, newPin);
            setPinMessage({ type: 'success', text: '✅ ' + t('changePinSuccess') });
            setOldPin('');
            setNewPin('');
            setConfirmNewPin('');
        } catch (err) {
            const msg = err?.message || '';
            if (msg.includes('NotAuthorizedException') || msg.includes('Incorrect')) {
                setPinMessage({ type: 'error', text: '❌ ' + t('changePinWrongOld') });
            } else {
                setPinMessage({ type: 'error', text: '❌ ' + (msg || t('error')) });
            }
        }
        setChangingPin(false);
    };

    // Find localized crop name for display
    const localizedCrop = (enValue) => {
        const idx = CROP_VALUES_EN.indexOf(enValue);
        return idx >= 0 ? t(CROP_KEYS[idx]) : enValue;
    };


    const handleDeleteAccount = async () => {
        setDeleting(true);
        try {
            await deleteAccount();
        } catch (err) {
            setMessage({ type: 'error', text: 'Failed to delete account. Please try again.' });
            setDeleting(false);
            setShowDeleteConfirm(false);
        }
    };

    return (
        <div className="profile-page">
            <div className="page-header">
                <h2>👤 {t('profileTitle')}</h2>
                <p>{t('profileSubtitle')}</p>
                <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>
                    {t('profileFarmerId')}: {farmerId}
                    {farmerPhone && ` • 📞 +91 ${farmerPhone}`}
                </p>
            </div>

            <div className="profile-page-scroll" ref={scrollRef}>

            {message && (
                <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
                    {message.text}
                </div>
            )}

            {/* Personal Details */}
            <div className="card">
                <h3>📋 {t('profilePersonalDetails')}</h3>
                <div className="form-grid">
                    <div className="form-group">
                        <label>{t('profileName')} <span className="required-star">*</span></label>
                        <input className="form-input" type="text" value={profile.name}
                            onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                            onKeyDown={e => e.key === 'Enter' && handleSave()}
                            placeholder={t('profileNamePlaceholder')} />
                    </div>
                    <div className="form-group">
                        <label>{t('profileState')} <span className="required-star">*</span></label>
                        <select className="form-input" value={profile.state}
                            onChange={e => setProfile(p => ({ ...p, state: e.target.value, district: '' }))}>
                            <option value="" disabled>{t('selectState') || 'Select state...'}</option>
                            {STATE_OPTION_OBJECTS.map(s => <option key={s.value} value={s.value}>{t(s.key)}</option>)}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>{t('profileDistrict')} <span className="required-star">*</span></label>
                        <select className="form-input" value={profile.district}
                            onChange={e => setProfile(p => ({ ...p, district: e.target.value }))}>
                            <option value="" disabled>{t('loginSelectDistrict')}</option>
                            {(DISTRICT_MAP[profile.state] || []).map(d =>
                                <option key={d} value={d}>{getDistrictName(d, language)}</option>
                            )}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>{t('profileLanguage')} <span className="required-star">*</span></label>
                        <select className="form-input" value={profile.language}
                            onChange={e => {
                                const lang = e.target.value;
                                setProfile(p => ({ ...p, language: lang }));
                            }}>
                            {Object.entries(LANGUAGES).map(([code, lang]) =>
                                <option key={code} value={code}>{lang.name}</option>
                            )}
                        </select>
                    </div>
                </div>
            </div>

            {/* Farm Details */}
            <div className="card">
                <h3>🌾 {t('profileFarmDetails')}</h3>
                <div className="form-group">
                    <label>{t('profileCrops')} <span className="required-star">*</span></label>
                    <div className="crop-chips">
                        {CROP_KEYS.map((key, i) => (
                            <button
                                key={key}
                                className={`crop-chip ${safeCrops.includes(CROP_VALUES_EN[i]) ? 'selected' : ''}`}
                                onClick={() => handleCropToggle(CROP_VALUES_EN[i])}
                            >
                                {t(key)}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="form-grid">
                    <div className="form-group">
                        <label>{t('profileSoilType')} <span className="required-star">*</span></label>
                        <select className="form-input" value={profile.soil_type}
                            onChange={e => setProfile(p => ({ ...p, soil_type: e.target.value }))}>
                            <option value="" disabled>{t('selectSoilType') || 'Select soil type...'}</option>
                            {SOIL_KEYS.map((key, i) =>
                                <option key={key} value={SOIL_VALUES_EN[i]}>{t(key)}</option>
                            )}
                        </select>
                    </div>
                    <div className="form-group">
                        <label>{t('profileLandSize')} <span className="required-star">*</span></label>
                        <input className="form-input" type="number" value={profile.land_size_acres} min="0" step="0.5"
                            onChange={e => setProfile(p => ({ ...p, land_size_acres: parseFloat(e.target.value) || 0 }))}
                            onKeyDown={e => e.key === 'Enter' && handleSave()} />
                    </div>
                </div>
            </div>

            {/* Save */}
            <div className="card profile-save-card">
                <div className="profile-save-row">
                    <button onClick={handleSave} disabled={saving} className="send-btn profile-save-btn">
                        {saving ? t('saving') : t('profileSaveBtn')}
                    </button>
                </div>
            </div>

            {/* Change PIN */}
            <div className="card">
                <h3>🔐 {t('changePinTitle')}</h3>
                <p style={{ fontSize: '13px', color: '#666', marginBottom: '12px' }}>{t('changePinSubtitle')}</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>{t('changePinOldLabel')}</label>
                        <input className="form-input" type="password" maxLength={20}
                            value={oldPin} onChange={e => setOldPin(e.target.value)}
                            placeholder={t('changePinOldPlaceholder')} />
                    </div>
                    <div className="form-group">
                        <label>{t('changePinNewLabel')}</label>
                        <input className="form-input" type="password" maxLength={20}
                            value={newPin} onChange={e => setNewPin(e.target.value)}
                            placeholder={t('changePinNewPlaceholder')} />
                    </div>
                    <div className="form-group">
                        <label>{t('changePinConfirmLabel')}</label>
                        <input className="form-input" type="password" maxLength={20}
                            value={confirmNewPin} onChange={e => setConfirmNewPin(e.target.value)}
                            placeholder={t('changePinConfirmPlaceholder')}
                            onKeyDown={e => e.key === 'Enter' && !changingPin && handleChangePin()} />
                    </div>
                </div>
                {pinMessage && (
                    <div className={`alert ${pinMessage.type === 'success' ? 'alert-success' : 'alert-error'}`}>
                        {pinMessage.text}
                    </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '8px' }}>
                    <button onClick={handleChangePin} disabled={changingPin || !oldPin || newPin.length < 6 || !confirmNewPin}
                        className="send-btn" style={{ padding: '12px 48px', fontSize: '15px', borderRadius: '12px' }}>
                        {changingPin ? '⏳ ...' : `🔐 ${t('changePinBtn')}`}
                    </button>
                </div>
            </div>

            {/* Profile Summary */}
            {profile.name && (
                <div className="card">
                    <h3>📊 {t('profileSummary')}</h3>
                    <div className="profile-summary">
                        <div className="summary-item">
                            <span className="summary-label">{t('profileSumName')}</span>
                            <span className="summary-value">{profile.name}</span>
                        </div>
                        <div className="summary-item">
                            <span className="summary-label">{t('profileSumLocation')}</span>
                            <span className="summary-value">{getDistrictName(profile.district, language)}, {t(STATE_OPTION_OBJECTS.find(s => s.value === profile.state)?.key || 'selectState')}</span>
                        </div>
                        <div className="summary-item">
                            <span className="summary-label">{t('profileSumCrops')}</span>
                            <span className="summary-value">
                                {safeCrops.length > 0
                                    ? safeCrops.map(c => localizedCrop(c)).join(', ')
                                    : t('profileNoneSelected')}
                            </span>
                        </div>
                        <div className="summary-item">
                            <span className="summary-label">{t('profileSumSoil')}</span>
                            <span className="summary-value">
                                {t(SOIL_KEYS[SOIL_VALUES_EN.indexOf(profile.soil_type)] || 'soilAlluvial')}
                            </span>
                        </div>
                        <div className="summary-item">
                            <span className="summary-label">{t('profileSumLand')}</span>
                            <span className="summary-value">{profile.land_size_acres} {t('profileAcres')}</span>
                        </div>
                    </div>
                </div>
            )}

            <div className="tip-box">
                <span className="tip-icon">💡</span>
                <span>{t('profileTip')}</span>
            </div>
            {/* ── Delete Account ── */}
            <div className="delete-zone-card">
                <div className="delete-zone-inner">
                    <div className="delete-zone-badge">⚠️</div>
                    <div className="delete-zone-text">
                        <h4 className="delete-zone-title">{t('deleteProfileTitle')}</h4>
                        <p className="delete-zone-desc">{t('deleteProfileWarning')}</p>
                    </div>
                    <button
                        className="delete-zone-btn"
                        onClick={() => setShowDeleteConfirm(true)}
                        disabled={deleting}
                    >
                        🗑️ {t('deleteProfileBtn')}
                    </button>
                </div>
            </div>

            </div>{/* end profile-page-scroll */}
            <ScrollPill scrollRef={scrollRef} />

            {/* Delete Confirmation Modal */}
            {showDeleteConfirm && (
                <div className="delete-modal-overlay" onClick={() => !deleting && setShowDeleteConfirm(false)}>
                    <div className="delete-modal" onClick={e => e.stopPropagation()}>
                        <div className="delete-modal-top">
                            <div className="delete-modal-icon-ring">
                                <span style={{ fontSize: '28px' }}>🗑️</span>
                            </div>
                            <h3>{t('deleteProfileConfirmTitle')}</h3>
                            <p>{t('deleteProfileConfirmMsg')}</p>
                        </div>
                        <div className="delete-modal-actions">
                            <button
                                className="delete-modal-cancel"
                                onClick={() => setShowDeleteConfirm(false)}
                                disabled={deleting}
                            >
                                {t('deleteProfileCancel')}
                            </button>
                            <button
                                className="delete-modal-confirm"
                                onClick={handleDeleteAccount}
                                disabled={deleting}
                            >
                                {deleting
                                    ? <span className="delete-spinner" />
                                    : <><span>🗑️</span> {t('deleteProfileConfirmBtn')}</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
}

export default ProfilePage;

