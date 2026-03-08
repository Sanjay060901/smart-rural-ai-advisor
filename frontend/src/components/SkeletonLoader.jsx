// src/components/SkeletonLoader.jsx

function SkeletonPulse({ width = '100%', height = '20px', radius = '8px', style = {} }) {
    return (
        <div
            className="skeleton-pulse"
            style={{ width, height, borderRadius: radius, ...style }}
        />
    );
}

export function WeatherSkeleton() {
    return (
        <div className="skeleton-container">
            {/* Search bar skeleton */}
            <SkeletonPulse height="52px" radius="16px" style={{ marginBottom: '24px' }} />

            {/* Stat cards */}
            <div className="stat-grid">
                {[1, 2, 3, 4].map(i => (
                    <div key={i} className="stat-card" style={{ padding: '20px' }}>
                        <SkeletonPulse width="48px" height="48px" radius="50%" style={{ margin: '0 auto 12px' }} />
                        <SkeletonPulse width="60%" height="28px" style={{ margin: '0 auto 8px' }} />
                        <SkeletonPulse width="40%" height="14px" style={{ margin: '0 auto' }} />
                    </div>
                ))}
            </div>

            {/* Advisory card */}
            <div className="card" style={{ marginTop: '18px' }}>
                <SkeletonPulse width="40%" height="22px" style={{ marginBottom: '14px' }} />
                <SkeletonPulse width="100%" height="14px" style={{ marginBottom: '8px' }} />
                <SkeletonPulse width="90%" height="14px" style={{ marginBottom: '8px' }} />
                <SkeletonPulse width="75%" height="14px" />
            </div>

            {/* Forecast */}
            <div style={{ marginTop: '24px' }}>
                <SkeletonPulse width="200px" height="22px" style={{ marginBottom: '14px' }} />
                <div className="forecast-grid">
                    {[1, 2, 3, 4, 5].map(i => (
                        <div key={i} className="forecast-card" style={{ padding: '16px' }}>
                            <SkeletonPulse width="60%" height="16px" style={{ margin: '0 auto 10px' }} />
                            <SkeletonPulse width="80%" height="14px" style={{ margin: '0 auto 6px' }} />
                            <SkeletonPulse width="70%" height="14px" style={{ margin: '0 auto' }} />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

export function SchemesSkeleton() {
    return (
        <div className="skeleton-container">
            {/* Search skeleton */}
            <SkeletonPulse height="52px" radius="16px" style={{ marginBottom: '20px' }} />

            {/* Scheme cards */}
            {[1, 2, 3, 4].map(i => (
                <div key={i} className="scheme-card" style={{ animationDelay: `${i * 0.1}s` }}>
                    <SkeletonPulse width="50%" height="22px" style={{ marginBottom: '6px' }} />
                    <SkeletonPulse width="70%" height="14px" style={{ marginBottom: '16px' }} />
                    <SkeletonPulse width="100%" height="14px" style={{ marginBottom: '8px' }} />
                    <SkeletonPulse width="90%" height="14px" style={{ marginBottom: '8px' }} />
                    <SkeletonPulse width="85%" height="14px" style={{ marginBottom: '8px' }} />
                    <SkeletonPulse width="50%" height="14px" />
                </div>
            ))}
        </div>
    );
}

export function ChatSkeleton() {
    return (
        <div className="skeleton-container" style={{ padding: '20px 0' }}>
            {[1, 2, 3].map(i => (
                <div key={i} className="skeleton-chat-row" style={{
                    display: 'flex',
                    gap: '12px',
                    marginBottom: '20px',
                    justifyContent: i % 2 === 0 ? 'flex-end' : 'flex-start',
                    flexDirection: i % 2 === 0 ? 'row-reverse' : 'row'
                }}>
                    <SkeletonPulse width="36px" height="36px" radius="50%" />
                    <div style={{ flex: `0 1 ${i % 2 === 0 ? '40%' : '65%'}` }}>
                        <SkeletonPulse height="56px" radius="16px" />
                    </div>
                </div>
            ))}
        </div>
    );
}

export default SkeletonPulse;
