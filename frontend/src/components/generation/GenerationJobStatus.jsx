import React, { useState, useEffect, useRef } from 'react';
import apiClient from '../../api/axiosConfig.js';

const PIPELINE_STEPS = [
  { key: 'WORD_LOOKUP', label: 'Word Lookup' },
  { key: 'DEDUP', label: 'Deduplication' },
  { key: 'TRANSLATION', label: 'Translation' },
  { key: 'QUESTION_GEN', label: 'Question Generation' },
  { key: 'PACK_CREATION', label: 'Pack Creation' },
  { key: 'PRIMER_GEN', label: 'Primer Generation' },
  { key: 'STORY_CLOZE_GEN', label: 'Story & Cloze Generation' },
  { key: 'CREATIVE_DIRECTION', label: 'Creative Direction' },
  { key: 'IMAGE_GEN', label: 'Image Generation' },
  { key: 'PICTURE_MATCH_GEN', label: 'Picture-Word Match' },
];

const POLL_INTERVAL = 3000;

export default function GenerationJobStatus({ jobId, onComplete, onFail }) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const [isResuming, setIsResuming] = useState(false);
  const [restartStep, setRestartStep] = useState('QUESTION_GEN');
  const [includeSubsequent, setIncludeSubsequent] = useState(true);
  const [isRestartingStep, setIsRestartingStep] = useState(false);
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
  const getStepStatus = (stepKey) => logMap[stepKey]?.status || 'PENDING';

  const statusIcon = (s) => s === 'COMPLETED' ? '\u2713' : s === 'FAILED' ? '\u2717' : s === 'RUNNING' ? '\u25CF' : '\u25CB';
  const statusCls = (s) => s === 'COMPLETED' ? 'pipeline-icon--done' : s === 'FAILED' ? 'pipeline-icon--failed' : s === 'RUNNING' ? 'pipeline-icon--running' : 'pipeline-icon--pending';
  const stepCls = (s) => s === 'RUNNING' ? 'pipeline-step--running' : s === 'FAILED' ? 'pipeline-step--failed' : '';

  return (
    <div style={{ maxWidth: 500 }}>
      <div style={{ marginBottom: 12 }}>
        <span className={`t-badge ${job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED' ? 't-badge--generated' : job.status === 'FAILED' ? 't-badge--failed' : 't-badge--generating'}`}
          style={{ padding: '4px 10px', fontSize: '0.78rem' }}>{job.status}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {PIPELINE_STEPS.map((step) => {
          const s = getStepStatus(step.key);
          const log = logMap[step.key];
          return (
            <div key={step.key} className={`pipeline-step ${stepCls(s)}`}>
              <span className={`pipeline-icon ${statusCls(s)}`}>{statusIcon(s)}</span>
              <span style={{ flex: 1, fontSize: '0.9rem', fontWeight: s === 'RUNNING' ? 600 : 400, color: s === 'PENDING' ? 'var(--t-text-tertiary)' : 'inherit' }}>{step.label}</span>
              {log?.duration_seconds != null && <span className="pipeline-duration">{log.duration_seconds.toFixed(1)}s</span>}
              {log?.error_message && <span style={{ fontSize: '0.8rem', color: 'var(--t-danger)' }} title={log.error_message}>Error</span>}
            </div>
          );
        })}
      </div>
      {(job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED') && (
        <div className="t-message t-message--success" style={{ marginTop: 12 }}>
          <strong>Summary:</strong> {job.words_created} words, {job.questions_created} questions, {job.primer_cards_created} primers, {job.stories_created} stories, {job.cloze_items_created} cloze items, {job.images_created} images
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
