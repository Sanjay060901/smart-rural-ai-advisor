// src/contexts/LanguageContext.jsx
// Global language state with explicit persistence control.
// Login screen should default to English unless the user is already authenticated.

import { createContext, useContext, useState, useCallback } from 'react';
import translations from '../i18n/translations';
import config from '../config';

const LanguageContext = createContext();

export function LanguageProvider({ children }) {
    const [language, setLanguageState] = useState(() => {
        const hasActiveLogin = !!localStorage.getItem('farmer_id');
        if (!hasActiveLogin) return config.DEFAULT_LANGUAGE;
        const stored = localStorage.getItem('app_language');
        return stored && translations[stored] ? stored : config.DEFAULT_LANGUAGE;
    });

    const setLanguage = useCallback((lang, options = {}) => {
        const { persist = true } = options;
        if (translations[lang]) {
            setLanguageState(lang);
            if (persist) {
                localStorage.setItem('app_language', lang);
            }
        }
    }, []);

    // t('key') returns the localized string, fallback to English
    const t = useCallback((key) => {
        return translations[language]?.[key]
            || translations['en-IN']?.[key]
            || key;
    }, [language]);

    return (
        <LanguageContext.Provider value={{ language, setLanguage, t }}>
            {children}
        </LanguageContext.Provider>
    );
}

export function useLanguage() {
    const ctx = useContext(LanguageContext);
    if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
    return ctx;
}
