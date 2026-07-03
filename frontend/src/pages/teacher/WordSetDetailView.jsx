import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';
import apiClient from '../../api/axiosConfig.js';

function WordInfo({ word }) {
  return (
    <div style={{ flexGrow: 1, marginRight: 10 }}>
      <strong>{word.text}</strong>
      {word.part_of_speech && <span className="t-muted" style={{ fontStyle: 'italic', marginLeft: 5 }}>({word.part_of_speech})</span>}
      <div className="t-hint" style={{ marginTop: 2 }}>{word.definition}</div>
    </div>
  );
}

export default function WordSetDetailView() {
  const { setId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const [wordSet, setWordSet] = useState(null);
  const [allWords, setAllWords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [packs, setPacks] = useState([]);

  const [generateMessage] = useState({});
  const [latestJobId, setLatestJobId] = useState(null);
  const [latestJobStatus, setLatestJobStatus] = useState(null);
  const [requestToast, setRequestToast] = useState(null);
  const [newWordsText, setNewWordsText] = useState('');

  const fetchWordSet = async () => {
    const response = await apiClient.get(`/word-sets/${setId}/`);
    setWordSet(response.data);
  };

  useEffect(() => {
    const fetchAllData = async () => {
      setIsLoading(true);
      try {
        const [setRes, allWordsRes] = await Promise.all([
          apiClient.get(`/word-sets/${setId}/`),
          apiClient.get('/words/'),
        ]);
        setWordSet(setRes.data);
        setNewWordsText(
          Array.isArray(setRes.data.input_words) ? setRes.data.input_words.join('\n') : ''
        );
        setAllWords(allWordsRes.data);
        try {
          const packsRes = await apiClient.get(`/word-sets/${setId}/packs/`);
          setPacks(packsRes.data);
        } catch { /* packs may not exist yet */ }
        try {
          const jobRes = await apiClient.get(`/word-sets/${setId}/latest-job/`);
          setLatestJobId(jobRes.data.id);
          setLatestJobStatus(jobRes.data.status);
        } catch { /* no job yet */ }
      } catch (err) {
        console.error("Error fetching data:", err);
        setError("Could not load data for this word set.");
      } finally {
        setIsLoading(false);
      }
    };
    fetchAllData();
  }, [setId]);

  const handleAddWord = async (word) => {
    try {
      await apiClient.post(`/word-sets/${wordSet.id}/add_word/`, { word_id: word.id });
      await fetchWordSet();
    } catch (err) { console.error("Error adding word:", err); }
  };

  const handleRemoveWord = async (word) => {
    try {
      await apiClient.post(`/word-sets/${wordSet.id}/remove_word/`, { word_id: word.id });
      await fetchWordSet();
    } catch (err) { console.error("Error removing word:", err); }
  };

  const availableWords = useMemo(() => {
    if (!wordSet) return [];
    const wordsInSetIds = new Set(wordSet.words.map(w => w.id));
    const lower = searchTerm.toLowerCase();
    return allWords.filter(word => {
      if (wordsInSetIds.has(word.id)) return false;
      if (!searchTerm) return true;
      return word.text.toLowerCase().includes(lower) || (word.part_of_speech && word.part_of_speech.toLowerCase().includes(lower)) || word.definition.toLowerCase().includes(lower);
    });
  }, [allWords, wordSet, searchTerm]);

  if (isLoading) return <p>Loading word set details...</p>;
  if (error) return <p style={{ color: 'var(--t-danger)' }}>{error}</p>;
  if (!wordSet) return <p>Word set not found.</p>;

  const wordsInPacks = new Set();
  packs.forEach(p => p.words.forEach(w => wordsInPacks.add(w.id)));
  const unpackedWords = wordSet.words.filter(w => !wordsInPacks.has(w.id));
  const handleSaveInputWords = async () => {
    const wordList = newWordsText.split(/[\n,]+/).map(w => w.trim()).filter(Boolean);
    try {
      await apiClient.patch(`/word-sets/${setId}/`, { input_words: wordList.length > 0 ? wordList : null });
      await fetchWordSet();
      setRequestToast({ type: 'success', text: 'Word list saved.' });
      setTimeout(() => setRequestToast(null), 3000);
    } catch (err) {
      setRequestToast({ type: 'error', text: err.response?.data?.detail || 'Failed to save words.' });
      setTimeout(() => setRequestToast(null), 5000);
    }
  };

  const handleRequestGeneration = async () => {
    try {
      await apiClient.post(`/word-sets/${setId}/request-generation/`);
      setWordSet(prev => ({ ...prev, generation_status: 'GENERATION_REQUESTED' }));
      setRequestToast({ type: 'success', text: 'Generation requested! An admin will process it soon.' });
      setTimeout(() => setRequestToast(null), 5000);
    } catch (err) {
      setRequestToast({ type: 'error', text: err.response?.data?.error || 'Failed to request generation.' });
      setTimeout(() => setRequestToast(null), 5000);
    }
  };

  const canRequestGeneration =
    (wordSet.generation_status === 'DRAFT' || wordSet.generation_status === 'TO_GENERATE')
    && wordSet.input_words?.length > 0;

  const isLocked = wordSet.generation_status === 'GENERATING' || wordSet.generation_status === 'GENERATED';

  return (
    <div>
      {requestToast && <div className={`t-toast t-toast--${requestToast.type}`}>{requestToast.text}</div>}

      <div className="t-page-header">
        <h1 className="t-page-title">Manage Words in "{wordSet.title}"</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {canRequestGeneration && (
            <button className="t-btn t-btn--sm" style={{ background: 'var(--t-warning)', color: '#fff' }} onClick={handleRequestGeneration}>Request Generation</button>
          )}
          {wordSet.generation_status === 'GENERATION_REQUESTED' && (
            <span className="t-badge t-badge--requested" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>Generation Requested</span>
          )}
          {user?.role === 'ADMIN' && wordSet.generation_status !== 'GENERATED' && wordSet.generation_status !== 'GENERATING' && (
            <button className="t-btn t-btn--primary t-btn--sm" onClick={() => navigate(`/teacher/generate/${setId}`)}>Generate Full Pipeline</button>
          )}
          {latestJobId && (
            <button className={`t-btn t-btn--sm ${latestJobStatus === 'FAILED' ? 't-btn--danger' : 't-btn--secondary'}`}
              style={latestJobStatus === 'COMPLETED' ? { background: 'var(--t-success)', color: '#fff' } : {}}
              onClick={() => navigate(`/teacher/generation-jobs/${latestJobId}`)}>
              {latestJobStatus === 'FAILED' ? 'View Failed Job' : 'View Latest Job'}
            </button>
          )}
          <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => navigate('/teacher/word-sets')}>Back to All Sets</button>
        </div>
      </div>
      {isLocked ? (
        <div className="t-card" style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: '0.95rem', fontWeight: 600 }}>Words in This Set ({wordSet.words.length}) (Locked)</h3>
          <p className="t-hint" style={{ margin: '0 0 10px' }}>
            This word set has generated content. Words cannot be added or removed directly.
          </p>
          <ul className="word-management-list">
            {wordSet.words.map(word => (
              <li key={word.id}><WordInfo word={word} /></li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <div className="t-card" style={{ marginBottom: 16 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: '0.95rem', fontWeight: 600 }}>Input Words for Generation</h3>
            <p className="t-hint" style={{ margin: '0 0 10px' }}>Enter the words you want generated (one per line or comma-separated). Save, then click "Request Generation".</p>
            <textarea className="t-form-textarea" value={newWordsText} onChange={e => setNewWordsText(e.target.value)} rows="4" placeholder="campaign&#10;philosophy&#10;dedicate" />
            {newWordsText.trim() && (
              <div className="t-form-hint" style={{ margin: '4px 0 8px' }}>{newWordsText.split(/[\n,]+/).map(w => w.trim()).filter(Boolean).length} word(s)</div>
            )}
            <button className="t-btn t-btn--accent t-btn--sm" onClick={handleSaveInputWords} type="button">Save Word List</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div className="t-card">
              <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Words in This Set ({wordSet.words.length})</h3>
              <ul className="word-management-list">
                {wordSet.words.map(word => (
                  <li key={word.id}><WordInfo word={word} /><button className="t-btn t-btn--danger t-btn--sm" onClick={() => handleRemoveWord(word)}>Remove</button></li>
                ))}
              </ul>
            </div>
            <div className="t-card">
              <h3 style={{ margin: '0 0 10px', fontSize: '0.95rem', fontWeight: 600 }}>Available Words ({availableWords.length})</h3>
              <input className="t-form-input" type="text" placeholder="Search by word, POS, or definition..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} style={{ marginBottom: 8 }} />
              <ul className="word-management-list">
                {availableWords.map(word => (
                  <li key={word.id}><WordInfo word={word} /><button className="t-btn t-btn--accent t-btn--sm" onClick={() => handleAddWord(word)}>Add</button></li>
                ))}
              </ul>
            </div>
          </div>
        </>
      )}
      <div>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: 4 }}>Learning Packs</h3>
        <p className="t-hint" style={{ marginBottom: 12 }}>
          Group words into packs of up to 9 for the instructional flow.
          {unpackedWords.length > 0 && <span style={{ color: 'var(--t-warning)' }}> {unpackedWords.length} word(s) not in any pack.</span>}
        </p>

        {packs.map((pack) => (
          <div key={pack.id} className="t-card" style={{ marginBottom: 10 }}>
            <div className="t-pack-header">
              <span className="t-pack-title">{pack.label} ({pack.word_count} word{pack.word_count !== 1 ? 's' : ''})</span>
            </div>
            {generateMessage[pack.id] && (
              <p style={{ fontSize: '0.85rem', margin: '0.5rem 0 0', color: generateMessage[pack.id].type === 'error' ? 'var(--t-danger)' : 'var(--t-success)' }}>{generateMessage[pack.id].text}</p>
            )}
            <ul className="t-pack-words">
              {pack.words.map((w) => (<li key={w.id} className="t-pack-word-tag">{w.term_text}</li>))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
