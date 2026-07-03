import React from 'react';
import TextToSpeechButton from '../TextToSpeechButton.jsx';

/**
 * Render 1–3 coaching bullets. A single bullet shows as a plain line; two or
 * three render as a list. The array is already capped server-side at 3.
 */
function HintBullets({ hints }) {
  const list = (hints || []).filter(Boolean);
  if (list.length === 0) return null;
  if (list.length === 1) {
    return <p className="block-body"><em>{list[0]}</em></p>;
  }
  return (
    <ul className="sw-hint-list">
      {list.map((h, i) => <li key={i}>{h}</li>)}
    </ul>
  );
}

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
  swHints,
  swLastSentence,
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
  const hintList = (swHints && swHints.length) ? swHints : (swHint ? [swHint] : []);

  if (feedbackDone) {
    const finalHints = (feedback.hints && feedback.hints.length)
      ? feedback.hints
      : (feedback.hint ? [feedback.hint] : []);
    return (
      <div className="sentence-write">
        <div className={`sw-verdict ${feedback.is_correct ? 'correct' : 'missed'}`}>
          <p className="correct-encouragement">
            {feedback.is_correct ? (correctMessage || 'Nicely done!') : "Good effort — here's a strong example:"}
          </p>
          {swLastSentence && (
            <div className="feedback-block your-sentence">
              <div className="block-title">Your sentence</div>
              <p className="block-body">“{swLastSentence}”</p>
            </div>
          )}
          {finalHints.length > 0 && (
            <div className="sw-hint-final"><HintBullets hints={finalHints} /></div>
          )}
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
      {hintList.length > 0 ? (
        <div className="retry-encouragement-banner">
          <span className="retry-encouragement-text">
            {incorrectMessage || 'Almost — try again!'}
          </span>
        </div>
      ) : null}
      {swLastSentence && hintList.length > 0 && (
        <div className="sw-your-sentence">
          <div className="block-title">You wrote</div>
          <p className="block-body"><em>“{swLastSentence}”</em></p>
        </div>
      )}
      {hintList.length > 0 && (
        <div className="retry-hint-block">
          <div className="block-title">
            {hintList.length > 1 ? 'Hints' : 'Hint'}
            <TextToSpeechButton textToSpeak={hintList.join('. ')} />
          </div>
          <HintBullets hints={hintList} />
        </div>
      )}
      {sw.sentence_starter && hintList.length === 0 && (
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
