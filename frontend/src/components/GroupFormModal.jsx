import React, { useState, useEffect } from 'react';

export default function GroupFormModal({ isOpen, onClose, onSave, group, allStudents }) {
  const [formData, setFormData] = useState({ name: '', description: '', students: [] });

  useEffect(() => {
    if (group) {
      setFormData({
        name: group.name || '',
        description: group.description || '',
        students: group.students.map(s => s.id) || [],
      });
    } else {
      setFormData({ name: '', description: '', students: [] });
    }
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
    if (!formData.name.trim()) { alert('Group name is required.'); return; }
    onSave(formData);
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-content">
        <h2>{group ? 'Edit Group' : 'Create New Group'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">Group Name</label>
            <input type="text" id="name" name="name" value={formData.name} onChange={handleChange} required />
          </div>
          <div className="form-group">
            <label htmlFor="description">Description (Optional)</label>
            <textarea id="description" name="description" value={formData.description} onChange={handleChange} rows="3"></textarea>
          </div>
          <div className="form-group">
            <label>Assign Students</label>
            <div className="student-checkbox-list">
              {allStudents.length > 0 ? (
                allStudents.map(student => (
                  <div key={student.id} className="checkbox-item">
                    <input type="checkbox" id={`student-${student.id}`}
                      checked={formData.students.includes(student.id)}
                      onChange={() => handleStudentToggle(student.id)} />
                    <label htmlFor={`student-${student.id}`}>{student.username}</label>
                  </div>
                ))
              ) : <p>You have no students to assign.</p>}
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>Cancel</button>
            <button type="submit">{group ? 'Save Changes' : 'Create Group'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
