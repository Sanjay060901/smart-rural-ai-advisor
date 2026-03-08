// src/hooks/useStreamingSpeech.js
// ChatGPT-style live speech-to-text using browser native SpeechRecognition.
// Runs in continuous mode and should keep listening across short pauses.
// Final transcript is delivered when user explicitly taps Stop.

import { useState, useRef, useCallback, useEffect } from 'react';
import config from '../config';

const STREAMING_SUPPORTED =
    typeof window !== 'undefined' &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

const IS_MOBILE_BROWSER =
    typeof navigator !== 'undefined' &&
    /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');

export function useStreamingSpeech(language = config.DEFAULT_LANGUAGE, onFinalTranscript) {
    const [isListening, setIsListening] = useState(false);
    const [partialTranscript, setPartialTranscript] = useState('');
    const [error, setError] = useState('');
    const [failed, setFailed] = useState(false);

    const recognitionRef = useRef(null);
    const onFinalRef = useRef(onFinalTranscript);
    const manualStopRef = useRef(false);
    const deliveredRef = useRef(false);     // prevent double-delivery
    const partialRef = useRef('');
    const finalTextRef = useRef('');         // accumulates isFinal segments

    useEffect(() => { onFinalRef.current = onFinalTranscript; }, [onFinalTranscript]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (recognitionRef.current) {
                try { recognitionRef.current.abort(); } catch { /* */ }
            }
        };
    }, []);

    // Helper: deliver final text exactly once and reset all state
    const _deliver = useCallback((text) => {
        if (deliveredRef.current) return;
        deliveredRef.current = true;
        setIsListening(false);
        setPartialTranscript('');
        partialRef.current = '';
        finalTextRef.current = '';
        if (text && onFinalRef.current) {
            onFinalRef.current(text);
        }
    }, []);

    /* ── start ─────────────────────────────────────────── */
    const startListening = useCallback(() => {
        if (!STREAMING_SUPPORTED) return false;
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return false;

        // Tear down previous
        if (recognitionRef.current) {
            try { recognitionRef.current.abort(); } catch { /* */ }
        }

        setError('');
        setPartialTranscript('');
        partialRef.current = '';
        finalTextRef.current = '';
        manualStopRef.current = false;
        deliveredRef.current = false;

        try {
            const recognition = new SR();
            recognitionRef.current = recognition;
            recognition.lang = language || config.DEFAULT_LANGUAGE;
            // iOS/Android can be unstable with continuous=true; restart on onend instead.
            recognition.continuous = !IS_MOBILE_BROWSER;
            recognition.interimResults = true;    // live partial transcripts
            recognition.maxAlternatives = 1;

            recognition.onresult = (event) => {
                let final = '';
                let interim = '';
                for (let i = 0; i < event.results.length; i++) {
                    const r = event.results[i];
                    if (r.isFinal) {
                        final += r[0].transcript;
                    } else {
                        interim += r[0].transcript;
                    }
                }
                if (final) finalTextRef.current = final;
                const display = (final || finalTextRef.current) + interim;
                partialRef.current = display;
                setPartialTranscript(display);
            };

            recognition.onerror = (event) => {
                const code = event?.error || 'unknown';
                if (code === 'aborted' && manualStopRef.current) return;
                if (code === 'not-allowed' || code === 'service-not-allowed') {
                    setError('Microphone permission denied. Please allow mic access.');
                    _deliver('');
                } else if (code === 'no-speech') {
                    // Keep listening on brief silence in continuous mode.
                    setError('');
                } else {
                    if (import.meta.env.DEV) console.warn('[StreamingSpeech] error, falling back to AWS:', code);
                    setFailed(true);
                    _deliver('');
                }
            };

            recognition.onend = () => {
                if (manualStopRef.current) {
                    const text = (finalTextRef.current || partialRef.current).trim();
                    _deliver(text);
                    return;
                }

                // Mobile browsers often block programmatic restart without fresh user gesture.
                // Finalize what we captured instead of entering a restart-fail loop.
                if (IS_MOBILE_BROWSER) {
                    const text = (finalTextRef.current || partialRef.current).trim();
                    _deliver(text);
                    return;
                }

                // Some browsers end recognition on pause even in continuous mode.
                // Restart automatically to preserve manual-stop UX.
                try {
                    recognition.start();
                    setIsListening(true);
                } catch {
                    setFailed(true);
                    _deliver('');
                }
            };

            recognition.start();
            setIsListening(true);

            return true;
        } catch (err) {
            if (import.meta.env.DEV) console.error('[StreamingSpeech] start error:', err);
            setFailed(true);
            return false;
        }
    }, [language, _deliver]);

    /* ── stop ──────────────────────────────────────────── */
    const stopListening = useCallback(() => {
        manualStopRef.current = true;
        const text = (finalTextRef.current || partialRef.current).trim();
        _deliver(text);
        // Force-kill — onend will no-op because deliveredRef is true
        if (recognitionRef.current) {
            try { recognitionRef.current.abort(); } catch { /* */ }
            recognitionRef.current = null;
        }
    }, [_deliver]);

    return {
        supported: STREAMING_SUPPORTED && !failed,
        isListening,
        partialTranscript,
        error,
        startListening,
        stopListening,
    };
}
