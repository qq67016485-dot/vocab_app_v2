import React, { useMemo, useState } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';

/**
 * Student reader for the single-page infographic content type.
 *
 * Renders the poster image plus the short explanatory intro text and an
 * accessible list of the per-word entries (term, definition, example). Much
 * simpler than the graphic novel reader: no pagination, no audio.
 */
export default function InfographicReader({ story, primerCards, onDone }) {
  const [zoomed, setZoomed] = useState(false);
  const entries = story?.entries || [];

  // Prefer the structured entries; fall back to primer cards if the design
  // didn't carry per-word entries (defensive — older/partial content).
  const wordList = useMemo(() => {
    if (entries.length > 0) {
      return entries.map((e) => ({
        term: e.term,
        definition: e.kid_friendly_definition || '',
        example: e.example_sentence || '',
      }));
    }
    return (primerCards || []).map((c) => ({
      term: c.term_text,
      definition: c.kid_friendly_definition || '',
      example: c.example_sentence || '',
    }));
  }, [entries, primerCards]);

  return (
    <div className="infographic-reader">
      <div className="infographic-reader-header">
        <h3>{story?.title}</h3>
        {story?.intro_text && (
          <p className="infographic-reader-intro">{story.intro_text}</p>
        )}
      </div>

      {story?.image_url ? (
        <button
          type="button"
          className="infographic-reader-image-button"
          onClick={() => setZoomed(true)}
          aria-label="Zoom in on the infographic"
        >
          <img
            className="infographic-reader-image"
            src={story.image_url}
            alt={`Infographic: ${story.title}`}
          />
        </button>
      ) : (
        <p className="infographic-reader-noimage">The infographic image is being prepared.</p>
      )}

      {wordList.length > 0 && (
        <ul className="infographic-reader-words">
          {wordList.map((w) => (
            <li key={w.term} className="infographic-reader-word">
              <span className="infographic-reader-term">
                {w.term}
                <TextToSpeechButton textToSpeak={w.term} />
              </span>
              {w.definition && (
                <span className="infographic-reader-def"> — {w.definition}</span>
              )}
              {w.example && (
                <span className="infographic-reader-example">{w.example}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <button className="graphic-reader-done" onClick={onDone} type="button">
        Continue
      </button>

      {zoomed && story?.image_url && (
        <div
          className="infographic-reader-lightbox"
          onClick={() => setZoomed(false)}
          role="dialog"
          aria-modal="true"
        >
          <img src={story.image_url} alt={`Infographic: ${story.title}`} />
        </div>
      )}
    </div>
  );
}
