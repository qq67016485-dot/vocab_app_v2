import React from 'react';
import { Outlet } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext.jsx';
import Navbar from '../Navbar.jsx';
import ThemeSwitcher from '../ThemeSwitcher.jsx';

export default function StudentLayout() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="app-shell" data-app="student" data-theme={theme}>
      <Navbar />

      <div className="page-title page-title--with-theme">
        <h1>Vocabulary Learning App</h1>
        <ThemeSwitcher
          value={theme}
          onChange={setTheme}
          compact
          asButton
        />
      </div>

      <Outlet />
    </div>
  );
}
