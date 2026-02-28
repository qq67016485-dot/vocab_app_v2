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
  const [isApproving, setIsApproving] = useState(false);
  const [approveMessage, setApproveMessage] = useState('');
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
      } catch (err) {
        setError('Failed to load job.');
      }
    };
    fetchJob();
  }, [jobId]);

  const handleJobComplete = useCallback(async (jobData) => {
    setJob(jobData);
    try {
      const res = await apiClient.get(`/generation-jobs/${jobData.id}/content/`);
      setContent(res.data);
    } catch (err) {
      setError('Failed to load generated content.');
    }
  }, []);

  const handleJobFail = useCallback((jobData) => {
    setJob(jobData);
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

  if (user?.role !== 'ADMIN') {
    return <p style={{ padding: '2rem' }}>Only admins can review generation jobs.</p>;
  }

  if (error) return <p style={{ padding: '2rem', color: '#dc2626' }}>{error}</p>;
  if (!job) return <p style={{ padding: '2rem' }}>Loading...</p>;

  const isRunning = job.status === 'RUNNING' || job.status === 'PENDING';
  const isComplete = job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED';

  if (isRunning) {
    return (
      <div style={{ padding: '1rem' }}>
        <h2>Generation Job #{jobId}</h2>
        <GenerationJobStatus jobId={jobId} onComplete={handleJobComplete} onFail={handleJobFail} />
        <button onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)}
          className="secondary-button" style={{ marginTop: '1rem' }}>
          Back to Word Set
        </button>
      </div>
    );
  }

  if (!isComplete || !content) {
    return (
      <div style={{ padding: '1rem' }}>
        <h2>Generation Job #{jobId}</h2>
        <p>Status: <strong>{job.status}</strong></p>
        {job.error_message && <p style={{ color: '#dc2626' }}>{job.error_message}</p>}
        <button onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)}
          className="secondary-button" style={{ marginTop: '1rem' }}>
          Back to Word Set
        </button>
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
    <div style={{ padding: '1rem' }}>
      <h2>Review: {content.word_set_title}</h2>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {tabs.map(t => (
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
          <button onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)} className="secondary-button">
            Back to Word Set
          </button>
        </div>
      </div>

      {activeTab === 'words' && (
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
            {content.words.map(w => (
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
      )}

      {activeTab === 'questions' && (() => {
        const grouped = {};
        content.questions.forEach(q => {
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
      })()}

      {activeTab === 'packs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {content.packs.map(pack => (
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
      )}

      {activeTab === 'images' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem' }}>
          {content.images.map(img => (
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
          {content.images.length === 0 && <p style={{ color: '#6b7280' }}>No images generated.</p>}
        </div>
      )}
    </div>
  );
}
