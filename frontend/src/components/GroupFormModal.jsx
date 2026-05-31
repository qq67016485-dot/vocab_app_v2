import React, { useState, useEffect } from 'react';

export default function GroupFormModal({ isOpen, onClose, onSave, group, allStudents }) {
  const [formData, setFormData] = useState({ name: '', description: '', students: [] });
  const [error, setError] = useState('');

  useEffect(() => {
    if (group) {
      setFormData({ name: group.name || '', description: group.description || '', students: group.students.map(s => s.id) || [] });
    } else {
      setFormData({ name: '', description: '', students: [] });
    }
    setError('');
  }, [group, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleStudentToggle = (studentId) => {
    setFormData(prev => {
      const newStudents = prev.students.includes(studentId)
        ? prev.students.filter(id => id !== studentId)
        : [...prev.students, studentId];
      return { ...prev, students: newStudents };
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name.trim()) { setError('Group name is required.'); return; }
    setError('');
    onSave(formData);
  };

  if (!isOpen) return null;

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="t-modal">
        <div className="t-modal-title">{group ? 'Edit Group' : 'Create New Group'}</div>
        <form onSubmit={handleSubmit}>
          <div className="t-form-group">
            <label className="t-form-label">Group Name</label>
            <input className="t-form-input" type="text" name="name" value={formData.name} onChange={handleChange} required />
          </div>
          <div className="t-form-group">
            <label className="t-form-label">Description (Optional)</label>
            <textarea className="t-form-textarea" name="description" value={formData.description} onChange={handleChange} rows="3" />
          </div>
          <div className="t-form-group">
            <label className="t-form-label">Assign Students</label>
            <div className="t-checklist">
              {allStudents.length > 0 ? allStudents.map(student => (
                <div key={student.id} className="t-checklist-item">
                  <input type="checkbox" id={`student-${student.id}`}
                    checked={formData.students.includes(student.id)}
                    onChange={() => handleStudentToggle(student.id)} />
                  <label htmlFor={`student-${student.id}`}>{student.username}</label>
                </div>
              )) : <p className="t-hint">You have no students to assign.</p>}
            </div>
          </div>
          {error && (
            <div className="t-message t-message--error" style={{ marginTop: 8 }}>{error}</div>
          )}
          <div className="t-modal-actions">
            <button type="button" className="t-btn t-btn--secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="t-btn t-btn--primary">{group ? 'Save Changes' : 'Create Group'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
