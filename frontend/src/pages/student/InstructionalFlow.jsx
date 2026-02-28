import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import PrimerCard from '../../components/PrimerCard.jsx';
import MicroStoryView from '../../components/MicroStoryView.jsx';
import ClozeQuiz from '../../components/ClozeQuiz.jsx';
import InstructionalSummary from '../../components/InstructionalSummary.jsx';

export default function InstructionalFlow() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const [packData, setPackData] = useState(null);
  const [step, setStep] = useState('primer');
  const [primerIndex, setPrimerIndex] = useState(0);
  const [quizResults, setQuizResults] = useState({ correct: 0, total: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const handleBack = () => navigate('/student/dashboard');

  useEffect(() => {
    const fetchPack = async () => {
      setIsLoading(true);
      try {
        const res = await apiClient.get(`/instructional/packs/${packId}/`);
        setPackData(res.data);
      } catch (err) {
        setError(err.response?.data?.error || 'Could not load pack data.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchPack();
  }, [packId]);

  const handlePrimerNext = () => {
    if (primerIndex < packData.primer_cards.length - 1) {
      setPrimerIndex(primerIndex + 1);
    } else if (packData.story) {
      setStep('story');
    } else if (packData.cloze_items.length > 0) {
      setStep('quiz');
    } else {
      handleComplete({ correct: 0, total: 0 });
    }
  };

  const handleStoryDone = () => {
    if (packData.cloze_items.length > 0) {
      setStep('quiz');
    } else {
      handleComplete({ correct: 0, total: 0 });
    }
  };

  const handleComplete = async (results) => {
    setQuizResults(results);
    setStep('summary');
    try {
      await apiClient.post(`/instructional/packs/${packId}/complete/`);
    } catch (err) {
      console.error('Could not mark pack complete:', err);
    }
  };

  if (isLoading) return <div className="instructional-shell"><p>Loading learning pack...</p></div>;
  if (error) return <div className="instructional-shell"><p style={{ color: 'red' }}>{error}</p><button onClick={handleBack}>Go Back</button></div>;
  if (!packData) return null;

  const stepLabel = step === 'primer' ? 'Learn' : step === 'story' ? 'Read' : step === 'quiz' ? 'Quiz' : 'Done';

  return (
    <div className="instructional-shell">
      <div className="instructional-header">
        <h2>{packData.label} &mdash; {stepLabel}</h2>
        <button onClick={handleBack} style={{ fontSize: '0.85rem' }}>Exit</button>
      </div>

      {step === 'primer' && (
        <PrimerCard
          card={packData.primer_cards[primerIndex]}
          index={primerIndex}
          total={packData.primer_cards.length}
          onNext={handlePrimerNext}
        />
      )}

      {step === 'story' && (
        <MicroStoryView
          story={packData.story}
          primerCards={packData.primer_cards}
          onDone={handleStoryDone}
        />
      )}

      {step === 'quiz' && (
        <ClozeQuiz
          items={packData.cloze_items}
          primerCards={packData.primer_cards}
          onComplete={handleComplete}
        />
      )}

      {step === 'summary' && (
        <InstructionalSummary
          results={quizResults}
          words={packData.primer_cards.map(c => c.term_text)}
          onBack={handleBack}
        />
      )}
    </div>
  );
}
