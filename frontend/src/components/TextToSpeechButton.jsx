import React, { useEffect } from 'react';

const SpeakerIcon = () => <span role="img" aria-label="speak word">&#x1f50a;</span>;

function TextToSpeechButton({ textToSpeak }) {
  // Cut off any in-flight utterance when this button unmounts (e.g. navigating
  // away mid-speech) so the voice doesn't keep talking on the next page.
  useEffect(() => () => {
    if (typeof window.speechSynthesis !== 'undefined') {
      window.speechSynthesis.cancel();
    }
  }, []);

  const handleSpeak = (event) => {
    event.stopPropagation();

    if (!textToSpeak || typeof window.speechSynthesis === 'undefined') {
      console.warn('Speech Synthesis not supported or no text provided.');
      return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.lang = 'en-US';
    utterance.rate = 0.8;

    window.speechSynthesis.speak(utterance);
  };

  return (
    <button onClick={handleSpeak} className="tts-button" title={`Pronounce "${textToSpeak}"`}>
      <SpeakerIcon />
    </button>
  );
}

export default TextToSpeechButton;
