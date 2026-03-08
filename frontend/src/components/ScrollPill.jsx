import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';

const SCROLL_LABELS = {
    'en-IN': 'Scroll down',
    'ta-IN': 'கீழே இழுக்கவும்',
    'hi-IN': 'नीचे स्क्रॉल करें',
    'te-IN': 'కిందికి స్క్రోల్ చేయండి',
    'kn-IN': 'ಕೆಳಗೆ ಸ್ಕ್ರಾಲ್ ಮಾಡಿ',
    'ml-IN': 'താഴേക്ക് സ്ക്രോൾ ചെയ്യുക',
    'bn-IN': 'নিচে স্ক্রল করুন',
    'mr-IN': 'खाली स्क्रोल करा',
    'gu-IN': 'નીચે સ્ક્રોલ કરો',
    'pa-IN': 'ਹੇਠਾਂ ਸਕ੍ਰੋਲ ਕਰੋ',
    'or-IN': 'ତଳକୁ ସ୍କ୍ରୋଲ କରନ୍ତୁ',
    'as-IN': 'তললৈ স্ক্ৰল কৰক',
    'ur-IN': 'نیچے سکرول کریں',
};

export default function ScrollPill({ scrollRef }) {
    const { language } = useLanguage();
    const [visible, setVisible] = useState(false);

    const checkScroll = useCallback(() => {
        const el = scrollRef?.current;
        if (!el) return;
        const hasMore = el.scrollHeight - el.scrollTop - el.clientHeight > 60;
        const nearTop = el.scrollTop < 80;
        setVisible(hasMore && nearTop);
    }, [scrollRef]);

    useEffect(() => {
        const el = scrollRef?.current;
        if (!el) return;
        checkScroll();
        el.addEventListener('scroll', checkScroll, { passive: true });
        const ro = new ResizeObserver(checkScroll);
        ro.observe(el);
        return () => {
            el.removeEventListener('scroll', checkScroll);
            ro.disconnect();
        };
    }, [scrollRef, checkScroll]);

    const label = SCROLL_LABELS[language] || SCROLL_LABELS['en-IN'];

    return (
        <div className={`scroll-pill${visible ? '' : ' hidden'}`}>
            {label}
            <span className="scroll-pill-icon">↓</span>
        </div>
    );
}
