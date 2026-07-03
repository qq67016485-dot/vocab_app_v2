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
      (pack.graphic_novels || []).forEach(novel => {
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
      } catch { setError('Failed to load job.'); }
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
    catch { setError('Failed to load generated content.'); }
  }, [seedAudioFromContent]);
  const handleJobFail = useCallback((jobData) => { setJob(jobData); }, []);

  const handlePageUpdated = useCallback((packId, updatedPage) => {
    setContent(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        packs: prev.packs.map(pack => {
          if (pack.id !== packId || !pack.graphic_novels) return pack;
          return {
            ...pack,
            graphic_novels: pack.graphic_novels.map(novel => ({
              ...novel,
              pages: novel.pages.map(p => p.id === updatedPage.id ? updatedPage : p),
            })),
          };
        }),
      };
    });
  }, []);

  const handleSelectCandidate = useCallback(async (packId, novelId) => {
    try {
      await apiClient.post(`/graphic-novels/${novelId}/select/`);
      setContent(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          packs: prev.packs.map(pack => {
            if (pack.id !== packId || !pack.graphic_novels) return pack;
            return {
              ...pack,
              graphic_novels: pack.graphic_novels.map(novel => ({
                ...novel,
                is_selected: novel.id === novelId,
              })),
            };
          }),
        };
      });
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to select candidate.');
    }
  }, []);

  const handleSelectInfographic = useCallback(async (packId, infographicId) => {
    try {
      await apiClient.post(`/infographics/${infographicId}/select/`);
      setContent(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          packs: prev.packs.map(pack => {
            if (pack.id !== packId || !pack.infographics) return pack;
            return {
              ...pack,
              infographics: pack.infographics.map(ig => ({
                ...ig,
                is_selected: ig.id === infographicId,
              })),
            };
          }),
        };
      });
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to select infographic.');
    }
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
                    {Array.isArray(q.options) && q.options.length > 0 && <ul style={{ margin: '4px 0', paddingLeft: 20, fontSize: '0.9rem' }}>
                      {q.options.map((opt, i) => (<li key={i} style={{ color: q.correct_answers?.includes(opt) ? 'var(--t-success)' : 'inherit', fontWeight: q.correct_answers?.includes(opt) ? 600 : 400, background: 'none', border: 'none', padding: '2px 0' }}>{opt}</li>))}
                    </ul>}
                    {q.options && !Array.isArray(q.options) && (
                      <dl style={{ margin: '4px 0', fontSize: '0.85rem' }}>
                        {q.options.sentence_starter && <><dt className="t-hint" style={{ fontSize: '0.75rem' }}>Sentence starter</dt><dd style={{ margin: '0 0 4px' }}>{q.options.sentence_starter}</dd></>}
                        {q.options.intended_sense && <><dt className="t-hint" style={{ fontSize: '0.75rem' }}>Intended sense</dt><dd style={{ margin: '0 0 4px' }}>{q.options.intended_sense}</dd></>}
                        {q.options.acceptable_use_notes && <><dt className="t-hint" style={{ fontSize: '0.75rem' }}>Acceptable use</dt><dd style={{ margin: '0 0 4px' }}>{q.options.acceptable_use_notes}</dd></>}
                      </dl>
                    )}
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
              {(pack.graphic_novels && pack.graphic_novels.length > 0) && (
                <PackGraphicNovels
                  pack={pack}
                  audioStateByNovel={audioState}
                  onGenerate={generateAudio}
                  onRegenAudio={regeneratePageAudio}
                  onSelect={handleSelectCandidate}
                  onPageUpdated={handlePageUpdated}
                />
              )}
              {!(pack.graphic_novels && pack.graphic_novels.length > 0) && pack.stories.length > 0 && <div style={{ marginBottom: 6 }}><strong style={{ fontSize: '0.85rem' }}>Legacy Micro Story:</strong>{pack.stories.map(s => (<p key={s.id} style={{ fontSize: '0.85rem', margin: '3px 0', whiteSpace: 'pre-wrap' }}>{s.story_text} <span className="t-hint">(Lexile: {s.reading_level})</span></p>))}</div>}
              {(pack.infographics && pack.infographics.length > 0) && (
                <PackInfographics pack={pack} onSelect={handleSelectInfographic} />
              )}
              {pack.cloze_items.length > 0 && <div><strong style={{ fontSize: '0.85rem' }}>Promoted Cloze Items:</strong>{pack.cloze_items.map(ci => (<div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.85rem', margin: '3px 0' }}>{ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong></div>))}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** The student-facing variant URL for a page (matches GraphicNovelPageEditor). */
function pageDisplayUrl(page) {
  if (page.use_edited_image) return page.edited_image_url || page.image_url || '';
  return page.original_image_url || page.image_url || '';
}

/**
 * All infographic candidates for one pack: a compare strip of poster thumbnails
 * plus a detail panel for the focused candidate, with a Select button to publish.
 */
function PackInfographics({ pack, onSelect }) {
  const infographics = pack.infographics;
  const noneSelected = !infographics.some(i => i.is_selected);
  const defaultId = (infographics.find(i => i.is_selected) || infographics[0]).id;
  const [activeId, setActiveId] = useState(defaultId);
  useEffect(() => {
    if (!infographics.some(i => i.id === activeId)) setActiveId(defaultId);
  }, [infographics, activeId, defaultId]);

  const active = infographics.find(i => i.id === activeId) || infographics[0];

  return (
    <div style={{ marginBottom: 6 }}>
      <strong style={{ fontSize: '0.85rem' }}>
        Infographic Candidates ({infographics.length}):
      </strong>
      {noneSelected && (
        <p className="t-hint" style={{ margin: '2px 0 6px', color: 'var(--t-warning, #b8860b)' }}>
          No infographic selected yet — students assigned the infographic format
          won't see one until you pick a candidate.
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
        {infographics.map(ig => (
          <button
            key={ig.id}
            type="button"
            onClick={() => setActiveId(ig.id)}
            className="t-card"
            style={{
              padding: 6, cursor: 'pointer', width: 140,
              border: ig.id === activeId ? '2px solid var(--t-primary)' : '1px solid var(--t-border)',
            }}
          >
            {ig.image_url
              ? <img src={ig.image_url} alt={ig.title} style={{ width: '100%', borderRadius: 4 }} />
              : <div className="t-hint" style={{ fontSize: '0.75rem', padding: 8 }}>
                  {ig.generation_status === 'FAILED' ? 'Image failed' : 'No image yet'}
                </div>}
            <div style={{ fontSize: '0.75rem', marginTop: 4 }}>
              #{ig.candidate_index}{ig.is_selected ? ' ✓ Selected' : ''}
            </div>
          </button>
        ))}
      </div>

      {active && (
        <div className="t-card" style={{ marginTop: 8, padding: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <h5 style={{ margin: 0 }}>{active.title}</h5>
            <button
              type="button"
              className={`t-btn ${active.is_selected ? 't-btn--secondary' : 't-btn--primary'}`}
              disabled={active.is_selected}
              onClick={() => onSelect(pack.id, active.id)}
            >
              {active.is_selected ? 'Selected' : 'Select this infographic'}
            </button>
          </div>
          {active.intro_text && <p style={{ fontSize: '0.85rem' }}>{active.intro_text}</p>}
          {active.image_url && (
            <img src={active.image_url} alt={active.title} style={{ maxWidth: '100%', borderRadius: 6, marginTop: 6 }} />
          )}
          {(active.entries || []).length > 0 && (
            <ul style={{ fontSize: '0.85rem', marginTop: 8, paddingLeft: 18 }}>
              {active.entries.map((e, i) => (
                <li key={i}><strong>{e.term}</strong> — {e.kid_friendly_definition}</li>
              ))}
            </ul>
          )}
          {(active.cloze_items || []).length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong style={{ fontSize: '0.8rem' }}>Staged Cloze:</strong>
              {active.cloze_items.map(ci => (
                <div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.8rem', margin: '2px 0' }}>
                  {ci.sentence_text} — <strong>{ci.correct_answer}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * All graphic-novel candidates for one pack, laid out as a compact compare
 * strip (every candidate's pages as thumbnails, side by side for scanning)
 * plus a full-width detail panel for the one candidate currently in focus.
 * Defaults focus to the selected candidate, else the first.
 */
function PackGraphicNovels({ pack, audioStateByNovel, onGenerate, onRegenAudio, onSelect, onPageUpdated }) {
  const novels = pack.graphic_novels;
  const noneSelected = !novels.some(n => n.is_selected);
  const defaultId = (novels.find(n => n.is_selected) || novels[0]).id;
  const [activeId, setActiveId] = useState(defaultId);
  // Keep focus valid if the set of candidates changes (e.g. after a refresh).
  useEffect(() => {
    if (!novels.some(n => n.id === activeId)) setActiveId(defaultId);
  }, [novels, activeId, defaultId]);

  const activeNovel = novels.find(n => n.id === activeId) || novels[0];

  return (
    <div style={{ marginBottom: 6 }}>
      <strong style={{ fontSize: '0.85rem' }}>
        Graphic Novel Candidates ({novels.length}):
      </strong>
      {noneSelected && (
        <p className="t-hint" style={{ margin: '2px 0 6px', color: 'var(--t-warning, #b8860b)' }}>
          No candidate selected yet — students cannot see this pack until you pick one.
        </p>
      )}

      {/* Compare strip — one row per candidate, thumbnails for quick scanning. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
        {novels.map(novel => (
          <CandidateStripRow
            key={novel.id}
            packId={pack.id}
            novel={novel}
            isActive={novel.id === activeId}
            onFocus={() => setActiveId(novel.id)}
            onSelect={onSelect}
          />
        ))}
      </div>

      {/* Detail panel for the focused candidate — large pages + edit/audio. */}
      {activeNovel && (
        <CandidateDetail
          packId={pack.id}
          novel={activeNovel}
          audioState={audioStateByNovel[activeNovel.id]}
          onGenerate={onGenerate}
          onRegenAudio={onRegenAudio}
          onSelect={onSelect}
          onPageUpdated={onPageUpdated}
        />
      )}
    </div>
  );
}

/** One row in the compare strip: label, select control, lexile, page thumbnails. */
function CandidateStripRow({ packId, novel, isActive, onFocus, onSelect }) {
  return (
    <div
      onClick={onFocus}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '6px 10px', cursor: 'pointer',
        borderRadius: 6,
        border: `1px solid ${isActive ? 'var(--t-primary)' : 'var(--t-border)'}`,
        background: isActive ? 'var(--t-primary-light)' : 'transparent',
        outline: novel.is_selected ? '2px solid var(--t-success, #2e7d32)' : 'none',
        outlineOffset: novel.is_selected ? '-2px' : 0,
      }}
    >
      <div style={{ minWidth: 200, flexShrink: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6 }}>
          Candidate {novel.candidate_index + 1}
          {novel.is_selected && <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--t-success, #2e7d32)' }}>✓ Selected</span>}
        </div>
        <div className="t-hint" style={{ fontSize: '0.75rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }}>
          {novel.title}
        </div>
        <div className="t-hint" style={{ fontSize: '0.72rem' }}>
          Lexile {novel.reading_level} · {novel.pages.length} pages
        </div>
      </div>
      <div style={{ display: 'flex', gap: 4, flex: 1, overflowX: 'auto' }}>
        {novel.pages.map(page => {
          const url = pageDisplayUrl(page);
          return url ? (
            <img
              key={page.id}
              src={url}
              alt={`C${novel.candidate_index + 1} p${page.page_number}`}
              style={{ height: 64, width: 'auto', borderRadius: 3, flexShrink: 0, border: '1px solid var(--t-border-light)' }}
            />
          ) : (
            <div key={page.id} className="t-hint" style={{ height: 64, width: 48, flexShrink: 0, display: 'grid', placeItems: 'center', fontSize: '0.6rem', border: '1px solid var(--t-border-light)', borderRadius: 3 }}>—</div>
          );
        })}
      </div>
      <div style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
        {novel.is_selected
          ? <span className="t-hint" style={{ fontSize: '0.72rem' }}>Published</span>
          : (
            <button
              className="t-btn t-btn--primary"
              style={{ fontSize: '0.72rem', padding: '2px 12px' }}
              onClick={() => onSelect(packId, novel.id)}
              title="Publish this candidate to students and promote its cloze"
            >
              Select
            </button>
          )}
      </div>
    </div>
  );
}

/** Full-width detail for the focused candidate: header, large page grid, cloze. */
function CandidateDetail({ packId, novel, audioState, onGenerate, onRegenAudio, onSelect, onPageUpdated }) {
  return (
    <div
      className="t-card"
      style={{
        marginTop: 10, padding: 12,
        border: novel.is_selected ? '2px solid var(--t-success, #2e7d32)' : '1px solid var(--t-border)',
        background: novel.is_selected ? 'var(--t-success-bg, rgba(46,125,50,0.06))' : 'transparent',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
          Candidate {novel.candidate_index + 1}: {novel.title}
        </span>
        {novel.is_selected
          ? <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--t-success, #2e7d32)' }}>✓ Selected</span>
          : (
            <button
              className="t-btn t-btn--primary"
              style={{ fontSize: '0.75rem', padding: '2px 12px' }}
              onClick={() => onSelect(packId, novel.id)}
              title="Publish this candidate to students and promote its cloze"
            >
              Select this candidate
            </button>
          )}
        <span className="t-hint" style={{ fontSize: '0.8rem' }}>
          (Lexile: {novel.reading_level}, Pages: {novel.pages.length})
        </span>
        <AudioControls novelId={novel.id} audioState={audioState} onGenerate={onGenerate} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, marginTop: 6 }}>
        {novel.pages.map(page => {
          const audioPage = audioState?.pages?.find(ap => ap.page_number === page.page_number);
          return (
            <GraphicNovelPageEditor
              key={page.id}
              page={page}
              audioUrl={audioPage?.audio_url || page.audio_url || ''}
              audioStatus={audioPage?.status}
              audioError={audioPage?.error}
              onRegenAudio={() => onRegenAudio(novel.id, page.id, page.page_number)}
              onUpdated={(updatedPage) => onPageUpdated(packId, updatedPage)}
            />
          );
        })}
      </div>
      {novel.cloze_items && novel.cloze_items.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <strong style={{ fontSize: '0.8rem' }}>Cloze for this candidate:</strong>
          {novel.cloze_items.map(ci => (
            <div key={ci.id} style={{ paddingLeft: 12, fontSize: '0.82rem', margin: '2px 0' }}>
              {ci.sentence_text} — Answer: <strong>{ci.correct_answer}</strong>
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
