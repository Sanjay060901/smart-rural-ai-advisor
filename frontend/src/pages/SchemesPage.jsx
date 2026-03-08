// src/pages/SchemesPage.jsx
// Government Schemes — Central + State tabs with structured cards & Ask AI per scheme

import { useState, useEffect, useCallback, useRef } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { sanitizeHtml } from '../utils/sanitize';
import { useFarmer } from '../contexts/FarmerContext';
import { SchemesSkeleton } from '../components/SkeletonLoader';
import schemeTranslations from '../i18n/schemeTranslations';
import { apiFetch } from '../utils/apiFetch';
import ScrollPill from '../components/ScrollPill';

// Map English state name → translation key
const STATE_KEY_MAP = {
    'Andhra Pradesh': 'stateAP', 'Arunachal Pradesh': 'stateAR', 'Assam': 'stateAS',
    'Bihar': 'stateBR', 'Chhattisgarh': 'stateCG', 'Goa': 'stateGA',
    'Gujarat': 'stateGJ', 'Haryana': 'stateHR', 'Himachal Pradesh': 'stateHP',
    'Jharkhand': 'stateJH', 'Karnataka': 'stateKA', 'Kerala': 'stateKL',
    'Madhya Pradesh': 'stateMP', 'Maharashtra': 'stateMH', 'Manipur': 'stateMN',
    'Meghalaya': 'stateML', 'Mizoram': 'stateMZ', 'Nagaland': 'stateNL',
    'Odisha': 'stateOD', 'Puducherry': 'statePY', 'Punjab': 'statePB',
    'Rajasthan': 'stateRJ', 'Sikkim': 'stateSK', 'Tamil Nadu': 'stateTN',
    'Telangana': 'stateTS', 'Tripura': 'stateTR', 'Uttar Pradesh': 'stateUP',
    'Uttarakhand': 'stateUK', 'West Bengal': 'stateWB',
};

function SchemesPage() {
    const { language, t } = useLanguage();
    const scrollRef = useRef(null);
    const { farmerProfile } = useFarmer();
    const [centralSchemes, setCentralSchemes] = useState([]);
    const [stateSchemes, setStateSchemes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [expandedId, setExpandedId] = useState(null);
    const [activeTab, setActiveTab] = useState('central'); // 'central' | 'state'

    // Ask AI state — per scheme
    const [aiSchemeName, setAiSchemeName] = useState(null);
    const [aiResponse, setAiResponse] = useState('');
    const [aiLoading, setAiLoading] = useState(false);

    const farmerState = farmerProfile?.state || '';

    // Fetch all schemes from backend
    useEffect(() => {
        const fetchSchemes = async () => {
            try {
                const res = await apiFetch(`/schemes`);
                const data = await res.json();

                // Central schemes
                const schemesObj = data.data?.schemes || data.schemes || {};
                const schemesArray = Array.isArray(schemesObj)
                    ? schemesObj
                    : Object.values(schemesObj);
                setCentralSchemes(schemesArray);

                // State schemes (keyed by state name)
                const allStateSchemes = data.data?.state_schemes || data.state_schemes || {};
                if (farmerState && allStateSchemes[farmerState]) {
                    setStateSchemes(allStateSchemes[farmerState]);
                } else {
                    setStateSchemes([]);
                }
            } catch {
                setCentralSchemes([]);
                setStateSchemes([]);
            }
            setLoading(false);
        };
        fetchSchemes();
    }, [farmerState]);

    // Get translated central scheme data
    const getTranslated = (scheme) => {
        const langData = schemeTranslations[language] || schemeTranslations['en-IN'] || {};
        const translated = langData[scheme.name] || (schemeTranslations['en-IN'] || {})[scheme.name];
        if (translated) return { ...scheme, ...translated };
        return scheme;
    };

    const applyNowText = (schemeTranslations[language] || schemeTranslations['en-IN'] || {}).applyNow || 'Apply Now';

    // Filter schemes based on search
    const filteredCentral = centralSchemes.map(getTranslated).filter(s =>
        s.name?.toLowerCase().includes(search.toLowerCase()) ||
        s.full_name?.toLowerCase().includes(search.toLowerCase()) ||
        s.benefit?.toLowerCase().includes(search.toLowerCase())
    );

    const filteredState = stateSchemes.map(getTranslated).filter(s =>
        s.name?.toLowerCase().includes(search.toLowerCase()) ||
        s.benefit?.toLowerCase().includes(search.toLowerCase())
    );

    const toggleCard = (id) => {
        setExpandedId(expandedId === id ? null : id);
        // Clear AI response when collapsing
        if (expandedId === id) {
            setAiResponse('');
            setAiSchemeName(null);
        }
    };

    // Ask AI about a specific scheme
    const askAI = useCallback(async (schemeName, schemeDetails) => {
        setAiSchemeName(schemeName);
        setAiResponse('');
        setAiLoading(true);
        try {
            const farmerContext = farmerProfile
                ? `I am a farmer from ${farmerProfile.state || 'India'}${farmerProfile.district ? ', ' + farmerProfile.district : ''}. I grow ${(farmerProfile.crops || []).join(', ') || 'crops'}. My land is ${farmerProfile.land_size_acres || 'unknown'} acres.`
                : '';
            const query = `${farmerContext ? farmerContext + ' ' : ''}Tell me everything I need to know about the "${schemeName}" scheme in detail. Include: full benefits with exact amounts, complete eligibility criteria, all required documents, step-by-step application process, important deadlines, and any tips to get maximum benefit. IMPORTANT: Only share information you are confident about. If you are unsure about specific details like exact amounts, documents, or deadlines for this scheme, clearly say so and advise the farmer to verify with their local agriculture office or Kisan Call Centre (1800-180-1551). Do not make up or guess specific numbers, dates, or document lists. Scheme info: ${schemeDetails}`;

            const res = await apiFetch(`/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: query, language, session_id: 'schemes-ai' }),
            });
            if (res.ok) {
                const data = await res.json();
                let reply = data.data?.reply || data.response || data.message || '';
                reply = reply.replace(/\n\s*Sources:\s*.+$/m, '').trim();
                setAiResponse(reply);
            } else {
                setAiResponse(t('schemesAIError') || 'Could not get AI response. Please try again.');
            }
        } catch {
            setAiResponse(t('schemesAIError') || 'Could not get AI response. Please try again.');
        } finally {
            setAiLoading(false);
        }
    }, [language, farmerProfile, t]);

    const displayedSchemes = activeTab === 'central' ? filteredCentral : filteredState;
    const hasStateSchemes = farmerState && stateSchemes.length > 0;

    // Render a scheme card (works for both central and state)
    const renderSchemeCard = (scheme, idx) => {
        const cardId = `${activeTab}-${idx}`;
        const isOpen = expandedId === cardId;
        const isCentral = activeTab === 'central';

        return (
            <div
                key={cardId}
                className={`scheme-card ${isOpen ? 'scheme-card--expanded' : ''}`}
                style={{ animationDelay: `${idx * 0.04}s` }}
            >
                {/* Clickable header */}
                <div className="scheme-card__header" onClick={() => toggleCard(cardId)}>
                    <div className="scheme-card__title-group">
                        <h3 className="scheme-card__name">{scheme.name}</h3>
                        {isCentral && scheme.full_name && (
                            <p className="scheme-card__fullname">{scheme.full_name}</p>
                        )}
                        {!isCentral && scheme.benefit && (
                            <p className="scheme-card__fullname">{scheme.benefit}</p>
                        )}
                    </div>
                    <span className={`scheme-card__chevron ${isOpen ? 'open' : ''}`}>▼</span>
                </div>

                {/* Expanded details */}
                {isOpen && (
                    <div className="scheme-card__body">
                        {scheme.benefit && (
                            <div className="scheme-detail">
                                <span className="detail-icon">💰</span>
                                <span><span className="detail-label">{t('schemesBenefit')}:</span> {scheme.benefit}</span>
                            </div>
                        )}
                        {scheme.eligibility && (
                            <div className="scheme-detail">
                                <span className="detail-icon">👤</span>
                                <span><span className="detail-label">{t('schemesEligibility')}:</span> {scheme.eligibility}</span>
                            </div>
                        )}
                        {scheme.how_to_apply && (
                            <div className="scheme-detail">
                                <span className="detail-icon">📝</span>
                                <span><span className="detail-label">{t('schemesHowToApply')}:</span> {scheme.how_to_apply}</span>
                            </div>
                        )}
                        {scheme.documents && (
                            <div className="scheme-detail">
                                <span className="detail-icon">📄</span>
                                <span><span className="detail-label">{t('schemesDocuments') || 'Required Documents'}:</span> {scheme.documents}</span>
                            </div>
                        )}
                        {scheme.deadline && (
                            <div className="scheme-detail">
                                <span className="detail-icon">📅</span>
                                <span><span className="detail-label">{t('schemesDeadline') || 'Deadline'}:</span> {scheme.deadline}</span>
                            </div>
                        )}
                        {scheme.helpline && (
                            <div className="scheme-detail">
                                <span className="detail-icon">📞</span>
                                <span><span className="detail-label">{t('schemesHelpline')}:</span> {scheme.helpline}</span>
                            </div>
                        )}
                        {scheme.website && (
                            <a
                                href={scheme.website}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="scheme-apply-btn"
                            >
                                🔗 {applyNowText} — {scheme.website.replace(/^https?:\/\//, '')}
                            </a>
                        )}

                        {/* Ask AI button */}
                        <div className="scheme-ask-ai-section">
                            <button
                                className="scheme-ask-ai-btn"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    const details = [scheme.benefit, scheme.eligibility, scheme.how_to_apply].filter(Boolean).join('. ');
                                    askAI(scheme.name, details);
                                }}
                                disabled={aiLoading && aiSchemeName === scheme.name}
                            >
                                {aiLoading && aiSchemeName === scheme.name
                                    ? `⏳ ${t('schemesAILoading') || 'AI is analyzing...'}`
                                    : `🤖 ${t('schemesAskAI') || 'Ask AI for Details'}`
                                }
                            </button>
                        </div>

                        {/* AI Response for this scheme */}
                        {aiSchemeName === scheme.name && aiResponse && (
                            <div className="scheme-ai-response">
                                <div className="scheme-ai-response__header">
                                    <span>🤖</span>
                                    <strong>{t('schemesAIAdvice') || 'AI Personalized Advice'}</strong>
                                </div>
                                <div
                                    className="scheme-ai-response__body"
                                    dangerouslySetInnerHTML={{
                                        __html: sanitizeHtml(aiResponse
                                            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                                            .replace(/\n/g, '<br/>'))
                                    }}
                                />
                                <div className="scheme-ai-disclaimer">
                                    ⚠️ {t('schemesAIDisclaimer') || 'Please verify details with your nearest agriculture office or call Kisan Helpline 1800-180-1551. Scheme details may change — always confirm before applying.'}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="schemes-page">
            <div className="page-header">
                <h2>📋 {t('schemesTitle')}</h2>
                <p>{t('schemesSubtitle')}</p>
            </div>

            <div className="schemes-page-scroll" ref={scrollRef}>

                {/* Tabs */}
                <div className="schemes-tabs">
                    <button
                        className={`schemes-tab ${activeTab === 'central' ? 'schemes-tab--active' : ''}`}
                        onClick={() => { setActiveTab('central'); setExpandedId(null); setAiResponse(''); setAiSchemeName(null); }}
                    >
                        🏛️ {t('schemesCentral') || 'Central Government Schemes'}
                        <span className="schemes-tab__count">{centralSchemes.length}</span>
                    </button>
                    <button
                        className={`schemes-tab ${activeTab === 'state' ? 'schemes-tab--active' : ''}`}
                        onClick={() => { setActiveTab('state'); setExpandedId(null); setAiResponse(''); setAiSchemeName(null); }}
                        disabled={!hasStateSchemes}
                        title={!hasStateSchemes ? (t('schemesNoState') || 'Set your state in Profile to see state schemes') : ''}
                    >
                        📍 {hasStateSchemes
                            ? `${t('schemesForState') || 'Schemes for'} ${t(STATE_KEY_MAP[farmerState]) || farmerState}`
                            : (t('schemesStateTab') || 'State Schemes')
                        }
                        {hasStateSchemes && <span className="schemes-tab__count">{stateSchemes.length}</span>}
                    </button>
                </div>

                {/* No state hint */}
                {activeTab === 'state' && !hasStateSchemes && (
                    <div className="schemes-no-state-hint">
                        <span>📍</span>
                        <p>{t('schemesSetState') || 'Please set your state in your Profile to see state-specific schemes available for you.'}</p>
                    </div>
                )}

                {/* Search bar */}
                <div className="search-bar">
                    <span className="search-icon">🔍</span>
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder={t('schemesSearch')}
                    />
                </div>

                {/* Scheme cards */}
                {loading ? (
                    <SchemesSkeleton />
                ) : (
                    <div className="schemes-grid">
                        {displayedSchemes.map((scheme, i) => renderSchemeCard(scheme, i))}
                        {displayedSchemes.length === 0 && !loading && (
                            <div className="alert alert-warning" style={{ gridColumn: '1 / -1' }}>
                                {search
                                    ? `${t('schemesNoMatch') || 'No schemes found matching'} "${search}"`
                                    : activeTab === 'state'
                                        ? (t('schemesNoStateData') || 'No state-specific schemes data available for your state yet.')
                                        : (t('schemesNoMatch') || 'No schemes found.')
                                }
                            </div>
                        )}
                    </div>
                )}

                {/* Helpline footer */}
                <div className="schemes-helpline-footer">
                    📞 {t('schemesKisanHelpline') || 'Kisan Call Centre'}: <strong>1800-180-1551</strong> ({t('schemesTollFree') || 'Toll-free, 27 languages'})
                </div>

            </div>{/* end schemes-page-scroll */}
            <ScrollPill scrollRef={scrollRef} />
        </div>
    );
}

export default SchemesPage;
