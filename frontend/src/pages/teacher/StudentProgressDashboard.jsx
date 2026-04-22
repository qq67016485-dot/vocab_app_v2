import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { SKILL_TAG_DISPLAY_NAMES_TEACHER } from '../../constants/skillTags.js';

export default function StudentProgressDashboard() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const [progressData, setProgressData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedAnswerId, setExpandedAnswerId] = useState(null);

  useEffect(() => {
    const fetchProgressData = async () => {
      if (!studentId) return;
      setIsLoading(true); setError('');
      try {
        const response = await apiClient.get(`/teacher/students/${studentId}/progress/`);
        setProgressData(response.data);
      } catch (err) {
        console.error("Error fetching progress data:", err);
        setError('Could not load student progress. Please try again.');
      } finally { setIsLoading(false); }
    };
    fetchProgressData();
  }, [studentId]);

  const toggleExpandAnswer = (id) => { setExpandedAnswerId(expandedAnswerId === id ? null : id); };
  const formatCorrectAnswer = (answer) => Array.isArray(answer) ? answer.join(', ') : answer;

  if (isLoading) return <p>Loading dashboard...</p>;
  if (error) return <p style={{ color: 'var(--t-danger)' }}>{error}</p>;
  if (!progressData) return <p>No data available.</p>;

  const { consecutive_mistakes, practice_stats, mastery_counts, frequent_mistakes, recent_answers } = progressData;

  return (
    <div>
      <div className="t-page-header">
        <h1 className="t-page-title">Progress: {progressData.student_username}</h1>
        <button className="t-btn t-btn--secondary" onClick={() => navigate(`/teacher/students/${studentId}/patterns`)}>View Learning Patterns</button>
      </div>

      {consecutive_mistakes && consecutive_mistakes.length > 0 && (
        <div className="t-card" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: '0 0 6px', fontSize: '0.95rem', fontWeight: 600 }}>Words Needing Attention</h3>
          <p className="t-hint" style={{ margin: '0 0 10px' }}>2+ consecutive mistakes on these words.</p>
          <ul style={{ padding: 0, listStyle: 'none' }}>
            {consecutive_mistakes.map(word => (
              <li key={word.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--t-border-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong>{word.term}</strong>
                  {word.skill_tags && word.skill_tags.map(tag => (
                    <span key={tag} className="t-skill-tag t-skill-tag--red">{SKILL_TAG_DISPLAY_NAMES_TEACHER[tag] || tag}</span>
                  ))}
                </div>
                <p className="t-hint" style={{ margin: '2px 0 0', fontStyle: 'italic' }}>{word.definition}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="t-card" style={{ marginBottom: 12 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Practice Statistics</h3>
        {practice_stats ? (
          <table className="t-stats-table">
            <thead><tr><th>Period</th><th>Practiced</th><th>Correct</th><th>Incorrect</th></tr></thead>
            <tbody>
              <tr><td>Today</td><td>{practice_stats.today.total_answered}</td><td>{practice_stats.today.total_correct}</td><td>{practice_stats.today.total_incorrect}</td></tr>
              <tr><td>Past 3 Days</td><td>{practice_stats.past_3_days.total_answered}</td><td>{practice_stats.past_3_days.total_correct}</td><td>{practice_stats.past_3_days.total_incorrect}</td></tr>
              <tr><td>Past 7 Days</td><td>{practice_stats.past_7_days.total_answered}</td><td>{practice_stats.past_7_days.total_correct}</td><td>{practice_stats.past_7_days.total_incorrect}</td></tr>
            </tbody>
          </table>
        ) : <p className="t-hint">No practice statistics available.</p>}
      </div>

      <div className="t-card" style={{ marginBottom: 12 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Mastery Levels</h3>
        {mastery_counts && mastery_counts.length > 0 ? (
          <ul style={{ padding: 0, listStyle: 'none' }}>
            {mastery_counts.map(level => (<li key={level.level_name} style={{ padding: '4px 0', background: 'none', border: 'none' }}>{level.level_name}: <strong>{level.word_count}</strong> words</li>))}
          </ul>
        ) : <p className="t-hint">No word mastery data available.</p>}
      </div>
/* APPEND_SPD */

      <div className="t-card" style={{ marginBottom: 12 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Most Frequent Mistakes (Last 50 incorrect)</h3>
        {frequent_mistakes && frequent_mistakes.length > 0 ? (
          <ul style={{ padding: 0, listStyle: 'none' }}>
            {frequent_mistakes.map(word => (
              <li key={word.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--t-border-light)' }}>
                <strong>{word.term}</strong> <span style={{ color: 'var(--t-danger)', marginLeft: 6, fontSize: '0.85rem' }}>({word.mistake_count} mistakes)</span>
                <p className="t-hint" style={{ margin: '2px 0 0', fontStyle: 'italic' }}>{word.definition}</p>
              </li>
            ))}
          </ul>
        ) : <p className="t-hint">No recurring mistakes found in recent practice.</p>}
      </div>

      <div className="t-card">
        <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Recent Activity (Last 50 Answers)</h3>
        {recent_answers && recent_answers.length > 0 ? (
          <ul style={{ maxHeight: 400, overflowY: 'auto', padding: 0, listStyle: 'none' }}>
            {recent_answers.map((ans, index) => (
              <li key={ans.id || index} onClick={() => !ans.is_correct && toggleExpandAnswer(ans.id)}
                style={{ display: 'flex', flexDirection: 'column', padding: '8px 0', borderBottom: '1px solid var(--t-border-light)', cursor: !ans.is_correct ? 'pointer' : 'default' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                  <div style={{ color: ans.is_correct ? 'var(--t-success)' : 'var(--t-danger)' }}>
                    <strong>{ans.term}</strong> - {ans.is_correct ? 'Correct' : 'Incorrect'}
                    {!ans.is_correct && <span className="t-hint" style={{ marginLeft: 6 }}>{expandedAnswerId === ans.id ? '\u25BC' : '\u25B6'}</span>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className="t-skill-tag">{SKILL_TAG_DISPLAY_NAMES_TEACHER[ans.skill_tag] || ans.skill_tag}</span>
                    <span className="t-hint" style={{ minWidth: 110, textAlign: 'right' }}>{ans.answered_at}</span>
                  </div>
                </div>
                {expandedAnswerId === ans.id && !ans.is_correct && (
                  <div style={{ marginTop: 8, background: '#f8fafc', padding: 12, borderRadius: 'var(--t-radius-sm)', border: '1px solid var(--t-border)', fontSize: '0.9rem' }}>
                    <div style={{ marginBottom: 6 }}>
                      <span style={{ fontWeight: 600, color: 'var(--t-text-secondary)', fontSize: '0.78rem', textTransform: 'uppercase' }}>Question:</span>
                      <div style={{ marginTop: 2 }}>{ans.question_text}</div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      <div style={{ background: '#fef2f2', padding: 8, borderRadius: 4, border: '1px solid #fee2e2' }}>
                        <span style={{ fontWeight: 600, color: 'var(--t-danger)', fontSize: '0.78rem' }}>Student said:</span>
                        <div style={{ color: '#991b1b', marginTop: 2 }}>{ans.user_answer || '(No Answer)'}</div>
                      </div>
                      <div style={{ background: '#f0fdf4', padding: 8, borderRadius: 4, border: '1px solid #dcfce7' }}>
                        <span style={{ fontWeight: 600, color: 'var(--t-success)', fontSize: '0.78rem' }}>Correct answer:</span>
                        <div style={{ color: '#166534', marginTop: 2 }}>{formatCorrectAnswer(ans.correct_answers)}</div>
                      </div>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : <p className="t-hint">No practice history found.</p>}
      </div>
    </div>
  );
}
