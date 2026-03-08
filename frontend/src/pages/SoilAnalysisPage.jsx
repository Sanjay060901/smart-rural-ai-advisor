// src/pages/SoilAnalysisPage.jsx
// AI-powered soil health analysis and fertilizer recommendation

import { useState, useRef, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { sanitizeHtml } from '../utils/sanitize';
import { useFarmer } from '../contexts/FarmerContext';
import config from '../config';
import { generateAsyncTts } from '../utils/asyncTts';
import { apiFetch } from '../utils/apiFetch';

const PH_RANGES = [
    { value: 'Below 4.5 (Very Acidic)', key: 'phVeryAcidic' },
    { value: '4.5 - 5.5 (Acidic)', key: 'phAcidic' },
    { value: '5.5 - 6.5 (Slightly Acidic)', key: 'phSlightlyAcidic' },
    { value: '6.5 - 7.5 (Neutral)', key: 'phNeutral' },
    { value: '7.5 - 8.5 (Alkaline)', key: 'phAlkaline' },
    { value: 'Above 8.5 (Very Alkaline)', key: 'phVeryAlkaline' },
    { value: "Don't know", key: 'phDontKnow' },
];
const NUTRIENT_LEVELS = [
    { value: 'Low', key: 'nutrientLow' },
    { value: 'Medium', key: 'nutrientMedium' },
    { value: 'High', key: 'nutrientHigh' },
    { value: "Don't know", key: 'nutrientDontKnow' },
];
const SOIL_COLORS = [
    { value: 'Dark Brown/Black', key: 'colorDarkBrown' },
    { value: 'Red/Reddish', key: 'colorRed' },
    { value: 'Yellow/Light Brown', key: 'colorYellow' },
    { value: 'Grey', key: 'colorGrey' },
    { value: 'White (salt crust)', key: 'colorWhiteSalt' },
];
const DRAINAGE = [
    { value: 'Water stands for days', key: 'drainageStands' },
    { value: 'Drains in a few hours', key: 'drainageHours' },
    { value: 'Drains quickly', key: 'drainageQuick' },
    { value: 'Very dry, cracks easily', key: 'drainageDryCracks' },
];
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

const LANG_NAMES = {
    'en-IN': 'English', 'hi-IN': 'Hindi', 'ta-IN': 'Tamil', 'te-IN': 'Telugu',
    'kn-IN': 'Kannada', 'ml-IN': 'Malayalam', 'bn-IN': 'Bengali', 'mr-IN': 'Marathi',
    'gu-IN': 'Gujarati', 'pa-IN': 'Punjabi', 'or-IN': 'Odia', 'as-IN': 'Assamese', 'ur-IN': 'Urdu'
};

function SoilAnalysisPage() {
    const { language, t } = useLanguage();
    const { farmerId, farmerProfile } = useFarmer();
    const [ph, setPh] = useState('');
    const [nitrogen, setNitrogen] = useState('');
    const [phosphorus, setPhosphorus] = useState('');
    const [potassium, setPotassium] = useState('');
    const [soilColor, setSoilColor] = useState('');
    const [drainage, setDrainage] = useState('');
    const [crop, setCrop] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const resultRef = useRef(null);

    const handleAnalyze = async () => {
        if (!ph && !soilColor && !drainage) {
            setError(t('soilSelectRequired') || 'Please fill in at least one soil parameter.');
            return;
        }
        setError('');
        setLoading(true);
        setResult(null);

        const soilDetails = [];
        if (ph) soilDetails.push(`pH Level: ${ph}`);
        if (nitrogen) soilDetails.push(`Nitrogen (N): ${nitrogen}`);
        if (phosphorus) soilDetails.push(`Phosphorus (P): ${phosphorus}`);
        if (potassium) soilDetails.push(`Potassium (K): ${potassium}`);
        if (soilColor) soilDetails.push(`Soil Color/Appearance: ${soilColor}`);
        if (drainage) soilDetails.push(`Water Drainage: ${drainage}`);
        const targetCrop = crop || 'General';
        const location = [farmerProfile?.district, farmerProfile?.state].filter(Boolean).join(', ') || 'India';

        const prompt = `Analyze the following soil test data and provide a detailed agricultural soil health report for an Indian farmer.

Soil Data:
${soilDetails.length ? soilDetails.map(d => `- ${d}`).join('\n') : '- No lab data provided (use visual observations)'}
- Target Crop: ${targetCrop}
- Location: ${location}

Provide these sections:
1. Soil Health Rating (Good / Moderate / Poor) with brief explanation
2. Key Issues Found — list specific problems based on the inputs
3. Fertilizer Recommendation — exact NPK ratio, brand names available in India, dosage per acre
4. Organic Amendments — compost, vermicompost, green manure suggestions
5. 3-Month Soil Improvement Plan — month-wise action items
6. Best Crops for This Soil — top 5 crops suited to these soil conditions
7. Warning Signs to Watch — what to look for in the field
8. Estimated Cost — approximate cost per acre in INR

Keep advice practical for Indian farmers. Use bullet points.`;

        const callAPI = async () => {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 55000);
            try {
                const res = await apiFetch(`/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: prompt,
                        session_id: 'soil-analysis-' + Date.now(),
                        farmer_id: farmerId || 'anonymous',
                        language: language
                    }),
                    signal: controller.signal
                });
                clearTimeout(timeout);
                return await res.json();
            } catch (err) {
                clearTimeout(timeout);
                throw err;
            }
        };

        const maxRetries = 2;
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                const data = await callAPI();
                if (data.status === 'success') {
                    const newResult = {
                        text: data.data.reply,
                        audioUrl: data.data.audio_url,
                        audioKey: data.data.audio_key,
                        audioLoading: !!data.data.audio_pending
                    };
                    setResult(newResult);
                    setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 200);
                    setLoading(false);
                    // Fire async TTS if audio is pending (gTTS languages)
                    if (data.data.audio_pending && data.data.reply) {
                        generateAsyncTts(data.data.reply, data.data.detected_language).then(tts => {
                            if (tts) {
                                setResult(prev => ({ ...prev, audioUrl: tts.audioUrl, audioKey: tts.audioKey, audioLoading: false }));
                            } else {
                                setResult(prev => ({ ...prev, audioLoading: false }));
                            }
                        });
                    }
                    return;
                } else if (attempt === maxRetries) {
                    setError(data.message || t('connectionError'));
                }
            } catch {
                if (attempt === maxRetries) {
                    setError(t('connectionError'));
                }
            }
        }
        setLoading(false);
    };

    function formatText(text) {
        if (!text) return '';
        const html = text
            .replace(/^###\s*(.+)$/gm, '<div class="ai-section-title">$1</div>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/^(\d+)\.\s+(.+)/gm, '<div class="ai-list-item"><span class="list-num">$1.</span> $2</div>')
            .replace(/^[•\-]\s+(.+)/gm, '<div class="ai-list-item"><span class="list-bullet">•</span> $1</div>')
            .replace(/^\s{2,}[\-•]\s+(.+)/gm, '<div class="ai-list-item ai-sub-item"><span class="list-bullet">◦</span> $1</div>')
            .replace(/\n\n/g, '<div class="ai-section-gap"></div>')
            .replace(/\n/g, '<br/>');
        return sanitizeHtml(html);
    }

    return (
        <div className="ai-feature-page" style={{ maxWidth: '100%', margin: 0 }}>
            <div className="page-header" style={{ marginBottom: '8px' }}>
                <div className="page-header-top">
                    <h2>🧪 {t('soilTitle') || 'AI Soil Health Analyzer'}</h2>
                </div>
                <p>{t('soilSubtitle') || 'Enter your soil test results or observations to get AI-powered fertilizer and improvement recommendations.'}</p>
            </div>

            <div className="ai-feature-page-scroll">

            <div className="ai-feature-form">
                {/* Soil test results section */}
                <h4 className="ai-form-section-title">🔬 {t('soilTestResults') || 'Soil Test Results'} <span className="ai-optional">({t('soilIfAvailable') || 'if available from soil testing lab'})</span></h4>
                <div className="ai-form-grid">
                    <div className="ai-form-group">
                        <label>pH {t('soilLevel') || 'Level'} <span className="required-star">*</span></label>
                        <select value={ph} onChange={e => setPh(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {PH_RANGES.map(p => <option key={p.value} value={p.value}>{t(p.key)}</option>)}
                        </select>
                    </div>
                    <div className="ai-form-group">
                        <label>🟢 {t('soilNitrogen') || 'Nitrogen (N)'}</label>
                        <select value={nitrogen} onChange={e => setNitrogen(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {NUTRIENT_LEVELS.map(n => <option key={n.value} value={n.value}>{t(n.key)}</option>)}
                        </select>
                    </div>
                    <div className="ai-form-group">
                        <label>🔵 {t('soilPhosphorus') || 'Phosphorus (P)'}</label>
                        <select value={phosphorus} onChange={e => setPhosphorus(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {NUTRIENT_LEVELS.map(n => <option key={n.value} value={n.value}>{t(n.key)}</option>)}
                        </select>
                    </div>
                    <div className="ai-form-group">
                        <label>🟠 {t('soilPotassium') || 'Potassium (K)'}</label>
                        <select value={potassium} onChange={e => setPotassium(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {NUTRIENT_LEVELS.map(n => <option key={n.value} value={n.value}>{t(n.key)}</option>)}
                        </select>
                    </div>
                </div>

                {/* Visual observation section */}
                <h4 className="ai-form-section-title" style={{ marginTop: '20px' }}>👁️ {t('soilObservations') || 'Visual Observations'}</h4>
                <div className="ai-form-grid">
                    <div className="ai-form-group">
                        <label>🎨 {t('soilColor') || 'Soil Color'} <span className="required-star">*</span></label>
                        <select value={soilColor} onChange={e => setSoilColor(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {SOIL_COLORS.map(c => <option key={c.value} value={c.value}>{t(c.key)}</option>)}
                        </select>
                    </div>
                    <div className="ai-form-group">
                        <label>💧 {t('soilDrainage') || 'Water Drainage'} <span className="required-star">*</span></label>
                        <select value={drainage} onChange={e => setDrainage(e.target.value)}>
                            <option value="" disabled>{t('soilSelect') || 'Select...'}</option>
                            {DRAINAGE.map(d => <option key={d.value} value={d.value}>{t(d.key)}</option>)}
                        </select>
                    </div>
                    <div className="ai-form-group">
                        <label>🌾 {t('soilTargetCrop') || 'Target Crop'}</label>
                        <select value={crop} onChange={e => setCrop(e.target.value)}>
                            <option value="" disabled>{t('soilSelectCrop') || 'Select crop...'}</option>
                            <option value="General">{t('cropGeneral') || 'General (all crops)'}</option>
                            {CROP_OPTIONS.map(c => <option key={c.value} value={c.value}>{t(c.key)}</option>)}
                        </select>
                    </div>
                </div>

                {error && <div className="ai-error">{error}</div>}

                <button className="ai-submit-btn" onClick={handleAnalyze} disabled={loading}>
                    {loading ? (
                        <><span className="spinner-sm"></span> {t('soilAnalyzing') || 'Analyzing soil health...'}</>
                    ) : (
                        <>🧪 {t('soilAnalyzeBtn') || 'Analyze Soil & Get Recommendations'}</>
                    )}
                </button>
            </div>

            {result && (
                <div className="ai-result-card" ref={resultRef}>
                    <div className="ai-result-header">
                        <h3>🧪 {t('soilResultTitle') || 'Soil Health Analysis Report'}</h3>
                    </div>
                    {result.audioUrl && (
                        <audio controls src={result.audioUrl} className="ai-result-audio"
                            onError={async (e) => {
                                if (result.audioKey) {
                                    try {
                                        const res = await apiFetch(`/chat`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ refresh_audio_key: result.audioKey })
                                        });
                                        const d = await res.json();
                                        if (d.status === 'success' && d.data?.audio_url) {
                                            e.target.src = d.data.audio_url;
                                            setResult(prev => ({ ...prev, audioUrl: d.data.audio_url }));
                                        }
                                    } catch { /* silent */ }
                                }
                            }}
                        />
                    )}
                    {result.audioLoading && (
                        <div className="audio-loading-indicator">
                            <span className="spinner-sm"></span> {t('ttsGenerating') || 'Generating audio...'}
                        </div>
                    )}
                    <div className="ai-result-body"
                        dangerouslySetInnerHTML={{ __html: formatText(result.text) }} />
                    <p className="ai-disclaimer">
                        {t('soilDisclaimer') || '⚠️ AI-generated analysis. For accurate results, get your soil tested at a government soil testing lab (₹50-100).'}
                    </p>
                </div>
            )}

            </div>
        </div>
    );
}

export default SoilAnalysisPage;
