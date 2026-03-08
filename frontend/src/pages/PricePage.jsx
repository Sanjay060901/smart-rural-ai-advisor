// src/pages/PricePage.jsx

import { useState, useMemo, useCallback, useRef } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { useFarmer } from '../contexts/FarmerContext';
import { sanitizeHtml } from '../utils/sanitize';
import { getPriceT } from '../i18n/priceTranslations';
import { mockPrices, mockPestAdvice } from '../services/mockApi';
import { generateAsyncTts } from '../utils/asyncTts';
import config from '../config';
import { apiFetch } from '../utils/apiFetch';
import ScrollPill from '../components/ScrollPill';

/* ── Season helper based on current month ─────── */
function getCurrentSeason() {
    const month = new Date().getMonth() + 1; // 1-12
    if (month >= 6 && month <= 10) return 'Kharif';
    if (month >= 11 || month <= 3) return 'Rabi';
    return 'Zaid (Summer)';
}

/* ── Sort helper ─────── */
function SortArrow({ column, sortCol, sortDir }) {
    const active = sortCol === column;
    return (
        <span className={`sort-arrow ${active ? 'active' : ''}`}>
            {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
        </span>
    );
}

/* ── Crop market price data (MSP + simulated market prices) — 66 crops from crop_data.csv ─────── */
const CROP_PRICES = [
    // Cereals
    { name: 'Rice', season: 'Kharif', msp: 2300, marketMin: 2100, marketMax: 2800, unit: '₹/quintal', trend: 'up' },
    { name: 'Wheat', season: 'Rabi', msp: 2425, marketMin: 2200, marketMax: 3000, unit: '₹/quintal', trend: 'stable' },
    { name: 'Maize', season: 'Kharif+Rabi', msp: 2225, marketMin: 2000, marketMax: 2700, unit: '₹/quintal', trend: 'down' },
    { name: 'Jowar', season: 'Kharif+Rabi', msp: 3371, marketMin: 3100, marketMax: 4100, unit: '₹/quintal', trend: 'stable' },
    { name: 'Bajra', season: 'Kharif', msp: 2625, marketMin: 2400, marketMax: 3200, unit: '₹/quintal', trend: 'stable' },
    { name: 'Barley', season: 'Rabi', msp: 1980, marketMin: 1800, marketMax: 2400, unit: '₹/quintal', trend: 'down' },
    { name: 'Ragi', season: 'Kharif', msp: 4290, marketMin: 3900, marketMax: 5200, unit: '₹/quintal', trend: 'up' },
    { name: 'Small Millets', season: 'Kharif', msp: 3500, marketMin: 3200, marketMax: 4300, unit: '₹/quintal', trend: 'stable' },
    // Pulses
    { name: 'Chickpea', season: 'Rabi', msp: 5650, marketMin: 5100, marketMax: 6900, unit: '₹/quintal', trend: 'stable' },
    { name: 'Pigeon Pea', season: 'Kharif', msp: 7550, marketMin: 6900, marketMax: 9200, unit: '₹/quintal', trend: 'up' },
    { name: 'Green Gram', season: 'Kharif+Summer', msp: 8682, marketMin: 7900, marketMax: 10600, unit: '₹/quintal', trend: 'up' },
    { name: 'Black Gram', season: 'Kharif', msp: 7400, marketMin: 6700, marketMax: 9000, unit: '₹/quintal', trend: 'stable' },
    { name: 'Lentil', season: 'Rabi', msp: 6700, marketMin: 6100, marketMax: 8200, unit: '₹/quintal', trend: 'stable' },
    { name: 'Peas', season: 'Rabi', msp: 6500, marketMin: 5900, marketMax: 7900, unit: '₹/quintal', trend: 'stable' },
    { name: 'Horse Gram', season: 'Kharif', msp: 5200, marketMin: 4700, marketMax: 6300, unit: '₹/quintal', trend: 'stable' },
    { name: 'Cowpea', season: 'Kharif+Summer', msp: 5800, marketMin: 5300, marketMax: 7100, unit: '₹/quintal', trend: 'stable' },
    { name: 'Moth Bean', season: 'Kharif', msp: 7500, marketMin: 6800, marketMax: 9200, unit: '₹/quintal', trend: 'stable' },
    // Vegetables
    { name: 'Potato', season: 'Rabi', msp: 1200, marketMin: 1100, marketMax: 1500, unit: '₹/quintal', trend: 'stable' },
    { name: 'Tomato', season: 'Rabi+Kharif', msp: 1800, marketMin: 1600, marketMax: 2200, unit: '₹/quintal', trend: 'up' },
    { name: 'Onion', season: 'Rabi', msp: 2000, marketMin: 1800, marketMax: 2400, unit: '₹/quintal', trend: 'down' },
    { name: 'Cabbage', season: 'Rabi', msp: 1500, marketMin: 1400, marketMax: 1800, unit: '₹/quintal', trend: 'down' },
    { name: 'Cauliflower', season: 'Rabi', msp: 2200, marketMin: 2000, marketMax: 2700, unit: '₹/quintal', trend: 'stable' },
    { name: 'Brinjal', season: 'Year-round', msp: 1800, marketMin: 1600, marketMax: 2200, unit: '₹/quintal', trend: 'stable' },
    { name: 'Okra', season: 'Kharif+Summer', msp: 2500, marketMin: 2300, marketMax: 3000, unit: '₹/quintal', trend: 'stable' },
    { name: 'Carrot', season: 'Rabi', msp: 2500, marketMin: 2300, marketMax: 3000, unit: '₹/quintal', trend: 'stable' },
    { name: 'Radish', season: 'Rabi', msp: 1200, marketMin: 1100, marketMax: 1500, unit: '₹/quintal', trend: 'down' },
    { name: 'Beans', season: 'Rabi+Kharif', msp: 4500, marketMin: 4100, marketMax: 5500, unit: '₹/quintal', trend: 'up' },
    { name: 'Pumpkin', season: 'Kharif+Summer', msp: 1500, marketMin: 1400, marketMax: 1800, unit: '₹/quintal', trend: 'up' },
    // Fibre Crops
    { name: 'Cotton', season: 'Kharif', msp: 7710, marketMin: 7000, marketMax: 9400, unit: '₹/quintal', trend: 'stable' },
    { name: 'Jute', season: 'Kharif', msp: 5335, marketMin: 4900, marketMax: 6500, unit: '₹/quintal', trend: 'stable' },
    { name: 'Hemp', season: 'Kharif', msp: 4500, marketMin: 4100, marketMax: 5500, unit: '₹/quintal', trend: 'stable' },
    { name: 'Sunn Hemp', season: 'Kharif', msp: 6800, marketMin: 6200, marketMax: 8300, unit: '₹/quintal', trend: 'stable' },
    // Oilseeds
    { name: 'Groundnut', season: 'Kharif', msp: 6783, marketMin: 6200, marketMax: 8300, unit: '₹/quintal', trend: 'up' },
    { name: 'Soybean', season: 'Kharif', msp: 4600, marketMin: 4200, marketMax: 5600, unit: '₹/quintal', trend: 'up' },
    { name: 'Sunflower', season: 'Kharif+Rabi', msp: 7280, marketMin: 6600, marketMax: 8900, unit: '₹/quintal', trend: 'down' },
    { name: 'Sesame', season: 'Kharif', msp: 8635, marketMin: 7900, marketMax: 10500, unit: '₹/quintal', trend: 'up' },
    { name: 'Mustard', season: 'Rabi', msp: 5950, marketMin: 5400, marketMax: 7300, unit: '₹/quintal', trend: 'stable' },
    { name: 'Linseed', season: 'Rabi', msp: 7200, marketMin: 6600, marketMax: 8800, unit: '₹/quintal', trend: 'stable' },
    { name: 'Castor Seed', season: 'Kharif', msp: 6850, marketMin: 6200, marketMax: 8400, unit: '₹/quintal', trend: 'up' },
    { name: 'Safflower', season: 'Rabi', msp: 5800, marketMin: 5300, marketMax: 7100, unit: '₹/quintal', trend: 'down' },
    { name: 'Niger Seed', season: 'Kharif', msp: 8717, marketMin: 7900, marketMax: 10600, unit: '₹/quintal', trend: 'down' },
    // Cash Crops
    { name: 'Sugarcane', season: 'Annual', msp: 315, marketMin: 300, marketMax: 400, unit: '₹/quintal (FRP)', trend: 'stable' },
    { name: 'Tobacco', season: 'Rabi', msp: 18000, marketMin: 16400, marketMax: 22000, unit: '₹/quintal', trend: 'down' },
    // Plantation Crops
    { name: 'Tea', season: 'Perennial', msp: 22000, marketMin: 20000, marketMax: 26800, unit: '₹/quintal', trend: 'stable' },
    { name: 'Coffee', season: 'Perennial', msp: 45000, marketMin: 41000, marketMax: 54900, unit: '₹/quintal', trend: 'up' },
    { name: 'Rubber', season: 'Perennial', msp: 17500, marketMin: 15900, marketMax: 21400, unit: '₹/quintal', trend: 'up' },
    { name: 'Coconut', season: 'Perennial', msp: 11582, marketMin: 10500, marketMax: 14100, unit: '₹/quintal (copra)', trend: 'up' },
    { name: 'Arecanut', season: 'Perennial', msp: 55000, marketMin: 50000, marketMax: 67100, unit: '₹/quintal', trend: 'up' },
    { name: 'Cocoa', season: 'Perennial', msp: 25000, marketMin: 22800, marketMax: 30500, unit: '₹/quintal', trend: 'up' },
    // Spices
    { name: 'Black Pepper', season: 'Perennial', msp: 42000, marketMin: 38200, marketMax: 51200, unit: '₹/quintal', trend: 'up' },
    { name: 'Cardamom', season: 'Perennial', msp: 120000, marketMin: 109200, marketMax: 146400, unit: '₹/quintal', trend: 'up' },
    { name: 'Turmeric', season: 'Kharif', msp: 12000, marketMin: 10900, marketMax: 14600, unit: '₹/quintal', trend: 'up' },
    { name: 'Ginger', season: 'Kharif', msp: 18000, marketMin: 16400, marketMax: 22000, unit: '₹/quintal', trend: 'up' },
    { name: 'Red Chilli', season: 'Kharif+Rabi', msp: 16000, marketMin: 14600, marketMax: 19500, unit: '₹/quintal', trend: 'stable' },
    { name: 'Coriander', season: 'Rabi', msp: 8500, marketMin: 7700, marketMax: 10400, unit: '₹/quintal', trend: 'up' },
    { name: 'Cumin', season: 'Rabi', msp: 25000, marketMin: 22800, marketMax: 30500, unit: '₹/quintal', trend: 'up' },
    { name: 'Fenugreek', season: 'Rabi', msp: 7500, marketMin: 6800, marketMax: 9200, unit: '₹/quintal', trend: 'up' },
    { name: 'Clove', season: 'Perennial', msp: 95000, marketMin: 86400, marketMax: 115900, unit: '₹/quintal', trend: 'up' },
    { name: 'Cinnamon', season: 'Perennial', msp: 35000, marketMin: 31800, marketMax: 42700, unit: '₹/quintal', trend: 'stable' },
    { name: 'Nutmeg', season: 'Perennial', msp: 65000, marketMin: 59200, marketMax: 79300, unit: '₹/quintal', trend: 'up' },
    // Fodder Crops
    { name: 'Berseem', season: 'Rabi', msp: 800, marketMin: 700, marketMax: 1000, unit: '₹/quintal (green)', trend: 'stable' },
    { name: 'Napier Grass', season: 'Perennial', msp: 600, marketMin: 500, marketMax: 700, unit: '₹/quintal (green)', trend: 'stable' },
    { name: 'Sorghum Fodder', season: 'Kharif', msp: 700, marketMin: 600, marketMax: 900, unit: '₹/quintal (green)', trend: 'stable' },
    { name: 'Cowpea Fodder', season: 'Kharif', msp: 750, marketMin: 700, marketMax: 900, unit: '₹/quintal (green)', trend: 'stable' },
    { name: 'Lucerne', season: 'Rabi', msp: 1200, marketMin: 1100, marketMax: 1500, unit: '₹/quintal (green)', trend: 'stable' },
    { name: 'Maize Fodder', season: 'Kharif+Rabi', msp: 650, marketMin: 600, marketMax: 800, unit: '₹/quintal (green)', trend: 'stable' },
];

/* ── Pesticide / Input prices ─────── */
const PEST_RATES = [
    { name: 'Neem Oil (1L)', category: 'Bio-pesticide', price: 350, unit: '₹/litre', usage: 'General pest control' },
    { name: 'Chlorpyrifos 20% EC', category: 'Insecticide', price: 480, unit: '₹/litre', usage: 'Termites, Borers, Aphids' },
    { name: 'Imidacloprid 17.8% SL', category: 'Insecticide', price: 650, unit: '₹/250ml', usage: 'Whitefly, Aphids, Jassids' },
    { name: 'Mancozeb 75% WP', category: 'Fungicide', price: 320, unit: '₹/500g', usage: 'Blight, Downy Mildew, Rust' },
    { name: 'Carbendazim 50% WP', category: 'Fungicide', price: 280, unit: '₹/500g', usage: 'Wilt, Rot, Blast' },
    { name: 'Glyphosate 41% SL', category: 'Herbicide', price: 520, unit: '₹/litre', usage: 'Broad-spectrum weed control' },
    { name: 'Trichoderma viride', category: 'Bio-fungicide', price: 180, unit: '₹/kg', usage: 'Soil-borne diseases' },
    { name: 'Beauveria bassiana', category: 'Bio-insecticide', price: 250, unit: '₹/kg', usage: 'Borers, Whitefly, Mealybug' },
    { name: 'Lambda Cyhalothrin 5% EC', category: 'Insecticide', price: 420, unit: '₹/litre', usage: 'Bollworm, Pod Borer, Army Worm' },
    { name: 'Copper Oxychloride 50% WP', category: 'Fungicide', price: 290, unit: '₹/500g', usage: 'Bacterial Blight, Leaf Spot' },
    { name: 'Thiamethoxam 25% WG', category: 'Insecticide', price: 580, unit: '₹/100g', usage: 'Sucking pests, Stem Borer' },
    { name: 'Propiconazole 25% EC', category: 'Fungicide', price: 750, unit: '₹/litre', usage: 'Rust, Sheath Blight, Smut' },
    { name: 'Emamectin Benzoate 5% SG', category: 'Insecticide', price: 620, unit: '₹/100g', usage: 'Fall Armyworm, Fruit Borer' },
    { name: 'Pseudomonas fluorescens', category: 'Bio-fungicide', price: 200, unit: '₹/kg', usage: 'Wilt, Root Rot, Damping Off' },
    { name: 'Yellow Sticky Traps (20 pcs)', category: 'Trap', price: 150, unit: '₹/pack', usage: 'Whitefly, Aphids monitoring' },
    { name: 'Pheromone Traps (set of 5)', category: 'Trap', price: 350, unit: '₹/set', usage: 'Fruit Fly, Bollworm monitoring' },
];

const SEASONS = ['All', 'Kharif', 'Rabi', 'Kharif+Rabi', 'Kharif+Summer', 'Annual', 'Perennial', 'Year-round', 'Rabi+Kharif'];
const PEST_CATEGORIES = ['All', 'Bio-pesticide', 'Bio-fungicide', 'Bio-insecticide', 'Insecticide', 'Fungicide', 'Herbicide', 'Trap'];

/* ── AI Advisory labels ─────── */
const AI_LABELS = {
    'en-IN': { ask: '🤖 Ask AI', asking: '⏳ Asking AI...', titleCrop: 'AI Price Advisory', titlePest: 'AI Pesticide Guide', source: 'Source', close: '✕ Close' },
    'ta-IN': { ask: '🤖 AI கேளுங்கள்', asking: '⏳ AI கேட்கிறது...', titleCrop: 'AI விலை ஆலோசனை', titlePest: 'AI பூச்சிக்கொல்லி வழிகாட்டி', source: 'மூலம்', close: '✕ மூடு' },
    'hi-IN': { ask: '🤖 AI से पूछें', asking: '⏳ AI से पूछ रहे...', titleCrop: 'AI मूल्य सलाह', titlePest: 'AI कीटनाशक गाइड', source: 'स्रोत', close: '✕ बंद करें' },
    'kn-IN': { ask: '🤖 AI ಕೇಳಿ', asking: '⏳ AI ಕೇಳುತ್ತಿದೆ...', titleCrop: 'AI ಬೆಲೆ ಸಲಹೆ', titlePest: 'AI ಕೀಟನಾಶಕ ಮಾರ್ಗದರ್ಶಿ', source: 'ಮೂಲ', close: '✕ ಮುಚ್ಚಿ' },
    'te-IN': { ask: '🤖 AI అడగండి', asking: '⏳ AI అడుగుతోంది...', titleCrop: 'AI ధర సలహా', titlePest: 'AI పురుగుమందు గైడ్', source: 'మూలం', close: '✕ మూసివేయి' },
    'ml-IN': { ask: '🤖 AI ചോദിക്കൂ', asking: '⏳ AI ചോദിക്കുന്നു...', titleCrop: 'AI വില ഉപദേശം', titlePest: 'AI കീടനാശിനി ഗൈഡ്', source: 'ഉറവிടം', close: '✕ അടയ്ക്കുക' },
    'bn-IN': { ask: '🤖 AI জিজ্ঞাসা', asking: '⏳ AI জিজ্ঞাসা করছে...', titleCrop: 'AI মূল্য পরামর্শ', titlePest: 'AI কীটনাশক গাইড', source: 'উৎস', close: '✕ বন্ধ' },
    'mr-IN': { ask: '🤖 AI ला विचारा', asking: '⏳ AI ला विचारत आहे...', titleCrop: 'AI किंमत सल्ला', titlePest: 'AI कीटकनाशक मार्गदर्शक', source: 'स्रोत', close: '✕ बंद करा' },
    'gu-IN': { ask: '🤖 AI પૂછો', asking: '⏳ AI પૂછી રહ્યું છે...', titleCrop: 'AI ભાવ સલાહ', titlePest: 'AI જંતુનાશક માર્ગદર્શિકા', source: 'સ્ત્રોત', close: '✕ બંધ કરો' },
    'pa-IN': { ask: '🤖 AI ਪੁੱਛੋ', asking: '⏳ AI ਪੁੱਛ ਰਿਹਾ ਹੈ...', titleCrop: 'AI ਕੀਮਤ ਸਲਾਹ', titlePest: 'AI ਕੀਟਨਾਸ਼ਕ ਗਾਈਡ', source: 'ਸ੍ਰੋਤ', close: '✕ ਬੰਦ ਕਰੋ' },
    'or-IN': { ask: '🤖 AI ପଚାରନ୍ତୁ', asking: '⏳ AI ପଚାରୁଛି...', titleCrop: 'AI ମୂଲ୍ୟ ପରାମର୍ଶ', titlePest: 'AI କୀଟନାଶକ ଗାଇଡ୍', source: 'ଉତ୍ସ', close: '✕ ବନ୍ଦ କରନ୍ତୁ' },
    'as-IN': { ask: '🤖 AI সুধিব', asking: '⏳ AI সুধিছে...', titleCrop: 'AI মূল্য পৰামৰ্শ', titlePest: 'AI কীটনাশক গাইড', source: 'উৎস', close: '✕ বন্ধ কৰক' },
    'ur-IN': { ask: '🤖 AI پوچھیں', asking: '⏳ AI پوچھ رہا ہے...', titleCrop: 'AI قیمت مشورہ', titlePest: 'AI کیڑے مار دوا گائیڈ', source: 'ذریعہ', close: '✕ بند کریں' },
};

function TrendBadge({ trend, pt }) {
    const icons = { up: ['📈', '#16a34a'], down: ['📉', '#dc2626'], stable: ['➡️', '#d97706'] };
    const labels = { up: pt.trendRising, down: pt.trendFalling, stable: pt.trendStable };
    const [icon, color] = icons[trend] || icons.stable;
    const label = labels[trend] || labels.stable;
    return <span className="price-trend" style={{ color, background: color + '14' }}>{icon} {label}</span>;
}

function PricePage() {
    const { language, t } = useLanguage();
    const scrollRef = useRef(null);
    const pt = getPriceT(language);
    const { farmerProfile, farmerId } = useFarmer();
    const [tab, setTab] = useState('crops');
    const [search, setSearch] = useState('');
    const [seasonFilter, setSeasonFilter] = useState('All');
    const [pestCatFilter, setPestCatFilter] = useState('All');

    // Sort state
    const [sortCol, setSortCol] = useState(null);
    const [sortDir, setSortDir] = useState('asc');

    const handleSort = (col) => {
        if (sortCol === col) {
            setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        } else {
            setSortCol(col);
            setSortDir('asc');
        }
    };

    // AI Advisory state
    const [aiAdvisory, setAiAdvisory] = useState(null);
    const [aiLoading, setAiLoading] = useState(false);
    const [aiCrop, setAiCrop] = useState(null);
    const [aiType, setAiType] = useState('crop'); // 'crop' or 'pest'
    const [aiAudioUrl, setAiAudioUrl] = useState(null);
    const [aiAudioKey, setAiAudioKey] = useState(null);
    const [aiAudioLoading, setAiAudioLoading] = useState(false);
    const advisoryRef = useRef(null);

    const aiLabel = AI_LABELS[language] || AI_LABELS['en-IN'];

    /* ── Strip conversational tail from AI response ─────── */
    function stripConversationalTail(text) {
        if (!text) return text;
        // Repeatedly strip trailing conversational lines (model may add multiple)
        let cleaned = text;
        const tailPatterns = [
            /\n*(?:If you (?:have|need|want|would like))[^\n]*$/i,
            /\n*(?:Feel free to|Don't hesitate|Please (?:feel free|don't hesitate|let me know|contact))[^\n]*$/i,
            /\n*(?:I hope this|I'm here to help|Happy farming|Best of luck|Good luck|Wishing you)[^\n]*$/i,
            /\n*(?:Let me know if|For (?:more|further|any) (?:detailed |specific )?(?:information|details|queries|questions|assistance|help))[^\n]*$/i,
            /\n*(?:Should you (?:need|have|require)|Do not hesitate|Reach out)[^\n]*$/i,
        ];
        for (let i = 0; i < 3; i++) { // up to 3 passes to catch stacked closings
            for (const pat of tailPatterns) {
                cleaned = cleaned.replace(pat, '');
            }
        }
        return cleaned.trim();
    }

    /* ── Rich text formatter (same as CropRecommend / FarmCalendar) ─────── */
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

    /* translate a crop name for display */
    const cropName = (en) => pt.crops?.[en] || en;
    /* translate a season for display */
    const seasonName = (en) => pt.seasons?.[en] || en;
    /* translate a pest category for display */
    const catName = (en) => pt.categories?.[en] || en;
    /* translate pest usage */
    const pestUsage = (en, fallback) => pt.pestUsage?.[en] || fallback;
    /* translate pest name */
    const pestName = (en) => pt.pestNames?.[en] || en;
    /* translate unit */
    const unitName = (en) => pt.units?.[en] || en;

    const filteredCrops = useMemo(() => {
        let result = CROP_PRICES.filter(c => {
            const translated = cropName(c.name);
            const matchSearch = c.name.toLowerCase().includes(search.toLowerCase()) ||
                                translated.toLowerCase().includes(search.toLowerCase());
            const matchSeason = seasonFilter === 'All' || c.season === seasonFilter;
            return matchSearch && matchSeason;
        });
        if (sortCol) {
            result = [...result].sort((a, b) => {
                let va, vb;
                switch (sortCol) {
                    case 'name': va = cropName(a.name).toLowerCase(); vb = cropName(b.name).toLowerCase(); break;
                    case 'season': va = a.season; vb = b.season; break;
                    case 'msp': va = a.msp || 0; vb = b.msp || 0; break;
                    case 'market': va = a.marketMin; vb = b.marketMin; break;
                    case 'trend': { const order = { up: 1, stable: 2, down: 3 }; va = order[a.trend] || 2; vb = order[b.trend] || 2; break; }
                    default: return 0;
                }
                if (va < vb) return sortDir === 'asc' ? -1 : 1;
                if (va > vb) return sortDir === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return result;
    }, [search, seasonFilter, language, sortCol, sortDir]);

    const filteredPests = useMemo(() => {
        let result = PEST_RATES.filter(p => {
            const translated = pestName(p.name);
            const matchSearch = p.name.toLowerCase().includes(search.toLowerCase()) ||
                                translated.toLowerCase().includes(search.toLowerCase());
            const matchCat = pestCatFilter === 'All' || p.category === pestCatFilter;
            return matchSearch && matchCat;
        });
        if (sortCol) {
            result = [...result].sort((a, b) => {
                let va, vb;
                switch (sortCol) {
                    case 'pname': va = pestName(a.name).toLowerCase(); vb = pestName(b.name).toLowerCase(); break;
                    case 'category': va = a.category; vb = b.category; break;
                    case 'price': va = a.price; vb = b.price; break;
                    case 'usage': va = a.usage; vb = b.usage; break;
                    default: return 0;
                }
                if (va < vb) return sortDir === 'asc' ? -1 : 1;
                if (va > vb) return sortDir === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return result;
    }, [search, pestCatFilter, language, sortCol, sortDir]);

    /* ── Ask AI for price advisory ─────── */
    const askAI = useCallback(async (crop) => {
        setAiCrop(crop.name);
        setAiType('crop');
        setAiLoading(true);
        setAiAdvisory(null);
        try {
            let result;
            if (config.MOCK_AI) {
                result = await mockPrices(crop.name, language);
            } else {
                const farmerState = farmerProfile?.state || '';
                const farmerDistrict = farmerProfile?.district || '';
                const farmerLocation = farmerState && farmerDistrict ? `${farmerDistrict}, ${farmerState}` : farmerState || 'India';
                const currentSeason = getCurrentSeason();
                const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
                const query = `You are an agricultural market analyst advising a farmer in ${farmerLocation}.\n\nDate: ${today} | Current Season: ${currentSeason}\n\nProvide a detailed price advisory for ${crop.name} (${crop.season} crop) based on this data:\n- Government MSP: ${crop.msp ? '₹' + crop.msp + '/quintal' : 'Not applicable (no MSP fixed)'}\n- Current Market Price Range: ₹${crop.marketMin} – ₹${crop.marketMax}/quintal\n- Price Trend: ${crop.trend === 'up' ? 'Rising' : crop.trend === 'down' ? 'Falling' : 'Stable'}\n\nGive advice specific to ${farmerLocation} region. Include: best time to sell in the current ${currentSeason} season, nearest recommended mandis for this region, storage tips to get better prices, price trend analysis, and market outlook for the next 3 months. Give specific actionable advice. IMPORTANT: This is a one-way advisory panel, NOT a conversation. Do NOT include any closing lines like "feel free to ask", "if you have any questions", "if you need more information", "I hope this helps", or any invitation to continue a dialogue. End with your last piece of actionable advice.`;
                const res = await apiFetch(`/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: query, language, session_id: 'price-advisory-' + Date.now(), farmer_id: farmerId || 'anonymous' }),
                });
                if (!res.ok) throw new Error('API error');
                const data = await res.json();
                let rawAdvisory = data.data?.reply || data.data?.response || data.response || data.message || 'No advisory available.';
                // Strip any leftover "Sources: ..." line and conversational tail
                rawAdvisory = rawAdvisory.replace(/\n\s*Sources:\s*.+$/m, '').trim();
                rawAdvisory = stripConversationalTail(rawAdvisory);
                result = {
                    status: 'success',
                    data: {
                        advisory: rawAdvisory,
                        audioUrl: data.data?.audio_url || null,
                        audioKey: data.data?.audio_key || null,
                        audioPending: !!data.data?.audio_pending,
                        detectedLang: data.data?.detected_language || language,
                    }
                };
            }
            const advisory = result.data;
            setAiAdvisory(advisory);
            setAiAudioUrl(advisory.audioUrl || null);
            setAiAudioKey(advisory.audioKey || null);
            // Fire async TTS if pending
            if (advisory.audioPending && advisory.advisory) {
                setAiAudioLoading(true);
                generateAsyncTts(advisory.advisory, advisory.detectedLang).then(tts => {
                    if (tts) {
                        setAiAudioUrl(tts.audioUrl);
                        setAiAudioKey(tts.audioKey);
                    }
                    setAiAudioLoading(false);
                });
            }
            setTimeout(() => advisoryRef.current?.scrollIntoView({ behavior: 'smooth' }), 200);
        } catch (err) {
            if (import.meta.env.DEV) console.error('AI price advisory error:', err);
            setAiAdvisory({
                advisory: t('priceAiUnavailable'),
            });
        } finally {
            setAiLoading(false);
        }
    }, [language, farmerProfile]);

    /* ── Ask AI for pesticide advisory ─────── */
    const askPestAI = useCallback(async (pest) => {
        setAiCrop(pest.name);
        setAiType('pest');
        setAiLoading(true);
        setAiAdvisory(null);
        try {
            let result;
            if (config.MOCK_AI) {
                result = await mockPestAdvice(pest.name, pest.category, pest.usage, language);
            } else {
                const farmerState = farmerProfile?.state || '';
                const farmerDistrict = farmerProfile?.district || '';
                const farmerLocation = farmerState && farmerDistrict ? `${farmerDistrict}, ${farmerState}` : farmerState || 'India';
                const currentSeason = getCurrentSeason();
                const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
                const query = `Pesticide product guide for a farmer in ${farmerLocation}.\n\nDate: ${today} | Current Season: ${currentSeason}\n\nProduct: ${pest.name} (${pest.category}), Primary Uses: ${pest.usage}, Market Price: ₹${pest.price} ${pest.unit}.\n\nProvide comprehensive usage guide specific to ${farmerLocation} region and ${currentSeason} season including: exact dosage per litre/acre, target pests and diseases, crops commonly used on, best application timing and method, safety precautions and PPE, pre-harvest interval (PHI in days), organic/bio alternatives, and storage advice. Give specific actionable advice. IMPORTANT: This is a one-way advisory panel, NOT a conversation. Do NOT include any closing lines like "feel free to ask", "if you have any questions", "if you need more information", "I hope this helps", or any invitation to continue a dialogue. End with your last piece of actionable advice.`;
                const res = await apiFetch(`/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: query, language, session_id: 'pest-advisory-' + Date.now(), farmer_id: farmerId || 'anonymous' }),
                });
                if (!res.ok) throw new Error('API error');
                const data = await res.json();
                let rawPestAdv = data.data?.reply || data.data?.response || data.response || data.message || 'No advisory available.';
                rawPestAdv = rawPestAdv.replace(/\n\s*Sources:\s*.+$/m, '').trim();
                rawPestAdv = stripConversationalTail(rawPestAdv);
                result = {
                    status: 'success',
                    data: {
                        advisory: rawPestAdv,
                        audioUrl: data.data?.audio_url || null,
                        audioKey: data.data?.audio_key || null,
                        audioPending: !!data.data?.audio_pending,
                        detectedLang: data.data?.detected_language || language,
                    }
                };
            }
            const advisory = result.data;
            setAiAdvisory(advisory);
            setAiAudioUrl(advisory.audioUrl || null);
            setAiAudioKey(advisory.audioKey || null);
            if (advisory.audioPending && advisory.advisory) {
                setAiAudioLoading(true);
                generateAsyncTts(advisory.advisory, advisory.detectedLang).then(tts => {
                    if (tts) {
                        setAiAudioUrl(tts.audioUrl);
                        setAiAudioKey(tts.audioKey);
                    }
                    setAiAudioLoading(false);
                });
            }
            setTimeout(() => advisoryRef.current?.scrollIntoView({ behavior: 'smooth' }), 200);
        } catch (err) {
            if (import.meta.env.DEV) console.error('AI pest advisory error:', err);
            setAiAdvisory({
                advisory: t('priceAiUnavailable'),
            });
        } finally {
            setAiLoading(false);
        }
    }, [language, farmerProfile]);

    return (
        <div className="price-page">
            <div className="page-header">
                <h2>💰 {pt.pageTitle}</h2>
                <p>{pt.pageSubtitle}</p>
            </div>

            <div className="price-page-scroll" ref={scrollRef}>

            {/* Tabs */}
            <div className="price-tabs">
                <button className={`price-tab ${tab === 'crops' ? 'active' : ''}`} onClick={() => { setTab('crops'); setSearch(''); setAiAdvisory(null); setAiCrop(null); setSortCol(null); setSortDir('asc'); }}>
                    🌾 {pt.tabCrops}
                </button>
                <button className={`price-tab ${tab === 'pests' ? 'active' : ''}`} onClick={() => { setTab('pests'); setSearch(''); setAiAdvisory(null); setAiCrop(null); setSortCol(null); setSortDir('asc'); }}>
                    🧪 {pt.tabPests}
                </button>
            </div>

            {/* AI Advisory Panel */}
            {aiAdvisory && (
                <div className={`ai-advisory-panel${aiType === 'pest' ? ' pest-panel' : ''}`} ref={advisoryRef}>
                    <div className="ai-advisory-header">
                        <h3>🤖 {aiType === 'pest' ? aiLabel.titlePest : aiLabel.titleCrop} — {aiType === 'pest' ? (pestName(aiCrop) || aiCrop) : (cropName(aiCrop) || aiCrop)}</h3>
                        <button className="ai-advisory-close" onClick={() => { setAiAdvisory(null); setAiCrop(null); setAiAudioUrl(null); setAiAudioKey(null); }}>{aiLabel.close}</button>
                    </div>
                    {aiAudioUrl && (
                        <audio controls src={aiAudioUrl} className="ai-result-audio"
                            onError={async (e) => {
                                if (aiAudioKey) {
                                    try {
                                        const res = await apiFetch(`/chat`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ refresh_audio_key: aiAudioKey })
                                        });
                                        const d = await res.json();
                                        if (d.status === 'success' && d.data?.audio_url) {
                                            e.target.src = d.data.audio_url;
                                            setAiAudioUrl(d.data.audio_url);
                                        }
                                    } catch { /* silent */ }
                                }
                            }}
                        />
                    )}
                    {aiAudioLoading && (
                        <div className="audio-loading-indicator">
                            <span className="spinner-sm"></span> {t('ttsGenerating') || 'Generating audio...'}
                        </div>
                    )}
                    <div className="ai-advisory-body"
                        dangerouslySetInnerHTML={{ __html: formatText(aiAdvisory.advisory) }} />
                </div>
            )}

            {/* Search & Filter */}
            <div className="price-toolbar">
                <input
                    type="text"
                    className="price-search"
                    placeholder={tab === 'crops' ? `🔍 ${pt.searchCrops}` : `🔍 ${pt.searchPests}`}
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                />
                {tab === 'crops' ? (
                    <select className="price-filter" value={seasonFilter} onChange={e => setSeasonFilter(e.target.value)}>
                        {SEASONS.map(s => <option key={s} value={s}>{s === 'All' ? `📅 ${pt.allSeasons}` : seasonName(s)}</option>)}
                    </select>
                ) : (
                    <select className="price-filter" value={pestCatFilter} onChange={e => setPestCatFilter(e.target.value)}>
                        {PEST_CATEGORIES.map(c => <option key={c} value={c}>{c === 'All' ? `📂 ${pt.allCategories}` : catName(c)}</option>)}
                    </select>
                )}
            </div>

            {/* Crop Prices Table */}
            {tab === 'crops' && (
                <div className="price-table-wrap">
                    <table className="price-table">
                        <thead>
                            <tr>
                                <th onClick={() => handleSort('name')}>{pt.thCrop} <SortArrow column="name" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('season')}>{pt.thSeason} <SortArrow column="season" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('msp')}>{pt.thMSP} <SortArrow column="msp" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('market')}>{pt.thMarketRange} <SortArrow column="market" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('trend')}>{pt.thTrend} <SortArrow column="trend" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th>AI</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredCrops.map((c, i) => (
                                <tr key={i} className={aiCrop === c.name ? 'ai-active-row' : ''}>
                                    <td className="price-crop-name">🌱 {cropName(c.name)}</td>
                                    <td><span className="price-season-badge">{seasonName(c.season)}</span></td>
                                    <td className="price-msp">{c.msp ? `₹${c.msp.toLocaleString()}` : '—'}</td>
                                    <td className="price-range">
                                        ₹{c.marketMin.toLocaleString()} – ₹{c.marketMax.toLocaleString()}
                                        <span className="price-unit">{unitName(c.unit)}</span>
                                    </td>
                                    <td><TrendBadge trend={c.trend} pt={pt} /></td>
                                    <td>
                                        <button
                                            className="ai-ask-btn"
                                            disabled={aiLoading}
                                            onClick={() => askAI(c)}
                                            title={aiLabel.ask}
                                        >
                                            {aiLoading && aiCrop === c.name ? aiLabel.asking : aiLabel.ask}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {filteredCrops.length === 0 && (
                        <p className="price-empty">{pt.emptyCrops}</p>
                    )}
                    <p className="price-disclaimer">
                        ⚠️ {pt.disclaimerCrops}
                    </p>
                </div>
            )}

            {/* Pesticide Rates Table */}
            {tab === 'pests' && (
                <div className="price-table-wrap">
                    <table className="price-table">
                        <thead>
                            <tr>
                                <th onClick={() => handleSort('pname')}>{pt.thProduct} <SortArrow column="pname" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('category')}>{pt.thCategory} <SortArrow column="category" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('price')}>{pt.thPrice} <SortArrow column="price" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th onClick={() => handleSort('usage')}>{pt.thUsage} <SortArrow column="usage" sortCol={sortCol} sortDir={sortDir} /></th>
                                <th>AI</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredPests.map((p, i) => (
                                <tr key={i} className={aiCrop === p.name && aiType === 'pest' ? 'ai-active-row' : ''}>
                                    <td className="price-crop-name">🧴 {pestName(p.name)}</td>
                                    <td><span className={`pest-cat-badge cat-${p.category.toLowerCase().replace(/[^a-z]/g, '')}`}>{catName(p.category)}</span></td>
                                    <td className="price-msp">₹{p.price} <span className="price-unit">{unitName(p.unit)}</span></td>
                                    <td className="price-usage">{pestUsage(p.name, p.usage)}</td>
                                    <td>
                                        <button
                                            className="ai-ask-btn ai-ask-pest"
                                            disabled={aiLoading}
                                            onClick={() => askPestAI(p)}
                                            title={aiLabel.ask}
                                        >
                                            {aiLoading && aiCrop === p.name && aiType === 'pest' ? aiLabel.asking : aiLabel.ask}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {filteredPests.length === 0 && (
                        <p className="price-empty">{pt.emptyPests}</p>
                    )}
                    <p className="price-disclaimer">
                        ⚠️ {pt.disclaimerPests}
                    </p>
                </div>
            )}
            </div>{/* end price-page-scroll */}
            <ScrollPill scrollRef={scrollRef} />
        </div>
    );
}

export default PricePage;