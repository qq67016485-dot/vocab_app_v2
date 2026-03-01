import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import TextToSpeechButton from '../../components/TextToSpeechButton.jsx';
import ProgressBar from '../../components/ProgressBar.jsx';
import { SKILL_TAG_DISPLAY_NAMES_STUDENT } from '../../constants/skillTags.js';
import { useTranslationVisibility } from '../../hooks/useTranslationVisibility.js';
import correctSfx from '../../assets/sounds/correct.mp3';
import incorrectSfx from '../../assets/sounds/incorrect.mp3';

const REFLECTION_ARCHETYPES = [
  {
    id: 'definition',
    match: ['DEFINITION_MC_SINGLE', 'DEFINITION_MATCHING', 'DEFINITION_TRUE_FALSE'],
    options: [
      { id: 'forgot', label: 'I knew it, but forgot' },
      { id: 'ambiguous', label: 'The choices were confusing' },
      { id: 'unknown', label: "I didn't know this word" },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
  {
    id: 'synonym_antonym',
    match: ['SYNONYM_MC_SINGLE', 'SYNONYM_MC_MULTI', 'SYNONYM_MATCHING', 'ANTONYM_MC_SINGLE', 'ANTONYM_MATCHING', 'ODD_ONE_OUT_MC_SINGLE'],
    options: [
      { id: 'mixed_polarity', label: 'I mixed up Synonym vs Antonym' },
      { id: 'distractor', label: 'Confused with similar word' },
      { id: 'unknown', label: "I didn't know the answer choices" },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
  {
    id: 'collocation',
    match: ['COLLOCATION_MC_SINGLE', 'COLLOCATION_FILL_IN_BLANK', 'COLLOCATION_MATCHING'],
    options: [
      { id: 'intuition_fail', label: 'It "sounded" right to me' },
      { id: 'nuance_gap', label: 'Unsure of the specific usage' },
      { id: 'guess', label: 'Just guessed' },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
  {
    id: 'word_form',
    match: ['WORD_FORM_MC', 'WORD_FORM_FILL_IN_BLANK', 'SPELLING_FILL_IN_BLANK'],
    options: [
      { id: 'wrong_clue', label: 'I looked at the wrong clue' },
      { id: 'morphology', label: 'Confused the word ending/suffix' },
      { id: 'intuition', label: 'I relied on "what sounds right"' },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
  {
    id: 'syntax',
    match: ['SENTENCE_SCRAMBLE'],
    options: [
      { id: 'syntax_error', label: 'Confused the word order' },
      { id: 'ambiguous', label: 'My answer seems correct too' },
      { id: 'logic', label: 'Misunderstood the sentence logic' },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
  {
    id: 'context',
    match: ['CONTEXT_MC_SINGLE', 'CONTEXT_FILL_IN_BLANK', 'CONNOTATION_SORTING', 'CONCEPTUAL_ASSOCIATION_MC_SINGLE'],
    options: [
      { id: 'blindness', label: 'Missed the clue in sentence' },
      { id: 'nuance', label: 'Choices were too similar' },
      { id: 'guess', label: 'Just guessed' },
      { id: 'next', label: 'Got it / Next', isNeutral: true },
    ],
  },
];

const getReflectionOptions = (qType) => {
  const archetype = REFLECTION_ARCHETYPES.find(arch => arch.match.includes(qType));
  if (archetype) return archetype.options;
  return [
    { id: 'forgot', label: 'I knew it, but forgot' },
    { id: 'unknown', label: "I didn't know this" },
    { id: 'slip', label: 'Accidental click' },
    { id: 'next', label: 'Got it / Next', isNeutral: true },
  ];
};

const reasonMessages = {
  NEW_WORD: [
    "Here's a brand new word for you!",
    "Let's learn something new.",
    "Time to add a new word to your collection.",
    "A fresh word coming your way.",
    "Let's explore a new term.",
  ],
  STRUGGLE_WORD: [
    "Repetition is key! Let's try this one again.",
    "Let's take another look at this one.",
    "This one can be tricky. You've got this!",
    "Practice makes perfect. Let's give it another go.",
    "Let's reinforce this one.",
  ],
  MASTERY_CHECK: [
    "Almost mastered! Let's lock it in.",
    "You've just about got this one memorized.",
    "This is the final check on this word.",
    "Let's get this one to the next level.",
    "Time to prove your mastery.",
  ],
  STANDARD_REVIEW: [
    "Time for a quick review!",
    "Let's see if you remember this one.",
    "Knockin' the rust off this word.",
    "Let's keep your memory sharp.",
    "Just checking in on this one.",
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
  const [submittedAnswer, setSubmittedAnswer] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [finishMessage, setFinishMessage] = useState('');
  const [sessionSummary, setSessionSummary] = useState(null);
  const [scrambledAttempt, setScrambledAttempt] = useState([]);
  const [feedbackPhase, setFeedbackPhase] = useState('showing');

  const [sessionGoalTotal, setSessionGoalTotal] = useState(0);
  const [questionsAnsweredThisSession, setQuestionsAnsweredThisSession] = useState(0);

  const { visibleTranslationTerm, handleShowTranslation } = useTranslationVisibility();

  const answerSwitchCount = useRef(0);
  const sessionStartTime = useRef(new Date().toISOString());
  const questionStartTimeRef = useRef(null);

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
    if (sessionGoalTotal > 0 && questionsAnsweredThisSession >= sessionGoalTotal) {
      setFinishMessage("You've completed your goal for this session!");
      return;
    }

    setIsLoading(true);
    setFeedback(null);
    setFeedbackPhase('showing');
    setUserAnswer('');
    setSubmittedAnswer('');
    setScrambledAttempt([]);
    setQuestion(null);
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

    setSubmittedAnswer(answerToSubmit);
    setQuestionsAnsweredThisSession((prev) => prev + 1);

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
      playFeedbackSound(data.is_correct);

      if (data.is_correct) {
        setFeedbackPhase('confirmed');
      } else {
        setFeedbackPhase('showing');
      }
      setFeedback(data);

      const stats = sessionStats.current;
      stats.totalCount++;

      if (data.is_correct) {
        stats.correctCount++;
        stats.baseXp += 5;

        for (const [key, value] of Object.entries(data.bonus_info)) {
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
      }
    } catch (error) {
      console.error('Error submitting answer:', error);
      setFeedback({ error: 'Could not submit answer.' });
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (question?.question_type === 'SENTENCE_SCRAMBLE') {
      const finalAnswer = scrambledAttempt.map((w) => w.text).join(' ').trim();
      handleAnswerSubmission(finalAnswer);
    } else {
      handleAnswerSubmission(userAnswer);
    }
  };

  const handleReflection = () => {
    fetchNextQuestion();
  };

  useEffect(() => {
    const startSession = async () => {
      try {
        const response = await apiClient.get('/student/dashboard/');
        const sessionTarget = response.data.session_goal_total || 0;
        const totalGoal = response.data.daily_question_limit || 20;
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

    const mcQuestionTypes = [
      'DEFINITION_MC_SINGLE', 'SYNONYM_MC_SINGLE', 'ANTONYM_MC_SINGLE',
      'CONTEXT_MC_SINGLE', 'COLLOCATION_MC_SINGLE', 'ODD_ONE_OUT_MC_SINGLE',
      'WORD_FORM_MC', 'CONCEPTUAL_ASSOCIATION_MC_SINGLE',
    ];

    const handleMcOptionClick = (option) => {
      if (userAnswer && userAnswer !== option) answerSwitchCount.current += 1;
      setUserAnswer(option);
    };

    if (
      question.question_type === 'DEFINITION_TRUE_FALSE' ||
      mcQuestionTypes.includes(question.question_type)
    ) {
      const choices =
        question.question_type === 'DEFINITION_TRUE_FALSE' ? ['True', 'False'] : optionsArray;

      return (
        <form onSubmit={handleSubmit}>
          <div
            className={
              question.question_type === 'DEFINITION_TRUE_FALSE'
                ? 'tf-options-container'
                : 'mc-options-container'
            }
          >
            {choices.map((option, index) => (
              <button
                key={index}
                type="button"
                className={`mc-option-button ${userAnswer === option ? 'selected' : ''}`}
                onClick={() => handleMcOptionClick(option)}
              >
                {option}
              </button>
            ))}
          </div>
          {userAnswer && (
            <button type="submit" className="btn btn-primary" style={{ marginTop: '20px', width: '100%' }}>
              Submit
            </button>
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
          <div className="scramble-controls">
            <button type="button" className="secondary-button" onClick={() => setScrambledAttempt([])}>
              Reset
            </button>
            <button type="submit" disabled={scrambledAttempt.length === 0}>
              Submit
            </button>
          </div>
        </form>
      );
    }

    return (
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={userAnswer}
          onChange={(e) => setUserAnswer(e.target.value)}
          placeholder="Type your answer..."
          autoFocus
          style={{ marginTop: '20px' }}
        />
        <button type="submit" className="btn btn-primary" style={{ marginTop: '10px', width: '100%' }}>
          Submit Answer
        </button>
      </form>
    );
  };

  const renderContent = () => {
    if (isLoading) return <p>Loading...</p>;

    if (finishMessage) {
      if (!sessionSummary) return <p>Great work! Generating your session report...</p>;
      const minutes = Math.max(1, Math.round((sessionSummary.timeSeconds || 0) / 60));
      return (
        <div className="session-summary">
          <section className="summary-hero">
            <h3>Great work!</h3>
            <p>You finished your practice.</p>
            <div className="metrics-row">
              <div className="metric-card">
                <div className="metric-value">
                  {sessionSummary.correctCount} / {sessionSummary.totalCount}
                </div>
                <div className="metric-label">Correct</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">{minutes} min</div>
                <div className="metric-label">Time</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">+{sessionSummary.totalSessionXp} XP</div>
                <div className="metric-label">XP earned</div>
              </div>
            </div>
          </section>
          {sessionSummary.strengths?.length > 0 && (
            <section className="summary-section chips">
              <h4>You're doing great with</h4>
              <div className="chip-list">
                {sessionSummary.strengths.map((w) => (
                  <span key={w} className="summary-chip">{w}</span>
                ))}
              </div>
            </section>
          )}
          {sessionSummary.weaknesses?.length > 0 && (
            <section className="summary-section weaknesses">
              <h4>Words to practice</h4>
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

    if (feedback) {
      const skillDisplayName = skillTagDisplayNames[feedback.skill_tag] || feedback.skill_tag;

      return (
        <div>
          <div className="feedback-header">
            <span className={`feedback-chip ${feedback.is_correct ? 'correct' : 'incorrect'}`}>
              {feedback.is_correct ? 'Correct!' : 'Incorrect'}
            </span>
            {feedback.skill_tag && (
              <span className="feedback-chip tag">{skillDisplayName}</span>
            )}
          </div>

          <div className="feedback-wordline">
            <div className="feedback-word-main">
              <span className="label">The word was:</span>
              <strong>{question.term_text}</strong>
              <TextToSpeechButton textToSpeak={question.term_text} />
              {!feedback.is_correct &&
                feedback.skill_tag === 'definition_recall' &&
                feedback.translation && (
                  <span className="feedback-translation">{feedback.translation}</span>
                )}
            </div>
          </div>

          {!feedback.is_correct && (
            <div className="feedback-context-card">
              <div className="feedback-question-text">
                <span className="label-tiny">Question:</span>
                <p>{question.question_text}</p>
              </div>
              <div className="feedback-comparison">
                <div className="answer-row user-error">
                  <span className="icon">&#10008;</span>
                  <span className="label-tiny">You said:</span>
                  <span className="text">{submittedAnswer || "(No answer)"}</span>
                </div>
                <div className="answer-row correct-target">
                  <span className="icon">&#10004;</span>
                  <span className="label-tiny">Answer:</span>
                  <span className="text">{feedback.correct_answer}</span>
                </div>
              </div>
            </div>
          )}

          {feedback.explanation && (
            <div className="feedback-block explain">
              <div className="block-title">
                Explanation
                <TextToSpeechButton textToSpeak={feedback.explanation} />
              </div>
              <p className="block-body">
                <em>{feedback.explanation}</em>
              </p>
            </div>
          )}

          {feedback.example_sentence && (
            <div className="feedback-block example">
              <div className="block-title">
                Example
                <TextToSpeechButton textToSpeak={feedback.example_sentence} />
              </div>
              <p className="block-body">{feedback.example_sentence}</p>
            </div>
          )}

          <div style={{ marginTop: '1.5rem' }}>
            {feedback.is_correct ? (
              <button
                className="next-question btn btn-primary"
                onClick={fetchNextQuestion}
                style={{ width: '100%' }}
              >
                Next Question
              </button>
            ) : (
              <div className="feedback-reflection-area">
                <p className="reflection-prompt">Self Reflection:</p>
                <div className="reflection-grid">
                  {getReflectionOptions(question.question_type).map((opt) => (
                    <button
                      key={opt.id}
                      className={`reflection-btn ${opt.isNeutral ? 'neutral' : ''}`}
                      onClick={() => handleReflection(opt.id)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      );
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
        <h2>Practice Session</h2>
        <ProgressBar
          current={questionsAnsweredThisSession}
          total={sessionGoalTotal}
          labelRight
          height={10}
        />
        <button
          className="end-session btn btn-primary"
          onClick={() => setFinishMessage("Session ended.")}
        >
          End Session
        </button>
      </div>
      <div className="practice-card">{renderContent()}</div>
    </div>
  );
}
