// src/components/VoiceInput.jsx
// Uses streaming (live partial transcript) on supported browsers,
// falls back to AWS Transcribe when streaming is unavailable or fails.

import { useCallback, useEffect, useRef } from 'react';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useStreamingSpeech } from '../hooks/useStreamingSpeech';
import { useLanguage } from '../contexts/LanguageContext';

/* ── Status labels (Recording = AWS path, Listening = streaming path) ─── */
const LISTENING_TEXT = {
    'en-IN': 'Listening...', 'hi-IN': 'सुन रहा है...', 'ta-IN': 'கேட்கிறது...',
    'te-IN': 'వింటున్నది...', 'kn-IN': 'ಕೇಳುತ್ತಿದೆ...', 'ml-IN': 'കേൾക്കുന്നു...',
    'bn-IN': 'শুনছে...', 'mr-IN': 'ऐकत आहे...', 'gu-IN': 'સાંભળે છે...',
    'pa-IN': 'ਸੁਣ ਰਿਹਾ ਹੈ...', 'or-IN': 'ଶୁଣୁଛି...', 'as-IN': 'শুনি আছে...',
    'ur-IN': 'سن رہا ہے...',
};

const RECORDING_TEXT = {
    'en-IN': 'Recording...', 'hi-IN': 'रिकॉर्डिंग...', 'ta-IN': 'பதிவு செய்கிறது...',
    'te-IN': 'రికార్డింగ్...', 'kn-IN': 'ರೆಕಾರ್ಡಿಂಗ್...', 'ml-IN': 'റെക്കോർഡ് ചെയ്യുന്നു...',
    'bn-IN': 'রেকর্ডিং...', 'mr-IN': 'रेकॉर्डिंग...', 'gu-IN': 'રેકોર્ડિંગ...',
    'pa-IN': 'ਰਿਕਾਰਡਿੰਗ...', 'or-IN': 'ରେକର୍ଡିଂ...', 'as-IN': 'ৰেকৰ্ডিং...',
    'ur-IN': 'ریکارڈنگ...',
};

const PROCESSING_TEXT = {
    'en-IN': 'Processing...', 'hi-IN': 'प्रोसेसिंग...', 'ta-IN': 'செயலாக்குகிறது...',
    'te-IN': 'ప్రాసెస్ చేస్తోంది...', 'kn-IN': 'ಪ್ರಕ್ರಿಯೆ...', 'ml-IN': 'പ്രോസസ്സ് ചെയ്യുന്നു...',
    'bn-IN': 'প্রসেসিং...', 'mr-IN': 'प्रक्रिया...', 'gu-IN': 'પ્રોસેસિંગ...',
    'pa-IN': 'ਪ੍ਰੋਸੈਸਿੰਗ...', 'or-IN': 'ପ୍ରକ୍ରିୟାକରଣ...', 'as-IN': 'প্ৰচেছিং...',
    'ur-IN': 'پروسیسنگ...',
};

function VoiceInput({ language, onTranscript, onPartialTranscript }) {
    const { t } = useLanguage();
    const streaming = useStreamingSpeech(language, onTranscript);

    // Reliability-first on mobile: streaming web speech is inconsistent across devices.
    const isMobileBrowser =
        typeof navigator !== 'undefined' &&
        /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');

    const aws = useSpeechRecognition(language, onTranscript, {
        preferNative: !isMobileBrowser,
    });

    // Use streaming only on desktop-class browsers.
    // Mobile uses recorder/transcribe path for consistent behavior.
    const useStreaming = streaming.supported && !isMobileBrowser;
    const fallbackRef = useRef(false);  // sticky: once streaming fails, stay on AWS

    // Forward live partial transcripts to parent (ChatPage shows them in input field)
    useEffect(() => {
        if (!onPartialTranscript) return;
        if (streaming.isListening) {
            onPartialTranscript(streaming.partialTranscript || '');
        } else {
            onPartialTranscript('');
        }
    }, [streaming.isListening, streaming.partialTranscript, onPartialTranscript]);

    const handleStart = useCallback(async () => {
        // Try streaming first (Chrome, Safari — instant partial results)
        if (useStreaming && !fallbackRef.current) {
            const started = streaming.startListening();
            if (started) return;
            // Streaming failed to start? Sticky fallback to AWS for this page session
            fallbackRef.current = true;
        }
        // Fallback: AWS Transcribe (MediaRecorder → batch upload)
        await aws.startListening();
    }, [useStreaming, streaming, aws]);

    const handleStop = useCallback(() => {
        if (streaming.isListening) streaming.stopListening();
        if (aws.isListening) aws.stopListening();
    }, [streaming, aws]);

    // Combine UI states from whichever path is active
    const isListening = streaming.isListening || aws.isListening;
    const isProcessing = aws.isProcessing;
    const error = streaming.error || aws.error;
    const isActive = isListening || isProcessing;

    // Pick label based on which path is active
    const listeningLabel = streaming.isListening
        ? (LISTENING_TEXT[language] || 'Listening...')
        : (RECORDING_TEXT[language] || 'Recording...');
    const processingLabel = PROCESSING_TEXT[language] || 'Processing...';

    return (
        <div className="voice-input-group">
            <button 
                className={`mic-btn ${isListening ? 'recording' : ''} ${isProcessing ? 'processing' : ''}`}
                onClick={isListening ? handleStop : handleStart}
                disabled={isProcessing}
                title={isListening ? (t('voiceStopListening') || 'Stop recording') : (t('voiceClickToSpeak') || 'Click to speak')}
            >
                {isListening ? '🔴' : isProcessing ? '⏳' : '🎤'}
            </button>
            {isListening && <span className="voice-status listening">{listeningLabel}</span>}
            {isProcessing && <span className="voice-status processing">{processingLabel}</span>}
            {error && !isActive && <span className="voice-status error">{error}</span>}
        </div>
    );
}

export default VoiceInput;
