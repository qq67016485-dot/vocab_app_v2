import React from 'react';

const TIER_SYMBOLS = {
  Bronze: '★',
  Silver: '★',
  Gold: '★',
  Platinum: '◆',
  Diamond: '◆',
};

export default function StudentNavbar({
  username,
  level,
  tierName,
  xpCurrent,
  xpNeeded,
  xpPercent,
  onSettingsClick,
}) {
  const tierKey = tierName || 'Bronze';
  const tierSymbol = TIER_SYMBOLS[tierKey] || '★';

  return (
    <div className="student-navbar">
      <div className="student-navbar-left">
        <div className="student-avatar" aria-hidden="true">
          {(username || '?')[0].toUpperCase()}
        </div>
        <div className="student-navbar-info">
          <div className="student-navbar-greeting">Hi, {username}</div>
          <div className="student-navbar-tier">
            <span className={`tier-badge-icon tier-${tierKey.toLowerCase()}`}>{tierSymbol}</span>
            <span className="tier-label">Level {level} · {tierName}</span>
          </div>
          <div className="student-xp-bar-wrap">
            <div className="student-xp-bar-bg">
              <div
                className="student-xp-bar-fill"
                style={{ width: `${xpPercent}%` }}
              />
            </div>
            <div className="student-xp-bar-label">
              {xpCurrent} / {xpNeeded} XP
            </div>
          </div>
        </div>
      </div>
      <button
        className="student-settings-btn"
        onClick={onSettingsClick}
        type="button"
        aria-label="Settings"
      >
        ⚙
      </button>
    </div>
  );
}
