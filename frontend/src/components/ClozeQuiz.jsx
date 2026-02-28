import React, { useState, useMemo, useCallback } from 'react';
import correctSfx from '../assets/sounds/correct.mp3';
import incorrectSfx from '../assets/sounds/incorrect.mp3';

export default function ClozeQuiz({ items, primerCards, onComplete }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [failures, setFailures] = useState(0);
  const [showPrimer, setShowPrimer] = useState(false);
  const [stats, setStats] = useState({ correct: 0, total: items.length });

  const currentItem = items[currentIndex];

  const options = useMemo(() => {
    if (!currentItem) return [];
    const all = [currentItem.correct_answer, ...currentItem.distractors];
    for (let i = all.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [all[i], all[j]] = [all[j], all[i]];
    }
    return all;
  }, [currentItem]);

  const playSound = useCallback((isCorrect) => {
    try {
      const audio = new Audio(isCorrect ? correctSfx : incorrectSfx);
      audio.volume = 0.4;
      audio.play().catch(() => {});
    } catch (e) { /* ignore */ }
  }, []);

  const advance = useCallback(() => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setSelected(null);
      setResult(null);
      setFailures(0);
      setShowPrimer(false);
    } else {
      onComplete(stats);
    }
  }, [currentIndex, items.length, onComplete, stats]);

  const handleSelect = (option) => {
    if (result === 'correct') return;
    setSelected(option);

    if (option === currentItem.correct_answer) {
      setResult('correct');
      playSound(true);
      setStats(prev => ({ ...prev, correct: prev.correct + 1 }));
    } else {
      setResult('incorrect');
      playSound(false);
      const newFailures = failures + 1;
      setFailures(newFailures);

      if (newFailures >= 3) return;
      setShowPrimer(true);
    }
  };

  const handleTryAgain = () => {
    setSelected(null);
    setResult(null);
    setShowPrimer(false);
  };

  if (!currentItem) return null;

  const primerCard = primerCards.find(
    c => c.term_text.toLowerCase() === currentItem.correct_answer.toLowerCase()
  );

  return (
    <div className="cloze-card">
      <div className="instructional-progress">
        <span>{currentIndex + 1} of {items.length}</span>
        <div className="instructional-progress-bar">
          <div
            className="instructional-progress-fill"
            style={{ width: `${((currentIndex + 1) / items.length) * 100}%` }}
          />
        </div>
      </div>

      <div className="cloze-sentence" style={{ marginTop: '1.5rem' }}>
        {currentItem.sentence_text.split('_______').map((part, i, arr) => (
          <span key={i}>
            {part}
            {i < arr.length - 1 && (
              result === 'correct'
                ? <span className="cloze-blank filled">{currentItem.correct_answer}</span>
                : <span className="cloze-blank">&nbsp;</span>
            )}
          </span>
        ))}
      </div>

      <div className="cloze-options">
        {options.map((opt) => {
          let cls = 'cloze-option';
          if (selected === opt && result === 'correct') cls += ' correct';
          if (selected === opt && result === 'incorrect') cls += ' incorrect';
          return (
            <button
              key={opt}
              className={cls}
              onClick={() => handleSelect(opt)}
              disabled={result === 'correct'}
              type="button"
            >
              {opt}
            </button>
          );
        })}
      </div>

      {result === 'correct' && (
        <button className="cloze-next-btn" onClick={advance} type="button">
          {currentIndex < items.length - 1 ? 'Next' : 'See Results'}
        </button>
      )}

      {failures >= 3 && result === 'incorrect' && (
        <button className="cloze-next-btn" onClick={advance} type="button" style={{ background: '#6b7280' }}>
          Let's move on
        </button>
      )}

      {showPrimer && primerCard && failures < 3 && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={handleTryAgain}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} role="document">
            <h3 style={{ marginTop: 0 }}>{primerCard.term_text}</h3>
            <p>{primerCard.kid_friendly_definition}</p>
            <p style={{ fontStyle: 'italic', color: '#6b7280' }}>{primerCard.example_sentence}</p>
            <button onClick={handleTryAgain} type="button">Try Again</button>
          </div>
        </div>
      )}
    </div>
  );
}
