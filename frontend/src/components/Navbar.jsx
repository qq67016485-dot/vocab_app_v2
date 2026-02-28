import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '../context/UserContext.jsx';
import LevelProgressBar from './LevelProgressBar.jsx';

export default function Navbar() {
  const { user, logoutUser } = useUser();
  const navigate = useNavigate();

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
