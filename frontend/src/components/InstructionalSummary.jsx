import React from 'react';

export default function InstructionalSummary({ results, words, onBack }) {
  return (
    <div className="instructional-summary">
      <h2>Pack Complete!</h2>

      {results.total > 0 && (
        <div className="summary-score">
          {results.correct} / {results.total} correct
        </div>
      )}

      <p>You learned {words.length} new word{words.length !== 1 ? 's' : ''}:</p>

      <div className="summary-words">
        {words.map((word) => (
          <span key={word} className="summary-word-chip">{word}</span>
        ))}
      </div>

      <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>
        These words are now ready for SRS practice.
      </p>

      <button className="summary-back-btn" onClick={onBack} type="button">
        Back to My Word Sets
      </button>
    </div>
  );
}
