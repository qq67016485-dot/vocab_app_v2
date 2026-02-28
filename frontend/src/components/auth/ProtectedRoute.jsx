import React from 'react';
import { Navigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';

export default function ProtectedRoute({ children, allowedRoles }) {
  const { user } = useUser();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // Redirect to the appropriate home for their role
    if (user.role === 'STUDENT') {
      return <Navigate to="/student/dashboard" replace />;
    }
    return <Navigate to="/teacher/command-center" replace />;
  }

  return children;
}
