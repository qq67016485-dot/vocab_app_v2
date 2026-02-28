import React from 'react';

export default function ProgressBar({
  current,
  total,
  labelRight = false,
  height = 10,
}) {
  const c = Math.max(0, Math.min(current ?? 0, total ?? 0));
  const pct = total > 0 ? Math.min((c / total) * 100, 100) : 0;

  const track = {
    height,
    width: '100%',
    flex: 1,
    maxWidth: 560,
    backgroundColor: 'var(--border)',
    borderRadius: 999,
    position: 'relative',
    overflow: 'hidden',
  };
  const fill = {
    height: '100%',
    width: `${pct}%`,
    backgroundColor: 'var(--primary)',
    borderRadius: 'inherit',
    transition: 'width 180ms var(--ease-std)',
  };

  if (labelRight) {
    return (
      <div
        className="session-progress-inline"
        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}
      >
        <div className="session-progress" style={track}>
          <div style={fill} />
        </div>
        <span className="session-progress-count" style={{ fontWeight: 700, color: 'var(--muted)' }}>
          {c} / {total}
        </span>
      </div>
    );
  }

  return (
    <div className="session-progress" style={track}>
      <div style={fill} />
      <div
        style={{
          position: 'absolute', inset: 0, display: 'flex',
          justifyContent: 'center', alignItems: 'center',
          fontWeight: 700, fontSize: '0.8rem', color: '#555', pointerEvents: 'none',
        }}
      >
        {c} / {total}
      </div>
    </div>
  );
}
