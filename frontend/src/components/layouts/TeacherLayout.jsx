import React from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from '../Navbar.jsx';
import '../../styles/teacher.css';

export default function TeacherLayout() {
  return (
    <div className="teacher-portal">
      <Navbar />
      <div className="t-shell">
        <Outlet />
      </div>
    </div>
  );
}
