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
      } catch (err) {
        console.error('Error fetching generation queue:', err);
      } finally {
        setIsLoading(false);
      }
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Generation Queue</h2>
        <button onClick={() => navigate('/teacher/word-sets')}>Back to Word Sets</button>
      </div>

      {queue.length === 0 ? (
        <p style={{ color: '#666' }}>No pending generation requests.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e1e1e1', textAlign: 'left' }}>
              <th style={{ padding: '10px' }}>Word Set</th>
              <th style={{ padding: '10px' }}>Requested By</th>
              <th style={{ padding: '10px' }}>Requested At</th>
              <th style={{ padding: '10px' }}>Words</th>
              <th style={{ padding: '10px' }}>Lexile</th>
              <th style={{ padding: '10px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {queue.map(item => (
              <tr key={item.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px' }}>
                  <div style={{ fontWeight: 'bold' }}>{item.title}</div>
                  {item.curriculum && <small style={{ color: '#666' }}>{item.curriculum}</small>}
                  {item.level && <small style={{ color: '#666' }}> / {item.level}</small>}
                </td>
                <td style={{ padding: '10px' }}>{item.requested_by || item.creator}</td>
                <td style={{ padding: '10px' }}>{formatDate(item.requested_at)}</td>
                <td style={{ padding: '10px' }}>{item.word_count}</td>
                <td style={{ padding: '10px' }}>{item.target_lexile}</td>
                <td style={{ padding: '10px' }}>
                  <button onClick={() => navigate(`/teacher/generate/${item.id}`)}
                    style={{ background: '#7c3aed', color: '#fff' }}>
                    Generate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}