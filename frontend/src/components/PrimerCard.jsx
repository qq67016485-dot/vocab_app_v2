import React, { useState, useEffect, useRef } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';
import correctSfx from '../assets/sounds/correct.mp3';

export default function PrimerCard({ card, index, total, onNext }) {
  const [gotIt, setGotIt] = useState(false);
  const [showDefTranslation, setShowDefTranslation] = useState(false);
  const [showExTranslation, setShowExTranslation] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    setGotIt(false);
    setShowDefTranslation(false);
    setShowExTranslation(false);

    if (card.audio_url) {
      try {
        const audio = new Audio(card.audio_url);
        audio.play().catch(() => {});
        audioRef.current = audio;
      } catch (e) { /* ignore */ }
    }
  }, [card, index]);

  const handleGotIt = () => {
    try {
      const audio = new Audio(correctSfx);
      audio.volume = 0.4;
      audio.play().catch(() => {});
    } catch (e) { /* ignore */ }
    setGotIt(true);
  };

  return (
    <div className="primer-card">
      <div className="primer-counter">{index + 1} of {total}</div>

      <div className="primer-word">{card.term_text}</div>
      <div className="primer-syllable">{card.syllable_text}</div>

      <TextToSpeechButton textToSpeak={card.term_text} />

      {card.image_url && (
        <img src={card.image_url} alt={card.term_text} className="primer-image" />
      )}

      <div className="primer-definition">
        {card.kid_friendly_definition}
      </div>

      {card.definition_translation && (
        showDefTranslation ? (
          <div className="primer-translation-text">{card.definition_translation}</div>
        ) : (
          <button
            className="primer-translation-btn"
            onClick={() => setShowDefTranslation(true)}
            type="button"
          >
            Show Translation
          </button>
        )
      )}

      <div className="primer-example">{card.example_sentence}</div>

      {card.example_translation && (
        showExTranslation ? (
          <div className="primer-translation-text">{card.example_translation}</div>
        ) : (
          <button
            className="primer-translation-btn"
            onClick={() => setShowExTranslation(true)}
            type="button"
          >
            Show Example Translation
          </button>
        )
      )}

      <div className="primer-actions">
        {!gotIt ? (
          <button className="primer-got-it" onClick={handleGotIt} type="button">
            I got it!
          </button>
        ) : (
          <button className="primer-next" onClick={onNext} type="button">
            {index < total - 1 ? 'Next Word' : 'Continue'}
          </button>
        )}
      </div>
    </div>
  );
}
