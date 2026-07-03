import React from 'react';

/**
 * Sentence-scramble question: tap word tiles from the bank to build the
 * sentence, tap a placed tile to remove it. Options come pre-shuffled.
 */
export default function ScrambleQuestion({
  optionsArray,
  scrambledAttempt,
  setScrambledAttempt,
  correctDone,
  retryMode,
  handleSubmit,
  retryHintBlock,
  correctFeedbackBlock,
}) {
  const initialWords = optionsArray.map((text, index) => ({ id: index, text }));
  const availableWords = initialWords.filter(
    (w) => !scrambledAttempt.some((aw) => aw.id === w.id),
  );
  const handleWordBankClick = (word) => setScrambledAttempt([...scrambledAttempt, word]);
  const handleAttemptClick = (wordToRemove) =>
    setScrambledAttempt(scrambledAttempt.filter((w) => w.id !== wordToRemove.id));

  return (
    <form onSubmit={handleSubmit}>
      {retryHintBlock}
      <div className="scramble-container">
        <div className="scramble-attempt-box">
          {scrambledAttempt.length > 0 ? (
            scrambledAttempt.map((word) => (
              <button
                type="button"
                key={word.id}
                className="scramble-word-tile attempt"
                onClick={() => handleAttemptClick(word)}
              >
                {word.text}
              </button>
            ))
          ) : (
            <span className="scramble-placeholder">
              Tap the words below to build your sentence…
            </span>
          )}
        </div>
        <div className="scramble-word-bank">
          {availableWords.map((word) => (
            <button
              type="button"
              key={word.id}
              className="scramble-word-tile"
              onClick={() => handleWordBankClick(word)}
            >
              {word.text}
            </button>
          ))}
        </div>
      </div>
      {correctDone ? correctFeedbackBlock : (
        <div className="scramble-controls">
          <button type="button" className="secondary-button" onClick={() => setScrambledAttempt([])}>
            Reset
          </button>
          <button type="submit" disabled={scrambledAttempt.length === 0}>
            {retryMode ? 'Try Again' : 'Submit'}
          </button>
        </div>
      )}
    </form>
  );
}
