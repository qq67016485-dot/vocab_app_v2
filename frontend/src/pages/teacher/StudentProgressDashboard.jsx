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
      setIsLoading(true);
      setError('');
      try {
        const response = await apiClient.get(`/teacher/students/${studentId}/progress/`);
        setProgressData(response.data);
      } catch (err) {
        console.error("Error fetching progress data:", err);
        setError('Could not load student progress. Please try again.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchProgressData();
  }, [studentId]);

  const toggleExpandAnswer = (id) => {
    setExpandedAnswerId(expandedAnswerId === id ? null : id);
  };

  const formatCorrectAnswer = (answer) => {
    if (Array.isArray(answer)) return answer.join(', ');
    return answer;
  };

  if (isLoading) return <p>Loading dashboard...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (!progressData) return <p>No data available.</p>;

  const { consecutive_mistakes, practice_stats, mastery_counts, frequent_mistakes, recent_answers } = progressData;

  return (
    <div>
      <h2>Progress Dashboard for {progressData.student_username}</h2>

      <div style={{ margin: '20px 0', textAlign: 'center' }}>
        <button
          onClick={() => navigate(`/teacher/students/${studentId}/patterns`)}
          className="secondary-button"
        >
          View Learning Patterns Report
        </button>
      </div>

      {consecutive_mistakes && consecutive_mistakes.length > 0 && (
        <div className="practice-card" style={{ marginTop: '0px' }}>
          <h3>Words Needing Attention</h3>
          <p style={{ fontSize: '0.9rem', color: '#666', margin: '4px 0 10px' }}>
            The student made 2+ consecutive mistakes on these words.
          </p>
          <ul>
            {consecutive_mistakes.map(word => (
              <li key={word.id}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <strong>{word.term}</strong>
                  {word.skill_tags && word.skill_tags.map(tag => (
                    <span key={tag} className="skill-tag-pill red" style={{ fontSize: '0.75rem' }}>
                      {SKILL_TAG_DISPLAY_NAMES_TEACHER[tag] || tag}
                    </span>
                  ))}
                </div>
                <p style={{ margin: '4px 0 0', fontStyle: 'italic' }}>{word.definition}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="practice-card" style={{ marginTop: '20px' }}>
        <h3>Practice Statistics</h3>
        {practice_stats ? (
          <table className="stats-table">
            <thead>
              <tr><th>Period</th><th>Practiced</th><th>Correct</th><th>Incorrect</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Today</td>
                <td>{practice_stats.today.total_answered}</td>
                <td>{practice_stats.today.total_correct}</td>
                <td>{practice_stats.today.total_incorrect}</td>
              </tr>
              <tr>
                <td>Past 3 Days</td>
                <td>{practice_stats.past_3_days.total_answered}</td>
                <td>{practice_stats.past_3_days.total_correct}</td>
                <td>{practice_stats.past_3_days.total_incorrect}</td>
              </tr>
              <tr>
                <td>Past 7 Days</td>
                <td>{practice_stats.past_7_days.total_answered}</td>
                <td>{practice_stats.past_7_days.total_correct}</td>
                <td>{practice_stats.past_7_days.total_incorrect}</td>
              </tr>
            </tbody>
          </table>
        ) : <p>No practice statistics available.</p>}
      </div>

      <div className="practice-card" style={{ marginTop: '20px' }}>
        <h3>Mastery Levels</h3>
        {mastery_counts && mastery_counts.length > 0 ? (
          <ul>
            {mastery_counts.map(level => (
              <li key={level.level_name}>
                {level.level_name}: <strong>{level.word_count}</strong> words
              </li>
            ))}
          </ul>
        ) : <p>No word mastery data available.</p>}
      </div>

      <div className="practice-card" style={{ marginTop: '20px' }}>
        <h3>Most Frequent Mistakes (Last 50 incorrect)</h3>
        {frequent_mistakes && frequent_mistakes.length > 0 ? (
          <ul>
            {frequent_mistakes.map(word => (
              <li key={word.id}>
                <strong>{word.term}</strong>
                <span style={{ color: 'red', marginLeft: '8px' }}>({word.mistake_count} mistakes)</span>
                <p style={{ margin: '4px 0 0', fontStyle: 'italic' }}>{word.definition}</p>
              </li>
            ))}
          </ul>
        ) : <p>No recurring mistakes found in recent practice.</p>}
      </div>

      <div className="practice-card" style={{ marginTop: '20px' }}>
        <h3>Recent Activity (Last 50 Answers)</h3>
        {recent_answers && recent_answers.length > 0 ? (
          <ul style={{ maxHeight: '400px', overflowY: 'auto', padding: '0 5px' }}>
            {recent_answers.map((ans, index) => (
              <li
                key={ans.id || index}
                onClick={() => !ans.is_correct && toggleExpandAnswer(ans.id)}
                style={{
                  display: 'flex', flexDirection: 'column',
                  padding: '8px 4px', borderBottom: '1px solid #f0f0f0',
                  cursor: !ans.is_correct ? 'pointer' : 'default',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                  <div style={{ color: ans.is_correct ? 'green' : 'red' }}>
                    <strong>{ans.term}</strong> - {ans.is_correct ? 'Correct' : 'Incorrect'}
                    {!ans.is_correct && (
                      <span style={{ fontSize: '0.8em', color: '#999', marginLeft: '6px' }}>
                        {expandedAnswerId === ans.id ? '\u25BC' : '\u25B6'}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span className="skill-tag-pill" style={{
                      backgroundColor: '#f1f5f9', color: '#64748b',
                      borderColor: '#e2e8f0', fontSize: '0.75rem', fontWeight: '500',
                    }}>
                      {SKILL_TAG_DISPLAY_NAMES_TEACHER[ans.skill_tag] || ans.skill_tag}
                    </span>
                    <span style={{ color: '#94a3b8', fontSize: '0.8rem', minWidth: '110px', textAlign: 'right' }}>
                      {ans.answered_at}
                    </span>
                  </div>
                </div>

                {expandedAnswerId === ans.id && !ans.is_correct && (
                  <div style={{
                    marginTop: '8px', backgroundColor: '#f8fafc', padding: '12px',
                    borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '0.9rem',
                  }}>
                    <div style={{ marginBottom: '6px' }}>
                      <span style={{ fontWeight: 'bold', color: '#64748b', fontSize: '0.8rem', textTransform: 'uppercase' }}>Question:</span>
                      <div style={{ marginTop: '2px', color: '#334155' }}>{ans.question_text}</div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div style={{ backgroundColor: '#fef2f2', padding: '8px', borderRadius: '4px', border: '1px solid #fee2e2' }}>
                        <span style={{ fontWeight: 'bold', color: '#dc2626', fontSize: '0.8rem' }}>Student said:</span>
                        <div style={{ color: '#991b1b', marginTop: '2px' }}>{ans.user_answer || '(No Answer)'}</div>
                      </div>
                      <div style={{ backgroundColor: '#f0fdf4', padding: '8px', borderRadius: '4px', border: '1px solid #dcfce7' }}>
                        <span style={{ fontWeight: 'bold', color: '#16a34a', fontSize: '0.8rem' }}>Correct answer:</span>
                        <div style={{ color: '#166534', marginTop: '2px' }}>{formatCorrectAnswer(ans.correct_answers)}</div>
                      </div>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : <p>No practice history found.</p>}
      </div>
    </div>
  );
}
