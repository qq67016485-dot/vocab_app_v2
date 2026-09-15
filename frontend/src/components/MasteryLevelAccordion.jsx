import React, { useState } from 'react';
import apiClient from '../api/axiosConfig.js';
import TextToSpeechButton from './TextToSpeechButton.jsx';

/**
 * Displays the "My Learning Journey" section.
 * Renders mastery levels as an accordion with word details.
 */
export default function MasteryLevelAccordion({ levels }) {
  const [expandedLevelId, setExpandedLevelId] = useState(null);
  const [wordsCache, setWordsCache] = useState({});
  // Loading tracked per level: two fetches can be in flight at once, and one
  // finishing must not clear the other's indicator (which briefly flashed the
  // "No words at this level yet." empty state).
  const [loadingLevelIds, setLoadingLevelIds] = useState(() => new Set());

  const handleToggle = async (levelId) => {
    if (expandedLevelId === levelId) {
      setExpandedLevelId(null);
      return;
    }

    setExpandedLevelId(levelId);

    if (!wordsCache[levelId]) {
      setLoadingLevelIds((prev) => new Set(prev).add(levelId));
      try {
        const response = await apiClient.get(`/student/words-by-level/${levelId}/`);
        setWordsCache((prev) => ({ ...prev, [levelId]: response.data }));
      } catch (error) {
        console.error(`Error fetching words for level ${levelId}:`, error);
      } finally {
        setLoadingLevelIds((prev) => {
          const next = new Set(prev);
          next.delete(levelId);
          return next;
        });
      }
    }
  };

  const renderDelta = (val, label) => {
    const value = val || 0;

    if (value === 0) {
      return <span className="stat-neutral">+0 {label}</span>;
    }

    const isPositive = value > 0;
    return (
      <span className={`stat-change ${isPositive ? 'positive' : 'negative'}`}>
        {isPositive ? '+' : ''}{value} {label}
      </span>
    );
  };

  return (
    <section className="journey-section">
      <h3>My Learning Journey</h3>

      <div className="accordion-container">
        {levels.map((level) => (
          <div key={level.level_id} className="accordion-item">
            <button
              onClick={() => handleToggle(level.level_id)}
              className="accordion-header"
              aria-expanded={expandedLevelId === level.level_id}
              type="button"
            >
              <div className="accordion-title">
                <strong>{level.level_name}</strong>
                <span className="count-badge">({level.word_count} words)</span>
              </div>

              <div className="accordion-stats">
                {renderDelta(level.delta_today, 'Today')}
                {renderDelta(level.delta_week, 'Week')}
              </div>

              <div className="accordion-icon" aria-hidden="true">
                {expandedLevelId === level.level_id ? '\u2212' : '+'}
              </div>
            </button>

            {expandedLevelId === level.level_id && (
              <div className="accordion-content" role="region">
                {loadingLevelIds.has(level.level_id) && <p>Loading words...</p>}

                {!loadingLevelIds.has(level.level_id) && wordsCache[level.level_id]?.length === 0 && (
                  <p className="empty-text">No words at this level yet.</p>
                )}

                {!loadingLevelIds.has(level.level_id) && wordsCache[level.level_id]?.length > 0 && (
                  <ul className="word-list-plain">
                    {wordsCache[level.level_id].map((word) => (
                      <li key={word.id} className="accordion-word-item">
                        <div className="word-and-tts">
                          <TextToSpeechButton textToSpeak={word.text} />
                          <strong>{word.text}</strong>
                          {word.part_of_speech && <small>({word.part_of_speech})</small>}
                        </div>
                        <p className="word-definition">{word.definition}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
