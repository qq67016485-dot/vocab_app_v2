import React from 'react';
import TextToSpeechButton from '../TextToSpeechButton.jsx';

/**
 * Shared "you got it" feedback panel shown after a correct answer on MC,
 * type-to-spell, and scramble questions. Two states: a compact Explain / Next
 * pair, and (once Explain is tapped) the full explanation + example + Next.
 *
 * The Next/Explain buttons are tabIndex-gated on `feedbackReady` so the keypress
 * that submitted the answer can't immediately activate the button that replaces
 * the now-removed input (see feedback_keyboard-focus-after-dom-removal).
 */
export default function CorrectFeedbackBlock({
  showExplanation,
  setShowExplanation,
  correctMessage,
  feedbackReady,
  feedbackSource,
  fetchNextQuestion,
  nextLabel,
}) {
  return (
    <div className="correct-inline-feedback" style={{ marginTop: '20px' }}>
      {!showExplanation ? (
        <>
          <p className="correct-encouragement">{correctMessage || 'Correct!'}</p>
          <div className="correct-actions">
            <button
              className="correct-action-btn outline"
              onClick={() => setShowExplanation(true)}
              type="button"
              tabIndex={feedbackReady ? 0 : -1}
            >
              Explain
            </button>
            <button
              className="correct-action-btn filled"
              onClick={fetchNextQuestion}
              type="button"
              tabIndex={feedbackReady ? 0 : -1}
            >
              {nextLabel}
            </button>
          </div>
        </>
      ) : (
        <>
          {feedbackSource.explanation && (
            <div className="feedback-block explain">
              <div className="block-title">
                Explanation
                <TextToSpeechButton textToSpeak={feedbackSource.explanation} />
              </div>
              <p className="block-body">
                <em>{feedbackSource.explanation}</em>
              </p>
            </div>
          )}
          {feedbackSource.example_sentence && (
            <div className="feedback-block example">
              <div className="block-title">
                Example
                <TextToSpeechButton textToSpeak={feedbackSource.example_sentence} />
              </div>
              <p className="block-body">{feedbackSource.example_sentence}</p>
            </div>
          )}
          <p className="correct-encouragement">{correctMessage || 'Correct!'}</p>
          <button
            className="correct-action-btn filled"
            onClick={fetchNextQuestion}
            type="button"
            style={{ width: '100%' }}
            tabIndex={feedbackReady ? 0 : -1}
          >
            {nextLabel}
          </button>
        </>
      )}
    </div>
  );
}
