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
  { key: 'IMAGE_GEN', label: 'Image Generation' },
];

const POLL_INTERVAL = 3000;

export default function GenerationJobStatus({ jobId, onComplete, onFail }) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const [isResuming, setIsResuming] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const [jobRes, logsRes] = await Promise.all([
          apiClient.get(`/generation-jobs/${jobId}/`),
          apiClient.get(`/generation-jobs/${jobId}/logs/`),
        ]);
        setJob(jobRes.data);
        setLogs(logsRes.data);

        if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') {
          clearInterval(intervalRef.current);
          onComplete?.(jobRes.data);
        } else if (jobRes.data.status === 'FAILED') {
          clearInterval(intervalRef.current);
          onFail?.(jobRes.data);
        }
      } catch (err) {
        console.error('Error polling job status:', err);
        setError('Failed to fetch job status.');
        clearInterval(intervalRef.current);
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [jobId, onComplete, onFail]);

  if (error) return <p style={{ color: '#dc2626' }}>{error}</p>;
  if (!job) return <p>Loading job status...</p>;

  const logMap = {};
  logs.forEach(log => { logMap[log.step] = log; });

  const getStepStatus = (stepKey) => {
    const log = logMap[stepKey];
    if (!log) return 'PENDING';
    return log.status;
  };

  const statusIcon = (s) => {
    if (s === 'COMPLETED') return '\u2713';
    if (s === 'FAILED') return '\u2717';
    if (s === 'RUNNING') return '\u25CF';
    return '\u25CB';
  };

  const statusColor = (s) => {
    if (s === 'COMPLETED') return '#16a34a';
    if (s === 'FAILED') return '#dc2626';
    if (s === 'RUNNING') return '#2563eb';
    return '#9ca3af';
  };

  return (
    <div style={{ maxWidth: '500px' }}>
      <div style={{ marginBottom: '1rem' }}>
        <span style={{
          display: 'inline-block',
          padding: '0.25rem 0.75rem',
          borderRadius: '12px',
          fontSize: '0.85rem',
          fontWeight: 600,
          color: '#fff',
          background: statusColor(job.status),
        }}>
          {job.status}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {PIPELINE_STEPS.map((step) => {
          const s = getStepStatus(step.key);
          const log = logMap[step.key];
          return (
            <div key={step.key} style={{
              display: 'flex', alignItems: 'center', gap: '0.75rem',
              padding: '0.5rem 0.75rem',
              borderRadius: '6px',
              background: s === 'RUNNING' ? '#eff6ff' : s === 'FAILED' ? '#fef2f2' : 'transparent',
            }}>
              <span style={{
                fontSize: '1.1rem', color: statusColor(s), fontWeight: 700,
                animation: s === 'RUNNING' ? 'pulse 1.5s infinite' : 'none',
              }}>
                {statusIcon(s)}
              </span>
              <span style={{ flex: 1, fontSize: '0.9rem', fontWeight: s === 'RUNNING' ? 600 : 400 }}>
                {step.label}
              </span>
              {log?.duration_seconds != null && (
                <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                  {log.duration_seconds.toFixed(1)}s
                </span>
              )}
              {log?.error_message && (
                <span style={{ fontSize: '0.8rem', color: '#dc2626' }} title={log.error_message}>
                  Error
                </span>
              )}
            </div>
          );
        })}
      </div>

      {(job.status === 'COMPLETED' || job.status === 'PARTIALLY_COMPLETED') && (
        <div style={{
          marginTop: '1rem', padding: '0.75rem',
          background: '#f0fdf4', borderRadius: '8px', fontSize: '0.85rem',
        }}>
          <strong>Summary:</strong>{' '}
          {job.words_created} words, {job.questions_created} questions,{' '}
          {job.primer_cards_created} primers, {job.stories_created} stories,{' '}
          {job.cloze_items_created} cloze items, {job.images_created} images
        </div>
      )}

      {job.status === 'FAILED' && job.error_message && (
        <div style={{
          marginTop: '1rem', padding: '0.75rem',
          background: '#fef2f2', borderRadius: '8px', fontSize: '0.85rem', color: '#dc2626',
        }}>
          <strong>Error:</strong> {job.error_message}
        </div>
      )}

      {job.status === 'FAILED' && (
        <button
          onClick={async () => {
            setIsResuming(true);
            try {
              await apiClient.post(`/generation-jobs/${jobId}/resume/`);
              // Restart polling
              const poll = async () => {
                const [jobRes, logsRes] = await Promise.all([
                  apiClient.get(`/generation-jobs/${jobId}/`),
                  apiClient.get(`/generation-jobs/${jobId}/logs/`),
                ]);
                setJob(jobRes.data);
                setLogs(logsRes.data);
                if (jobRes.data.status === 'COMPLETED' || jobRes.data.status === 'PARTIALLY_COMPLETED') {
                  clearInterval(intervalRef.current);
                  onComplete?.(jobRes.data);
                } else if (jobRes.data.status === 'FAILED') {
                  clearInterval(intervalRef.current);
                  onFail?.(jobRes.data);
                }
              };
              poll();
              intervalRef.current = setInterval(poll, POLL_INTERVAL);
            } catch (err) {
              setError(err.response?.data?.error || 'Failed to resume pipeline.');
            } finally {
              setIsResuming(false);
            }
          }}
          disabled={isResuming}
          style={{
            marginTop: '0.75rem', padding: '0.5rem 1.5rem',
            background: '#e67e22', color: '#fff', border: 'none',
            borderRadius: '6px', cursor: 'pointer', fontWeight: 600,
          }}
        >
          {isResuming ? 'Resuming...' : 'Resume Pipeline'}
        </button>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
