import React, { useState, useMemo, useEffect } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';

export default function MicroStoryView({ story, primerCards, onDone }) {
  const [activeTooltip, setActiveTooltip] = useState(null);

  useEffect(() => {
    if (activeTooltip === null) return;
    const close = () => setActiveTooltip(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [activeTooltip]);

  const wordLookup = useMemo(() => {
    const map = {};
    for (const card of primerCards) {
      map[card.term_text.toLowerCase()] = card;
    }
    return map;
  }, [primerCards]);

  const parts = useMemo(() => {
    if (!story?.story_text) return [];
    const paragraphs = story.story_text.split(/\n\n+/);
    return paragraphs.map((para) => {
      const regex = /\*\*(.+?)\*\*/g;
      const segments = [];
      let lastIndex = 0;
      let match;
      while ((match = regex.exec(para)) !== null) {
        if (match.index > lastIndex) {
          segments.push({ type: 'text', content: para.slice(lastIndex, match.index) });
        }
        segments.push({ type: 'highlight', content: match[1] });
        lastIndex = regex.lastIndex;
      }
      if (lastIndex < para.length) {
        segments.push({ type: 'text', content: para.slice(lastIndex) });
      }
      return segments;
    });
  }, [story]);

  const handleHighlightClick = (e, index) => {
    e.stopPropagation();
    setActiveTooltip(activeTooltip === index ? null : index);
  };

  return (
    <div className="story-container">
      <div className="story-text">
        {parts.map((paragraph, pi) => (
          <p key={pi}>
            {paragraph.map((part, si) => {
              const id = `${pi}-${si}`;
              if (part.type === 'text') {
                return <span key={id}>{part.content}</span>;
              }
              const cardData = wordLookup[part.content.toLowerCase()];
              return (
                <span
                  key={id}
                  className="story-highlight"
                  onClick={(e) => handleHighlightClick(e, id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleHighlightClick(e, id)}
                >
                  {part.content}
                  {activeTooltip === id && cardData && (
                    <span className="story-tooltip" onClick={(e) => e.stopPropagation()}>
                      <div className="story-tooltip-word">
                        {cardData.term_text}
                        <TextToSpeechButton textToSpeak={cardData.term_text} />
                      </div>
                      <div className="story-tooltip-def">{cardData.kid_friendly_definition}</div>
                    </span>
                  )}
                </span>
              );
            })}
          </p>
        ))}
      </div>

      <button className="story-done-btn" onClick={onDone} type="button">
        I'm Done Reading
      </button>
    </div>
  );
}
