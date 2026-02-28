import React from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from '../Navbar.jsx';

export default function TeacherLayout() {
  return (
    <div className="cc-shell">
      <Navbar />
      <Outlet />
    </div>
  );
}
