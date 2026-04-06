import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '../context/UserContext.jsx';
import apiClient from '../api/axiosConfig.js';
import LevelProgressBar from './LevelProgressBar.jsx';

export default function Navbar() {
  const { user, logoutUser } = useUser();
  const navigate = useNavigate();
  const [queueCount, setQueueCount] = useState(0);

  useEffect(() => {
    if (user?.role !== 'ADMIN') return;
    const fetchCount = async () => {
      try {
        const res = await apiClient.get('/admin/generation-queue/');
        setQueueCount(res.data.length);
      } catch (err) {
        console.error('Failed to fetch generation queue:', err);
      }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 60_000);
    return () => clearInterval(interval);
  }, [user?.role]);

  const handleLogoutClick = async () => {
    try {
      await logoutUser();
      navigate('/login');
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  const handleNavigateHome = () => {
    if (user?.role === 'STUDENT') {
      navigate('/student/dashboard');
    } else {
      navigate('/teacher/command-center');
    }
  };

  if (!user) {
    return null;
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        Vocabulary App
      </div>

      {user.role === 'STUDENT' && <LevelProgressBar />}

      <div className="navbar-user">
        <span>Welcome, {user.username}!</span>

        {user.role === 'ADMIN' && queueCount > 0 && (
          <button className="navbar-button" onClick={() => navigate('/teacher/generation-queue')}
            style={{ position: 'relative' }}>
            Generation Queue
            <span style={{
              position: 'absolute', top: '-6px', right: '-6px',
              background: '#dc2626', color: '#fff', borderRadius: '50%',
              width: '20px', height: '20px', fontSize: '0.75rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {queueCount}
            </span>
          </button>
        )}

        {(user.role === 'TEACHER' || user.role === 'ADMIN') && (
          <button className="navbar-button" onClick={handleNavigateHome}>
            Back to Home
          </button>
        )}

        <button onClick={handleLogoutClick} className="logout-button">
          Logout
        </button>
      </div>
    </nav>
  );
}
