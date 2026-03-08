// src/App.jsx

import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import React, { useEffect, useRef, useState, lazy, Suspense } from 'react';
import { LanguageProvider, useLanguage } from './contexts/LanguageContext';
import { FarmerProvider, useFarmer } from './contexts/FarmerContext';
import * as cognitoAuth from './services/cognitoAuth';
import Sidebar from './components/Sidebar';
import DashboardPage from './pages/DashboardPage';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import './App.css';

// Lazy-load heavy pages (Leaflet map ~150KB, etc.) — only fetched when navigated to
const WeatherPage = lazy(() => import('./pages/WeatherPage'));
const SchemesPage = lazy(() => import('./pages/SchemesPage'));
const CropDoctorPage = lazy(() => import('./pages/CropDoctorPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const PricePage = lazy(() => import('./pages/PricePage'));
const CropRecommendPage = lazy(() => import('./pages/CropRecommendPage'));
const FarmCalendarPage = lazy(() => import('./pages/FarmCalendarPage'));
const SoilAnalysisPage = lazy(() => import('./pages/SoilAnalysisPage'));

// ErrorBoundary — catches render errors and shows a retry button instead of white screen
class PageErrorBoundary extends React.Component {
    constructor(props) { super(props); this.state = { hasError: false, error: null }; }
    static getDerivedStateFromError(error) { return { hasError: true, error }; }
    componentDidCatch(err, info) { console.error('Page crash:', err, info); }
    render() {
        if (this.state.hasError) {
            return (
                <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '12px' }}>⚠️</div>
                    <h2 style={{ color: '#dc2626', marginBottom: '8px' }}>Something went wrong</h2>
                    <p style={{ color: '#666', marginBottom: '20px' }}>This page encountered an error.</p>
                    {this.state.error && <p style={{ color: '#999', fontSize: '12px', fontFamily: 'monospace', maxWidth: '500px', margin: '0 auto 20px', wordBreak: 'break-word' }}>{this.state.error.message || String(this.state.error)}</p>}
                    <button onClick={() => this.setState({ hasError: false, error: null })} style={{ padding: '10px 24px', background: '#15803d', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '15px' }}>Try Again</button>
                </div>
            );
        }
        return this.props.children;
    }
}

// Lightweight loading fallback for lazy pages
const PageLoader = () => (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh', opacity: 0.6 }}>
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', marginBottom: '8px' }}>🌾</div>
            <div style={{ color: 'var(--text-secondary, #666)' }}>Loading...</div>
        </div>
    </div>
);

function ScrollToTop() {
    const { pathname } = useLocation();
    useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
    return null;
}

// 404 fallback for unknown routes
function NotFoundPage() {
    const navigate = useNavigate();
    return (
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
            <div style={{ fontSize: '4rem', marginBottom: '16px' }}>🌾</div>
            <h2 style={{ color: '#15803d', marginBottom: '12px' }}>Page Not Found</h2>
            <p style={{ color: '#666', marginBottom: '24px' }}>The page you are looking for does not exist.</p>
            <button onClick={() => navigate('/')} style={{ padding: '10px 24px', background: '#15803d', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '15px' }}>Go to Dashboard</button>
        </div>
    );
}

function MicFab() {
    const { pathname } = useLocation();
    const navigate = useNavigate();
    const { t } = useLanguage();
    if (pathname === '/chat') return null;
    return (
        <div className="mic-fab-wrapper">
            <span className="mic-fab-tooltip">{t('micFabTooltip')}</span>
            <button
                className="dash-mic-fab"
                onClick={() => navigate('/chat')}
                aria-label={t('micFabTooltip')}
            >
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                    <line x1="12" y1="19" x2="12" y2="23"/>
                    <line x1="8" y1="23" x2="16" y2="23"/>
                </svg>
            </button>
        </div>
    );
}

function EmailVerifyScreen() {
    const { t } = useLanguage();
    const { setNeedsEmailVerification } = useFarmer();
    const [code, setCode] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);
    const [showVerifyCode, setShowVerifyCode] = useState(false);

    const handleVerify = async () => {
        if (code.length < 6) { setError(t('forgotPinOtpRequired') || 'Enter the 6-digit code'); return; }
        setLoading(true);
        setError('');
        try {
            await cognitoAuth.verifyEmail(code.trim());
            setSuccess(true);
            setTimeout(() => setNeedsEmailVerification(false), 1500);
        } catch (err) {
            const msg = err?.message || '';
            if (msg.includes('CodeMismatch') || msg.includes('Invalid')) {
                setError(t('forgotPinInvalidOtp') || 'Invalid code. Please check and try again.');
            } else if (msg.includes('Expired')) {
                setError(t('forgotPinExpiredOtp') || 'Code expired. Please request a new one.');
            } else {
                setError(msg || 'Verification failed.');
            }
        }
        setLoading(false);
    };

    const handleResend = async () => {
        setLoading(true);
        setError('');
        try {
            await cognitoAuth.sendEmailVerificationCode();
            setError('');
        } catch {
            setError('Could not resend code.');
        }
        setLoading(false);
    };

    return (
        <div className="login-page">
            <div className="login-container">
                <div className="login-logo">
                    <span className="login-logo-icon">📧</span>
                    <h1>{t('verifyEmailTitle') || 'Verify Your Email'}</h1>
                    <p className="login-tagline">{t('verifyEmailSubtitle') || 'We sent a verification code to your email. Enter it below to complete registration.'}</p>
                </div>
                <div className="login-form">
                    {success ? (
                        <div className="login-success" style={{ fontSize: '16px', textAlign: 'center', padding: '24px 0' }}>
                            ✅ {t('verifyEmailSuccess') || 'Email verified successfully! Entering the app...'}
                        </div>
                    ) : (
                        <>
                            <div className="login-form-group">
                                <label>{t('forgotPinOtpLabel') || 'Verification Code'}</label>
                                <div className="auth-code-input-wrap">
                                    <input
                                        type={showVerifyCode ? 'text' : 'password'}
                                        className="form-input"
                                        maxLength={6}
                                        value={code}
                                        inputMode="numeric"
                                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                                        placeholder={t('forgotPinOtpPlaceholder') || 'Enter 6-digit code'}
                                        autoFocus
                                        onKeyDown={(e) => { if (e.key === 'Enter' && code.length >= 6 && !loading) handleVerify(); }}
                                        style={{ textAlign: 'center', fontSize: '20px', letterSpacing: '4px' }}
                                    />
                                    <button
                                        type="button"
                                        className="auth-visibility-btn"
                                        onClick={() => setShowVerifyCode(prev => !prev)}
                                        aria-label={showVerifyCode ? 'Hide code' : 'Show code'}
                                        title={showVerifyCode ? 'Hide code' : 'Show code'}
                                    >
                                        {showVerifyCode ? '🙈' : '👁'}
                                    </button>
                                </div>
                            </div>
                            {error && <div className="login-error">{error}</div>}
                            <button
                                className="login-btn login-btn-primary"
                                onClick={handleVerify}
                                disabled={loading || code.length < 6}
                            >
                                {loading ? '⏳ ...' : `✅ ${t('verifyEmailBtn') || 'Verify Email'}`}
                            </button>
                            <button
                                className="login-btn-link login-forgot-pin"
                                onClick={handleResend}
                                disabled={loading}
                                style={{ marginTop: '8px' }}
                            >
                                📨 {t('verifyEmailResend') || 'Resend Code'}
                            </button>
                            <button
                                className="login-btn-link"
                                onClick={() => setNeedsEmailVerification(false)}
                                style={{ marginTop: '4px', opacity: 0.6 }}
                            >
                                {t('verifyEmailSkip') || 'Skip for now'}
                            </button>
                        </>
                    )}
                </div>
                <div className="login-footer">
                    <p>📞 {t('helpline')}</p>
                </div>
            </div>
        </div>
    );
}

function AppContent() {
    const { isLoggedIn, authReady, needsEmailVerification, farmerProfile } = useFarmer();
    const { setLanguage } = useLanguage();
    const navigate = useNavigate();
    const prevLoggedIn = useRef(isLoggedIn);

    // Enforce language lifecycle:
    // 1) Logged out/login page starts in English.
    // 2) Logged in users get their saved profile language.
    useEffect(() => {
        if (!isLoggedIn) {
            setLanguage('en-IN', { persist: false });
            return;
        }

        const storedLanguage = localStorage.getItem('app_language');
        const profileLanguage = farmerProfile?.language;
        const effectiveLanguage = profileLanguage || storedLanguage || 'en-IN';
        // Keep language stable across refresh/tab switches even before profile fully hydrates.
        setLanguage(effectiveLanguage, { persist: !!(profileLanguage || storedLanguage) });
    }, [isLoggedIn, farmerProfile?.language, setLanguage]);

    // Navigate to home when user logs in (prevents landing on stale route like /weather)
    useEffect(() => {
        if (isLoggedIn && !prevLoggedIn.current) {
            navigate('/', { replace: true });
        }
        prevLoggedIn.current = isLoggedIn;
    }, [isLoggedIn, navigate]);

    // Prefetch ALL lazy-loaded chunks during idle time
    // → navigation becomes instant because JS is already cached
    useEffect(() => {
        if (!isLoggedIn) return;
        const prefetch = () => {
            import('./pages/WeatherPage');
            import('./pages/SchemesPage');
            import('./pages/CropDoctorPage');
            import('./pages/ProfilePage');
            import('./pages/PricePage');
            import('./pages/CropRecommendPage');
            import('./pages/FarmCalendarPage');
            import('./pages/SoilAnalysisPage');
        };
        // Use requestIdleCallback (fires during browser idle) with 3s hard deadline
        if ('requestIdleCallback' in window) {
            const id = requestIdleCallback(prefetch, { timeout: 3000 });
            return () => cancelIdleCallback(id);
        } else {
            const id = setTimeout(prefetch, 2000);
            return () => clearTimeout(id);
        }
    }, [isLoggedIn]);

    // Wait for Cognito session check before rendering anything
    if (!authReady) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)' }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '12px', animation: 'pulse 1.5s ease-in-out infinite' }}>🌾</div>
                    <div style={{ color: '#15803d', fontSize: '14px', fontWeight: 500 }}>Loading...</div>
                </div>
            </div>
        );
    }

    if (!isLoggedIn) {
        return <LoginPage />;
    }

    if (needsEmailVerification) {
        return <EmailVerifyScreen />;
    }

    return (
        <>
            <ScrollToTop />
            <Sidebar />
            <div className="app-body">
                <main className="main-content">
                    <Routes>
                        <Route path="/" element={<DashboardPage />} />
                        <Route path="/chat" element={<ChatPage />} />
                        <Route path="/weather" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><WeatherPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/schemes" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><SchemesPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/crop-doctor" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><CropDoctorPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/prices" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><PricePage /></Suspense></PageErrorBoundary>} />
                        <Route path="/crop-recommend" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><CropRecommendPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/farm-calendar" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><FarmCalendarPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/soil-analysis" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><SoilAnalysisPage /></Suspense></PageErrorBoundary>} />
                        <Route path="/profile" element={<PageErrorBoundary><Suspense fallback={<PageLoader />}><ProfilePage /></Suspense></PageErrorBoundary>} />
                        <Route path="*" element={<NotFoundPage />} />
                    </Routes>
                </main>
            </div>
            <MicFab />
        </>
    );
}

function App() {
    return (
        <BrowserRouter>
            <LanguageProvider>
                <FarmerProvider>
                    <AppContent />
                </FarmerProvider>
            </LanguageProvider>
        </BrowserRouter>
    );
}

export default App;
