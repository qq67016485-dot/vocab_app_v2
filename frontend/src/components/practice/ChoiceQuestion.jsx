import React from 'react';

/**
 * Multiple-choice, true/false, and type-to-spell questions. Type-to-spell shows
 * the options as read-only reference and requires typing the target word (used
 * when the answer IS the term and Lexile > 600).
 */
export default function ChoiceQuestion({
  question,
  choices,
  isTypeToSpell,
  userAnswer,
  setUserAnswer,
  wrongOptions,
  correctDone,
  retryMode,
  typoHint,
  setTypoHint,
  answerSwitchCount,
  handleSubmit,
  retryHintBlock,
  correctFeedbackBlock,
}) {
  const handleMcOptionClick = (option) => {
    if (userAnswer && userAnswer !== option) answerSwitchCount.current += 1;
    setUserAnswer(option);
  };

  if (isTypeToSpell) {
    return (
      <form onSubmit={handleSubmit}>
        <div className="mc-options-container">
          {choices.map((option, index) => (
            <div key={index} className="mc-option-button reference">
              {option}
            </div>
          ))}
        </div>
        {retryHintBlock}
        {typoHint && (
          <div className="typo-hint">{typoHint}</div>
        )}
        {!correctDone && (
          <input
            type="text"
            className={`type-to-spell-input${typoHint ? ' typo-shake' : ''}`}
            placeholder={retryMode ? "Try typing the word again..." : "Type the correct word..."}
            value={userAnswer || ''}
            onChange={(e) => { setUserAnswer(e.target.value); setTypoHint(''); }}
            autoFocus
          />
        )}
        {correctDone ? correctFeedbackBlock : userAnswer && (
          <button type="submit" className="btn btn-primary" style={{ marginTop: '20px', width: '100%' }}>
            {retryMode ? 'Try Again' : 'Submit'}
          </button>
        )}
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <div
        className={
          question.question_type === 'DEFINITION_TRUE_FALSE'
            ? 'tf-options-container'
            : 'mc-options-container'
        }
      >
        {choices.map((option, index) => {
          const isWrong = wrongOptions.includes(option);
          const isCorrectOption = correctDone && userAnswer === option;
          return (
            <button
              key={index}
              type="button"
              className={`mc-option-button ${isCorrectOption ? 'correct-answer' : userAnswer === option ? 'selected' : ''}${isWrong ? ' wrong-answer' : ''}`}
              onClick={() => handleMcOptionClick(option)}
              disabled={isWrong || correctDone}
            >
              {option}
            </button>
          );
        })}
      </div>
      {retryHintBlock}
      {correctDone ? correctFeedbackBlock : (
        <>
          {/* No reveal-and-move-on escape by design: wrong options are disabled
              when struck out, so elimination always ends at the correct answer,
              and type-to-spell shows the answer among the read-only reference
              options. (Removed 2026-08-27: the old condition
              `wrongOptions.length >= choices.length` was unreachable — a correct
              option is never in wrongOptions.) */}
          {userAnswer && (
            <button type="submit" className="btn btn-primary" style={{ marginTop: '20px', width: '100%' }}>
              {retryMode ? 'Try Again' : 'Submit'}
            </button>
          )}
        </>
      )}
    </form>
  );
}
