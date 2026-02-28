import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';

export default function WordSetDetailView() {
  const { setId } = useParams();
  const navigate = useNavigate();
  const [wordSet, setWordSet] = useState(null);
  const [allWords, setAllWords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [packs, setPacks] = useState([]);
  const [newPackLabel, setNewPackLabel] = useState('');
  const [expandedPackId, setExpandedPackId] = useState(null);

  const [generatingPackId, setGeneratingPackId] = useState(null);
  const [generateMessage, setGenerateMessage] = useState({});
  const [packImages, setPackImages] = useState({});
  const [reviewingImageId, setReviewingImageId] = useState(null);

  const fetchWordSet = async () => {
    const response = await apiClient.get(`/word-sets/${setId}/`);
    setWordSet(response.data);
  };

  const fetchPacks = async () => {
    try {
      const response = await apiClient.get(`/word-sets/${setId}/packs/`);
      setPacks(response.data);
    } catch (err) {
      console.error('Error fetching packs:', err);
    }
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
        setAllWords(allWordsRes.data);
        try {
          const packsRes = await apiClient.get(`/word-sets/${setId}/packs/`);
          setPacks(packsRes.data);
        } catch (e) { /* packs may not exist yet */ }
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

  const handleCreatePack = async () => {
    if (!newPackLabel.trim()) return;
    try {
      await apiClient.post(`/word-sets/${setId}/packs/`, { label: newPackLabel.trim(), word_ids: [] });
      setNewPackLabel('');
      await fetchPacks();
    } catch (err) { console.error('Error creating pack:', err); }
  };

  const handleDeletePack = async (packId) => {
    if (!window.confirm('Delete this pack?')) return;
    try {
      await apiClient.delete(`/word-sets/${setId}/packs/${packId}/`);
      await fetchPacks();
    } catch (err) { console.error('Error deleting pack:', err); }
  };

  const handleAddWordToPack = async (packId, wordId) => {
    const pack = packs.find(p => p.id === packId);
    if (!pack) return;
    if (pack.words.length >= 9) { alert('Max 9 words per pack.'); return; }
    const newWordIds = [...pack.words.map(w => w.id), wordId];
    try {
      await apiClient.patch(`/word-sets/${setId}/packs/${packId}/`, { word_ids: newWordIds });
      await fetchPacks();
    } catch (err) { console.error('Error adding word to pack:', err); }
  };

  const handleRemoveWordFromPack = async (packId, wordId) => {
    const pack = packs.find(p => p.id === packId);
    if (!pack) return;
    const newWordIds = pack.words.filter(w => w.id !== wordId).map(w => w.id);
    try {
      await apiClient.patch(`/word-sets/${setId}/packs/${packId}/`, { word_ids: newWordIds });
      await fetchPacks();
    } catch (err) { console.error('Error removing word from pack:', err); }
  };

  const handleGenerateContent = async (packId) => {
    setGeneratingPackId(packId);
    setGenerateMessage(prev => ({ ...prev, [packId]: null }));
    try {
      const res = await apiClient.post(`/word-sets/${setId}/packs/${packId}/generate/`);
      const s = res.data.summary;
      setGenerateMessage(prev => ({
        ...prev,
        [packId]: { type: 'success', text: `Generated ${s.primer_cards} primer cards, ${s.cloze_items} cloze items${s.story ? ', 1 story' : ''}${s.images ? `, ${s.images} images` : ''}.` },
      }));
      await fetchPackImages(packId);
    } catch (err) {
      const msg = err.response?.data?.error || 'Generation failed.';
      setGenerateMessage(prev => ({ ...prev, [packId]: { type: 'error', text: msg } }));
    } finally {
      setGeneratingPackId(null);
    }
  };

  const fetchPackImages = async (packId) => {
    try {
      const res = await apiClient.get(`/word-sets/${setId}/packs/${packId}/images/`);
      setPackImages(prev => ({ ...prev, [packId]: res.data }));
    } catch (err) { console.error('Error fetching images:', err); }
  };

  const handleApproveImage = async (packId, imageId) => {
    setReviewingImageId(imageId);
    try {
      await apiClient.post(`/word-sets/${setId}/packs/${packId}/images/${imageId}/approve/`);
      await fetchPackImages(packId);
    } catch (err) { console.error('Error approving image:', err); }
    finally { setReviewingImageId(null); }
  };

  const handleRejectImage = async (packId, imageId) => {
    setReviewingImageId(imageId);
    try {
      await apiClient.post(`/word-sets/${setId}/packs/${packId}/images/${imageId}/reject/`);
      await fetchPackImages(packId);
    } catch (err) { console.error('Error rejecting image:', err); }
    finally { setReviewingImageId(null); }
  };

  const availableWords = useMemo(() => {
    if (!wordSet) return [];
    const wordsInSetIds = new Set(wordSet.words.map(w => w.id));
    const lower = searchTerm.toLowerCase();
    return allWords.filter(word => {
      if (wordsInSetIds.has(word.id)) return false;
      if (!searchTerm) return true;
      return (
        word.text.toLowerCase().includes(lower) ||
        (word.part_of_speech && word.part_of_speech.toLowerCase().includes(lower)) ||
        word.definition.toLowerCase().includes(lower)
      );
    });
  }, [allWords, wordSet, searchTerm]);

  if (isLoading) return <p>Loading word set details...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (!wordSet) return <p>Word set not found.</p>;

  const wordsInPacks = new Set();
  packs.forEach(p => p.words.forEach(w => wordsInPacks.add(w.id)));
  const unpackedWords = wordSet.words.filter(w => !wordsInPacks.has(w.id));

  const WordInfo = ({ word }) => (
    <div className="word-info-container">
      <strong>{word.text}</strong>
      {word.part_of_speech && <span className="part-of-speech"> ({word.part_of_speech})</span>}
      <div className="word-definition">{word.definition}</div>
    </div>
  );

  return (
    <div>
      <button onClick={() => navigate('/teacher/word-sets')} style={{ float: 'right' }}>Back to All Sets</button>
      <h2>Manage Words in "{wordSet.title}"</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div className="practice-card">
          <h3>Words in This Set ({wordSet.words.length})</h3>
          <ul className="word-management-list">
            {wordSet.words.map(word => (
              <li key={word.id}>
                <WordInfo word={word} />
                <button onClick={() => handleRemoveWord(word)} className="small-button remove-button">Remove</button>
              </li>
            ))}
          </ul>
        </div>

        <div className="practice-card">
          <h3>Available Words ({availableWords.length})</h3>
          <input type="text" placeholder="Search by word, POS, or definition..."
            value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
          <ul className="word-management-list">
            {availableWords.map(word => (
              <li key={word.id}>
                <WordInfo word={word} />
                <button onClick={() => handleAddWord(word)} className="small-button add-button">Add</button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="pack-management">
        <h3>Learning Packs</h3>
        <p style={{ fontSize: '0.85rem', color: '#6b7280', marginBottom: '1rem' }}>
          Group words into packs of up to 9 for the instructional flow.
          {unpackedWords.length > 0 && (
            <span className="unassigned-indicator"> {unpackedWords.length} word(s) not in any pack.</span>
          )}
        </p>

        <div className="pack-form">
          <input type="text" placeholder="New pack label..." value={newPackLabel}
            onChange={(e) => setNewPackLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreatePack()} />
          <button onClick={handleCreatePack} className="small-button add-button" type="button">Create Pack</button>
        </div>

        {packs.map((pack) => (
          <div key={pack.id} className="pack-card">
            <div className="pack-card-header">
              <span className="pack-card-title">
                {pack.label} ({pack.word_count} word{pack.word_count !== 1 ? 's' : ''})
              </span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => handleGenerateContent(pack.id)}
                  disabled={generatingPackId === pack.id || pack.word_count === 0}
                  className="small-button" type="button"
                  style={{ background: '#7c3aed', color: '#fff', opacity: (generatingPackId === pack.id || pack.word_count === 0) ? 0.5 : 1 }}>
                  {generatingPackId === pack.id ? 'Generating...' : 'Generate Content'}
                </button>
                <button onClick={() => {
                  const newId = expandedPackId === pack.id ? null : pack.id;
                  setExpandedPackId(newId);
                  if (newId) fetchPackImages(pack.id);
                }} className="small-button" type="button">
                  {expandedPackId === pack.id ? 'Collapse' : 'Expand'}
                </button>
                <button onClick={() => handleDeletePack(pack.id)} className="small-button remove-button" type="button">Delete</button>
              </div>
            </div>

            {generateMessage[pack.id] && (
              <p style={{ fontSize: '0.85rem', margin: '0.5rem 0 0', color: generateMessage[pack.id].type === 'error' ? '#dc2626' : '#16a34a' }}>
                {generateMessage[pack.id].text}
              </p>
            )}

            <ul className="pack-word-list">
              {pack.words.map((w) => (
                <li key={w.id} className="pack-word-tag">
                  {w.term_text}
                  <button onClick={() => handleRemoveWordFromPack(pack.id, w.id)} title="Remove from pack" type="button">x</button>
                </li>
              ))}
            </ul>

            {expandedPackId === pack.id && (
              <>
                {pack.words.length < 9 && (
                  <div style={{ marginTop: '0.5rem', borderTop: '1px dashed #e1e1e1', paddingTop: '0.5rem' }}>
                    <p style={{ fontSize: '0.8rem', color: '#6b7280', margin: '0 0 0.5rem' }}>Add words from this set:</p>
                    <ul className="pack-word-list">
                      {wordSet.words
                        .filter(w => !pack.words.some(pw => pw.id === w.id))
                        .map((w) => (
                          <li key={w.id} className="pack-word-tag" style={{ cursor: 'pointer', background: '#f0fdf4' }}
                            onClick={() => handleAddWordToPack(pack.id, w.id)}>
                            + {w.text}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}

                {packImages[pack.id] && packImages[pack.id].length > 0 && (
                  <div style={{ marginTop: '1rem', borderTop: '1px solid #e5e7eb', paddingTop: '0.75rem' }}>
                    <p style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>Image Review</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem' }}>
                      {packImages[pack.id]
                        .filter(img => img.status !== 'REJECTED')
                        .map((img) => (
                        <div key={img.id} style={{
                          border: `2px solid ${img.status === 'APPROVED' ? '#16a34a' : img.status === 'PENDING_REVIEW' ? '#d97706' : '#e5e7eb'}`,
                          borderRadius: '8px', padding: '0.5rem', textAlign: 'center',
                        }}>
                          <img src={img.image_url} alt={img.term} style={{ width: '100%', borderRadius: '4px', marginBottom: '0.25rem' }} />
                          <p style={{ fontSize: '0.8rem', fontWeight: 500, margin: '0.25rem 0' }}>{img.term}</p>
                          <p style={{ fontSize: '0.7rem', color: img.status === 'APPROVED' ? '#16a34a' : '#d97706', margin: '0 0 0.25rem' }}>
                            {img.status === 'APPROVED' ? 'Approved' : 'Pending Review'}
                          </p>
                          {img.status === 'PENDING_REVIEW' && (
                            <div style={{ display: 'flex', gap: '0.25rem', justifyContent: 'center' }}>
                              <button onClick={() => handleApproveImage(pack.id, img.id)}
                                disabled={reviewingImageId === img.id}
                                className="small-button add-button" type="button" style={{ fontSize: '0.75rem' }}>
                                Approve
                              </button>
                              <button onClick={() => handleRejectImage(pack.id, img.id)}
                                disabled={reviewingImageId === img.id}
                                className="small-button remove-button" type="button" style={{ fontSize: '0.75rem' }}>
                                Reject
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
