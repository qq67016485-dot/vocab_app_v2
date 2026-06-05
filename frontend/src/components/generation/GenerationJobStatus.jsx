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
  const lastCompletedIdx = job.last_completed_step
    ? PIPELINE_STEPS.findIndex(s => s.key === job.last_completed_step)
    : -1;
  const currentStepKey = jobActive ? PIPELINE_STEPS[lastCompletedIdx + 1]?.key : null;

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

  const statusIcon = (s) => s === 'COMPLETED' ? '\u2713' : s === 'FAILED' ? '\u2717' : s === 'RUNNING' ? '\u25CF' : '\u25CB';
  const statusCls = (s) => s === 'COMPLETED' ? 'pipeline-icon--done' : s === 'FAILED' ? 'pipeline-icon--failed' : s === 'RUNNING' ? 'pipeline-icon--running' : 'pipeline-icon--pending';
  const stepCls = (s) => s === 'RUNNING' ? 'pipeline-step--running' : s === 'FAILED' ? 'pipeline-step--failed' : '';
  const handleSubstepRestart = async (packId, substepKey) => {
    setRestartingSubstep(`${packId}_${substepKey}`);
    setError('');
    try {
      const res = await apiClient.post(`/generation-jobs/${jobId}/restart-substep/`, {
        pack_id: packId,
        substep: substepKey,
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

  const renderGraphicNovelScriptSubsteps = () => {
    // Before the pipeline reaches this step there is no per-pack substep data
    // yet. Show a collapsible preview of the canonical substep order so the
    // workflow is visible ahead of time.
    if (graphicNovelScriptSubsteps.length === 0) {
      return (
        <details style={{ margin: '2px 0 6px 30px', padding: '8px 10px', border: '1px solid var(--t-border)', borderRadius: 6, background: 'var(--t-bg-secondary)' }}>
          <summary style={{ cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>Planning Substeps (preview)</summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
            {GRAPHIC_NOVEL_SUBSTEPS.map((substep) => (
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
          {graphicNovelScriptSubsteps.map((pack) => (
            <div key={pack.pack_id || pack.pack_label}>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: 4 }}>{pack.pack_label}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {pack.substeps.map((substep) => {
                  const s = substep.status || 'PENDING';
                  const isRestarting = restartingSubstep === `${pack.pack_id}_${substep.substep}`;
                  const canRestart = job.status !== 'RUNNING' && job.status !== 'PENDING' && !restartingSubstep;
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
                          onClick={() => handleSubstepRestart(pack.pack_id, substep.substep)}
                          title={`Restart from ${substep.label}`}
                        >
                          {isRestarting ? '...' : '↻'}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </details>
    );
  };

  return (
    <div style={{ maxWidth: 680 }}>
      <div style={{ marginBottom: 12 }}>
        <span className={`t-badge ${job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED' ? 't-badge--generated' : job.status === 'FAILED' ? 't-badge--failed' : 't-badge--generating'}`}
          style={{ padding: '4px 10px', fontSize: '0.78rem' }}>{job.status}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {PIPELINE_STEPS.map((step) => {
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
              {step.key === 'GRAPHIC_NOVEL_SCRIPT' && renderGraphicNovelScriptSubsteps()}
            </React.Fragment>
          );
        })}
      </div>
      {graphicNovelImagePages.length > 0 && (
        <div style={{ marginTop: 8, padding: '8px 10px', border: '1px solid var(--t-border)', borderRadius: 6, background: 'var(--t-bg-secondary)' }}>
          <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 6 }}>Graphic Novel Pages</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {graphicNovelImagePages.map((page) => {
              const s = page.status || (page.has_image ? 'COMPLETED' : 'PENDING');
              return (
                <div key={page.id} style={{ display: 'grid', gridTemplateColumns: '22px minmax(0, 1fr) auto', gap: 8, alignItems: 'center', fontSize: '0.82rem' }}>
                  <span className={`pipeline-icon ${statusCls(s)}`}>{statusIcon(s)}</span>
                  <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${page.pack_label} - ${page.novel_title}`}>
                    {page.pack_label} · Page {page.page_number}
                  </span>
                  <span style={{ color: s === 'FAILED' ? 'var(--t-danger)' : 'var(--t-text-secondary)' }} title={page.error_message || ''}>
                    {s}{page.attempts ? ` · try ${page.attempts}` : ''}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
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
