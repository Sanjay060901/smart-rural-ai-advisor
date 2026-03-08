// src/components/ChatMessage.jsx

import { useState, useCallback, useRef, useEffect } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import config from '../config';
import { formatAndSanitize } from '../utils/sanitize';
import { apiFetch } from '../utils/apiFetch';
import { generateAsyncTts as generateAsyncTtsRequest } from '../utils/asyncTts';

function formatMessage(text) {
    return formatAndSanitize(text);
}

function formatTimestamp(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString([], {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function ChatMessage({ message, onUpdateAudioUrl }) {
    const isUser = message.role === 'user';
    const { t } = useLanguage();
    const [refreshedUrl, setRefreshedUrl] = useState(null);
    const [audioLoading, setAudioLoading] = useState(false);
    const refreshingRef = useRef(false);
    const ttsRequestedRef = useRef(false);

    const currentAudioUrl = refreshedUrl || message.audioUrl;

    // Fire async TTS generation for pending audio (gTTS languages)
    const generateAsyncTts = useCallback(async () => {
        if (ttsRequestedRef.current || currentAudioUrl) return;
        if (!message.audioPending || !message.content) return;
        ttsRequestedRef.current = true;
        setAudioLoading(true);
        const ttsResult = await generateAsyncTtsRequest(
            message.content,
            message.detected_language || 'en'
        );
        if (ttsResult?.audioUrl) {
            setRefreshedUrl(ttsResult.audioUrl);
            if (onUpdateAudioUrl) {
                onUpdateAudioUrl(message.timestamp, ttsResult.audioUrl, ttsResult.audioKey);
            }
        }
        setAudioLoading(false);
    }, [message.audioPending, message.content, message.detected_language, message.timestamp, currentAudioUrl, onUpdateAudioUrl]);

    // Auto-trigger async TTS when message has audio_pending
    useEffect(() => {
        if (message.audioPending && !currentAudioUrl && !ttsRequestedRef.current) {
            generateAsyncTts();
        }
    }, [message.audioPending, currentAudioUrl, generateAsyncTts]);

    const audioRef = useCallback(node => {
        if (node) {
            // Auto-refresh expired presigned URLs on error
            node.onerror = async () => {
                if (message.audioKey && !refreshingRef.current) {
                    refreshingRef.current = true;
                    try {
                        const res = await apiFetch(`/chat`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ refresh_audio_key: message.audioKey })
                        });
                        const data = await res.json();
                        if (data.status === 'success' && data.data?.audio_url) {
                            setRefreshedUrl(data.data.audio_url);
                            if (onUpdateAudioUrl) {
                                onUpdateAudioUrl(message.timestamp, data.data.audio_url);
                            }
                        }
                    } catch { /* silent */ }
                    refreshingRef.current = false;
                }
            };
        }
    }, [message.audioKey, message.timestamp, onUpdateAudioUrl]);

    return (
        <div className={`message ${message.role}`}>
            <div className="message-avatar">
                {isUser ? '👨‍🌾' : '🤖'}
            </div>
            <div className="message-body">
                <div 
                    className="message-text"
                    dangerouslySetInnerHTML={{ __html: formatMessage(message.content) }} 
                />
                {/* Audio player bar for Polly/gTTS audio */}
                {currentAudioUrl && (
                    <audio
                        id={'tts-audio-' + message.timestamp}
                        ref={audioRef}
                        controls
                        src={currentAudioUrl}
                        className="ai-result-audio"
                        preload="metadata"
                    />
                )}
                {audioLoading && (
                    <div className="audio-loading-indicator">
                        <span className="spinner-sm"></span> {t('ttsGenerating') || 'Generating audio...'}
                    </div>
                )}
                <div className="message-footer">
                    {message.timestamp && (
                        <span className="message-time" style={{ opacity: 1 }}>{formatTimestamp(message.timestamp)}</span>
                    )}
                </div>
            </div>
        </div>
    );
}

export default ChatMessage;
