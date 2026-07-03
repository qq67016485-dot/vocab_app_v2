import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import TextToSpeechButton from '../../components/TextToSpeechButton.jsx';
import { SKILL_TAG_DISPLAY_NAMES_STUDENT } from '../../constants/skillTags.js';
import { useTranslationVisibility } from '../../hooks/useTranslationVisibility.js';
import correctSfx from '../../assets/sounds/correct.mp3';
import incorrectSfx from '../../assets/sounds/incorrect.mp3';

const correctMessages = {
  firstAttempt: [
    "Nice! Paying off.",
    "Solid effort!",
    "That one's sticking!",
    "Progress!",
    "You earned that.",
  ],
  selfCorrected: [
    "You figured it out!",
    "Persistence paid off!",
    "Got there! That's growth.",
    "Try, adjust, succeed.",
    "Mistakes help you learn.",
  ],
};

const incorrectMessages = [
  "Not yet. Try again!",
  "Tricky one! Check the hint.",
  "Almost! One more try.",
  "Keep at it!",
  "Not quite. You'll get it.",
];

const getCorrectMessage = (isSelfCorrected) => {
  const pool = isSelfCorrected ? correctMessages.selfCorrected : correctMessages.firstAttempt;
  return pool[Math.floor(Math.random() * pool.length)];
};

const reasonMessages = {
  NEW_WORD: [
    "New word!",
    "A fresh one.",
    "Let's learn this.",
    "Something new!",
    "New challenge!",
  ],
  STRUGGLE_WORD: [
    "Let's strengthen this one.",
    "Still building this one.",
    "Tricky words take time.",
    "Coming back makes it stick.",
    "One more round with this one.",
  ],
  MASTERY_CHECK: [
    "Almost there!",
    "One more check!",
    "Your effort's about to pay off.",
    "Show what you know!",
    "Close to locking this in.",
  ],
  STANDARD_REVIEW: [
    "Quick check-in.",
    "Keeping it fresh.",
    "Still remember this one?",
    "Staying sharp!",
    "Let's keep this one strong.",
  ],
};

const getRandomMessage = (category) => {
  if (!category || !reasonMessages[category]) return null;
  const messages = reasonMessages[category];
  return messages[Math.floor(Math.random() * messages.length)];
};

const ReasonDisplay = ({ category }) => {
  const message = useMemo(() => getRandomMessage(category), [category]);
  if (!message) return null;
  return <p className="reason-display"><em>{message}</em></p>;
};

export default function PracticeView() {
  const navigate = useNavigate();
  const { user, refreshUser } = useUser();

  const [question, setQuestion] = useState(null);
  const [userAnswer, setUserAnswer] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [finishMessage, setFinishMessage] = useState('');
  const [sessionSummary, setSessionSummary] = useState(null);
  const [scrambledAttempt, setScrambledAttempt] = useState([]);

  const [retryMode, setRetryMode] = useState(false);
  const [wrongOptions, setWrongOptions] = useState([]);
  const [hintText, setHintText] = useState('');
  const [showExplanation, setShowExplanation] = useState(false);
  const [retryFeedback, setRetryFeedback] = useState(null);
  const [correctMessage, setCorrectMessage] = useState('');
  const [incorrectMessage, setIncorrectMessage] = useState('');
  const [feedbackReady, setFeedbackReady] = useState(false);

  const [sessionGoalTotal, setSessionGoalTotal] = useState(0);
  const [questionsAnsweredThisSession, setQuestionsAnsweredThisSession] = useState(0);
  const [typoHint, setTypoHint] = useState('');
  const [showKeepGoingPrompt, setShowKeepGoingPrompt] = useState(false);
  const [dailyGoalMax, setDailyGoalMax] = useState(50);

  // Sentence-writing (productive, LLM-judged) state. The backend holds the
  // authoritative attempt history in the session (revision cap + fragility);
  // the frontend only tracks the attempt count for display. swBusy drives the
  // disabled/checking UI; swSubmittingRef guards re-entry (state updates are
  // async, so a ref is the reliable double-click gate).
  const [swSentence, setSwSentence] = useState('');
  const [swHint, setSwHint] = useState('');
  const [swAttempts, setSwAttempts] = useState(0);
  const [swBusy, setSwBusy] = useState(false);
  const swSubmittingRef = useRef(false);

  const { visibleTranslationTerm, handleShowTranslation } = useTranslationVisibility();

  const answerSwitchCount = useRef(0);
  const isSubmittingRetry = useRef(false);
  const sessionStartTime = useRef(new Date().toISOString());
  const questionStartTimeRef = useRef(null);
  const skipGoalCheck = useRef(false);

  const sessionStats = useRef({
    correctCount: 0,
    totalCount: 0,
    baseXp: 0,
    bonusXp: 0,
    bonuses: {},
    maxFocusStreak: 0,
    currentFocusStreak: 0,
    leveledUp: false,
    finalLevel: user?.level || 1,
  });

  const skillTagDisplayNames = SKILL_TAG_DISPLAY_NAMES_STUDENT;

  const shuffledOptions = useMemo(() => {
    if (!question || !question.options || !Array.isArray(question.options)) return [];
    const opts = [...question.options];
    for (let i = opts.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [opts[i], opts[j]] = [opts[j], opts[i]];
    }
    return opts;
  }, [question]);

  const playFeedbackSound = (isCorrect) => {
    try {
      const audio = new Audio(isCorrect ? correctSfx : incorrectSfx);
      audio.volume = 0.5;
      audio.play().catch(err => console.warn("Audio play blocked:", err));
    } catch (e) {
      console.error("Audio error:", e);
    }
  };

  const fetchNextQuestion = async () => {
    if (!skipGoalCheck.current && sessionGoalTotal > 0 && questionsAnsweredThisSession >= sessionGoalTotal) {
      if (sessionGoalTotal + 5 <= dailyGoalMax) {
        try {
          const peek = await apiClient.get('/practice/next/', {
            params: { session_start: sessionStartTime.current, peek: true },
          });
          if (peek.data.message) {
            setFinishMessage("You've reviewed everything available!");
            return;
          }
        } catch {
          // If peek fails, fall through to show the prompt anyway
        }
        setShowKeepGoingPrompt(true);
        return;
      }
      setFinishMessage("You've completed your goal for this session!");
      return;
    }
    skipGoalCheck.current = false;

    setIsLoading(true);
    setFeedback(null);
    setUserAnswer('');
    setScrambledAttempt([]);
    setTypoHint('');
    setQuestion(null);
    setRetryMode(false);
    setWrongOptions([]);
    setHintText('');
    setShowExplanation(false);
    setRetryFeedback(null);
    setCorrectMessage('');
    setIncorrectMessage('');
    setFeedbackReady(false);
    setSwSentence('');
    setSwHint('');
    setSwAttempts(0);
    answerSwitchCount.current = 0;

    try {
      const response = await apiClient.get('/practice/next/', {
        params: { session_start: sessionStartTime.current },
      });
      if (response.data.message) {
        setFinishMessage(response.data.message);
      } else {
        setQuestion(response.data);
        questionStartTimeRef.current = new Date();
      }
    } catch (error) {
      console.error('Error fetching next question:', error);
      setFinishMessage('An error occurred while fetching a question.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFinishSession = async () => {
    const finalStats = sessionStats.current;
    const focusStreakValue = finalStats.maxFocusStreak;
    const focusStreakBonus = Math.min(focusStreakValue, 10);

    if (focusStreakValue > 0) {
      try {
        await apiClient.post('/practice/apply-bonuses/', {
          max_focus_streak: focusStreakValue,
        });
      } catch (error) {
        console.error('Could not apply session bonuses:', error);
      }
      finalStats.bonuses['Focus Streak Bonus'] =
        (finalStats.bonuses['Focus Streak Bonus'] || 0) + focusStreakBonus;
    }

    const totalBonusXp = Object.values(finalStats.bonuses).reduce((s, v) => s + v, 0);
    const totalSessionXp = finalStats.baseXp + totalBonusXp;

    const totalSeconds = Math.max(
      1,
      Math.floor((new Date() - new Date(sessionStartTime.current)) / 1000)
    );

    let summaryAnalysis = { strengths: [], weaknesses: [] };
    try {
      const response = await apiClient.post('/practice/session-summary/', {
        start_time: sessionStartTime.current,
      });
      summaryAnalysis = response.data;
    } catch (error) {
      console.error('Could not fetch session analysis:', error);
    }

    setSessionSummary({
      ...finalStats,
      totalSessionXp,
      timeSeconds: totalSeconds,
      ...summaryAnalysis,
    });
    refreshUser();
  };

  const handleAnswerSubmission = async (answerToSubmit) => {
    if (!question || feedback || !answerToSubmit) return;

    const endTime = new Date();
    const durationMillis = endTime - questionStartTimeRef.current;
    const durationSeconds = Math.round(durationMillis / 1000);

    try {
      const response = await apiClient.post('/practice/submit/', {
        question_id: question.id,
        user_answer: answerToSubmit,
        duration_seconds: durationSeconds,
        answer_switches: answerSwitchCount.current,
      });
      const data = response.data;

      if (data.is_typo) {
        setTypoHint(data.message || 'Almost! Check your spelling and try again.');
        setUserAnswer('');
        return;
      }

      setTypoHint('');
      setQuestionsAnsweredThisSession((prev) => prev + 1);
      if (data.is_correct) document.activeElement?.blur();
      playFeedbackSound(data.is_correct);
      setFeedback(data);
      if (data.is_correct) {
        setCorrectMessage(getCorrectMessage(false));
        setTimeout(() => setFeedbackReady(true), 50);
      }

      const stats = sessionStats.current;
      stats.totalCount++;

      if (data.is_correct) {
        stats.correctCount++;
        stats.baseXp += 5;

        for (const [key, value] of Object.entries(data.bonus_info ?? {})) {
          const bonusName = key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
          if (stats.bonuses[bonusName]) stats.bonuses[bonusName] += value;
          else stats.bonuses[bonusName] = value;
        }

        stats.currentFocusStreak++;
        stats.maxFocusStreak = Math.max(stats.maxFocusStreak, stats.currentFocusStreak);

        if (data.did_level_up_user) {
          stats.leveledUp = true;
          stats.finalLevel++;
        }
      } else {
        stats.currentFocusStreak = 0;
        setRetryMode(true);
        setWrongOptions([answerToSubmit]);
        setHintText(data.explanation || '');
        setIncorrectMessage(incorrectMessages[Math.floor(Math.random() * incorrectMessages.length)]);
        setUserAnswer('');
        setScrambledAttempt([]);
      }
    } catch (error) {
      console.error('Error submitting answer:', error);
      setFeedback({ error: 'Could not submit answer.' });
    }
  };

  const handleRetrySubmission = async (answerToSubmit) => {
    if (!question || !answerToSubmit || isSubmittingRetry.current) return;
    isSubmittingRetry.current = true;

    try {
      const response = await apiClient.post('/practice/submit/', {
        question_id: question.id,
        user_answer: answerToSubmit,
        is_retry: true,
      });
      const data = response.data;

      if (data.is_typo) {
        setTypoHint(data.message || 'Almost! Check your spelling and try again.');
        setUserAnswer('');
        return;
      }

      setTypoHint('');

      if (data.is_correct) {
        document.activeElement?.blur();
        playFeedbackSound(true);
        setRetryMode(false);
        setRetryFeedback(data);
        setCorrectMessage(getCorrectMessage(true));
        setTimeout(() => setFeedbackReady(true), 50);
      } else {
        setWrongOptions((prev) => [...prev, answerToSubmit]);
        setHintText(data.explanation || '');
        setIncorrectMessage(incorrectMessages[Math.floor(Math.random() * incorrectMessages.length)]);
        setUserAnswer('');
        setScrambledAttempt([]);
      }
    } catch (error) {
      console.error('Error submitting retry:', error);
    } finally {
      isSubmittingRetry.current = false;
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const handler = retryMode ? handleRetrySubmission : handleAnswerSubmission;
    if (question?.question_type === 'SENTENCE_SCRAMBLE') {
      const finalAnswer = scrambledAttempt.map((w) => w.text).join(' ').trim();
      handler(finalAnswer);
    } else {
      handler(userAnswer);
    }
  };

  // Apply session stats for a terminal answer (used by MC + sentence-write).
  const applyTerminalStats = (data, { selfCorrected = false } = {}) => {
    setQuestionsAnsweredThisSession((prev) => prev + 1);
    playFeedbackSound(data.is_correct);

    const stats = sessionStats.current;
    stats.totalCount++;
    if (data.is_correct) {
      stats.correctCount++;
      stats.baseXp += 5;
      for (const [key, value] of Object.entries(data.bonus_info ?? {})) {
        const bonusName = key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
        stats.bonuses[bonusName] = (stats.bonuses[bonusName] || 0) + value;
      }
      stats.currentFocusStreak++;
      stats.maxFocusStreak = Math.max(stats.maxFocusStreak, stats.currentFocusStreak);
      if (data.did_level_up_user) {
        stats.leveledUp = true;
        stats.finalLevel++;
      }
      setCorrectMessage(getCorrectMessage(selfCorrected));
      setTimeout(() => setFeedbackReady(true), 50);
    } else {
      stats.currentFocusStreak = 0;
    }
  };

  const submitSentenceWrite = async (sentenceText, { gaveUp = false } = {}) => {
    if (swSubmittingRef.current) return;
    if (!gaveUp && !sentenceText.trim()) return;
    swSubmittingRef.current = true;
    setSwBusy(true);
    setSwHint('');

    try {
      // Attempt history lives server-side in the session; the backend caps
      // revisions and decides fragility, so only the sentence is posted.
      const response = await apiClient.post('/practice/submit/', {
        question_id: question.id,
        user_answer: gaveUp ? (sentenceText || '') : sentenceText,
        gave_up: gaveUp,
      });
      const data = response.data;

      if (data.sentence_write_unavailable) {
        // Judge is down — discard silently and move to a different question.
        fetchNextQuestion();
        return;
      }

      if (data.sentence_write_pending) {
        // Non-terminal miss: show the hint, let them revise.
        setSwAttempts(data.attempts_used ?? swAttempts + 1);
        setSwHint(data.hint || '');
        setIncorrectMessage(
          incorrectMessages[Math.floor(Math.random() * incorrectMessages.length)],
        );
        setSwSentence('');
        return;
      }

      // Terminal — scored.
      if (data.is_correct) document.activeElement?.blur();
      const selfCorrected = swAttempts > 0;
      applyTerminalStats(data, { selfCorrected });
      if (!data.is_correct) {
        setIncorrectMessage(
          incorrectMessages[Math.floor(Math.random() * incorrectMessages.length)],
        );
      }
      setFeedback(data);
    } catch (error) {
      console.error('Error submitting sentence:', error);
      setFeedback({ error: 'Could not submit answer.' });
    } finally {
      swSubmittingRef.current = false;
      setSwBusy(false);
    }
  };

  useEffect(() => {
    const startSession = async () => {
      try {
        const response = await apiClient.get('/student/dashboard/');
        const goalMax = response.data.daily_goal_max || 50;
        setDailyGoalMax(goalMax);

        let sessionTarget = response.data.session_goal_total || 0;
        const totalGoal = response.data.daily_question_limit || 30;

        const overrideRaw = sessionStorage.getItem('daily_goal_override');
        if (overrideRaw) {
          try {
            const override = JSON.parse(overrideRaw);
            const today = new Date().toISOString().slice(0, 10);
            if (override.date === today && override.value > 0) {
              const answeredToday = response.data.questions_answered_today || 0;
              const overrideRemaining = Math.max(0, override.value - answeredToday);
              const wordsDue = response.data.session_goal_total || 0;
              sessionTarget = Math.min(overrideRemaining, wordsDue);
            }
          } catch { /* ignore bad JSON */ }
        }

        setSessionGoalTotal(sessionTarget);

        if (sessionTarget > 0) {
          fetchNextQuestion();
        } else {
          if (response.data.questions_answered_today >= totalGoal) {
            setFinishMessage("You've already met your goal for today!");
          } else {
            setFinishMessage('No words are due for review right now. Great work!');
          }
          setIsLoading(false);
        }
      } catch (error) {
        console.error('Could not fetch session goal:', error);
        setSessionGoalTotal(20);
        fetchNextQuestion();
      }
    };
    startSession();
  }, []);

  useEffect(() => {
    if (finishMessage && !sessionSummary) handleFinishSession();
  }, [finishMessage, sessionSummary]);

  const renderQuestionInput = () => {
    if (!question) return null;

    const optionsArray = shuffledOptions;
    const feedbackSource = retryFeedback || feedback;
    const correctDone = feedbackSource?.is_correct && !retryMode;

    const isLastQuestion = sessionGoalTotal > 0 && questionsAnsweredThisSession >= sessionGoalTotal;
    const nextLabel = isLastQuestion ? 'Finish Session' : 'Next Question';

    const correctFeedbackBlock = correctDone ? (
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
            >
              {nextLabel}
            </button>
          </>
        )}
      </div>
    ) : null;

    const mcQuestionTypes = [
      'DEFINITION_MC_SINGLE', 'SYNONYM_MC_SINGLE', 'ANTONYM_MC_SINGLE',
      'CONTEXT_MC_SINGLE', 'COLLOCATION_MC_SINGLE', 'ODD_ONE_OUT_MC_SINGLE',
      'WORD_FORM_MC', 'CONCEPTUAL_ASSOCIATION_MC_SINGLE',
      'REVERSE_DEFINITION_MC', 'SYNONYM_IN_CONTEXT_MC',
      'REVERSE_SYNONYM_IN_CONTEXT_MC', 'APPLICATION_MC',
      'REVERSE_ASSOCIATION_MC', 'REVERSE_COLLOCATION_MC',
      'NUANCE_CONTRAST_MC',
    ];

    const handleMcOptionClick = (option) => {
      if (userAnswer && userAnswer !== option) answerSwitchCount.current += 1;
      setUserAnswer(option);
    };

    // Type-to-spell: when answer is the target word and Lexile > 600,
    // show options as read-only reference and require typing the answer
    const isTypeToSpell =
      question.correct_answer_is_term &&
      question.lexile_score > 600 &&
      question.question_type !== 'DEFINITION_TRUE_FALSE';

    const retryHintBlock = retryMode ? (
      <>
        {incorrectMessage && (
          <div className="retry-encouragement-banner">
            <span className="retry-encouragement-text">{incorrectMessage}</span>
          </div>
        )}
        {hintText && (
          <div className="retry-hint-block">
            <div className="block-title">
              Hint
              <TextToSpeechButton textToSpeak={hintText} />
            </div>
            <p className="block-body"><em>{hintText}</em></p>
          </div>
        )}
      </>
    ) : null;

    if (
      question.question_type === 'SENTENCE_WRITE_GUIDED' ||
      question.question_type === 'SENTENCE_WRITE_OPEN'
    ) {
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

    if (
      question.question_type === 'DEFINITION_TRUE_FALSE' ||
      mcQuestionTypes.includes(question.question_type)
    ) {
      const choices =
        question.question_type === 'DEFINITION_TRUE_FALSE' ? ['True', 'False'] : optionsArray;

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
              {retryMode && wrongOptions.length >= choices.length && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ marginTop: '20px', width: '100%' }}
                  onClick={fetchNextQuestion}
                >
                  {nextLabel}
                </button>
              )}
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

    if (question.question_type === 'SENTENCE_SCRAMBLE') {
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
                  Click words below to build your sentence...
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

    return (
      <form onSubmit={handleSubmit}>
        {retryHintBlock}
        {!correctDone && (
          <input
            type="text"
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            placeholder={retryMode ? "Try typing the answer again..." : "Type your answer..."}
            autoFocus
            style={{ marginTop: '20px' }}
          />
        )}
        {correctDone ? correctFeedbackBlock : (
          <button type="submit" className="btn btn-primary" style={{ marginTop: '10px', width: '100%' }}>
            {retryMode ? 'Try Again' : 'Submit Answer'}
          </button>
        )}
      </form>
    );
  };

  const renderContent = () => {
    if (isLoading) return <p>Loading...</p>;

    if (showKeepGoingPrompt) {
      return (
        <div className="keep-going-prompt">
          <h3>Goal reached!</h3>
          <p>You answered {questionsAnsweredThisSession} questions. Want to keep going?</p>
          <div className="keep-going-actions">
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => {
                const newGoal = Math.min(sessionGoalTotal + 5, dailyGoalMax);
                setSessionGoalTotal(newGoal);
                setShowKeepGoingPrompt(false);
                skipGoalCheck.current = true;
                fetchNextQuestion();
              }}
            >
              +5 More
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => {
                setShowKeepGoingPrompt(false);
                setFinishMessage("Great session!");
              }}
            >
              I'm Done
            </button>
          </div>
        </div>
      );
    }

    if (finishMessage) {
      if (!sessionSummary) return <p>Wrapping up your session...</p>;
      const minutes = Math.max(1, Math.round((sessionSummary.timeSeconds || 0) / 60));
      return (
        <div className="session-summary">
          <section className="summary-hero">
            <h3>You put in the work!</h3>
            <p>{minutes} min of focused practice — that effort adds up.</p>
            <div className="metrics-row">
              <div className="metric-card">
                <div className="metric-value">{sessionSummary.totalCount}</div>
                <div className="metric-label">Attempted</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">{sessionSummary.correctCount}</div>
                <div className="metric-label">Correct</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">+{sessionSummary.totalSessionXp} XP</div>
                <div className="metric-label">Earned</div>
              </div>
            </div>
          </section>
          {sessionSummary.strengths?.length > 0 && (
            <section className="summary-section chips">
              <h4>Getting stronger at</h4>
              <div className="chip-list">
                {sessionSummary.strengths.map((w) => (
                  <span key={w} className="summary-chip">{w}</span>
                ))}
              </div>
            </section>
          )}
          {sessionSummary.weaknesses?.length > 0 && (
            <section className="summary-section weaknesses">
              <h4>Still building these</h4>
              <ul className="weakness-list">
                {sessionSummary.weaknesses.map((word) => (
                  <li key={word.term} className="weakness-row">
                    <div className="weakness-left">
                      <div className="word-and-tts">
                        <TextToSpeechButton textToSpeak={word.term} />
                        <strong>{word.term}</strong>
                        {word.skill_tags?.length > 0 && (
                          <span className="summary-chip soft">
                            {skillTagDisplayNames[word.skill_tags[0]] || word.skill_tags[0]}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="weakness-right">
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
                  </li>
                ))}
              </ul>
            </section>
          )}
          <button className="back-home" onClick={() => navigate('/student/dashboard')}>
            Back to Home
          </button>
        </div>
      );
    }

    if (!question) {
      if (!finishMessage) return <p>Loading next question...</p>;
      return null;
    }

    return (
      <div>
        <div className="question-heading">
          <div className="question-title">
            <h3>{question.question_text}</h3>
            <TextToSpeechButton textToSpeak={question.question_text} />
          </div>
          <div className="question-note">
            <ReasonDisplay category={question.reason_category} />
          </div>
        </div>
        {renderQuestionInput()}
      </div>
    );
  };

  return (
    <div>
      <div className="practice-header compact">
        <div className="session-progress-track">
          <div
            className="session-progress-fill"
            style={{ width: sessionGoalTotal > 0 ? `${Math.min((questionsAnsweredThisSession / sessionGoalTotal) * 100, 100)}%` : '0%' }}
          />
          <span className="session-progress-label">
            {questionsAnsweredThisSession} / {sessionGoalTotal}
          </span>
        </div>
        <button
          className="end-session"
          type="button"
          onClick={() => setFinishMessage("Session ended.")}
        >
          End Session
        </button>
      </div>
      <div className="practice-card" key={question?.id || 'loading'}>{renderContent()}</div>
    </div>
  );
}
