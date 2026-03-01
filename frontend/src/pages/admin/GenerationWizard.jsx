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
  const [isAddWordsMode, setIsAddWordsMode] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [activeTab, setActiveTab] = useState('words');
  const [isApproving, setIsApproving] = useState(false);
  const [approveMessage, setApproveMessage] = useState('');

  const [formData, setFormData] = useState({
    words: '',
    source_title: '',
    source_chapter: '',
    source_text: '',
    target_language: 'zh-CN',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchWordSet = async () => {
      try {
        const res = await apiClient.get(`/word-sets/${setId}/`);
        setWordSet(res.data);
        const alreadyGenerated = res.data.generation_status === 'GENERATED';
        setIsAddWordsMode(alreadyGenerated);
        const prefilledWords = alreadyGenerated
          ? ''
          : Array.isArray(res.data.input_words)
            ? res.data.input_words.join('\n')
            : '';
        setFormData(prev => ({
          ...prev,
          words: prefilledWords,
          source_title: res.data.input_source_title || res.data.title || '',
          source_chapter: res.data.input_source_chapter || res.data.unit_or_chapter || '',
          source_text: res.data.source_text || '',
        }));

        // If already generated, check for a completed job to resume review
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
          } catch {
            // No job found or fetch failed — stay on input step
          }
        }
      } catch (err) {
        setError('Could not load word set.');
      }
    };
    fetchWordSet();
  }, [setId]);

  if (user?.role !== 'ADMIN') {
    return <p style={{ padding: '2rem' }}>Only admins can access the generation wizard.</p>;
  }

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleStartGeneration = async () => {
    const wordList = formData.words
      .split(/[\n,]+/)
      .map(w => w.trim())
      .filter(Boolean);

    if (wordList.length === 0) {
      setError('Please enter at least one word.');
      return;
    }

    setIsSubmitting(true);
    setError('');
    try {
      const endpoint = isAddWordsMode
        ? `/word-sets/${setId}/add-words/`
        : `/word-sets/${setId}/generate/`;
      const res = await apiClient.post(endpoint, {
        words: wordList,
        source_title: formData.source_title,
        source_chapter: formData.source_chapter,
        source_text: formData.source_text,
        target_lexile: wordSet?.target_lexile || 650,
        target_language: formData.target_language,
      });
      setJobId(res.data.job_id);
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to start generation.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleJobComplete = useCallback(async (jobData) => {
    try {
      const res = await apiClient.get(`/generation-jobs/${jobData.id}/content/`);
      setReviewData(res.data);
      setStep(3);
    } catch (err) {
      console.error('Error fetching content for review:', err);
      setError('Failed to load generated content for review.');
      setStep(3);
    }
  }, []);

  const handleJobFail = useCallback(() => {
    // Stay on step 2 — GenerationJobStatus shows the error
  }, []);

  const handleApproveAll = async () => {
    setIsApproving(true);
    setApproveMessage('');
    try {
      const res = await apiClient.post(`/generation-jobs/${jobId}/approve/`);
      setApproveMessage(`Approved. ${res.data.images_approved} image(s) approved.`);
    } catch (err) {
      setApproveMessage(err.response?.data?.error || 'Approval failed.');
    } finally {
      setIsApproving(false);
    }
  };

  const renderStepIndicator = () => (
    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
      {['Input', 'Processing', 'Review'].map((label, i) => (
        <div key={label} style={{
          padding: '0.5rem 1rem', borderRadius: '20px', fontSize: '0.85rem', fontWeight: 600,
          background: step === i + 1 ? '#7c3aed' : step > i + 1 ? '#16a34a' : '#e5e7eb',
          color: step >= i + 1 ? '#fff' : '#6b7280',
        }}>
          {i + 1}. {label}
        </div>
      ))}
    </div>
  );

  const renderInputStep = () => (
    <div>
      {isAddWordsMode && (
        <div style={{
          padding: '0.75rem 1rem', marginBottom: '1rem',
          background: '#eff6ff', borderRadius: '8px', fontSize: '0.9rem', color: '#1e40af',
        }}>
          This word set already has generated content. Enter only the new words you want to add.
          {wordSet?.input_words?.length > 0 && (
            <div style={{ marginTop: '0.5rem', color: '#6b7280', fontSize: '0.85rem' }}>
              Existing words: {wordSet.input_words.join(', ')}
            </div>
          )}
        </div>
      )}
      <div className="form-group">
        <label>{isAddWordsMode ? 'New Words to Add' : 'Word List'} (one per line or comma-separated)</label>
        <textarea name="words" value={formData.words} onChange={handleChange}
          rows="8" placeholder={isAddWordsMode ? 'Enter new words only...' : 'abundant\nbenevolent\ncascade\ndiligent'}
          style={{ fontFamily: 'monospace' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <div className="form-group">
          <label>Source Title</label>
          <input name="source_title" value={formData.source_title} onChange={handleChange} />
        </div>
        <div className="form-group">
          <label>Source Chapter</label>
          <input name="source_chapter" value={formData.source_chapter} onChange={handleChange} />
        </div>
        <div className="form-group">
          <label>Target Lexile (from word set)</label>
          <input type="number" value={wordSet?.target_lexile || 650} disabled
            style={{ background: '#f3f4f6', cursor: 'not-allowed' }} />
        </div>
        <div className="form-group">
          <label>Target Language</label>
          <select name="target_language" value={formData.target_language} onChange={handleChange}>
            {SUPPORTED_LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
      </div>
      <div className="form-group">
        <label>Source Text / Passage (optional)</label>
        <textarea name="source_text" value={formData.source_text} onChange={handleChange} rows="4"
          placeholder="Paste a passage for additional context..." />
      </div>
      {error && <p style={{ color: '#dc2626', marginBottom: '1rem' }}>{error}</p>}
      <button onClick={handleStartGeneration} disabled={isSubmitting}
        style={{ background: '#7c3aed', color: '#fff', padding: '0.75rem 2rem' }}>
        {isSubmitting ? 'Starting...' : isAddWordsMode ? 'Add Words & Generate' : 'Start Generation'}
      </button>
    </div>
  );

  const renderProcessingStep = () => (
    <div>
      <h3>Pipeline Running...</h3>
      <GenerationJobStatus jobId={jobId} onComplete={handleJobComplete} onFail={handleJobFail} />
      <button onClick={() => navigate(`/teacher/word-sets/${setId}`)}
        className="secondary-button" style={{ marginTop: '1rem' }}>
        Back to Word Set
      </button>
    </div>
  );

  const renderReviewStep = () => {
    if (!reviewData) {
      return <p>{error || 'Loading review data...'}</p>;
    }

    const tabs = [
      { key: 'words', label: `Words (${reviewData.words.length})` },
      { key: 'questions', label: `Questions (${reviewData.questions.length})` },
      { key: 'packs', label: `Packs (${reviewData.packs.length})` },
      { key: 'images', label: `Images (${reviewData.images.length})`, hidden: true },
    ];

    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {tabs.filter(t => !t.hidden).map(t => (
              <button key={t.key} onClick={() => setActiveTab(t.key)}
                className={activeTab === t.key ? '' : 'secondary-button'}
                style={activeTab === t.key ? { background: '#7c3aed', color: '#fff' } : {}}>
                {t.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {approveMessage && (
              <span style={{ fontSize: '0.85rem', color: approveMessage.startsWith('Approved') ? '#16a34a' : '#dc2626' }}>
                {approveMessage}
              </span>
            )}
            <button onClick={handleApproveAll} disabled={isApproving}
              style={{ background: '#16a34a', color: '#fff' }}>
              {isApproving ? 'Approving...' : 'Approve All'}
            </button>
            <button onClick={() => navigate(`/teacher/word-sets/${setId}`)} className="secondary-button">
              Back to Word Set
            </button>
            <button onClick={() => { setStep(1); setReviewData(null); setIsAddWordsMode(true); }} className="secondary-button">
              Add More Words
            </button>
          </div>
        </div>

        {activeTab === 'words' && renderWordsTab()}
        {activeTab === 'questions' && renderQuestionsTab()}
        {activeTab === 'packs' && renderPacksTab()}
        {activeTab === 'images' && renderImagesTab()}
      </div>
    );
  };

  const renderWordsTab = () => (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
          <th style={{ padding: '0.5rem' }}>Word</th>
          <th style={{ padding: '0.5rem' }}>POS</th>
          <th style={{ padding: '0.5rem' }}>Definition</th>
          <th style={{ padding: '0.5rem' }}>Example</th>
        </tr>
      </thead>
      <tbody>
        {reviewData.words.map(w => (
          <tr key={w.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
            <td style={{ padding: '0.5rem', fontWeight: 600 }}>{w.text}</td>
            <td style={{ padding: '0.5rem', color: '#6b7280' }}>{w.part_of_speech}</td>
            <td style={{ padding: '0.5rem', fontSize: '0.9rem' }}>
              {w.definitions.map(d => d.definition_text).join('; ')}
            </td>
            <td style={{ padding: '0.5rem', fontSize: '0.85rem', fontStyle: 'italic', color: '#6b7280' }}>
              {w.definitions.map(d => d.example_sentence).filter(Boolean).join('; ')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderQuestionsTab = () => {
    const grouped = {};
    reviewData.questions.forEach(q => {
      if (!grouped[q.word_text]) grouped[q.word_text] = [];
      grouped[q.word_text].push(q);
    });

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {Object.entries(grouped).map(([word, questions]) => (
          <div key={word} style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1rem' }}>
            <h4 style={{ margin: '0 0 0.5rem', color: '#7c3aed' }}>{word}</h4>
            {questions.map(q => (
              <div key={q.id} style={{ marginBottom: '0.75rem', paddingLeft: '1rem', borderLeft: '3px solid #e5e7eb' }}>
                <p style={{ fontSize: '0.8rem', color: '#6b7280', margin: '0 0 0.25rem' }}>{q.question_type}</p>
                <p style={{ margin: '0 0 0.25rem' }}>{q.question_text}</p>
                {q.options && (
                  <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem', fontSize: '0.9rem' }}>
                    {q.options.map((opt, i) => (
                      <li key={i} style={{
                        color: q.correct_answers?.includes(opt) ? '#16a34a' : 'inherit',
                        fontWeight: q.correct_answers?.includes(opt) ? 600 : 400,
                      }}>{opt}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  };

  const renderPacksTab = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {reviewData.packs.map(pack => (
        <div key={pack.id} style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1rem' }}>
          <h4 style={{ margin: '0 0 0.5rem' }}>{pack.label}</h4>
          <p style={{ fontSize: '0.85rem', color: '#6b7280', margin: '0 0 0.5rem' }}>
            Words: {pack.words.map(w => w.text).join(', ')}
          </p>

          {pack.primer_cards.length > 0 && (
            <div style={{ marginBottom: '0.5rem' }}>
              <strong style={{ fontSize: '0.85rem' }}>Primer Cards:</strong>
              {pack.primer_cards.map(pc => (
                <div key={pc.id} style={{ paddingLeft: '1rem', fontSize: '0.85rem', margin: '0.25rem 0' }}>
                  <span style={{ fontWeight: 600 }}>{pc.word_text}</span> ({pc.syllable_text}) — {pc.kid_friendly_definition}
                </div>
              ))}
            </div>
          )}

          {pack.stories.length > 0 && (
            <div style={{ marginBottom: '0.5rem' }}>
              <strong style={{ fontSize: '0.85rem' }}>Story:</strong>
              {pack.stories.map(s => (
                <p key={s.id} style={{ fontSize: '0.85rem', margin: '0.25rem 0', whiteSpace: 'pre-wrap' }}>
                  {s.story_text} <span style={{ color: '#6b7280' }}>(Lexile: {s.reading_level})</span>
                </p>
              ))}
            </div>
          )}

          {pack.cloze_items.length > 0 && (
            <div>
              <strong style={{ fontSize: '0.85rem' }}>Cloze Items:</strong>
              {pack.cloze_items.map(ci => (
                <div key={ci.id} style={{ paddingLeft: '1rem', fontSize: '0.85rem', margin: '0.25rem 0' }}>
                  {ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const renderImagesTab = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem' }}>
      {reviewData.images.map(img => (
        <div key={img.id} style={{
          border: `2px solid ${img.status === 'APPROVED' ? '#16a34a' : img.status === 'PENDING_REVIEW' ? '#d97706' : '#dc2626'}`,
          borderRadius: '8px', padding: '0.5rem', textAlign: 'center',
        }}>
          <img src={img.image_url} alt={img.word_text}
            style={{ width: '100%', borderRadius: '4px', marginBottom: '0.25rem' }} />
          <p style={{ fontSize: '0.85rem', fontWeight: 600, margin: '0.25rem 0' }}>{img.word_text}</p>
          <p style={{
            fontSize: '0.75rem', margin: 0,
            color: img.status === 'APPROVED' ? '#16a34a' : img.status === 'PENDING_REVIEW' ? '#d97706' : '#dc2626',
          }}>
            {img.status.replace('_', ' ')}
          </p>
        </div>
      ))}
      {reviewData.images.length === 0 && <p style={{ color: '#6b7280' }}>No images generated.</p>}
    </div>
  );

  return (
    <div style={{ padding: '1rem' }}>
      <h2>{isAddWordsMode ? 'Add Words to' : 'Generate Content for'} "{wordSet?.title || '...'}"</h2>
      {renderStepIndicator()}
      {step === 1 && renderInputStep()}
      {step === 2 && renderProcessingStep()}
      {step === 3 && renderReviewStep()}
    </div>
  );
}




