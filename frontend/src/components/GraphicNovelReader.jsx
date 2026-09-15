import React, { useEffect, useMemo, useRef, useState } from 'react';
import TextToSpeechButton from './TextToSpeechButton.jsx';

export default function GraphicNovelReader({ story, primerCards, onDone }) {
  const pages = story?.pages || [];
  const [pageIndex, setPageIndex] = useState(0);
  const [showVocab, setShowVocab] = useState(true);
  // Per-word L1 translation reveals in the vocab panel (off by default).
  const [shownTranslations, setShownTranslations] = useState({});
  const [doneVisible, setDoneVisible] = useState(false);
  const touchStartX = useRef(null);
  // Set when a horizontal swipe is consumed; the synthesized click that
  // follows the gesture must not also toggle the vocab panel.
  const swipeConsumed = useRef(false);

  const currentPage = pages[pageIndex] || null;
  const isFirst = pageIndex === 0;
  const isLast = pageIndex === pages.length - 1;

  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [autoplay, setAutoplay] = useState(() => {
    if (typeof window === 'undefined') return true;
    return window.localStorage.getItem('gnReaderAutoplay') !== 'off';
  });
  const audioUrl = currentPage?.audio_url || '';
  const hasAnyAudio = useMemo(
    () => pages.some((page) => page?.audio_url),
    [pages],
  );

  // Keep the latest autoplay value readable inside the page-change effect
  // without making that effect re-run (so toggling never disrupts the
  // currently playing page — it only affects the next page turn).
  const autoplayRef = useRef(autoplay);
  autoplayRef.current = autoplay;

  const persistAutoplay = (next) => {
    setAutoplay(next);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('gnReaderAutoplay', next ? 'on' : 'off');
    }
  };

  // Reset playback whenever the page (and thus its audio source) changes,
  // then auto-start the new page's audio if autoplay is enabled.
  useEffect(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    setIsPlaying(false);

    let timer;
    if (audio && audioUrl && autoplayRef.current) {
      // Defer so the swapped <audio> src is loaded before play().
      timer = setTimeout(() => {
        audio.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
      }, 0);
    }
    // Pause the exact element this effect saw. The <audio> is keyed on
    // audioUrl, so a page turn swaps in a NEW element before the next run of
    // this effect — pausing only audioRef.current there would leave the old
    // detached element playing. The cleanup captures the old one instead.
    return () => {
      if (timer) clearTimeout(timer);
      audio?.pause();
    };
  }, [audioUrl]);

  const toggleAudio = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
    } else {
      audio.pause();
      setIsPlaying(false);
    }
  };

  useEffect(() => {
    if (!isLast) {
      setDoneVisible(false);
      return undefined;
    }
    const timer = setTimeout(() => setDoneVisible(true), 3000);
    return () => clearTimeout(timer);
  }, [isLast]);

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
    setPageIndex((idx) => Math.max(0, idx - 1));
  };

  const goNext = () => {
    setPageIndex((idx) => Math.min(pages.length - 1, idx + 1));
  };

  useEffect(() => {
    if (pages.length === 0) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'ArrowLeft') {
        setPageIndex((idx) => Math.max(0, idx - 1));
      }
      if (event.key === 'ArrowRight') {
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
    swipeConsumed.current = true;
    if (delta > 0) goPrevious();
    else goNext();
  };

  const handleFrameClick = () => {
    // Ignore the click synthesized at the end of a page-turn swipe.
    if (swipeConsumed.current) {
      swipeConsumed.current = false;
      return;
    }
    setShowVocab((value) => !value);
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
      <div className="graphic-reader-toolbar">
        <div className="graphic-reader-toolbar-left">
          <span className="graphic-reader-count">{pageIndex + 1} / {pages.length}</span>
          <h3>{story.title}</h3>
        </div>

        {hasAnyAudio && (
          <div className="graphic-reader-audio-controls">
            {audioUrl && (
              <button
                className={`graphic-reader-audio${isPlaying ? ' playing' : ''}`}
                onClick={toggleAudio}
                type="button"
                aria-label={isPlaying ? 'Pause read-along' : 'Play read-along'}
                title={isPlaying ? 'Pause read-along' : 'Play read-along'}
              >
                <span aria-hidden="true">{isPlaying ? '⏸' : '▶'}</span>
                <span className="graphic-reader-audio-label">
                  {isPlaying ? 'Pause' : 'Listen'}
                </span>
              </button>
            )}
            <label className="graphic-reader-autoplay" title="Automatically read each page aloud">
              <input
                type="checkbox"
                checked={autoplay}
                onChange={(event) => persistAutoplay(event.target.checked)}
              />
              <span className="graphic-reader-autoplay-track" aria-hidden="true">
                <span className="graphic-reader-autoplay-thumb" />
              </span>
              <span className="graphic-reader-autoplay-label">Auto-read</span>
            </label>
          </div>
        )}

        <div className="graphic-reader-dots" aria-label="Pages">
          {pages.map((page, idx) => (
            <button
              key={page.page_number}
              className={`graphic-reader-dot ${idx === pageIndex ? 'active' : ''}`}
              onClick={() => {
                setPageIndex(idx);
              }}
              type="button"
              aria-label={`Page ${idx + 1}`}
            />
          ))}
        </div>

        <div className="graphic-reader-toolbar-right">
          {isLast ? (
            <button
              className={`graphic-reader-done${doneVisible ? ' visible' : ''}`}
              onClick={onDone}
              type="button"
              disabled={!doneVisible}
            >
              Done Reading
            </button>
          ) : <span />}
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
          onClick={handleFrameClick}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          type="button"
          aria-label={showVocab ? 'Hide vocabulary' : 'Show vocabulary'}
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

      {audioUrl && (
        <audio
          key={audioUrl}
          ref={audioRef}
          src={audioUrl}
          onEnded={() => setIsPlaying(false)}
          onPause={() => setIsPlaying(false)}
          onPlay={() => setIsPlaying(true)}
          preload="none"
        />
      )}

      {showVocab && pageWords.length > 0 && (
        <div className="graphic-vocab-panel">
          {pageWords.map((card) => (
            <div className="graphic-vocab-item" key={card.word_id}>
              <div className="graphic-vocab-word">
                {card.term_text}
                <TextToSpeechButton textToSpeak={card.term_text} />
              </div>
              <div className="graphic-vocab-def">{card.kid_friendly_definition}</div>
              {card.definition_translation && (
                shownTranslations[card.word_id] ? (
                  <div className="graphic-vocab-def primer-translation-text">
                    {card.definition_translation}
                  </div>
                ) : (
                  <button
                    className="primer-translation-btn"
                    onClick={() =>
                      setShownTranslations((prev) => ({ ...prev, [card.word_id]: true }))
                    }
                    type="button"
                  >
                    Show Translation
                  </button>
                )
              )}
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
