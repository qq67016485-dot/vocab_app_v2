import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import { useTheme } from '../../context/ThemeContext.jsx';
import MasteryLevelAccordion from '../../components/MasteryLevelAccordion.jsx';
import StudentNavbar from '../../components/StudentNavbar.jsx';

export default function StudentDashboard() {
  const navigate = useNavigate();
  const { user, logoutUser } = useUser();
  const { theme, setTheme, THEMES } = useTheme();
  const [dashboardData, setDashboardData] = useState(null);
  const [assignedSets, setAssignedSets] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showFreezeInfo, setShowFreezeInfo] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const [dashRes, setsRes] = await Promise.all([
          apiClient.get('/student/dashboard/'),
          apiClient.get('/student/assigned-sets/'),
        ]);
        setDashboardData(dashRes.data);
        setAssignedSets(setsRes.data);
      } catch (error) {
        console.error('Error fetching student dashboard data:', error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  if (isLoading) return <p>Loading your dashboard...</p>;
  if (!dashboardData) return <p>Could not load your dashboard data.</p>;

  const handleLogout = async () => {
    await logoutUser();
    navigate('/login');
  };

  // Determine which packs to show: max 2 incomplete packs across all sets
  const incompletePacks = [];
  for (const ws of assignedSets) {
    for (const pack of ws.packs) {
      if (!pack.is_completed && incompletePacks.length < 2) {
        incompletePacks.push({
          ...pack,
          set_title: ws.title,
          curriculum: ws.curriculum,
        });
      }
    }
  }

  // Show "Learn New Words" only when words due < daily question limit
  const showLearnSection =
    incompletePacks.length > 0 &&
    dashboardData.words_due_today < dashboardData.daily_question_limit;

  // All done: no words due and no incomplete packs
  const allDone = dashboardData.words_due_today === 0 && incompletePacks.length === 0;

  const tierName = user?.tier_info?.name || 'Bronze';
  const level = user?.level || 1;
  const xpCurrent = user?.xp_in_current_level || 0;
  const xpNeeded = user?.xp_for_next_level || 200;
  const xpPercent = xpNeeded > 0 ? Math.min((xpCurrent / xpNeeded) * 100, 100) : 0;

  return (
    <div className="student-dashboard-v2">
      {/* Hero Navbar */}
      <StudentNavbar
        username={user?.username}
        level={level}
        tierName={tierName}
        xpCurrent={xpCurrent}
        xpNeeded={xpNeeded}
        xpPercent={xpPercent}
        onSettingsClick={() => setShowSettings(true)}
        onLogout={handleLogout}
      />

      {/* Two-column layout */}
      <div className="dashboard-columns">
        {/* Left column: actions */}
        <div className="dashboard-col-main">
          {allDone ? (
            /* All Done state */
            <div className="all-done-hero">
              <div className="all-done-emoji">🌟</div>
              <h2 className="all-done-title">You're All Caught Up!</h2>
              <p className="all-done-subtitle">
                No words to review and no new packs to learn.
                <br />Enjoy your break — you've earned it!
              </p>
            </div>
          ) : (
            <>
              {/* Review Due Words */}
              {dashboardData.words_due_today > 0 && (
                <section className="review-card">
                  <h3 className="review-card-title">Review Due Words</h3>
                  <p className="review-card-desc">
                    These words are ready for their next review
                  </p>
                  <div className="review-card-count-row">
                    <span className="review-count">{dashboardData.words_due_today}</span>
                    <span className="review-count-label">words due today</span>
                  </div>
                  <button
                    className="btn-primary review-start-btn"
                    onClick={() => navigate('/student/practice')}
                    type="button"
                  >
                    Start Practice
                  </button>
                </section>
              )}

              {/* Learn New Words */}
              {showLearnSection && (
                <section className="learn-card">
                  <h3 className="learn-card-title">Learn New Words</h3>
                  <p className="learn-card-desc">
                    Complete a word pack to unlock new words for practice
                  </p>
                  {incompletePacks.map((pack) => (
                    <div key={pack.pack_id} className="pack-row">
                      <div>
                        <div className="pack-row-name">{pack.label}</div>
                        <div className="pack-row-meta">
                          {pack.curriculum || pack.set_title} · {pack.word_count} words
                        </div>
                      </div>
                      <button
                        className="btn-primary pack-learn-btn-lg"
                        onClick={() => navigate(`/student/instructional/${pack.pack_id}`)}
                        type="button"
                      >
                        Learn
                      </button>
                    </div>
                  ))}
                </section>
              )}

              {/* Review-only note when learn is hidden */}
              {!showLearnSection && incompletePacks.length > 0 && (
                <div className="learn-waiting-note">
                  <strong>New words are waiting!</strong> Finish your reviews first,
                  then new word packs will appear here.
                </div>
              )}
            </>
          )}
        </div>

        {/* Right column: journey */}
        <div className="dashboard-col-side">
          <h3 className="journey-heading">My Learning Journey</h3>

          {/* Stats row */}
          <div className="journey-stats-row">
            <div className="journey-stat">
              <div className="journey-stat-val">{dashboardData.total_words}</div>
              <div className="journey-stat-lbl">Total Words</div>
            </div>
            <div className="journey-stat">
              <div className="journey-stat-val">
                {dashboardData.practice_streak} <span className="stat-icon-flame" aria-label="streak">🔥</span>
              </div>
              <div className="journey-stat-lbl">Day Streak</div>
            </div>
            <div className="journey-stat journey-stat-freeze" onClick={() => setShowFreezeInfo(true)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setShowFreezeInfo(true)}>
              <div className="journey-stat-val">
                {dashboardData.streak_freezes_available} <span className="stat-icon-freeze" aria-label="freezes">❄️</span>
              </div>
              <div className="journey-stat-lbl">Freezes <span className="freeze-info-hint">ⓘ</span></div>
            </div>
          </div>

          {/* Mastery accordion (has its own heading internally) */}
          {dashboardData.mastery_breakdown && dashboardData.mastery_breakdown.length > 0 && (
            <MasteryLevelAccordion levels={dashboardData.mastery_breakdown} />
          )}
          {(!dashboardData.mastery_breakdown || dashboardData.mastery_breakdown.length === 0) && (
            <p className="journey-empty">Start practicing to see your progress!</p>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div
          className="settings-overlay"
          onClick={() => setShowSettings(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="settings-panel"
            onClick={(e) => e.stopPropagation()}
            role="document"
          >
            <div className="settings-header">
              <span className="settings-title">Settings</span>
              <button
                className="settings-close"
                onClick={() => setShowSettings(false)}
                type="button"
                aria-label="Close settings"
              >
                ✕
              </button>
            </div>

            <div className="settings-section-label">Theme Color</div>
            <p className="settings-section-desc">Pick your favorite color</p>
            <div className="theme-color-grid">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  className={`theme-swatch-btn${theme === t.id ? ' active' : ''}`}
                  data-theme-id={t.id}
                  onClick={() => setTheme(t.id)}
                  type="button"
                  aria-label={t.label}
                >
                  <span className="theme-swatch-label">{t.label}</span>
                </button>
              ))}
            </div>

            <button
              className="settings-logout"
              onClick={handleLogout}
              type="button"
            >
              Logout
            </button>
          </div>
        </div>
      )}
      {/* Freeze Info Modal */}
      {showFreezeInfo && (
        <div
          className="settings-overlay"
          onClick={() => setShowFreezeInfo(false)}
          role="dialog"
          aria-modal="true"
          aria-label="How Streak Freezes Work"
        >
          <div
            className="freeze-info-panel"
            onClick={(e) => e.stopPropagation()}
            role="document"
          >
            <h3 className="freeze-info-title">How Streak Freezes Work ❄️</h3>
            <p className="freeze-info-intro">A Streak Freeze is your safety net for busy days!</p>
            <ul className="freeze-info-list">
              <li><strong>Automatic Use:</strong> If you miss a day of practice, one freeze is used automatically to save your streak.</li>
              <li><strong>Earning More:</strong> You earn one freeze for every <strong>3 consecutive days</strong> of practice.</li>
              <li><strong>Maximum:</strong> You can hold up to <strong>5 freezes</strong> at a time.</li>
            </ul>
            <button
              className="btn-primary freeze-info-btn"
              onClick={() => setShowFreezeInfo(false)}
              type="button"
            >
              Got it!
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
