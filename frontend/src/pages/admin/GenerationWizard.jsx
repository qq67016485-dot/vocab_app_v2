import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';
import apiClient from '../../api/axiosConfig.js';
import GenerationJobStatus from '../../components/generation/GenerationJobStatus.jsx';

const SUPPORTED_LANGUAGES = [
  { code: 'zh-CN', label: 'Chinese (Simplified)' },
  { code: 'zh-TW', label: 'Chinese (Traditional)' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'es', label: 'Spanish' },
  { code: 'vi', label: 'Vietnamese' },
  { code: 'th', label: 'Thai' },
  { code: 'ar', label: 'Arabic' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'fr', label: 'French' },
];

export default function GenerationWizard() {
  const { setId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const [step, setStep] = useState(1);
  const [wordSet, setWordSet] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [activeTab, setActiveTab] = useState('words');
  const [formData, setFormData] = useState({ words: '', source_title: '', source_chapter: '', source_text: '', target_language: 'zh-CN' });
  const [contentTypes, setContentTypes] = useState(['graphic_novel']);

  const toggleContentType = (type) => {
    setContentTypes(prev => (
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    ));
  };
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchWordSet = async () => {
      try {
        const res = await apiClient.get(`/word-sets/${setId}/`);
        setWordSet(res.data);
        const alreadyGenerated = res.data.generation_status === 'GENERATED';
        const prefilledWords = alreadyGenerated ? '' : Array.isArray(res.data.input_words) ? res.data.input_words.join('\n') : '';
        setFormData(prev => ({ ...prev, words: prefilledWords, source_title: res.data.input_source_title || res.data.title || '', source_chapter: res.data.input_source_chapter || '', source_text: res.data.source_text || '' }));
        if (alreadyGenerated) {
          try {
            const jobRes = await apiClient.get(`/word-sets/${setId}/latest-job/`);
            const latestJob = jobRes.data;
            if (latestJob.status === 'COMPLETED' || latestJob.status === 'PARTIALLY_COMPLETED') {
              setJobId(latestJob.id);
              const contentRes = await apiClient.get(`/word-sets/${setId}/content/`);
              setReviewData(contentRes.data);
              setStep(3);
            }
          } catch { /* no job */ }
        }
      } catch { setError('Could not load word set.'); }
    };
    fetchWordSet();
  }, [setId]);

  const handleChange = (e) => { const { name, value } = e.target; setFormData(prev => ({ ...prev, [name]: value })); };

  const handleStartGeneration = async () => {
    const wordList = formData.words.split(/[\n,]+/).map(w => w.trim()).filter(Boolean);
    if (wordList.length === 0) { setError('Please enter at least one word.'); return; }
    if (contentTypes.length === 0) { setError('Select at least one content type to generate.'); return; }
    setIsSubmitting(true); setError('');
    try {
      const res = await apiClient.post(`/word-sets/${setId}/generate/`, { words: wordList, source_title: formData.source_title, source_chapter: formData.source_chapter, source_text: formData.source_text, target_lexile: wordSet?.target_lexile || 650, target_language: formData.target_language, content_types: contentTypes });
      setJobId(res.data.job_id); setStep(2);
    } catch (err) { setError(err.response?.data?.error || 'Failed to start generation.'); }
    finally { setIsSubmitting(false); }
  };

  const handleJobComplete = useCallback(async (jobData) => {
    try { const res = await apiClient.get(`/generation-jobs/${jobData.id}/content/`); setReviewData(res.data); setStep(3); }
    catch (err) { console.error('Error fetching content for review:', err); setError('Failed to load generated content for review.'); setStep(3); }
  }, []);
  const handleJobFail = useCallback(() => {}, []);

  if (user?.role !== 'ADMIN') return <p style={{ padding: '2rem' }}>Only admins can access the generation wizard.</p>;

  const renderStepIndicator = () => (
    <div className="gen-steps">
      {['Input', 'Processing', 'Review'].map((label, i) => (
        <span key={label} className={`gen-step ${step === i + 1 ? 'gen-step--active' : step > i + 1 ? 'gen-step--done' : 'gen-step--pending'}`}>
          {i + 1}. {label}
        </span>
      ))}
    </div>
  );

  const renderInputStep = () => (
    <div>
      <div className="t-form-group">
        <label className="t-form-label">Word List (one per line or comma-separated)</label>
        <textarea className="t-form-textarea" name="words" value={formData.words} onChange={handleChange} rows="8" placeholder={'abundant\nbenevolent\ncascade'} style={{ fontFamily: 'var(--t-font-mono)' }} />
      </div>
      <div className="t-form-row">
        <div className="t-form-group"><label className="t-form-label">Source Title</label><input className="t-form-input" name="source_title" value={formData.source_title} onChange={handleChange} /></div>
        <div className="t-form-group"><label className="t-form-label">Source Chapter</label><input className="t-form-input" name="source_chapter" value={formData.source_chapter} onChange={handleChange} /></div>
        <div className="t-form-group"><label className="t-form-label">Target Lexile</label><input className="t-form-input" type="number" value={wordSet?.target_lexile || 650} disabled style={{ background: '#f3f4f6', cursor: 'not-allowed' }} /></div>
        <div className="t-form-group"><label className="t-form-label">Target Language</label>
          <select className="t-form-select" name="target_language" value={formData.target_language} onChange={handleChange}>
            {SUPPORTED_LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
      </div>
      <div className="t-form-group"><label className="t-form-label">Source Text / Passage (optional)</label><textarea className="t-form-textarea" name="source_text" value={formData.source_text} onChange={handleChange} rows="4" placeholder="Paste a passage for additional context..." /></div>
      <div className="t-form-group">
        <label className="t-form-label">Content types to generate</label>
        <div style={{ display: 'flex', gap: 20, marginTop: 4 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={contentTypes.includes('graphic_novel')}
              onChange={() => toggleContentType('graphic_novel')} />
            Graphic novel
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={contentTypes.includes('infographic')}
              onChange={() => toggleContentType('infographic')} />
            Infographic
          </label>
        </div>
        <p className="t-hint" style={{ marginTop: 4 }}>
          Each selected type generates 3 candidates per pack for you to review and publish.
        </p>
      </div>
      {error && <p style={{ color: 'var(--t-danger)', marginBottom: 12, fontSize: '0.85rem' }}>{error}</p>}
      <button className="t-btn t-btn--primary" onClick={handleStartGeneration} disabled={isSubmitting}>
        {isSubmitting ? 'Starting...' : 'Start Generation'}
      </button>
    </div>
  );
/* APPEND_WIZ_2 */

  const renderProcessingStep = () => (
    <div>
      <h3 style={{ marginBottom: 12 }}>Pipeline Running...</h3>
      <GenerationJobStatus jobId={jobId} onComplete={handleJobComplete} onFail={handleJobFail} />
      <button className="t-btn t-btn--secondary" onClick={() => navigate(`/teacher/word-sets/${setId}`)} style={{ marginTop: 12 }}>Back to Word Set</button>
    </div>
  );

  const renderReviewStep = () => {
    if (!reviewData) return <p>{error || 'Loading review data...'}</p>;
    const tabs = [
      { key: 'words', label: `Words (${reviewData.words.length})` },
      { key: 'questions', label: `Questions (${reviewData.questions.length})` },
      { key: 'packs', label: `Packs (${reviewData.packs.length})` },
    ];
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div className="t-tabs" style={{ marginBottom: 0, borderBottom: 'none' }}>
            {tabs.map(t => (<button key={t.key} onClick={() => setActiveTab(t.key)} className={`t-tab${activeTab === t.key ? ' t-tab--active' : ''}`}>{t.label}</button>))}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => navigate(`/teacher/word-sets/${setId}`)}>Back to Word Set</button>
          </div>
        </div>
        {activeTab === 'words' && renderWordsTab()}
        {activeTab === 'questions' && renderQuestionsTab()}
        {activeTab === 'packs' && renderPacksTab()}
      </div>
    );
  };

  const renderWordsTab = () => (
    <table className="t-table">
      <thead><tr><th>Word</th><th>POS</th><th>Definition</th><th>Example</th></tr></thead>
      <tbody>
        {reviewData.words.map(w => (
          <tr key={w.id}>
            <td style={{ fontWeight: 600 }}>{w.text}</td>
            <td className="t-muted">{w.part_of_speech}</td>
            <td style={{ fontSize: '0.9rem' }}>{w.definitions.map(d => d.definition_text).join('; ')}</td>
            <td className="t-hint" style={{ fontStyle: 'italic' }}>{w.definitions.map(d => d.example_sentence).filter(Boolean).join('; ')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderQuestionsTab = () => {
    const grouped = {};
    reviewData.questions.forEach(q => { if (!grouped[q.word_text]) grouped[q.word_text] = []; grouped[q.word_text].push(q); });
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {Object.entries(grouped).map(([word, questions]) => (
          <div key={word} className="t-card">
            <h4 style={{ margin: '0 0 8px', color: 'var(--t-primary)' }}>{word}</h4>
            {questions.map(q => (
              <div key={q.id} style={{ marginBottom: 10, paddingLeft: 12, borderLeft: '3px solid var(--t-border)' }}>
                <p className="t-hint" style={{ margin: '0 0 2px', fontSize: '0.78rem' }}>{q.question_type}</p>
                <p style={{ margin: '0 0 4px' }}>{q.question_text}</p>
                {q.options && <ul style={{ margin: '4px 0', paddingLeft: 20, fontSize: '0.9rem' }}>
                  {q.options.map((opt, i) => (<li key={i} style={{ color: q.correct_answers?.includes(opt) ? 'var(--t-success)' : 'inherit', fontWeight: q.correct_answers?.includes(opt) ? 600 : 400, background: 'none', border: 'none', padding: '2px 0' }}>{opt}</li>))}
                </ul>}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  };
/* APPEND_WIZ_3 */

  const renderPacksTab = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {reviewData.packs.map(pack => (
        <div key={pack.id} className="t-card">
          <h4 style={{ margin: '0 0 6px' }}>{pack.label}</h4>
          <p className="t-hint" style={{ margin: '0 0 8px' }}>Words: {pack.words.map(w => w.text).join(', ')}</p>
          {pack.primer_cards.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <strong style={{ fontSize: '0.85rem' }}>Primer Cards:</strong>
              {pack.primer_cards.map(pc => (<div key={pc.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}><span style={{ fontWeight: 600 }}>{pc.word_text}</span> ({pc.syllable_text}) — {pc.kid_friendly_definition}</div>))}
            </div>
          )}
          {!(pack.graphic_novels && pack.graphic_novels.length > 0) && pack.stories.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <strong style={{ fontSize: '0.85rem' }}>Legacy Micro Story:</strong>
              {pack.stories.map(s => (<p key={s.id} style={{ fontSize: '0.85rem', margin: '3px 0', whiteSpace: 'pre-wrap' }}>{s.story_text} <span className="t-hint">(Lexile: {s.reading_level})</span></p>))}
            </div>
          )}
          {pack.cloze_items.length > 0 && (
            <div>
              <strong style={{ fontSize: '0.85rem' }}>Cloze Items:</strong>
              {pack.cloze_items.map(ci => (<div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}>{ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong></div>))}
            </div>
          )}
        </div>
      ))}
    </div>
  );

  return (
    <div>
      <div className="t-page-header">
        <h1 className="t-page-title">Generate Content for "{wordSet?.title || '...'}"</h1>
      </div>
      {renderStepIndicator()}
      {step === 1 && renderInputStep()}
      {step === 2 && renderProcessingStep()}
      {step === 3 && renderReviewStep()}
    </div>
  );
}
