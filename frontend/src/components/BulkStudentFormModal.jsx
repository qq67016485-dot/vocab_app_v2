import React, { useState } from 'react';
import apiClient from '../api/axiosConfig.js';

const MAX_STUDENTS = 10;

export default function BulkStudentFormModal({ isOpen, onClose, onSuccess, groups = [] }) {
  const createInitialRow = () => ({ id: Date.now(), username: '', password: '', first_name: '', last_name: '', group_name: '' });
  const [students, setStudents] = useState([createInitialRow()]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAddRow = () => { if (students.length < MAX_STUDENTS) setStudents([...students, createInitialRow()]); };
  const handleRemoveRow = (id) => { if (students.length > 1) setStudents(students.filter(s => s.id !== id)); };
  const handleInputChange = (id, field, value) => { setStudents(students.map(s => s.id === id ? { ...s, [field]: value } : s)); };

  const handleReset = () => { setStudents([createInitialRow()]); setError(''); setIsLoading(false); onClose(); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    const studentsToSubmit = students
      .map(({ username, password, first_name, last_name, group_name }) => ({ username: username.trim(), password: password.trim(), first_name: first_name.trim(), last_name: last_name.trim(), group_name: group_name.trim() }))
      .filter(s => s.username && s.password);
    if (studentsToSubmit.length === 0) { setError('Please fill out at least one student row.'); setIsLoading(false); return; }
    try {
      const response = await apiClient.post('/teacher/students/bulk/', studentsToSubmit);
      alert(`Successfully created ${response.data.success_count} new student(s)!`);
      onSuccess();
      handleReset();
    } catch (err) {
      setError(err.response?.data?.error || 'An unknown error occurred. No students were created.');
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && handleReset()}>
      <div className="t-modal t-modal--wide">
        <div className="t-modal-title">Add Multiple Students</div>
        <p className="t-hint" style={{ marginBottom: 12 }}>Fill out the form below. Empty rows will be ignored. Type a new group name to create it automatically.</p>
        <form onSubmit={handleSubmit}>
          <div className="t-bulk-container">
            {students.map((student) => (
              <div key={student.id} className="t-bulk-row">
                <input className="t-form-input" type="text" placeholder="Username *" value={student.username} onChange={e => handleInputChange(student.id, 'username', e.target.value)} />
                <input className="t-form-input" type="password" placeholder="Password *" value={student.password} onChange={e => handleInputChange(student.id, 'password', e.target.value)} />
                <input className="t-form-input" type="text" placeholder="First Name" value={student.first_name} onChange={e => handleInputChange(student.id, 'first_name', e.target.value)} />
                <input className="t-form-input" type="text" placeholder="Last Name" value={student.last_name} onChange={e => handleInputChange(student.id, 'last_name', e.target.value)} />
                <select className="t-form-select" value={student.group_name} onChange={e => handleInputChange(student.id, 'group_name', e.target.value)}>
                  <option value="">No Group</option>
                  {groups.map(group => <option key={group.id} value={group.name}>{group.name}</option>)}
                </select>
                <button type="button" className="t-bulk-remove" onClick={() => handleRemoveRow(student.id)} disabled={students.length <= 1}>&times;</button>
              </div>
            ))}
          </div>
          <button type="button" className="t-btn t-btn--secondary t-btn--sm" onClick={handleAddRow} disabled={students.length >= MAX_STUDENTS}>+ Add Another Student</button>
          {error && <div className="t-message t-message--error" style={{ marginTop: 12 }}>{error}</div>}
          <div className="t-modal-actions">
            <button type="button" className="t-btn t-btn--secondary" onClick={handleReset} disabled={isLoading}>Cancel</button>
            <button type="submit" className="t-btn t-btn--primary" disabled={isLoading}>
              {isLoading ? 'Creating...' : `Create ${students.filter(s => s.username && s.password).length} Student(s)`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
