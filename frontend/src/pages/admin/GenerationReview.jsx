import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';
import apiClient from '../../api/axiosConfig.js';
import GenerationJobStatus from '../../components/generation/GenerationJobStatus.jsx';
import GraphicNovelPageEditor from '../../components/generation/GraphicNovelPageEditor.jsx';

const AUDIO_POLL_INTERVAL = 5000;

export default function GenerationReview() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const [job, setJob] = useState(null);
  const [content, setContent] = useState(null);
  const [activeTab, setActiveTab] = useState('words');
  const [error, setError] = useState('');
  // novelId → { busy, error, pages: [{page_number, status, audio_url, ...}] }
  const [audioState, setAudioState] = useState({});
  const audioPolls = useRef({});

  // Clean up all polls on unmount.
  useEffect(() => () => {
    Object.values(audioPolls.current).forEach(clearInterval);
  }, []);

  // Seed audioState from loaded content so existing per-page audio shows its
  // play button + the "Regen audio" label on first render (before any poll).
  const seedAudioFromContent = useCallback((contentData) => {
    const seed = {};
    (contentData?.packs || []).forEach(pack => {
      const novel = pack.graphic_novel;
      if (!novel) return;
      const pages = (novel.pages || [])
        .filter(p => !p.is_review_page)
        .map(p => ({
          page_id: p.id,
          page_number: p.page_number,
          status: p.audio_url ? 'COMPLETED' : 'PENDING',
          audio_url: p.audio_url || '',
        }));
      if (pages.some(p => p.audio_url)) {
        seed[novel.id] = { busy: false, error: '', pages };
      }
    });
    if (Object.keys(seed).length) {
      setAudioState(prev => ({ ...seed, ...prev }));
    }
  }, []);

  useEffect(() => {
    const fetchJob = async () => {
      try {
        const res = await apiClient.get(`/generation-jobs/${jobId}/`);
        setJob(res.data);
        if (res.data.status === 'COMPLETED' || res.data.status === 'PARTIALLY_COMPLETED') {
          const contentRes = await apiClient.get(`/generation-jobs/${jobId}/content/`);
          setContent(contentRes.data);
          seedAudioFromContent(contentRes.data);
        }
      } catch (err) { setError('Failed to load job.'); }
    };
    fetchJob();
  }, [jobId, seedAudioFromContent]);

  const handleJobComplete = useCallback(async (jobData) => {
    setJob(jobData);
    try {
      const res = await apiClient.get(`/generation-jobs/${jobData.id}/content/`);
      setContent(res.data);
      seedAudioFromContent(res.data);
    }
    catch (err) { setError('Failed to load generated content.'); }
  }, [seedAudioFromContent]);
  const handleJobFail = useCallback((jobData) => { setJob(jobData); }, []);

  const handlePageUpdated = useCallback((packId, updatedPage) => {
    setContent(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        packs: prev.packs.map(pack => {
          if (pack.id !== packId || !pack.graphic_novel) return pack;
          return {
            ...pack,
            graphic_novel: {
              ...pack.graphic_novel,
              pages: pack.graphic_novel.pages.map(p => p.id === updatedPage.id ? updatedPage : p),
            },
          };
        }),
      };
    });
  }, []);

  const stopAudioPoll = (novelId) => {
    if (audioPolls.current[novelId]) {
      clearInterval(audioPolls.current[novelId]);
      delete audioPolls.current[novelId];
    }
  };

  const startAudioPoll = useCallback((novelId) => {
    stopAudioPoll(novelId);
    audioPolls.current[novelId] = setInterval(async () => {
      try {
        const res = await apiClient.get(`/graphic-novels/${novelId}/audio-status/`);
        const pages = res.data.pages || [];
        const anyRunning = pages.some(p => p.status === 'RUNNING');
        setAudioState(prev => ({
          ...prev,
          [novelId]: { ...prev[novelId], pages, busy: anyRunning },
        }));
        if (!anyRunning) stopAudioPoll(novelId);
      } catch {
        stopAudioPoll(novelId);
        setAudioState(prev => ({
          ...prev,
          [novelId]: { ...prev[novelId], busy: false, error: 'Lost audio status. Refresh to check.' },
        }));
      }
    }, AUDIO_POLL_INTERVAL);
  }, []);

  const generateAudio = useCallback(async (novelId, regenerate = false) => {
    setAudioState(prev => ({ ...prev, [novelId]: { busy: true, error: '', pages: prev[novelId]?.pages || [] } }));
    try {
      await apiClient.post(`/graphic-novels/${novelId}/generate-audio/`, { regenerate });
      startAudioPoll(novelId);
    } catch (err) {
      setAudioState(prev => ({
        ...prev,
        [novelId]: { busy: false, error: err.response?.data?.error || 'Audio generation failed.', pages: prev[novelId]?.pages || [] },
      }));
    }
  }, [startAudioPoll]);

  // Regenerate audio for a single page (fills a gap left by a failed API call
  // without redoing every page). Marks just that page RUNNING, fires the
  // per-page endpoint, then reuses the novel-level poll to track completion.
  const regeneratePageAudio = useCallback(async (novelId, pageId, pageNumber) => {
    setAudioState(prev => {
      const cur = prev[novelId] || { pages: [] };
      const list = cur.pages || [];
      const found = list.some(p => p.page_id === pageId);
      const pages = found
        ? list.map(p => (p.page_id === pageId ? { ...p, status: 'RUNNING', error: '' } : p))
        : [...list, { page_id: pageId, page_number: pageNumber, status: 'RUNNING', audio_url: '', error: '' }];
      return { ...prev, [novelId]: { ...cur, busy: true, error: '', pages } };
    });
    try {
      await apiClient.post(`/graphic-novel-pages/${pageId}/regenerate-audio/`);
      startAudioPoll(novelId);
    } catch (err) {
      setAudioState(prev => ({
        ...prev,
        [novelId]: {
          ...prev[novelId],
          busy: false,
          error: err.response?.data?.error || 'Page audio regeneration failed.',
        },
      }));
    }
  }, [startAudioPoll]);

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
        <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => navigate(`/teacher/word-sets/${job.word_set_id}`)}>Back to Word Set</button>
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
              {pack.graphic_novel && (
                <div style={{ marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <strong style={{ fontSize: '0.85rem' }}>Graphic Novel:</strong>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{pack.graphic_novel.title}</span>
                    <span className="t-hint" style={{ fontSize: '0.78rem' }}>(Lexile: {pack.graphic_novel.reading_level}, Pages: {pack.graphic_novel.pages.length})</span>
                    <AudioControls
                      novelId={pack.graphic_novel.id}
                      audioState={audioState[pack.graphic_novel.id]}
                      onGenerate={generateAudio}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8, paddingLeft: 12, marginTop: 6 }}>
                    {pack.graphic_novel.pages.map(page => {
                      const audioPage = audioState[pack.graphic_novel.id]?.pages?.find(ap => ap.page_number === page.page_number);
                      return (
                        <GraphicNovelPageEditor
                          key={page.id}
                          page={page}
                          audioUrl={audioPage?.audio_url || page.audio_url || ''}
                          audioStatus={audioPage?.status}
                          audioError={audioPage?.error}
                          onRegenAudio={() => regeneratePageAudio(pack.graphic_novel.id, page.id, page.page_number)}
                          onUpdated={(updatedPage) => handlePageUpdated(pack.id, updatedPage)}
                        />
                      );
                    })}
                  </div>
                </div>
              )}
              {!pack.graphic_novel && pack.stories.length > 0 && <div style={{ marginBottom: 6 }}><strong style={{ fontSize: '0.85rem' }}>Legacy Micro Story:</strong>{pack.stories.map(s => (<p key={s.id} style={{ fontSize: '0.85rem', margin: '3px 0', whiteSpace: 'pre-wrap' }}>{s.story_text} <span className="t-hint">(Lexile: {s.reading_level})</span></p>))}</div>}
              {pack.cloze_items.length > 0 && <div><strong style={{ fontSize: '0.85rem' }}>Cloze Items:</strong>{pack.cloze_items.map(ci => (<div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}>{ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong></div>))}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Generate / regenerate audio button + running indicator for one novel. */
function AudioControls({ novelId, audioState, onGenerate }) {
  const busy = audioState?.busy;
  const hasAny = audioState?.pages?.some(p => p.audio_url);
  const err = audioState?.error;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <button
        className="t-btn t-btn--secondary"
        style={{ fontSize: '0.72rem', padding: '1px 8px' }}
        disabled={busy}
        onClick={() => onGenerate(novelId, hasAny)}
        title={hasAny ? 'Regenerate read-along audio for all pages' : 'Generate read-along audio for all pages'}
      >
        {busy ? '⏳ Generating audio…' : hasAny ? '↺ Regen audio' : '🔊 Generate audio'}
      </button>
      {err && <span style={{ fontSize: '0.72rem', color: 'var(--t-danger)' }}>{err}</span>}
    </span>
  );
}
