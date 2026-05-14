import React, { useEffect, useMemo, useRef, useState } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';

export default function GraphicNovelReader({ story, primerCards, onDone }) {
  const pages = story?.pages || [];
  const [pageIndex, setPageIndex] = useState(0);
  const [showVocab, setShowVocab] = useState(false);
  const touchStartX = useRef(null);

  const currentPage = pages[pageIndex] || null;
  const isFirst = pageIndex === 0;
  const isLast = pageIndex === pages.length - 1;

  const wordLookup = useMemo(() => {
    const map = {};
    for (const card of primerCards || []) {
      map[card.term_text.toLowerCase()] = card;
    }
    return map;
  }, [primerCards]);

  const pageWords = useMemo(() => {
    const words = currentPage?.vocab_words || [];
    return words
      .map((word) => wordLookup[word.toLowerCase()])
      .filter(Boolean);
  }, [currentPage, wordLookup]);

  const goPrevious = () => {
    setShowVocab(false);
    setPageIndex((idx) => Math.max(0, idx - 1));
  };

  const goNext = () => {
    setShowVocab(false);
    setPageIndex((idx) => Math.min(pages.length - 1, idx + 1));
  };

  useEffect(() => {
    if (pages.length === 0) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'ArrowLeft') {
        setShowVocab(false);
        setPageIndex((idx) => Math.max(0, idx - 1));
      }
      if (event.key === 'ArrowRight') {
        setShowVocab(false);
        setPageIndex((idx) => Math.min(pages.length - 1, idx + 1));
      }
      if (event.key === 'Escape') setShowVocab(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [pages.length]);

  const handleTouchStart = (event) => {
    touchStartX.current = event.touches[0].clientX;
  };

  const handleTouchEnd = (event) => {
    if (touchStartX.current === null) return;
    const delta = event.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(delta) < 48) return;
    if (delta > 0) goPrevious();
    else goNext();
  };

  if (!currentPage) {
    return (
      <div className="graphic-reader">
        <button className="graphic-reader-done" onClick={onDone} type="button">
          Continue
        </button>
      </div>
    );
  }

  return (
    <div className="graphic-reader">
      <div className="graphic-reader-title-row">
        <h3>{story.title}</h3>
        <div className="graphic-reader-count">
          {pageIndex + 1} / {pages.length}
        </div>
      </div>

      <div className="graphic-reader-stage">
        <button
          className="graphic-reader-nav graphic-reader-nav-left"
          onClick={goPrevious}
          disabled={isFirst}
          type="button"
          aria-label="Previous page"
          title="Previous page"
        >
          &lsaquo;
        </button>

        <button
          className="graphic-page-frame"
          onClick={() => setShowVocab((value) => !value)}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          type="button"
          aria-label="Open vocabulary"
        >
          {currentPage.image_url ? (
            <img
              className="graphic-page-image"
              src={currentPage.image_url}
              alt={`Page ${currentPage.page_number} of ${story.title}`}
            />
          ) : (
            <div className="graphic-page-missing">
              Page image pending
            </div>
          )}
        </button>

        <button
          className="graphic-reader-nav graphic-reader-nav-right"
          onClick={goNext}
          disabled={isLast}
          type="button"
          aria-label="Next page"
          title="Next page"
        >
          &rsaquo;
        </button>
      </div>

      {showVocab && pageWords.length > 0 && (
        <div className="graphic-vocab-panel">
          {pageWords.map((card) => (
            <div className="graphic-vocab-item" key={card.word_id}>
              <div className="graphic-vocab-word">
                {card.term_text}
                <TextToSpeechButton textToSpeak={card.term_text} />
              </div>
              <div className="graphic-vocab-def">{card.kid_friendly_definition}</div>
            </div>
          ))}
        </div>
      )}

      <div className="graphic-reader-footer">
        <div className="graphic-reader-dots" aria-label="Pages">
          {pages.map((page, idx) => (
            <button
              key={page.page_number}
              className={`graphic-reader-dot ${idx === pageIndex ? 'active' : ''}`}
              onClick={() => {
                setShowVocab(false);
                setPageIndex(idx);
              }}
              type="button"
              aria-label={`Page ${idx + 1}`}
            />
          ))}
        </div>

        {isLast && (
          <button className="graphic-reader-done" onClick={onDone} type="button">
            Done Reading
          </button>
        )}
      </div>
    </div>
  );
}
