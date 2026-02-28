import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import TextToSpeechButton from '../../components/TextToSpeechButton.jsx';
import { SKILL_TAG_DISPLAY_NAMES_STUDENT } from '../../constants/skillTags.js';
import { useTranslationVisibility } from '../../hooks/useTranslationVisibility.js';

export default function LearningPatternsView() {
  const { user } = useUser();
  const navigate = useNavigate();
  const { studentId } = useParams();
  const [reportData, setReportData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const { visibleTranslationTerm, handleShowTranslation } = useTranslationVisibility();
  const skillTagDisplayNames = SKILL_TAG_DISPLAY_NAMES_STUDENT;

  const chipClassFor = (tag) => {
    switch (tag) {
      case 'definition_recall': return 'purple';
      case 'word_forms': return 'orange';
      case 'synonym_antonym': return 'magenta';
      default: return 'blue';
    }
  };

  const handleBack = () => {
    if (studentId) {
      navigate(`/teacher/students/${studentId}/progress`);
    } else {
      navigate('/student/dashboard');
    }
  };

  useEffect(() => {
    const fetchLearningPatterns = async () => {
      setIsLoading(true);
      setError('');

      let url = '/student/learning-patterns/';
      if ((user.role === 'TEACHER' || user.role === 'ADMIN') && studentId) {
        url = `/teacher/students/${studentId}/learning-patterns/`;
      }

      try {
        const response = await apiClient.get(url);
        setReportData(response.data);
      } catch (err) {
        console.error('Error fetching learning patterns:', err);
        setError('Could not load the learning patterns report. Please try again.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchLearningPatterns();
  }, [user.role, studentId]);

  if (isLoading) return <p>Analyzing your patterns...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (!reportData || reportData.total_analyzed === 0) {
    return (
      <div className="lp-container">
        <div className="lp-header">
          <h2>My Learning Patterns</h2>
          <button className="back-top" onClick={handleBack}>Back</button>
        </div>
        <p className="lp-subtitle">Not enough data to generate a report yet. Keep practicing!</p>
      </div>
    );
  }

  const pageTitle =
    (user.role === 'TEACHER' || user.role === 'ADMIN')
      ? `Learning Patterns for ${reportData.student_username}`
      : 'My Learning Patterns';

  return (
    <div className="lp-container">
      <div className="lp-header">
        <h2>{pageTitle}</h2>
        <button className="back-top" onClick={handleBack}>Back</button>
      </div>
      <p className="lp-subtitle">
        This report analyzes your last {reportData.total_analyzed} incorrect answers.
      </p>

      <div className="lp-grid">
        <section className="lp-card breakdown">
          <h3>Error Breakdown</h3>
          {reportData.patterns?.length ? (
            reportData.patterns.map((pattern) => (
              <div key={pattern.name} className="bd-row">
                <div className="bd-top">
                  <strong className="bd-name">{pattern.name}</strong>
                  <span className="bd-percent">{pattern.percentage}%</span>
                </div>
                <div className="bd-bar">
                  <div className="bd-fill" style={{ width: `${pattern.percentage}%` }} />
                </div>
                <p className="bd-desc"><em>{pattern.description}</em></p>
              </div>
            ))
          ) : (
            <p>No incorrect answers found to analyze.</p>
          )}
        </section>

        <section className="lp-card focus">
          <h3>Words to Focus On</h3>
          {reportData.challenging_words?.length ? (
            <ul className="focus-list">
              {reportData.challenging_words.map((word) => (
                <li key={word.term} className="focus-item">
                  <div className="focus-head">
                    <div className="word-and-tts">
                      <TextToSpeechButton textToSpeak={word.term} />
                      <strong className="focus-word">{word.term}</strong>
                      <span className="mistake-count">({word.mistake_count} mistakes)</span>
                      {word.skill_tags?.[0] && (
                        <span className={`pattern-chip ${chipClassFor(word.skill_tags[0])}`}>
                          {skillTagDisplayNames[word.skill_tags[0]] || word.skill_tags[0]}
                        </span>
                      )}
                    </div>
                    <div className="focus-actions">
                      {visibleTranslationTerm === word.term ? (
                        <span className="translation-display">{word.translation}</span>
                      ) : (
                        word.translation && (
                          <button
                            className="show-zh-btn"
                            onClick={() => handleShowTranslation(word.term)}
                            type="button"
                          >
                            Show Translation
                          </button>
                        )
                      )}
                    </div>
                  </div>
                  <p className="focus-def">{word.definition}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p>No specific words are standing out as challenging right now. Keep up the great work!</p>
          )}
        </section>
      </div>

      <button className="back-home" onClick={handleBack}>
        Back to Home
      </button>
    </div>
  );
}
