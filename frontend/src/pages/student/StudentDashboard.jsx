import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import MasteryLevelAccordion from '../../components/MasteryLevelAccordion.jsx';

export default function StudentDashboard() {
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState(null);
  const [assignedSets, setAssignedSets] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
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

  const streakTitle =
    dashboardData.practice_streak > 0
      ? 'Current Practice Streak'
      : 'Start a Practice Streak!';

  return (
    <div>
      {/* Info modal for Streak Freezes */}
      {showFreezeInfo && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          onClick={() => setShowFreezeInfo(false)}
        >
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            role="document"
          >
            <h2>How Streak Freezes Work</h2>
            <p>A Streak Freeze is your safety net for busy days!</p>
            <ul>
              <li>
                <strong>Automatic Use:</strong> If you miss a day of practice,
                one freeze is used automatically to save your streak.
              </li>
              <li>
                <strong>Earning More:</strong> You earn one freeze for every{' '}
                <strong>3 consecutive days</strong> of practice.
              </li>
              <li>
                <strong>Maximum:</strong> You can hold up to 5 freezes at a
                time.
              </li>
            </ul>
            <button onClick={() => setShowFreezeInfo(false)}>Got it!</button>
          </div>
        </div>
      )}

      {/* Callout: See Your Learning Patterns */}
      <div className="patterns-callout">
        <div className="left">
          <div className="callout-icon" aria-hidden="true">&#10003;</div>
          <div>
            <div className="callout-title">See Your Learning Patterns</div>
            <div className="callout-subtitle">
              Spot mistakes faster and get smart tips to improve.
            </div>
          </div>
        </div>
        <button
          className="callout-cta"
          onClick={() => navigate('/student/learning-patterns')}
          type="button"
        >
          View My Learning Patterns
        </button>
      </div>

      {/* Today's Mission */}
      <section className="mission-card" aria-labelledby="mission-title">
        <h3 id="mission-title">Today's Mission</h3>
        <p style={{ fontSize: '1.05rem', margin: '10px 0 18px' }}>
          You have <strong>{dashboardData.words_due_today}</strong> words due
          for review today.
        </p>
        <button
          className="primary"
          onClick={() => navigate('/student/practice')}
          type="button"
        >
          Start Practice Session
        </button>
      </section>

      {/* Stats Row */}
      <div className="stats-row" role="list">
        <div className="stat-card" role="listitem">
          <div className="stat-value">{dashboardData.total_words}</div>
          <div className="stat-label">Words in Collection</div>
        </div>
        <div className="stat-card" role="listitem">
          <div className="stat-value">
            {dashboardData.practice_streak} Days
          </div>
          <div className="stat-label">{streakTitle}</div>
        </div>
        <div className="stat-card" role="listitem">
          <div className="stat-value" title="Earn a freeze for every 3-day streak!">
            {dashboardData.streak_freezes_available}
          </div>
          <div className="stat-label">
            Streak Freezes{' '}
            <button
              type="button"
              className="info-icon"
              onClick={() => setShowFreezeInfo(true)}
              title="What are Streak Freezes?"
              aria-label="What are Streak Freezes?"
            >
              ?
            </button>
          </div>
        </div>
      </div>

      {/* Learning Journey */}
      {dashboardData.mastery_breakdown && dashboardData.mastery_breakdown.length > 0 && (
        <MasteryLevelAccordion levels={dashboardData.mastery_breakdown} />
      )}
      {(!dashboardData.mastery_breakdown || dashboardData.mastery_breakdown.length === 0) && (
        <section className="journey-section">
          <h3>My Learning Journey</h3>
          <p>Start practicing to see your progress!</p>
        </section>
      )}

      {/* My Word Sets */}
      {assignedSets.length > 0 && (
        <section className="assigned-sets-section">
          <h3>My Word Sets</h3>
          <div className="assigned-sets-grid">
            {assignedSets.map((ws) => {
              const nextPack = ws.packs.find(p => !p.is_completed);
              return (
                <div key={ws.set_id} className="assigned-set-card">
                  <div className="assigned-set-title">{ws.title}</div>
                  <div className="assigned-set-meta">
                    {ws.curriculum && <span className="set-pill">{ws.curriculum}</span>}
                    {ws.level && <span className="set-pill">{ws.level}</span>}
                    <span className="set-pill">{ws.total_words} words</span>
                  </div>
                  {ws.packs.length > 0 ? (
                    <ul className="pack-list">
                      {ws.packs.map((pack) => (
                        <li key={pack.pack_id} className="pack-item">
                          <span className="pack-item-label">
                            {pack.label}
                            <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                              ({pack.word_count} words)
                            </span>
                          </span>
                          {pack.is_completed ? (
                            <span className="pack-completed-badge">Done</span>
                          ) : pack.pack_id === nextPack?.pack_id ? (
                            <button
                              className="pack-learn-btn"
                              onClick={() => navigate(`/student/instructional/${pack.pack_id}`)}
                              type="button"
                            >
                              Learn
                            </button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>No learning packs yet.</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
