import { useEffect, useRef, useState } from 'react';

const TRANSLATION_DISPLAY_MS = 10000;

export function useTranslationVisibility() {
  const [visibleTranslationTerm, setVisibleTranslationTerm] = useState(null);
  const timerRef = useRef(null);

  const handleShowTranslation = (term) => {
    // A new tap restarts the 10s window — clear the previous timeout so it
    // can't hide the new translation early.
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisibleTranslationTerm(term);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setVisibleTranslationTerm(null);
    }, TRANSLATION_DISPLAY_MS);
  };

  // Never leave a pending timeout behind on unmount.
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return { visibleTranslationTerm, handleShowTranslation };
}
