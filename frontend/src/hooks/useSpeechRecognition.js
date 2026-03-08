// src/hooks/useSpeechRecognition.js
// ALWAYS uses MediaRecorder + AWS Transcribe — reliable for all 13 languages
// and all browsers (Chrome, Firefox, Edge, Safari)

import { useState, useRef, useCallback, useEffect } from 'react';
import config from '../config';
import { apiFetch } from '../utils/apiFetch';

export function useSpeechRecognition(language = config.DEFAULT_LANGUAGE, onResult, options = {}) {
    const [isListening, setIsListening] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [error, setError] = useState('');
    const recognitionRef = useRef(null);
    const manualStopRef = useRef(false);
    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);
    const streamRef = useRef(null);
    const onResultRef = useRef(onResult);
    const autoStopTimerRef = useRef(null);
    const nativeGotResultRef = useRef(false);
    const nativeFallbackTriggeredRef = useRef(false);
    const recorderAutoStopTimerRef = useRef(null);
    const preferNative = options?.preferNative !== false;

    // Always keep the callback ref synced with the latest value
    useEffect(() => { onResultRef.current = onResult; }, [onResult]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (autoStopTimerRef.current) clearTimeout(autoStopTimerRef.current);
            if (recorderAutoStopTimerRef.current) clearTimeout(recorderAutoStopTimerRef.current);
            if (recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch { /* */ }
            }
            if (mediaRecorderRef.current?.state === 'recording') {
                try { mediaRecorderRef.current.stop(); } catch { /* */ }
            }
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(t => t.stop());
            }
        };
    }, []);

    const _supportsNativeSpeech = useCallback(() => {
        return typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    }, []);

    const _isEdgeBrowser = useCallback(() => {
        return typeof navigator !== 'undefined' && /Edg\//.test(navigator.userAgent || '');
    }, []);

    const _sendToTranscribe = useCallback(async (chunks, mimeType) => {
        if (chunks.length === 0) {
            setError('No audio captured. Please try again.');
            setIsProcessing(false);
            return;
        }

        const blob = new Blob(chunks, { type: mimeType });

        // Skip tiny recordings (likely noise/silence)
        if (blob.size < 1000) {
            setError('Recording too short. Please hold the mic button and speak clearly.');
            setIsProcessing(false);
            return;
        }

        const reader = new FileReader();
        reader.onloadend = async () => {
            const base64 = reader.result.split(',')[1];
            try {
                const res = await apiFetch(`/transcribe`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio: base64, language, format: mimeType })
                });
                const data = await res.json();
                const transcript = data?.data?.transcript || data?.transcript;
                if (transcript?.trim() && onResultRef.current) {
                    onResultRef.current(transcript.trim());
                    setError('');
                } else {
                    setError('Could not understand. Please speak clearly and try again.');
                }
            } catch {
                setError('Connection error. Please check your internet and try again.');
            }
            setIsProcessing(false);
        };
        reader.readAsDataURL(blob);
    }, [language]);

    const _startAwsRecorder = useCallback(async () => {
        // Stop any previous recording
        if (recognitionRef.current) {
            try { recognitionRef.current.stop(); } catch { /* */ }
            recognitionRef.current = null;
        }
        if (mediaRecorderRef.current?.state === 'recording') {
            try { mediaRecorderRef.current.stop(); } catch { /* */ }
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => t.stop());
            streamRef.current = null;
        }

        try {
            if (!navigator?.mediaDevices?.getUserMedia) {
                setError('Microphone is not supported in this browser. Please use Chrome or Safari.');
                setIsListening(false);
                setIsProcessing(false);
                return false;
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    channelCount: 1,
                }
            });
            streamRef.current = stream;

            if (typeof window === 'undefined' || !window.MediaRecorder) {
                stream.getTracks().forEach(t => t.stop());
                streamRef.current = null;
                setError('Audio recording is not supported in this browser. Please use latest Chrome/Safari.');
                setIsListening(false);
                setIsProcessing(false);
                return false;
            }

            const MR = window.MediaRecorder;
            const mimeType = MR.isTypeSupported?.('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MR.isTypeSupported?.('audio/webm')
                    ? 'audio/webm'
                    : MR.isTypeSupported?.('audio/mp4')
                        ? 'audio/mp4'
                        : MR.isTypeSupported?.('audio/ogg;codecs=opus')
                            ? 'audio/ogg;codecs=opus'
                            : '';

            const recorder = mimeType
                ? new MR(stream, { mimeType })
                : new MR(stream);
            mediaRecorderRef.current = recorder;
            chunksRef.current = [];

            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            recorder.onstop = () => {
                if (recorderAutoStopTimerRef.current) {
                    clearTimeout(recorderAutoStopTimerRef.current);
                    recorderAutoStopTimerRef.current = null;
                }
                stream.getTracks().forEach(t => t.stop());
                streamRef.current = null;

                setIsListening(false);
                setIsProcessing(true);
                _sendToTranscribe(chunksRef.current, mimeType || 'audio/webm');
            };

            recorder.start(250);

            // Mobile users often tap once and expect auto-finish.
            // Auto-stop after a short window to ensure transcript gets submitted.
            recorderAutoStopTimerRef.current = setTimeout(() => {
                if (mediaRecorderRef.current?.state === 'recording') {
                    try { mediaRecorderRef.current.stop(); } catch { /* */ }
                }
            }, 7000);

            setIsListening(true);

            return true;
        } catch (err) {
            if (import.meta.env.DEV) console.error('Mic access error:', err);
            if (err.name === 'NotAllowedError') {
                setError('Microphone permission denied. Please allow mic access in your browser settings.');
            } else if (err.name === 'NotFoundError') {
                setError('No microphone found. Please connect a mic and try again.');
            } else {
                setError('Could not access microphone. Please try again.');
            }
            setIsListening(false);
            setIsProcessing(false);
            return false;
        }
    }, [_sendToTranscribe]);

    const _startNativeSpeechRecognition = useCallback(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return false;

        try {
            const recognition = new SpeechRecognition();
            recognitionRef.current = recognition;
            recognition.lang = language || config.DEFAULT_LANGUAGE;
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;
            nativeGotResultRef.current = false;
            nativeFallbackTriggeredRef.current = false;

            recognition.onresult = (event) => {
                const transcript = event?.results?.[0]?.[0]?.transcript?.trim();
                if (transcript && onResultRef.current) {
                    nativeGotResultRef.current = true;
                    onResultRef.current(transcript);
                    setError('');
                } else {
                    setError('Could not understand. Please speak clearly and try again.');
                }
            };

            recognition.onerror = (event) => {
                const code = event?.error || 'unknown';
                if (code === 'aborted' && manualStopRef.current) return;
                if (code === 'not-allowed' || code === 'service-not-allowed') {
                    setError('Microphone permission denied. Please allow mic access in your browser settings.');
                } else if (code === 'no-speech') {
                    setError('No speech detected. Please try again.');
                } else {
                    // Fallback to AWS Transcribe path for better cross-browser reliability
                    setError('');
                    setIsListening(false);
                    setIsProcessing(false);
                    nativeFallbackTriggeredRef.current = true;
                    _startAwsRecorder();
                }
            };

            recognition.onend = () => {
                if (!manualStopRef.current && !nativeGotResultRef.current && !nativeFallbackTriggeredRef.current) {
                    // Some browsers end native recognition with no result and no explicit error.
                    // Recover silently by switching to AWS recorder.
                    nativeFallbackTriggeredRef.current = true;
                    setError('');
                    setIsListening(false);
                    setIsProcessing(false);
                    _startAwsRecorder();
                    return;
                }

                manualStopRef.current = false;
                setIsListening(false);
                setIsProcessing(false);
                if (autoStopTimerRef.current) {
                    clearTimeout(autoStopTimerRef.current);
                    autoStopTimerRef.current = null;
                }
            };

            setIsListening(true);
            setIsProcessing(false);
            recognition.start();

            // Hard stop native recognition after 8s so UI never hangs
            autoStopTimerRef.current = setTimeout(() => {
                try { recognition.stop(); } catch { /* */ }
            }, 8000);

            return true;
        } catch {
            return false;
        }
    }, [language, _startAwsRecorder]);

    const startListening = useCallback(async () => {
        setError('');
        setIsProcessing(false);
        manualStopRef.current = false;

        // Fast path: browser-native speech recognition (much lower latency)
        if (preferNative && _supportsNativeSpeech()) {
            const started = _startNativeSpeechRecognition();
            if (started) return;
        }
        await _startAwsRecorder();
    }, [_startAwsRecorder, _startNativeSpeechRecognition, _supportsNativeSpeech, preferNative]);

    const stopListening = useCallback(() => {
        manualStopRef.current = true;
        if (autoStopTimerRef.current) {
            clearTimeout(autoStopTimerRef.current);
            autoStopTimerRef.current = null;
        }
        if (recorderAutoStopTimerRef.current) {
            clearTimeout(recorderAutoStopTimerRef.current);
            recorderAutoStopTimerRef.current = null;
        }

        // Update UI immediately on user stop tap
        setIsListening(false);
        setIsProcessing(false);

        if (recognitionRef.current) {
            try { recognitionRef.current.abort(); } catch { /* */ }
            try { recognitionRef.current.stop(); } catch { /* */ }
            recognitionRef.current = null;
        }
        if (mediaRecorderRef.current?.state === 'recording') {
            mediaRecorderRef.current.stop();
        }
    }, []);

    return { isListening, isProcessing, error, startListening, stopListening };
}
