import React from 'react';
import TextToSpeechButton from '../TextToSpeechButton.jsx';

/**
 * Productive, LLM-judged sentence-writing question. Two views: the write/revise
 * form, and the terminal verdict panel (once `feedbackDone`). The revision cap
 * and fragility are decided server-side; this component only reflects state.
 */
export default function SentenceWriteQuestion({
  question,
  feedback,
  correctMessage,
  incorrectMessage,
  feedbackReady,
  isLastQuestion,
  swSentence,
  setSwSentence,
  swHint,
  swAttempts,
  swBusy,
  submitSentenceWrite,
  fetchNextQuestion,
}) {
  const sw = question.sentence_write || {};
  const feedbackDone = feedback && !feedback.error;
  const maxRevisions = sw.max_revisions ?? 2;
  const revisionsLeft = Math.max(0, maxRevisions - swAttempts);
  const canRevise = revisionsLeft > 0 && !feedbackDone;

  if (feedbackDone) {
    return (
      <div className="sentence-write">
        <div className={`sw-verdict ${feedback.is_correct ? 'correct' : 'missed'}`}>
          <p className="correct-encouragement">
            {feedback.is_correct ? (correctMessage || 'Nicely done!') : "Good effort — here's a strong example:"}
          </p>
          {feedback.hint && <p className="sw-hint-final"><em>{feedback.hint}</em></p>}
          {feedback.model_sentence && (
            <div className="feedback-block example">
              <div className="block-title">
                Example sentence
                <TextToSpeechButton textToSpeak={feedback.model_sentence} />
              </div>
              <p className="block-body">{feedback.model_sentence}</p>
            </div>
          )}
        </div>
        <button
          className="correct-action-btn filled"
          onClick={fetchNextQuestion}
          type="button"
          style={{ width: '100%', marginTop: '16px' }}
          tabIndex={feedbackReady ? 0 : -1}
        >
          {isLastQuestion ? 'Finish Session' : 'Next Question'}
        </button>
      </div>
    );
  }

  return (
    <div className="sentence-write">
      {sw.definition && (
        <div className="sw-definition">
          <span className="sw-def-label">{question.term_text}</span>
          <span className="sw-def-text">{sw.definition}</span>
          <TextToSpeechButton textToSpeak={`${question.term_text}. ${sw.definition}`} />
        </div>
      )}
      {swHint ? (
        <div className="retry-encouragement-banner">
          <span className="retry-encouragement-text">
            {incorrectMessage || 'Almost — try again!'}
          </span>
        </div>
      ) : null}
      {swHint && (
        <div className="retry-hint-block">
          <div className="block-title">
            Hint
            <TextToSpeechButton textToSpeak={swHint} />
          </div>
          <p className="block-body"><em>{swHint}</em></p>
        </div>
      )}
      {sw.sentence_starter && !swHint && (
        <p className="sw-starter">Try starting with: <em>{sw.sentence_starter}</em></p>
      )}
      <form
        onSubmit={(e) => { e.preventDefault(); submitSentenceWrite(swSentence); }}
      >
        <textarea
          className="sw-textarea"
          value={swSentence}
          onChange={(e) => setSwSentence(e.target.value)}
          placeholder={swAttempts > 0
            ? 'Rewrite your sentence...'
            : `Write a sentence using "${question.term_text}"...`}
          rows={3}
          autoFocus
        />
        <div className="sw-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!swSentence.trim() || swBusy}
          >
            {swBusy ? 'Checking…' : (swAttempts > 0 ? 'Try Again' : 'Submit')}
          </button>
          {swAttempts > 0 && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => submitSentenceWrite(swSentence, { gaveUp: true })}
              disabled={swBusy}
            >
              Show me an example
            </button>
          )}
        </div>
        {!canRevise && swAttempts > 0 && (
          <p className="sw-note">Last try — this one counts.</p>
        )}
      </form>
    </div>
  );
}
