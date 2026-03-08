// src/pages/CropDoctorPage.jsx

import { useState, useRef } from 'react';
import config from '../config';
import { useLanguage } from '../contexts/LanguageContext';
import { sanitizeHtml } from '../utils/sanitize';
import { mockImageAnalyze } from '../services/mockApi';
import { apiFetch } from '../utils/apiFetch';
import ScrollPill from '../components/ScrollPill';

function CropDoctorPage() {
    const { language, t } = useLanguage();
    const [image, setImage] = useState(null);
    const [preview, setPreview] = useState(null);
    const [analysis, setAnalysis] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [cropType, setCropType] = useState('');
    const fileInputRef = useRef(null);
    const scrollRef = useRef(null);

    const CROP_OPTIONS = [
        // Cereals
        { value: 'Rice', key: 'cropRice' },
        { value: 'Wheat', key: 'cropWheat' },
        { value: 'Maize', key: 'cropMaize' },
        { value: 'Jowar', key: 'cropJowar' },
        { value: 'Bajra', key: 'cropBajra' },
        { value: 'Barley', key: 'cropBarley' },
        { value: 'Ragi', key: 'cropRagi' },
        { value: 'Small Millets', key: 'cropSmallMillets' },
        // Pulses
        { value: 'Chickpea', key: 'cropChickpea' },
        { value: 'Pigeon Pea', key: 'cropPigeonPea' },
        { value: 'Green Gram', key: 'cropGreenGram' },
        { value: 'Black Gram', key: 'cropBlackGram' },
        { value: 'Lentil', key: 'cropLentil' },
        { value: 'Peas', key: 'cropPeas' },
        { value: 'Horse Gram', key: 'cropHorseGram' },
        { value: 'Cowpea', key: 'cropCowpea' },
        { value: 'Moth Bean', key: 'cropMothBean' },
        // Vegetables
        { value: 'Tomato', key: 'cropTomato' },
        { value: 'Onion', key: 'cropOnion' },
        { value: 'Potato', key: 'cropPotato' },
        { value: 'Brinjal', key: 'cropBrinjal' },
        { value: 'Cabbage', key: 'cropCabbage' },
        { value: 'Cauliflower', key: 'cropCauliflower' },
        { value: 'Okra', key: 'cropOkra' },
        { value: 'Carrot', key: 'cropCarrot' },
        { value: 'Radish', key: 'cropRadish' },
        { value: 'Beans', key: 'cropBeans' },
        { value: 'Pumpkin', key: 'cropPumpkin' },
        // Fibre Crops
        { value: 'Cotton', key: 'cropCotton' },
        { value: 'Jute', key: 'cropJute' },
        { value: 'Hemp', key: 'cropHemp' },
        { value: 'Sunn Hemp', key: 'cropSunnHemp' },
        // Oilseeds
        { value: 'Groundnut', key: 'cropGroundnut' },
        { value: 'Soybean', key: 'cropSoybean' },
        { value: 'Mustard', key: 'cropMustard' },
        { value: 'Sunflower', key: 'cropSunflower' },
        { value: 'Sesame', key: 'cropSesame' },
        { value: 'Linseed', key: 'cropLinseed' },
        { value: 'Castor Seed', key: 'cropCastorSeed' },
        { value: 'Safflower', key: 'cropSafflower' },
        { value: 'Niger Seed', key: 'cropNigerSeed' },
        // Cash Crops
        { value: 'Sugarcane', key: 'cropSugarcane' },
        { value: 'Tobacco', key: 'cropTobacco' },
        // Plantation Crops
        { value: 'Tea', key: 'cropTea' },
        { value: 'Coffee', key: 'cropCoffee' },
        { value: 'Coconut', key: 'cropCoconut' },
        { value: 'Rubber', key: 'cropRubber' },
        { value: 'Arecanut', key: 'cropArecanut' },
        { value: 'Cocoa', key: 'cropCocoa' },
        // Spices
        { value: 'Chilli', key: 'cropChilli' },
        { value: 'Turmeric', key: 'cropTurmeric' },
        { value: 'Black Pepper', key: 'cropBlackPepper' },
        { value: 'Cardamom', key: 'cropCardamom' },
        { value: 'Ginger', key: 'cropGinger' },
        { value: 'Red Chilli', key: 'cropRedChilli' },
        { value: 'Coriander', key: 'cropCoriander' },
        { value: 'Cumin', key: 'cropCumin' },
        { value: 'Fenugreek', key: 'cropFenugreek' },
        { value: 'Clove', key: 'cropClove' },
        { value: 'Cinnamon', key: 'cropCinnamon' },
        { value: 'Nutmeg', key: 'cropNutmeg' },
        // Fruits
        { value: 'Banana', key: 'cropBanana' },
        { value: 'Mango', key: 'cropMango' },
        // Fodder
        { value: 'Millets', key: 'cropMillets' },
        { value: 'Pulses', key: 'cropPulses' },
    ];

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) {
            setError(t('cropDocImageTooLarge'));
            return;
        }
        setImage(file);
        // Revoke previous blob URL to prevent memory leak
        if (preview) URL.revokeObjectURL(preview);
        setPreview(URL.createObjectURL(file));
        setError('');
        setAnalysis('');
    };

    const compressImage = (file, maxWidth, quality) => {
        return new Promise((resolve) => {
            const img = new Image();
            const blobUrl = URL.createObjectURL(file);
            img.onload = () => {
                URL.revokeObjectURL(blobUrl); // free blob URL after image loads
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                if (width > maxWidth) {
                    height = (height * maxWidth) / width;
                    width = maxWidth;
                }
                canvas.width = width;
                canvas.height = height;
                canvas.getContext('2d').drawImage(img, 0, 0, width, height);
                canvas.toBlob(resolve, 'image/jpeg', quality);
            };
            img.src = blobUrl;
        });
    };

    const analyzeImage = async () => {
        if (!image) return;
        setLoading(true);
        setError('');

        try {
            if (config.MOCK_AI) {
                const data = await mockImageAnalyze(null, 'Crop', 'India', language);
                if (data.status === 'success') {
                    setAnalysis(data.data.analysis);
                } else {
                    setError(t('error'));
                }
                setLoading(false);
                return;
            }

            const compressed = await compressImage(image, 1024, 0.85);
            const reader = new FileReader();
            reader.onloadend = async () => {
                const base64 = reader.result.split(',')[1];
                try {
                    const res = await apiFetch(`/image-analyze`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            image_base64: base64,
                            language: language,
                            crop_type: cropType || undefined
                        })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        setAnalysis(data.data.analysis);
                    } else {
                        setError(data.error || t('error'));
                    }
                } catch {
                    setError(t('connectionError'));
                }
                setLoading(false);
            };
            reader.readAsDataURL(compressed);
        } catch {
            setError(t('connectionError'));
            setLoading(false);
        }
    };

    const resetForm = () => {
        setImage(null);
        setPreview(null);
        setAnalysis('');
        setError('');
        setCropType('');
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <div className="cropdoctor-page">
            <div className="page-header">
                <h2>
                    📸 {t('cropDocTitle')}
                </h2>
                <p>{t('cropDocSubtitle')}</p>
            </div>

            <div className="cropdoctor-page-scroll" ref={scrollRef}>

            <div>
                {/* Crop Type Dropdown — always visible */}
                <div style={{ marginBottom: '12px' }}>
                    <label style={{ fontWeight: 600, fontSize: '15px', marginBottom: '6px', display: 'block', color: 'var(--text-primary)' }}>
                        🌾 {t('cropDocSelectCropType')}
                    </label>
                    <select
                        value={cropType}
                        onChange={(e) => setCropType(e.target.value)}
                        className="form-input"
                        style={{ width: '100%', cursor: 'pointer' }}
                    >
                        <option value="" disabled>{t('cropDocSelectCropType')}</option>
                        {CROP_OPTIONS.map(c => (
                            <option key={c.value} value={c.value}>{t(c.key)}</option>
                        ))}
                    </select>
                </div>

                {/* Image Upload */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div
                        className={preview ? '' : 'upload-zone'}
                        onClick={() => fileInputRef.current.click()}
                        style={preview ? { cursor: 'pointer', padding: '16px', position: 'relative' } : {}}
                    >
                        {preview ? (
                            <>
                                <img src={preview} alt="Crop" style={{ width: '100%', borderRadius: '12px', display: 'block' }} />
                                <button
                                    onClick={(e) => { e.stopPropagation(); resetForm(); }}
                                    style={{
                                        position: 'absolute', top: 24, right: 24,
                                        background: 'rgba(0,0,0,0.6)', color: '#fff', border: 'none',
                                        borderRadius: '50%', width: 32, height: 32, cursor: 'pointer',
                                        fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center'
                                    }}
                                    title={t('cropDocRemoveImage')}
                                >✕</button>
                            </>
                        ) : (
                            <>
                                <span className="upload-icon">📷</span>
                                <p><strong>{t('cropDocUpload')}</strong></p>
                                <p>{t('cropDocDragDrop')}</p>
                                <p style={{ fontSize: '12px', color: 'var(--text-light)', marginTop: 8 }}>{t('cropDocFormats')}</p>
                            </>
                        )}
                    </div>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        onChange={handleFileChange}
                        style={{ display: 'none' }}
                    />
                </div>

                {/* Analyze Button */}
                {image && (
                    <>
                        <button
                            onClick={analyzeImage}
                            disabled={loading || !cropType}
                            className="send-btn"
                            style={{ width: '100%', padding: '16px', fontSize: '16px', borderRadius: '12px', marginTop: '12px', justifyContent: 'center', opacity: (!cropType) ? 0.5 : 1 }}
                        >
                            {loading ? `⏳ ${t('cropDocAnalyzing')}` : `🔍 ${t('cropDocAnalyze')}`}
                        </button>
                        {!cropType && (
                            <p style={{ textAlign: 'center', color: 'var(--warning)', fontSize: '13px', marginTop: '6px' }}>
                                ⚠️ {t('cropDocSelectCropType')}
                            </p>
                        )}
                    </>
                )}

                <div className="tip-box" style={{ marginTop: '14px' }}>
                    <span className="tip-icon">💡</span>
                    <span><strong>{t('cropDocTips')}:</strong> {t('cropDocTipsText')}</span>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="alert alert-error" style={{ marginTop: '18px' }}>
                    ❌ {error}
                </div>
            )}

            {/* Analysis Result */}
            {analysis && (
                <div className="card" style={{ marginTop: '18px', borderLeft: '4px solid var(--success)' }}>
                    <h3>✅ {t('cropDocResult')}</h3>
                    <div
                        style={{ lineHeight: 1.7, color: 'var(--text-secondary)' }}
                        dangerouslySetInnerHTML={{
                            __html: sanitizeHtml(analysis.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                                             .replace(/\n/g, '<br/>'))
                        }}
                    />
                    <div className="alert alert-warning" style={{ marginTop: '16px', marginBottom: 0 }}>
                        🏥 {t('cropDocDisclaimer')}
                    </div>
                </div>
            )}
            </div>{/* end cropdoctor-page-scroll */}
            <ScrollPill scrollRef={scrollRef} />
        </div>
    );
}

export default CropDoctorPage;
