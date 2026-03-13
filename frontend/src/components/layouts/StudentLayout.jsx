import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext.jsx';
import { useUser } from '../../context/UserContext.jsx';
import Navbar from '../Navbar.jsx';
import StudentNavbar from '../StudentNavbar.jsx';

export default function StudentLayout() {
  const { theme } = useTheme();
  const { user } = useUser();
  const location = useLocation();

  // Dashboard renders its own StudentNavbar internally (needs settings panel access)
  const isDashboard = location.pathname === '/student/dashboard' || location.pathname === '/student';

  // Practice and other student pages use StudentNavbar from the layout
  const isPractice = location.pathname.startsWith('/student/practice');

  const tierName = user?.tier_info?.name || 'Bronze';
  const level = user?.level || 1;
  const xpCurrent = user?.xp_in_current_level || 0;
  const xpNeeded = user?.xp_for_next_level || 200;
  const xpPercent = xpNeeded > 0 ? Math.min((xpCurrent / xpNeeded) * 100, 100) : 0;

  return (
    <div className="app-shell" data-app="student" data-theme={theme}>
      {isDashboard ? null : isPractice ? (
        <StudentNavbar
          username={user?.username}
          level={level}
          tierName={tierName}
          xpCurrent={xpCurrent}
          xpNeeded={xpNeeded}
          xpPercent={xpPercent}
          onSettingsClick={null}
        />
      ) : (
        <Navbar />
      )}
      <Outlet />
    </div>
  );
}
