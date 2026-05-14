import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';
import apiClient from '../../api/axiosConfig.js';
import GenerationJobStatus from '../../components/generation/GenerationJobStatus.jsx';

export default function GenerationReview() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const [job, setJob] = useState(null);
  const [content, setContent] = useState(null);
  const [activeTab, setActiveTab] = useState('words');
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchJob = async () => {
      try {
        const res = await apiClient.get(`/generation-jobs/${jobId}/`);
        setJob(res.data);
        if (res.data.status === 'COMPLETED' || res.data.status === 'PARTIALLY_COMPLETED') {
          const contentRes = await apiClient.get(`/generation-jobs/${jobId}/content/`);
          setContent(contentRes.data);
        }
      } catch (err) { setError('Failed to load job.'); }
    };
    fetchJob();
  }, [jobId]);

  const handleJobComplete = useCallback(async (jobData) => {
    setJob(jobData);
    try { const res = await apiClient.get(`/generation-jobs/${jobData.id}/content/`); setContent(res.data); }
    catch (err) { setError('Failed to load generated content.'); }
  }, []);
  const handleJobFail = useCallback((jobData) => { setJob(jobData); }, []);

  if (user?.role !== 'ADMIN') return <p style={{ padding: '2rem' }}>Only admins can review generation jobs.</p>;
  if (error) return <p style={{ padding: '2rem', color: 'var(--t-danger)' }}>{error}</p>;
  if (!job) return <p style={{ padding: '2rem' }}>Loading...</p>;

  const isComplete = job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED';

  if (!isComplete || !content) {
    return (
      <div>
        <div className="t-page-header"><h1 className="t-page-title">Generation Job #{jobId}</h1></div>
        <GenerationJobStatus jobId={jobId} onComplete={handleJobComplete} onFail={handleJobFail} />
        {isComplete && !content && <p>Loading generated content...</p>}
        <button className="t-btn t-btn--secondary" onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)} style={{ marginTop: 12 }}>Back to Word Set</button>
      </div>
    );
  }

  const tabs = [
    { key: 'words', label: `Words (${content.words.length})` },
    { key: 'questions', label: `Questions (${content.questions.length})` },
    { key: 'packs', label: `Packs (${content.packs.length})` },
    { key: 'images', label: `Images (${content.images.length})` },
  ];

  return (
    <div>
      <div className="t-page-header"><h1 className="t-page-title">Review: {content.word_set_title}</h1></div>
      <div style={{ marginBottom: 16 }}>
        <GenerationJobStatus jobId={jobId} onComplete={handleJobComplete} onFail={handleJobFail} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div className="t-tabs" style={{ marginBottom: 0, borderBottom: 'none' }}>
          {tabs.map(t => (<button key={t.key} onClick={() => setActiveTab(t.key)} className={`t-tab${activeTab === t.key ? ' t-tab--active' : ''}`}>{t.label}</button>))}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)}>Back to Word Set</button>
        </div>
      </div>

      {activeTab === 'words' && (
        <table className="t-table">
          <thead><tr><th>Word</th><th>POS</th><th>Definition</th><th>Example</th></tr></thead>
          <tbody>{content.words.map(w => (
            <tr key={w.id}>
              <td style={{ fontWeight: 600 }}>{w.text}</td>
              <td className="t-muted">{w.part_of_speech}</td>
              <td style={{ fontSize: '0.9rem' }}>{w.definitions.map(d => d.definition_text).join('; ')}</td>
              <td className="t-hint" style={{ fontStyle: 'italic' }}>{w.definitions.map(d => d.example_sentence).filter(Boolean).join('; ')}</td>
            </tr>
          ))}</tbody>
        </table>
      )}

      {activeTab === 'questions' && (() => {
        const grouped = {};
        content.questions.forEach(q => { if (!grouped[q.word_text]) grouped[q.word_text] = []; grouped[q.word_text].push(q); });
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
      })()}

      {activeTab === 'packs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {content.packs.map(pack => (
            <div key={pack.id} className="t-card">
              <h4 style={{ margin: '0 0 6px' }}>{pack.label}</h4>
              <p className="t-hint" style={{ margin: '0 0 8px' }}>Words: {pack.words.map(w => w.text).join(', ')}</p>
              {pack.primer_cards.length > 0 && <div style={{ marginBottom: 6 }}><strong style={{ fontSize: '0.85rem' }}>Primer Cards:</strong>{pack.primer_cards.map(pc => (<div key={pc.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}><span style={{ fontWeight: 600 }}>{pc.word_text}</span> ({pc.syllable_text}) — {pc.kid_friendly_definition}</div>))}</div>}
              {pack.stories.length > 0 && <div style={{ marginBottom: 6 }}><strong style={{ fontSize: '0.85rem' }}>Story:</strong>{pack.stories.map(s => (<p key={s.id} style={{ fontSize: '0.85rem', margin: '3px 0', whiteSpace: 'pre-wrap' }}>{s.story_text} <span className="t-hint">(Lexile: {s.reading_level})</span></p>))}</div>}
              {pack.cloze_items.length > 0 && <div><strong style={{ fontSize: '0.85rem' }}>Cloze Items:</strong>{pack.cloze_items.map(ci => (<div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}>{ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong></div>))}</div>}
            </div>
          ))}
        </div>
      )}

      {activeTab === 'images' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
          {content.images.map(img => (
            <div key={img.id} style={{ border: `2px solid ${img.status === 'APPROVED' ? 'var(--t-success)' : img.status === 'PENDING_REVIEW' ? 'var(--t-warning)' : 'var(--t-danger)'}`, borderRadius: 'var(--t-radius)', padding: 8, textAlign: 'center' }}>
              <img src={img.image_url} alt={img.word_text} style={{ width: '100%', borderRadius: 4, marginBottom: 4 }} />
              <p style={{ fontSize: '0.85rem', fontWeight: 600, margin: '4px 0' }}>{img.word_text}</p>
              <p style={{ fontSize: '0.75rem', margin: 0, color: img.status === 'APPROVED' ? 'var(--t-success)' : img.status === 'PENDING_REVIEW' ? 'var(--t-warning)' : 'var(--t-danger)' }}>{img.status.replace('_', ' ')}</p>
            </div>
          ))}
          {content.images.length === 0 && <p className="t-hint">No images generated.</p>}
        </div>
      )}
    </div>
  );
}
