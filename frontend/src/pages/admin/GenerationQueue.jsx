import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';

export default function GenerationQueue() {
  const navigate = useNavigate();
  const [queue, setQueue] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const res = await apiClient.get('/admin/generation-queue/');
        setQueue(res.data);
      } catch (err) { console.error('Error fetching generation queue:', err); }
      finally { setIsLoading(false); }
    };
    fetchQueue();
  }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  if (isLoading) return <p>Loading queue...</p>;

  return (
    <div>
      <div className="t-page-header">
        <h1 className="t-page-title">Generation Queue</h1>
        <button className="t-btn t-btn--secondary" onClick={() => navigate('/teacher/word-sets')}>Back to Word Sets</button>
      </div>

      {queue.length === 0 ? (
        <div className="t-empty">No pending generation requests.</div>
      ) : (
        <div className="t-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="t-table">
            <thead>
              <tr><th>Word Set</th><th>Requested By</th><th>Requested At</th><th>Words</th><th>Lexile</th><th>Action</th></tr>
            </thead>
            <tbody>
              {queue.map(item => (
                <tr key={item.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{item.title}</div>
                    {item.curriculum && <span className="t-hint">{item.curriculum}</span>}
                    {item.level && <span className="t-hint"> / {item.level}</span>}
                  </td>
                  <td>{item.requested_by || item.creator}</td>
                  <td><span className="t-mono" style={{ fontSize: '0.8rem' }}>{formatDate(item.requested_at)}</span></td>
                  <td><span className="ws-word-count">{item.word_count}</span></td>
                  <td><span className="ws-word-count">{item.target_lexile}</span></td>
                  <td><button className="t-btn t-btn--primary t-btn--sm" onClick={() => navigate(`/teacher/generate/${item.id}`)}>Generate</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
