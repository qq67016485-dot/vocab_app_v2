import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUser } from '../context/UserContext.jsx';
import apiClient from '../api/axiosConfig.js';
import LevelProgressBar from './LevelProgressBar.jsx';

export default function Navbar() {
  const { user, logoutUser } = useUser();
  const navigate = useNavigate();
  const location = useLocation();
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

  if (!user) return null;

  // Student navbar (unchanged)
  if (user.role === 'STUDENT') {
    return (
      <nav className="navbar">
        <div className="navbar-brand">Vocabulary App</div>
        <LevelProgressBar />
        <div className="navbar-user">
          <span>Welcome, {user.username}!</span>
          <button onClick={() => navigate('/student/dashboard')} className="navbar-button">Back to Home</button>
          <button onClick={handleLogoutClick} className="logout-button">Logout</button>
        </div>
      </nav>
    );
  }

  // Teacher/Admin navbar — new design
  const isActive = (path) => location.pathname.startsWith(path);

  return (
    <nav className="t-navbar">
      <div className="t-navbar-brand">Vocab<span>App</span></div>
      <button
        className={`t-nav-link${isActive('/teacher/command-center') ? ' t-nav-link--active' : ''}`}
        onClick={() => navigate('/teacher/command-center')}
      >
        Command Center
      </button>
      <button
        className={`t-nav-link${isActive('/teacher/word-sets') ? ' t-nav-link--active' : ''}`}
        onClick={() => navigate('/teacher/word-sets')}
      >
        Word Sets
      </button>
      <button
        className={`t-nav-link${isActive('/teacher/groups') ? ' t-nav-link--active' : ''}`}
        onClick={() => navigate('/teacher/groups')}
      >
        Groups
      </button>
      <div className="t-navbar-spacer" />
      <div className="t-navbar-user">
        {user.role === 'ADMIN' && (
          <button className="t-navbar-queue" onClick={() => navigate('/teacher/llm-config')} style={{ marginRight: '0.5rem' }}>
            LLM Config
          </button>
        )}
        {user.role === 'ADMIN' && queueCount > 0 && (
          <button className="t-navbar-queue" onClick={() => navigate('/teacher/generation-queue')}>
            Gen Queue
            <span className="t-queue-badge">{queueCount}</span>
          </button>
        )}
        <span>{user.username}</span>
        <button onClick={handleLogoutClick} className="t-navbar-logout">Logout</button>
      </div>
    </nav>
  );
}
