import React, { useState, useEffect, useRef } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';
import correctSfx from '../assets/sounds/correct.mp3';

function highlightWord(sentence, word) {
  if (!sentence || !word) return sentence;
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`\\b(${escaped})\\b`, 'gi');
  const parts = sentence.split(regex);
  return parts.map((part, i) =>
    part.toLowerCase() === word.toLowerCase()
      ? <strong key={i} className="primer-highlight-word">{part}</strong>
      : part
  );
}

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

      <div className="primer-word">
        <div className="primer-syllable-headline">
          {card.syllable_text || card.term_text}
          <TextToSpeechButton textToSpeak={card.term_text} />
        </div>
        {card.syllable_text && (
          <div className="primer-term-sub">
            {card.term_text}
            {card.part_of_speech && (
              <span className="primer-pos">({card.part_of_speech})</span>
            )}
          </div>
        )}
        {!card.syllable_text && card.part_of_speech && (
          <span className="primer-pos">({card.part_of_speech})</span>
        )}
      </div>

      <div className="primer-definition-box">
        <p className="primer-definition">{card.kid_friendly_definition}</p>
        {card.definition_translation && (
          showDefTranslation ? (
            <p className="primer-translation-text">{card.definition_translation}</p>
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
      </div>

      {card.image_url && (
        <img src={card.image_url} alt={card.term_text} className="primer-image" />
      )}

      <p className="primer-example">
        {highlightWord(card.example_sentence, card.term_text)}
      </p>

      {card.example_translation && (
        showExTranslation ? (
          <p className="primer-ex-translation-text">{card.example_translation}</p>
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