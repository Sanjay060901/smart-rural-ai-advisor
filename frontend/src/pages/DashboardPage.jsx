// src/pages/DashboardPage.jsx

import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import { useFarmer } from '../contexts/FarmerContext';
import ScrollPill from '../components/ScrollPill';

// Daily tips rotate based on day-of-year
const DAILY_TIPS = {
    'en-IN': [
        'Apply neem-based pesticides early morning for best results.',
        'Mulching helps retain soil moisture during dry spells.',
        'Rotate crops every season to maintain soil health.',
        'Drip irrigation saves up to 60% water compared to flood irrigation.',
        'Sow green manure crops like dhaincha between main seasons.',
        'Test your soil every 2 years to optimize fertilizer use.',
        'Install yellow sticky traps near crops to catch whiteflies.',
    ],
    'hi-IN': [
        'सबसे अच्छे परिणाम के लिए सुबह जल्दी नीम आधारित कीटनाशक लगाएं।',
        'सूखे मौसम में मल्चिंग से मिट्टी की नमी बनी रहती है।',
        'मिट्टी की सेहत बनाए रखने के लिए हर मौसम फसल बदलें।',
        'ड्रिप सिंचाई से बाढ़ सिंचाई की तुलना में 60% पानी बचता है।',
        'मुख्य मौसम के बीच ढैंचा जैसी हरी खाद की फसलें बोएं।',
        'उर्वरक उपयोग को अनुकूलित करने के लिए हर 2 साल में मिट्टी की जांच करें।',
        'सफेद मक्खी पकड़ने के लिए फसलों के पास पीले चिपचिपे जाल लगाएं।',
    ],
    'ta-IN': [
        'சிறந்த முடிவுகளுக்கு அதிகாலையில் வேப்பம் பூச்சிக்கொல்லிகளைப் பயன்படுத்தவும்.',
        'வறண்ட காலத்தில் மண்ணின் ஈரப்பதத்தைத் தக்கவைக்க மல்ச்சிங் உதவுகிறது.',
        'மண் ஆரோக்கியத்தை பராமரிக்க ஒவ்வொரு பருவத்திலும் பயிர் சுழற்சி செய்யுங்கள்.',
        'சொட்டு நீர் பாசனம் வெள்ள பாசனத்தை விட 60% தண்ணீரை சேமிக்கிறது.',
        'முக்கிய பருவங்களுக்கு இடையே தக்கை போன்ற பசுந்தாள் உரப் பயிர்களை விதைக்கவும்.',
        'உர பயன்பாட்டை மேம்படுத்த ஒவ்வொரு 2 ஆண்டுகளுக்கும் மண் பரிசோதனை செய்யுங்கள்.',
        'வெள்ளை ஈக்களைப் பிடிக்க பயிர்களுக்கு அருகில் மஞ்சள் ஒட்டும் பொறிகளை நிறுவவும்.',
    ],
    'kn-IN': [
        'ಉತ್ತಮ ಫಲಿತಾಂಶಗಳಿಗಾಗಿ ಬೆಳಗ್ಗೆ ಬೇಗನೆ ಬೇವಿನ ಕೀಟನಾಶಕಗಳನ್ನು ಬಳಸಿ.',
        'ಒಣ ಸಮಯದಲ್ಲಿ ಮಣ್ಣಿನ ತೇವಾಂಶವನ್ನು ಉಳಿಸಿಕೊಳ್ಳಲು ಮಲ್ಚಿಂಗ್ ಸಹಾಯ ಮಾಡುತ್ತದೆ.',
        'ಮಣ್ಣಿನ ಆರೋಗ್ಯವನ್ನು ಕಾಪಾಡಲು ಪ್ರತಿ ಋತುವಿನಲ್ಲಿ ಬೆಳೆ ಸರದಿ ಮಾಡಿ.',
        'ಹನಿ ನೀರಾವರಿ ಪ್ರವಾಹ ನೀರಾವರಿಗೆ ಹೋಲಿಸಿದರೆ 60% ನೀರನ್ನು ಉಳಿಸುತ್ತದೆ.',
        'ಮುಖ್ಯ ಋತುಗಳ ನಡುವೆ ಹಸಿರು ಗೊಬ್ಬರ ಬೆಳೆಗಳನ್ನು ಬಿತ್ತಿ.',
        'ರಸಗೊಬ್ಬರ ಬಳಕೆಯನ್ನು ಅತ್ಯುತ್ತಮವಾಗಿಸಲು ಪ್ರತಿ 2 ವರ್ಷಕ್ಕೊಮ್ಮೆ ಮಣ್ಣು ಪರೀಕ್ಷೆ ಮಾಡಿ.',
        'ಬಿಳಿ ನೊಣಗಳನ್ನು ಹಿಡಿಯಲು ಬೆಳೆಗಳ ಬಳಿ ಹಳದಿ ಅಂಟು ಬಲೆಗಳನ್ನು ಅಳವಡಿಸಿ.',
    ],
    'te-IN': [
        'ఉత్తమ ఫలితాల కోసం ఉదయాన్నే వేప ఆధారిత పురుగుమందులను వర్తింపజేయండి.',
        'ఎండ కాలంలో నేల తేమను నిలుపుకోవడానికి మల్చింగ్ సహాయపడుతుంది.',
        'నేల ఆరోగ్యాన్ని కాపాడుకోవడానికి ప్రతి సీజన్‌లో పంటలను మార్చండి.',
        'డ్రిప్ ఇరిగేషన్ వరద సేద్యంతో పోలిస్తే 60% నీటిని ఆదా చేస్తుంది.',
        'ప్రధాన సీజన్ల మధ్య జీలుగ వంటి పచ్చి ఎరువు పంటలను విత్తండి.',
        'ఎరువుల వినియోగాన్ని మెరుగుపరచడానికి ప్రతి 2 సంవత్సరాలకు నేల పరీక్ష చేయండి.',
        'తెల్ల ఈగలను పట్టుకోవడానికి పంటల దగ్గర పసుపు అంటుకునే ట్రాప్‌లను ఏర్పాటు చేయండి.',
    ],
    'ml-IN': [
        'മികച്ച ഫലങ്ങൾക്കായി രാവിലെ വേപ്പ് അധിഷ്ഠിത കീടനാശിനികൾ പ്രയോഗിക്കുക.',
        'വരൾച്ചക്കാലത്ത് മണ്ണിലെ ഈർപ്പം നിലനിർത്താൻ മൾച്ചിംഗ് സഹായിക്കുന്നു.',
        'മണ്ണിന്റെ ആരോഗ്യം നിലനിർത്താൻ ഓരോ സീസണിലും വിള മാറ്റം ചെയ്യുക.',
        'ഡ്രിപ്പ് ജലസേചനം വെള്ളപ്പൊക്ക ജലസേചനത്തെ അപേക്ഷിച്ച് 60% വെള്ളം ലാഭിക്കുന്നു.',
        'പ്രധാന സീസണുകൾക്കിടയിൽ പച്ചില വളമായി ധൈഞ്ച പോലുള്ള വിളകൾ വിതയ്ക്കുക.',
        'വളപ്രയോഗം ഒപ്റ്റിമൈസ് ചെയ്യാൻ ഓരോ 2 വർഷത്തിലും മണ്ണ് പരിശോധിക്കുക.',
        'വെള്ളീച്ചകളെ പിടിക്കാൻ വിളകൾക്ക് സമീപം മഞ്ഞ ഒട്ടുന്ന കെണികൾ സ്ഥാപിക്കുക.',
    ],
    'bn-IN': [
        'সেরা ফলাফলের জন্য সকালে নিম ভিত্তিক কীটনাশক প্রয়োগ করুন।',
        'শুষ্ক মরসুমে মাটির আর্দ্রতা ধরে রাখতে মালচিং সাহায্য করে।',
        'মাটির স্বাস্থ্য বজায় রাখতে প্রতি মরসুমে শস্য পরিবর্তন করুন।',
        'ড্রিপ সেচ বন্যা সেচের তুলনায় 60% জল বাঁচায়।',
        'প্রধান মরসুমের মধ্যে ধৈঞ্চার মতো সবুজ সার ফসল বুনুন।',
        'সার ব্যবহার অনুকূল করতে প্রতি 2 বছরে মাটি পরীক্ষা করুন।',
        'সাদা মাছি ধরতে ফসলের কাছে হলুদ আঠালো ফাঁদ লাগান।',
    ],
    'mr-IN': [
        'सर्वोत्तम परिणामांसाठी सकाळी लवकर कडुलिंबावर आधारित कीटकनाशके वापरा.',
        'कोरड्या हवामानात मातीचा ओलावा टिकवून ठेवण्यासाठी मल्चिंग मदत करते.',
        'मातीचे आरोग्य राखण्यासाठी दर हंगामात पीक फिरवा.',
        'ठिबक सिंचन पूर सिंचनाच्या तुलनेत 60% पाणी वाचवते.',
        'मुख्य हंगामांदरम्यान ताग सारख्या हिरव्या खताच्या पिकांची पेरणी करा.',
        'खत वापर अनुकूल करण्यासाठी दर 2 वर्षांनी माती तपासणी करा.',
        'पांढऱ्या माशा पकडण्यासाठी पिकांजवळ पिवळे चिकट सापळे लावा.',
    ],
    'gu-IN': [
        'શ્રેષ્ઠ પરિણામો માટે સવારે વહેલા લીમડા આધારિત જંતુનાશકો લગાવો.',
        'સૂકી ઋતુમાં જમીનની ભેજ જાળવવા મલ્ચિંગ મદદ કરે છે.',
        'જમીનની તંદુરસ્તી જાળવવા દર સિઝનમાં પાક ફેરબદલી કરો.',
        'ટપક સિંચાઈ પૂર સિંચાઈની સરખામણીમાં 60% પાણી બચાવે છે.',
        'મુખ્ય સિઝન વચ્ચે ધૈંચા જેવા લીલા ખાતરના પાક વાવો.',
        'ખાતર વપરાશ ઑપ્ટિમાઇઝ કરવા દર 2 વર્ષે જમીન પરીક્ષણ કરો.',
        'સફેદ માખી પકડવા પાક નજીક પીળા ચીકણા ટ્રેપ લગાવો.',
    ],
    'pa-IN': [
        'ਸਭ ਤੋਂ ਵਧੀਆ ਨਤੀਜਿਆਂ ਲਈ ਸਵੇਰੇ ਜਲਦੀ ਨਿੰਮ ਅਧਾਰਿਤ ਕੀਟਨਾਸ਼ਕ ਲਗਾਓ।',
        'ਸੁੱਕੇ ਮੌਸਮ ਵਿੱਚ ਮਿੱਟੀ ਦੀ ਨਮੀ ਬਣਾਈ ਰੱਖਣ ਲਈ ਮਲਚਿੰਗ ਮਦਦ ਕਰਦੀ ਹੈ।',
        'ਮਿੱਟੀ ਦੀ ਸਿਹਤ ਬਣਾਈ ਰੱਖਣ ਲਈ ਹਰ ਮੌਸਮ ਫ਼ਸਲ ਬਦਲੋ।',
        'ਡ੍ਰਿਪ ਸਿੰਚਾਈ ਹੜ੍ਹ ਸਿੰਚਾਈ ਦੇ ਮੁਕਾਬਲੇ 60% ਪਾਣੀ ਬਚਾਉਂਦੀ ਹੈ।',
        'ਮੁੱਖ ਮੌਸਮਾਂ ਵਿਚਕਾਰ ਢੈਂਚਾ ਵਰਗੀਆਂ ਹਰੀ ਖਾਦ ਦੀਆਂ ਫ਼ਸਲਾਂ ਬੀਜੋ।',
        'ਖਾਦ ਵਰਤੋਂ ਨੂੰ ਅਨੁਕੂਲ ਬਣਾਉਣ ਲਈ ਹਰ 2 ਸਾਲਾਂ ਬਾਅਦ ਮਿੱਟੀ ਪਰੀਖਿਆ ਕਰੋ।',
        'ਚਿੱਟੀ ਮੱਖੀ ਫੜਨ ਲਈ ਫ਼ਸਲਾਂ ਕੋਲ ਪੀਲੇ ਚਿਪਕਣ ਵਾਲੇ ਜਾਲ ਲਗਾਓ।',
    ],
    'or-IN': [
        'ସର୍ବୋତ୍ତମ ଫଳାଫଳ ପାଇଁ ସକାଳୁ ନିମ ଆଧାରିତ କୀଟନାଶକ ପ୍ରୟୋଗ କରନ୍ତୁ।',
        'ଶୁଷ୍କ ସମୟରେ ମାଟିର ଆର୍ଦ୍ରତା ଧରି ରଖିବାରେ ମଲ୍ଚିଂ ସାହାଯ୍ୟ କରେ।',
        'ମାଟିର ସ୍ୱାସ୍ଥ୍ୟ ବଜାୟ ରଖିବା ପାଇଁ ପ୍ରତି ଋତୁରେ ଫସଲ ପରିବର୍ତ୍ତନ କରନ୍ତୁ।',
        'ଡ୍ରିପ ଜଳସେଚନ ବନ୍ୟା ଜଳସେଚନ ତୁଳନାରେ 60% ଜଳ ସଞ୍ଚୟ କରେ।',
        'ମୁଖ୍ୟ ଋତୁ ମଧ୍ୟରେ ଧୈଞ୍ଚା ପରି ସବୁଜ ସାର ଫସଲ ବୁଣନ୍ତୁ।',
        'ସାର ବ୍ୟବହାର ଅନୁକୂଳ କରିବାକୁ ପ୍ରତି 2 ବର୍ଷରେ ମାଟି ପରୀକ୍ଷା କରନ୍ତୁ।',
        'ଧଳା ମାଛି ଧରିବା ପାଇଁ ଫସଲ ପାଖରେ ହଳଦିଆ ଆଠାଳିଆ ଫାନ୍ଦ ଲଗାନ୍ତୁ।',
    ],
    'as-IN': [
        'সৰ্বোত্তম ফলাফলৰ বাবে ৰাতিপুৱা নিম ভিত্তিক কীটনাশক প্ৰয়োগ কৰক।',
        'শুকান সময়ত মাটিৰ আৰ্দ্ৰতা ধৰি ৰাখিবলৈ মালচিং সহায়ক।',
        'মাটিৰ স্বাস্থ্য বজাই ৰাখিবলৈ প্ৰতি ঋতুত শস্য সলনি কৰক।',
        'ড্ৰিপ জলসিঞ্চনে বানপানী জলসিঞ্চনতকৈ 60% পানী ৰাহি কৰে।',
        'মুখ্য ঋতুৰ মাজত ধৈঞ্চাৰ দৰে সেউজ সাৰ শস্য সিঁচক।',
        'সাৰ ব্যৱহাৰ অনুকূল কৰিবলৈ প্ৰতি 2 বছৰত মাটি পৰীক্ষা কৰক।',
        'বগা মাখি ধৰিবলৈ শস্যৰ ওচৰত হালধীয়া আঠাল ফান্দ লগাওক।',
    ],
    'ur-IN': [
        'بہترین نتائج کے لیے صبح سویرے نیم پر مبنی کیڑے مار دوائیں لگائیں۔',
        'خشک موسم میں مٹی کی نمی برقرار رکھنے میں ملچنگ مدد کرتی ہے۔',
        'مٹی کی صحت برقرار رکھنے کے لیے ہر موسم فصل بدلیں۔',
        'ڈرپ آبپاشی سیلابی آبپاشی کے مقابلے 60% پانی بچاتی ہے۔',
        'اہم موسموں کے درمیان ڈھینچا جیسی سبز کھاد کی فصلیں بوئیں۔',
        'کھاد کے استعمال کو بہتر بنانے کے لیے ہر 2 سال میں مٹی کی جانچ کریں۔',
        'سفید مکھی پکڑنے کے لیے فصلوں کے قریب پیلے چپکنے والے جال لگائیں۔',
    ],
};

function DashboardPage() {
    const { language, t } = useLanguage();
    const { farmerName } = useFarmer();
    const navigate = useNavigate();
    const [greeting, setGreeting] = useState('');
    const [currentTime, setCurrentTime] = useState(new Date());
    const scrollRef = useRef(null);

    useEffect(() => {
        const hour = new Date().getHours();
        if (hour < 12) setGreeting(t('dashGreetMorning'));
        else if (hour < 17) setGreeting(t('dashGreetAfternoon'));
        else setGreeting(t('dashGreetEvening'));

        const timer = setInterval(() => setCurrentTime(new Date()), 60000);
        return () => clearInterval(timer);
    }, [t]);

    const dayOfYear = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 0)) / 86400000);
    const tips = DAILY_TIPS[language] || DAILY_TIPS['en-IN'];
    const dailyTip = tips[dayOfYear % tips.length];

    const quickActions = [
        { icon: '💬', title: t('dashActionChat'), desc: t('dashActionChatDesc'), path: '/chat', color: '#16a34a' },
        { icon: '🌤️', title: t('dashActionWeather'), desc: t('dashActionWeatherDesc'), path: '/weather', color: '#0284c7' },
        { icon: '📋', title: t('dashActionSchemes'), desc: t('dashActionSchemesDesc'), path: '/schemes', color: '#d97706' },
        { icon: '📸', title: t('dashActionCropDoc'), desc: t('dashActionCropDocDesc'), path: '/crop-doctor', color: '#7c3aed' },
        { icon: '💰', title: t('dashActionMarket'), desc: t('dashActionMarketDesc'), path: '/prices', color: '#dc2626' },
        { icon: '🌱', title: t('dashActionCropRec'), desc: t('dashActionCropRecDesc'), path: '/crop-recommend', color: '#059669' },
        { icon: '📅', title: t('dashActionFarmCal'), desc: t('dashActionFarmCalDesc'), path: '/farm-calendar', color: '#7c3aed' },
        { icon: '🧪', title: t('dashActionSoil'), desc: t('dashActionSoilDesc'), path: '/soil-analysis', color: '#b45309' },
    ];

    const seasonInfo = (() => {
        const month = new Date().getMonth() + 1;
        if (month >= 6 && month <= 9) return { name: t('dashSeasonKharif'), icon: '🌧️', months: t('dashMonthsKharif') || 'Jun–Sep' };
        if (month >= 10 && month <= 2) return { name: t('dashSeasonRabi'), icon: '❄️', months: t('dashMonthsRabi') || 'Oct–Feb' };
        return { name: t('dashSeasonZaid'), icon: '☀️', months: t('dashMonthsZaid') || 'Mar–May' };
    })();

    return (
        <div className="dashboard">
            {/* Hero greeting */}
            <div className="dash-hero">
                <div className="dash-hero-text">
                    <h1>{greeting}{farmerName ? `, ${farmerName}` : ''} 👋</h1>
                    <p className="dash-subtitle">{t('dashWelcome')}</p>
                    <div className="dash-meta">
                        <span className="dash-meta-item">
                            📅 {currentTime.toLocaleDateString(language, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                        </span>
                        <span className="dash-meta-item">
                            {seasonInfo.icon} {seasonInfo.name} ({seasonInfo.months})
                        </span>
                    </div>
                </div>
                <div className="dash-hero-art">🌾</div>
            </div>

            <div className="dashboard-scroll" ref={scrollRef}>

            {/* Quick Actions */}
            <h3 className="dash-section-title">{t('dashQuickActions')}</h3>
            <div className="dash-actions">
                {quickActions.map((action, i) => (
                    <button key={i} className="dash-action-card" onClick={() => navigate(action.path)}
                        style={{ '--action-color': action.color }}>
                        <span className="dash-action-icon">{action.icon}</span>
                        <span className="dash-action-title">{action.title}</span>
                        <span className="dash-action-desc">{action.desc}</span>
                    </button>
                ))}
            </div>

            {/* Daily Tip */}
            <div className="dash-tip-card">
                <div className="dash-tip-icon">💡</div>
                <div>
                    <h4>{t('dashDailyTip')}</h4>
                    <p>{dailyTip}</p>
                </div>
            </div>
            </div>{/* end dashboard-scroll */}
            <ScrollPill scrollRef={scrollRef} />
        </div>
    );
}

export default DashboardPage;
