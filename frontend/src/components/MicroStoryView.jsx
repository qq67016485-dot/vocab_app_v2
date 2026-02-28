import React, { useState, useMemo } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';

export default function MicroStoryView({ story, primerCards, onDone }) {
  const [activeTooltip, setActiveTooltip] = useState(null);

  const wordLookup = useMemo(() => {
    const map = {};
    for (const card of primerCards) {
      map[card.term_text.toLowerCase()] = card;
    }
    return map;
  }, [primerCards]);

  const parts = useMemo(() => {
    if (!story?.story_text) return [];
    const regex = /\*\*(.+?)\*\*/g;
    const result = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(story.story_text)) !== null) {
      if (match.index > lastIndex) {
        result.push({ type: 'text', content: story.story_text.slice(lastIndex, match.index) });
      }
      result.push({ type: 'highlight', content: match[1] });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < story.story_text.length) {
      result.push({ type: 'text', content: story.story_text.slice(lastIndex) });
    }
    return result;
  }, [story]);

  const handleHighlightClick = (index) => {
    setActiveTooltip(activeTooltip === index ? null : index);
  };

  return (
    <div className="story-container">
      <div className="story-text">
        {parts.map((part, i) => {
          if (part.type === 'text') {
            return <span key={i}>{part.content}</span>;
          }
          const cardData = wordLookup[part.content.toLowerCase()];
          return (
            <span
              key={i}
              className="story-highlight"
              onClick={() => handleHighlightClick(i)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleHighlightClick(i)}
            >
              {part.content}
              {activeTooltip === i && cardData && (
                <span className="story-tooltip" onClick={(e) => e.stopPropagation()}>
                  <div className="story-tooltip-word">
                    {cardData.term_text}
                    <TextToSpeechButton textToSpeak={cardData.term_text} />
                  </div>
                  {cardData.image_url && (
                    <img src={cardData.image_url} alt={cardData.term_text} style={{ width: 60, borderRadius: 6, marginBottom: 4 }} />
                  )}
                  <div className="story-tooltip-def">{cardData.kid_friendly_definition}</div>
                </span>
              )}
            </span>
          );
        })}
      </div>

      <button className="story-done-btn" onClick={onDone} type="button">
        I'm Done Reading
      </button>
    </div>
  );
}
