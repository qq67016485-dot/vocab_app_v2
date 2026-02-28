import React, { useState } from 'react';
import apiClient from '../api/axiosConfig.js';

const MAX_STUDENTS = 10;

export default function BulkStudentFormModal({ isOpen, onClose, onSuccess, groups = [] }) {
  const createInitialRow = () => ({ id: Date.now(), username: '', password: '', group_name: '' });
  const [students, setStudents] = useState([createInitialRow()]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAddRow = () => {
    if (students.length < MAX_STUDENTS) {
      setStudents([...students, createInitialRow()]);
    }
  };

  const handleRemoveRow = (id) => {
    if (students.length > 1) {
      setStudents(students.filter(s => s.id !== id));
    }
  };

  const handleInputChange = (id, field, value) => {
    setStudents(students.map(s => s.id === id ? { ...s, [field]: value } : s));
  };

  const handleReset = () => {
    setStudents([createInitialRow()]);
    setError('');
    setIsLoading(false);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const studentsToSubmit = students
      .map(({ username, password, group_name }) => ({
        username: username.trim(),
        password: password.trim(),
        group_name: group_name.trim(),
      }))
      .filter(s => s.username && s.password);

    if (studentsToSubmit.length === 0) {
      setError('Please fill out at least one student row.');
      setIsLoading(false);
      return;
    }

    try {
      const response = await apiClient.post('/teacher/students/bulk/', studentsToSubmit);
      alert(`Successfully created ${response.data.success_count} new student(s)!`);
      onSuccess();
      handleReset();
    } catch (err) {
      const errorMsg = err.response?.data?.error || 'An unknown error occurred. No students were created.';
      setError(errorMsg);
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-content" style={{ maxWidth: '800px' }}>
        <h2>Add Multiple Students</h2>
        <p>Fill out the form below. Any empty rows will be ignored. You can assign to an existing group or type a new name to create a new group automatically.</p>
        <form onSubmit={handleSubmit}>
          <div className="bulk-form-container">
            {students.map((student) => (
              <div key={student.id} className="bulk-form-row">
                <input type="text" placeholder="Username *" value={student.username} onChange={e => handleInputChange(student.id, 'username', e.target.value)} />
                <input type="password" placeholder="Password *" value={student.password} onChange={e => handleInputChange(student.id, 'password', e.target.value)} />
                <select value={student.group_name} onChange={e => handleInputChange(student.id, 'group_name', e.target.value)}>
                  <option value="">No Group</option>
                  {groups.map(group => <option key={group.id} value={group.name}>{group.name}</option>)}
                </select>
                <button type="button" className="remove-row-btn" onClick={() => handleRemoveRow(student.id)} disabled={students.length <= 1}>
                  &times;
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="secondary-button" onClick={handleAddRow} disabled={students.length >= MAX_STUDENTS}>
            + Add Another Student
          </button>
          {error && <div className="message-box error" style={{ marginTop: '1rem' }}>{error}</div>}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={handleReset} disabled={isLoading}>Cancel</button>
            <button type="submit" disabled={isLoading}>
              {isLoading ? 'Creating...' : `Create ${students.filter(s => s.username && s.password).length} Student(s)`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
