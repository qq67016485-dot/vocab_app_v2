import React, { useState, useEffect, useRef } from 'react';
import apiClient from '../../api/axiosConfig.js';

const PIPELINE_STEPS = [
  { key: 'WORD_LOOKUP', label: 'Word Lookup' },
  { key: 'DEDUP', label: 'Deduplication' },
  { key: 'TRANSLATION', label: 'Translation' },
  { key: 'QUESTION_GEN', label: 'Question Generation' },
  { key: 'PRIMER_GEN', label: 'Primer Generation' },
  { key: 'PACK_CREATION', label: 'Pack Creation' },
  { key: 'GRAPHIC_NOVEL_SCRIPT', label: 'Graphic Novel Script' },
  { key: 'GRAPHIC_NOVEL_IMAGES', label: 'Graphic Novel Images' },
  { key: 'INFOGRAPHIC_DESIGN', label: 'Infographic Design' },
  { key: 'INFOGRAPHIC_IMAGE', label: 'Infographic Image' },
];

// Canonical substep order for the Graphic Novel Script step (mirrors
// backend GRAPHIC_NOVEL_SUBSTEPS in services/generation/constants.py).
// Used to preview substeps in the accordion before the pipeline reaches them.
const GRAPHIC_NOVEL_SUBSTEPS = [
  { key: 'team_selection', label: 'Team Selection' },
  { key: 'router_premises', label: 'Router + Premises' },
  { key: 'premise_scoring', label: 'Premise Scoring' },
  { key: 'cloze_generation', label: 'Cloze Generation' },
  { key: 'beat_sheet_vocab_roles', label: 'Beat Sheet + Vocab Roles' },
  { key: 'final_script_self_check', label: 'Final Script + Self-Check' },
];

// Canonical substep order for the Infographic Design step (mirrors backend
// INFOGRAPHIC_DESIGN_SUBSTEPS). Both substeps log under the single
// INFOGRAPHIC_DESIGN step, so without this breakdown the step row only reflects
// whichever substep logged last (cloze) — hiding the design substep entirely.
const INFOGRAPHIC_SUBSTEPS = [
  { key: 'design', label: 'Infographic Design' },
  { key: 'cloze', label: 'Infographic Cloze' },
];

const POLL_INTERVAL = 30000;

export default function GenerationJobStatus({ jobId, onComplete, onFail }) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const [isResuming, setIsResuming] = useState(false);
  const [restartStep, setRestartStep] = useState('QUESTION_GEN');
  const [includeSubsequent, setIncludeSubsequent] = useState(true);
  const [isRestartingStep, setIsRestartingStep] = useState(false);
  const [restartingSubstep, setRestartingSubstep] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    const poll = async () => {
      try {
        const [jobRes, logsRes] = await Promise.all([
          apiClient.get(`/generation-jobs/${jobId}/`),
          apiClient.get(`/generation-jobs/${jobId}/logs/`),
        ]);
        setJob(jobRes.data); setLogs(logsRes.data);
        if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') { clearInterval(intervalRef.current); onComplete?.(jobRes.data); }
        else if (jobRes.data.status === 'FAILED') { clearInterval(intervalRef.current); onFail?.(jobRes.data); }
      } catch (err) { console.error('Error polling job status:', err); setError('Failed to fetch job status.'); clearInterval(intervalRef.current); }
    };
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [jobId, onComplete, onFail]);

  if (error) return <p style={{ color: 'var(--t-danger)' }}>{error}</p>;
  if (!job) return <p>Loading job status...</p>;

  const logMap = {};
  logs.forEach(log => { logMap[log.step] = log; });

  // last_completed_step only advances after a step fully succeeds, so while the
  // job is still RUNNING/PENDING the active step is the one right after it.
  // That step may have logged transient retry FAILEDs (primary site failed, now
  // retrying on the fallback) — those are not terminal, so we show the step as
  // RUNNING with the retry detail rather than a false FAILED.
  const jobActive = job.status === 'RUNNING' || job.status === 'PENDING';
  // Hide a content type's steps when the job didn't generate it (empty/legacy
  // content_types = graphic novel only), so skipped steps don't show as stuck.
  const contentTypes = (job.content_types && job.content_types.length > 0)
    ? job.content_types
    : ['graphic_novel'];
  const visibleSteps = PIPELINE_STEPS.filter((s) => {
    if (s.key === 'GRAPHIC_NOVEL_SCRIPT' || s.key === 'GRAPHIC_NOVEL_IMAGES') {
      return contentTypes.includes('graphic_novel');
    }
    if (s.key === 'INFOGRAPHIC_DESIGN' || s.key === 'INFOGRAPHIC_IMAGE') {
      return contentTypes.includes('infographic');
    }
    return true;
  });
  const lastCompletedIdx = job.last_completed_step
    ? visibleSteps.findIndex(s => s.key === job.last_completed_step)
    : -1;
  const currentStepKey = jobActive ? visibleSteps[lastCompletedIdx + 1]?.key : null;

  const getStepStatus = (stepKey) => {
    if (stepKey === currentStepKey) return 'RUNNING';
    return logMap[stepKey]?.status || 'PENDING';
  };
  // Retry message for the active step, if its latest log is a (non-terminal)
  // retry marker. Falls back to a generic line for older logs without one.
  const getRetryMessage = (stepKey) => {
    if (stepKey !== currentStepKey) return '';
    const log = logMap[stepKey];
    if (!log || log.status !== 'FAILED' || !log.output_data?.retrying) return '';
    return log.output_data.retry_message || 'Previous attempt failed; retrying…';
  };

  const graphicNovelImagePages = job.graphic_novel_image_pages || [];
  const graphicNovelScriptSubsteps = job.graphic_novel_script_substeps || [];
  const infographicDesignSubsteps = job.infographic_design_substeps || [];

  const statusIcon = (s) => s === 'COMPLETED' ? '\u2713' : s === 'FAILED' ? '\u2717' : s === 'RUNNING' ? '\u25CF' : '\u25CB';
  const statusCls = (s) => s === 'COMPLETED' ? 'pipeline-icon--done' : s === 'FAILED' ? 'pipeline-icon--failed' : s === 'RUNNING' ? 'pipeline-icon--running' : 'pipeline-icon--pending';
  const stepCls = (s) => s === 'RUNNING' ? 'pipeline-step--running' : s === 'FAILED' ? 'pipeline-step--failed' : '';
  const handleSubstepRestart = async (packId, substepKey, candidateIndex = 0, endpoint = 'restart-substep') => {
    setRestartingSubstep(`${packId}_${candidateIndex}_${substepKey}`);
    setError('');
    try {
      const res = await apiClient.post(`/generation-jobs/${jobId}/${endpoint}/`, {
        pack_id: packId,
        substep: substepKey,
        candidate_index: candidateIndex,
      });
      setJob(prev => prev ? { ...prev, ...res.data, status: 'RUNNING', error_message: '' } : res.data);
      clearInterval(intervalRef.current);
      const poll = async () => {
        const [jobRes, logsRes] = await Promise.all([apiClient.get(`/generation-jobs/${jobId}/`), apiClient.get(`/generation-jobs/${jobId}/logs/`)]);
        setJob(jobRes.data); setLogs(logsRes.data);
        if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') { clearInterval(intervalRef.current); setRestartingSubstep(null); onComplete?.(jobRes.data); }
        else if (jobRes.data.status === 'FAILED') { clearInterval(intervalRef.current); setRestartingSubstep(null); onFail?.(jobRes.data); }
      };
      poll(); intervalRef.current = setInterval(poll, POLL_INTERVAL);
    } catch (err) { setError(err.response?.data?.error || 'Failed to restart substep.'); setRestartingSubstep(null); }
  };

  // Renders the per-pack, per-candidate substep accordion for a step that runs
  // multiple substeps under one pipeline step (graphic novel script + infographic
  // design). `substepData` is the backend per-pack payload; `previewSubsteps` is
  // the canonical order shown before the pipeline reaches the step; `restartEndpoint`
  // is the job-relative restart route for the per-substep ↻ button (null = no
  // restart button, e.g. a step whose restart API doesn't exist).
  const renderSubstepAccordion = (substepData, previewSubsteps, restartEndpoint) => {
    // Before the pipeline reaches this step there is no per-pack substep data
    // yet. Show a collapsible preview of the canonical substep order so the
    // workflow is visible ahead of time.
    if (substepData.length === 0) {
      return (
        <details style={{ margin: '2px 0 6px 30px', padding: '8px 10px', border: '1px solid var(--t-border)', borderRadius: 6, background: 'var(--t-bg-secondary)' }}>
          <summary style={{ cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>Planning Substeps (preview)</summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
            {previewSubsteps.map((substep) => (
              <div key={substep.key} style={{ display: 'grid', gridTemplateColumns: '22px minmax(0, 1fr)', gap: 8, alignItems: 'center', fontSize: '0.8rem' }}>
                <span className={`pipeline-icon ${statusCls('PENDING')}`}>{statusIcon('PENDING')}</span>
                <span style={{ color: 'var(--t-text-tertiary)' }}>{substep.label}</span>
              </div>
            ))}
          </div>
        </details>
      );
    }
    return (
      <details open style={{ margin: '2px 0 6px 30px', padding: '8px 10px', border: '1px solid var(--t-border)', borderRadius: 6, background: 'var(--t-bg-secondary)' }}>
        <summary style={{ cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>Planning Substeps</summary>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
          {substepData.map((pack) => (
            <div key={pack.pack_id || pack.pack_label}>
              <div style={{ fontSize: '0.82rem', fontWeight: 700, marginBottom: 6 }}>{pack.pack_label}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(pack.candidates || []).map((candidate) => renderCandidateSubsteps(pack, candidate, restartEndpoint))}
              </div>
            </div>
          ))}
        </div>
      </details>
    );
  };

  // One candidate's substep list, grouped under its own collapsible header so
  // the candidates per pack are visually distinct (rather than the same rows
  // repeating with no label). Completed candidates collapse by default. The
  // per-substep restart button only shows when `restartEndpoint` is set; it
  // posts to that job-relative route (GN and infographic have separate ones).
  const renderCandidateSubsteps = (pack, candidate, restartEndpoint = null) => {
    const substeps = candidate.substeps || [];
    const ci = candidate.candidate_index ?? 0;
    const done = substeps.filter((s) => s.status === 'COMPLETED').length;
    const anyFailed = substeps.some((s) => s.status === 'FAILED');
    const allDone = done === substeps.length && substeps.length > 0;
    return (
      <details
        key={ci}
        open={!allDone}
        style={{
          padding: '6px 8px', borderRadius: 6,
          border: `1px solid ${anyFailed ? 'var(--t-danger)' : 'var(--t-border)'}`,
          background: 'var(--t-bg)',
        }}
      >
        <summary style={{ cursor: 'pointer', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600 }}>Candidate {ci + 1}</span>
          <span style={{ fontSize: '0.75rem', color: anyFailed ? 'var(--t-danger)' : 'var(--t-text-secondary)' }}>
            {allDone ? 'complete' : `${done}/${substeps.length}`}
          </span>
        </summary>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
          {substeps.map((substep) => {
            const s = substep.status || 'PENDING';
            const isRestarting = restartingSubstep === `${pack.pack_id}_${ci}_${substep.substep}`;
            const canRestart = restartEndpoint && job.status !== 'RUNNING' && job.status !== 'PENDING' && !restartingSubstep;
            return (
              <div key={substep.substep} style={{ display: 'grid', gridTemplateColumns: '22px minmax(0, 1fr) auto auto', gap: 8, alignItems: 'center', fontSize: '0.8rem' }}>
                <span className={`pipeline-icon ${statusCls(s)}`}>{statusIcon(s)}</span>
                <span style={{ minWidth: 0 }}>
                  <span>{substep.label}</span>
                  {substep.artifact_name && (
                    <span style={{ marginLeft: 8, color: 'var(--t-text-secondary)' }} title={substep.artifact_path}>
                      {substep.artifact_name}
                    </span>
                  )}
                </span>
                <span style={{ color: s === 'FAILED' ? 'var(--t-danger)' : 'var(--t-text-secondary)' }} title={substep.error_message || substep.artifact_path || ''}>
                  {s}{substep.duration_seconds != null ? ` - ${substep.duration_seconds.toFixed(1)}s` : ''}
                </span>
                {canRestart && (
                  <button
                    style={{ padding: '2px 6px', fontSize: '0.72rem', borderRadius: 4, border: '1px solid var(--t-border)', background: 'var(--t-bg)', cursor: 'pointer' }}
                    onClick={() => handleSubstepRestart(pack.pack_id, substep.substep, ci, restartEndpoint)}
                    title={`Restart Candidate ${ci + 1} from ${substep.label}`}
                  >
                    {isRestarting ? '...' : '↻'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </details>
    );
  };

  return (
    <div style={{ maxWidth: 1000 }}>
      <div style={{ marginBottom: 12 }}>
        <span className={`t-badge ${job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED' ? 't-badge--generated' : job.status === 'FAILED' ? 't-badge--failed' : 't-badge--generating'}`}
          style={{ padding: '4px 10px', fontSize: '0.78rem' }}>{job.status}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {visibleSteps.map((step) => {
          const s = getStepStatus(step.key);
          const log = logMap[step.key];
          const retryMsg = getRetryMessage(step.key);
          return (
            <React.Fragment key={step.key}>
              <div className={`pipeline-step ${stepCls(s)}`}>
                <span className={`pipeline-icon ${statusCls(s)}`}>{statusIcon(s)}</span>
                <span style={{ flex: 1, fontSize: '0.9rem', fontWeight: s === 'RUNNING' ? 600 : 400, color: s === 'PENDING' ? 'var(--t-text-tertiary)' : 'inherit' }}>
                  {step.label}
                  {step.key === 'GRAPHIC_NOVEL_IMAGES' && graphicNovelImagePages.length > 0 && (
                    <span style={{ marginLeft: 8, fontSize: '0.78rem', color: 'var(--t-text-secondary)', fontWeight: 400 }}>
                      {graphicNovelImagePages.filter(page => page.status === 'COMPLETED').length}/{graphicNovelImagePages.length} pages
                    </span>
                  )}
                </span>
                {log?.duration_seconds != null && s !== 'RUNNING' && <span className="pipeline-duration">{log.duration_seconds.toFixed(1)}s</span>}
                {retryMsg
                  ? <span style={{ fontSize: '0.8rem', color: 'var(--t-warning)' }}>Retrying</span>
                  : (s === 'FAILED' && log?.error_message && <span style={{ fontSize: '0.8rem', color: 'var(--t-danger)' }} title={log.error_message}>Error</span>)}
              </div>
              {retryMsg && (
                <div style={{ margin: '0 0 4px 30px', fontSize: '0.78rem', color: 'var(--t-warning)' }}>
                  {retryMsg}
                </div>
              )}
              {step.key === 'GRAPHIC_NOVEL_SCRIPT' && renderSubstepAccordion(graphicNovelScriptSubsteps, GRAPHIC_NOVEL_SUBSTEPS, 'restart-substep')}
              {step.key === 'INFOGRAPHIC_DESIGN' && renderSubstepAccordion(infographicDesignSubsteps, INFOGRAPHIC_SUBSTEPS, 'restart-infographic-substep')}
            </React.Fragment>
          );
        })}
      </div>
      {graphicNovelImagePages.length > 0 && (
        <GraphicNovelImageProgress
          pages={graphicNovelImagePages}
          statusIcon={statusIcon}
          statusCls={statusCls}
        />
      )}
      {(job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED') && (
        <div className="t-message t-message--success" style={{ marginTop: 12 }}>
          <strong>Summary:</strong> {job.words_created} words, {job.questions_created} questions, {job.primer_cards_created} primers, {job.graphic_novels_created || 0} graphic novels, {job.cloze_items_created} cloze items
        </div>
      )}
      {job.status === 'FAILED' && job.error_message && (
        <div className="t-message t-message--error" style={{ marginTop: 12 }}><strong>Error:</strong> {job.error_message}</div>
      )}
      {job.status !== 'RUNNING' && job.status !== 'PENDING' && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--t-border)' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <select
              value={restartStep}
              onChange={(event) => setRestartStep(event.target.value)}
              style={{ minWidth: 190, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--t-border)' }}
            >
              {PIPELINE_STEPS.map((step) => (
                <option key={step.key} value={step.key}>{step.label}</option>
              ))}
            </select>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.85rem' }}>
              <input
                type="checkbox"
                checked={includeSubsequent}
                onChange={(event) => setIncludeSubsequent(event.target.checked)}
              />
              Run following steps
            </label>
            <button
              className="t-btn t-btn--sm"
              onClick={async () => {
                setIsRestartingStep(true);
                setError('');
                try {
                  const restartRes = await apiClient.post(`/generation-jobs/${jobId}/restart-step/`, {
                    step: restartStep,
                    include_subsequent: includeSubsequent,
                  });
                  setJob(prev => prev ? { ...prev, ...restartRes.data, status: 'RUNNING', error_message: '' } : restartRes.data);
                  clearInterval(intervalRef.current);
                  const poll = async () => {
                    const [jobRes, logsRes] = await Promise.all([apiClient.get(`/generation-jobs/${jobId}/`), apiClient.get(`/generation-jobs/${jobId}/logs/`)]);
                    setJob(jobRes.data); setLogs(logsRes.data);
                    if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') { clearInterval(intervalRef.current); setIsRestartingStep(false); onComplete?.(jobRes.data); }
                    else if (jobRes.data.status === 'FAILED') { clearInterval(intervalRef.current); setIsRestartingStep(false); onFail?.(jobRes.data); }
                  };
                  poll(); intervalRef.current = setInterval(poll, POLL_INTERVAL);
                } catch (err) { setError(err.response?.data?.error || 'Failed to restart pipeline step.'); setIsRestartingStep(false); }
              }}
              disabled={isRestartingStep}
            >
              {isRestartingStep ? 'Restarting...' : 'Restart Step'}
            </button>
          </div>
        </div>
      )}
      {job.status === 'FAILED' && (
        <button className="t-btn t-btn--sm" style={{ marginTop: 10, background: 'var(--t-warning)', color: '#fff' }}
          onClick={async () => {
            setIsResuming(true);
            setError('');
            try {
              const resumeRes = await apiClient.post(`/generation-jobs/${jobId}/resume/`);
              setJob(prev => prev ? { ...prev, ...resumeRes.data, status: 'RUNNING', error_message: '' } : resumeRes.data);
              clearInterval(intervalRef.current);
              const poll = async () => {
                const [jobRes, logsRes] = await Promise.all([apiClient.get(`/generation-jobs/${jobId}/`), apiClient.get(`/generation-jobs/${jobId}/logs/`)]);
                setJob(jobRes.data); setLogs(logsRes.data);
                if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') { clearInterval(intervalRef.current); onComplete?.(jobRes.data); }
                else if (jobRes.data.status === 'FAILED') { clearInterval(intervalRef.current); setIsResuming(false); onFail?.(jobRes.data); }
              };
              poll(); intervalRef.current = setInterval(poll, POLL_INTERVAL);
            } catch (err) { setError(err.response?.data?.error || 'Failed to resume pipeline.'); setIsResuming(false); }
          }} disabled={isResuming}>
          {isResuming ? 'Resuming...' : 'Resume Pipeline'}
        </button>
      )}
    </div>
  );
}

/**
 * Compact image-generation progress: pages grouped by pack, then by candidate
 * novel. Each candidate is a single row showing an overall count plus one small
 * status chip per page — instead of one tall list row per page. This keeps a
 * 3-candidate × 7-page job readable at a glance rather than as a 40-row scroll.
 */
function GraphicNovelImageProgress({ pages, statusIcon, statusCls }) {
  const pageStatus = (page) => page.status || (page.has_image ? 'COMPLETED' : 'PENDING');

  // Group: pack_id → { pack_label, novels: novel_id → { title, candidate_index, pages[] } }
  const packs = [];
  const packIndex = {};
  const novelIndex = {};
  pages.forEach((page) => {
    const pk = page.pack_id ?? page.pack_label;
    if (!(pk in packIndex)) {
      packIndex[pk] = packs.length;
      packs.push({ pack_label: page.pack_label, novels: [] });
    }
    const pack = packs[packIndex[pk]];
    const nkey = `${pk}:${page.novel_id}`;
    if (!(nkey in novelIndex)) {
      novelIndex[nkey] = pack.novels.length;
      pack.novels.push({
        novel_id: page.novel_id,
        title: page.novel_title,
        candidate_index: page.candidate_index,
        pages: [],
      });
    }
    pack.novels[novelIndex[nkey]].pages.push(page);
  });

  const totalDone = pages.filter((p) => pageStatus(p) === 'COMPLETED').length;

  return (
    <div style={{ marginTop: 8, padding: '10px 12px', border: '1px solid var(--t-border)', borderRadius: 6, background: 'var(--t-bg-secondary)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Graphic Novel Pages</span>
        <span style={{ fontSize: '0.78rem', color: 'var(--t-text-secondary)' }}>{totalDone}/{pages.length} pages rendered</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {packs.map((pack, pi) => (
          <div key={pi}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: 6 }}>{pack.pack_label}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {pack.novels.map((novel) => {
                const done = novel.pages.filter((p) => pageStatus(p) === 'COMPLETED').length;
                const anyFailed = novel.pages.some((p) => pageStatus(p) === 'FAILED');
                return (
                  <div
                    key={novel.novel_id}
                    style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 220px) auto 1fr', gap: 10, alignItems: 'center' }}
                  >
                    <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8rem' }} title={novel.title}>
                      <span style={{ fontWeight: 600 }}>Candidate {(novel.candidate_index ?? 0) + 1}</span>
                      <span style={{ color: 'var(--t-text-secondary)' }}> · {novel.title}</span>
                    </span>
                    <span style={{ fontSize: '0.76rem', color: anyFailed ? 'var(--t-danger)' : 'var(--t-text-secondary)', whiteSpace: 'nowrap' }}>
                      {done}/{novel.pages.length}
                    </span>
                    <span style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {novel.pages.map((page) => {
                        const s = pageStatus(page);
                        return (
                          <span
                            key={page.id}
                            className={`pipeline-icon ${statusCls(s)}`}
                            title={`Page ${page.page_number}: ${s}${page.attempts ? ` (try ${page.attempts})` : ''}${page.error_message ? ` — ${page.error_message}` : ''}`}
                            style={{ fontSize: '0.78rem' }}
                          >
                            {statusIcon(s)}
                          </span>
                        );
                      })}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
