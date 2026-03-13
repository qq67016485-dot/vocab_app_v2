import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext.jsx';
import Navbar from '../Navbar.jsx';

export default function StudentLayout() {
  const { theme } = useTheme();
  const location = useLocation();

  // Dashboard has its own navbar, so hide the old one there
  const isDashboard = location.pathname === '/student/dashboard' || location.pathname === '/student';

  return (
    <div className="app-shell" data-app="student" data-theme={theme}>
      {!isDashboard && <Navbar />}
      <Outlet />
    </div>
  );
}
