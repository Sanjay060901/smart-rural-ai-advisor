// src/config.js

import LANGUAGES from './languages';

const config = {
    // API Gateway URL
    API_URL: import.meta.env.VITE_API_URL || '',
    
    // Mock mode
    MOCK_AI: import.meta.env.VITE_MOCK_AI === 'true',

    // Cognito User Pool
    COGNITO_USER_POOL_ID: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
    COGNITO_CLIENT_ID: import.meta.env.VITE_COGNITO_CLIENT_ID || '',

    // Reference the standalone LANGUAGES export
    LANGUAGES,
    
    DEFAULT_LANGUAGE: 'en-IN',

    // Nominatim geocoding service base URL (no trailing slash)
    NOMINATIM_BASE_URL: 'https://nominatim.openstreetmap.org',

    // Country code prefix for phone numbers
    COUNTRY_CODE: '+91',
};

export default config;
