import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useUser } from './context/UserContext.jsx';
import ProtectedRoute from './components/auth/ProtectedRoute.jsx';
import StudentLayout from './components/layouts/StudentLayout.jsx';
import TeacherLayout from './components/layouts/TeacherLayout.jsx';
import Login from './components/Login.jsx';

import StudentDashboard from './pages/student/StudentDashboard.jsx';
import PracticeView from './pages/student/PracticeView.jsx';
import InstructionalFlow from './pages/student/InstructionalFlow.jsx';
import LearningPatternsView from './pages/shared/LearningPatternsView.jsx';

import CommandCenter from './pages/teacher/CommandCenter.jsx';
import WordSetListView from './pages/teacher/WordSetListView.jsx';
import WordSetDetailView from './pages/teacher/WordSetDetailView.jsx';
import GroupManagementView from './pages/teacher/GroupManagementView.jsx';
import StudentProgressDashboard from './pages/teacher/StudentProgressDashboard.jsx';

import './styles/main.css';
import './styles/students.css';

function RoleRedirect() {
  const { user } = useUser();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'STUDENT') return <Navigate to="/student/dashboard" replace />;
  return <Navigate to="/teacher/command-center" replace />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* Student routes */}
        <Route
          path="/student"
          element={
            <ProtectedRoute allowedRoles={['STUDENT']}>
              <StudentLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<StudentDashboard />} />
          <Route path="practice" element={<PracticeView />} />
          <Route path="learning-patterns" element={<LearningPatternsView />} />
          <Route path="instructional/:packId" element={<InstructionalFlow />} />
        </Route>

        {/* Teacher / Admin routes */}
        <Route
          path="/teacher"
          element={
            <ProtectedRoute allowedRoles={['TEACHER', 'ADMIN']}>
              <TeacherLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="command-center" replace />} />
          <Route path="command-center" element={<CommandCenter />} />
          <Route path="word-sets" element={<WordSetListView />} />
          <Route path="word-sets/:setId" element={<WordSetDetailView />} />
          <Route path="groups" element={<GroupManagementView />} />
          <Route path="students/:studentId/progress" element={<StudentProgressDashboard />} />
          <Route path="students/:studentId/patterns" element={<LearningPatternsView />} />
        </Route>

        {/* Root — redirect by role */}
        <Route path="/" element={<RoleRedirect />} />
        <Route path="*" element={<RoleRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
