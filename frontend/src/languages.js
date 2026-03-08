// src/languages.js - Standalone language definitions
// Separated from config.js to ensure proper code-split chunk resolution

const LANGUAGES = {
    'en-IN': { name: 'English', code: 'en' },
    'hi-IN': { name: '\u0939\u093f\u0928\u094d\u0926\u0940 (Hindi)', code: 'hi' },
    'ta-IN': { name: '\u0ba4\u0bae\u0bbf\u0bb4\u0bcd (Tamil)', code: 'ta' },
    'te-IN': { name: '\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41 (Telugu)', code: 'te' },
    'kn-IN': { name: '\u0c95\u0ca8\u0ccd\u0ca8\u0ca1 (Kannada)', code: 'kn' },
    'ml-IN': { name: '\u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02 (Malayalam)', code: 'ml' },
    'bn-IN': { name: '\u09ac\u09be\u0982\u09b2\u09be (Bengali)', code: 'bn' },
    'mr-IN': { name: '\u092e\u0930\u093e\u0920\u0940 (Marathi)', code: 'mr' },
    'gu-IN': { name: '\u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0 (Gujarati)', code: 'gu' },
    'pa-IN': { name: '\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40 (Punjabi)', code: 'pa' },
    'or-IN': { name: '\u0b13\u0b21\u0b3c\u0b3f\u0b06 (Odia)', code: 'or' },
    'as-IN': { name: '\u0985\u09b8\u09ae\u09c0\u09af\u09bc\u09be (Assamese)', code: 'as' },
    'ur-IN': { name: '\u0627\u0631\u062f\u0648 (Urdu)', code: 'ur' }
};

export default LANGUAGES;
