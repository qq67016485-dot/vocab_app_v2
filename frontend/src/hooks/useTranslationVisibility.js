import { useState } from 'react';

const TRANSLATION_DISPLAY_MS = 10000;

export function useTranslationVisibility() {
  const [visibleTranslationTerm, setVisibleTranslationTerm] = useState(null);

  const handleShowTranslation = (term) => {
    setVisibleTranslationTerm(term);
    setTimeout(() => setVisibleTranslationTerm(null), TRANSLATION_DISPLAY_MS);
  };

  return { visibleTranslationTerm, handleShowTranslation };
}
