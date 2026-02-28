import React from 'react';
import { useUser } from '../context/UserContext';

function LevelProgressBar() {
  const { user } = useUser();

  if (!user || user.role !== 'STUDENT' || !user.tier_info) {
    return null;
  }

  const { xp_in_current_level, xp_for_next_level, tier_info, level } = user;

  const progressPercentage = xp_for_next_level > 0
    ? Math.min((xp_in_current_level / xp_for_next_level) * 100, 100)
    : 0;

  return (
    <div className="level-progress-container">
      <div className="level-badge" style={{ backgroundColor: tier_info.color || '#bdc3c7' }}>
        Lvl {level}
      </div>
      <div className="progress-bar-wrapper">
        <div className="progress-bar-fill" style={{ width: `${progressPercentage}%` }}></div>
        <div className="progress-bar-text">{`${xp_in_current_level} / ${xp_for_next_level} XP`}</div>
      </div>
    </div>
  );
}

export default LevelProgressBar;
