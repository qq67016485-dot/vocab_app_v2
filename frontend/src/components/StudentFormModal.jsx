import React, { useState, useEffect } from 'react';

export default function StudentFormModal({ isOpen, onClose, onSave, studentToEdit, groups }) {
  const isEditing = !!studentToEdit;

  const getInitialState = () => ({
    username: '',
    password: '',
    group_id: '',
    daily_question_limit: 20,
    lexile_min: 0,
    lexile_max: 1200,
  });

  const [formData, setFormData] = useState(getInitialState());
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      if (isEditing && studentToEdit) {
        setFormData({
          username: studentToEdit.username || '',
          password: '',
          group_id: '',
          daily_question_limit: studentToEdit.daily_question_limit || 20,
          lexile_min: studentToEdit.lexile_min || 0,
          lexile_max: studentToEdit.lexile_max || 1200,
        });
      } else {
        setFormData(getInitialState());
      }
      setError('');
    }
  }, [isOpen, studentToEdit, isEditing]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    const processedValue = e.target.type === 'number' ? parseInt(value, 10) : value;
    setFormData({ ...formData, [name]: processedValue });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isEditing && !formData.password) {
      setError('Password is required for new students.');
      return;
    }
    const dataToSave = { ...formData };
    if (!dataToSave.password) delete dataToSave.password;
    if (dataToSave.group_id === '') dataToSave.group_id = null;
    onSave(dataToSave);
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-content">
        <h2>{isEditing ? `Edit ${studentToEdit.username}` : 'Add New Student'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input type="text" id="username" name="username" value={formData.username} onChange={handleChange} required readOnly={isEditing} />
          </div>
          <div className="form-group">
            <label htmlFor="password">{isEditing ? 'Reset Password (optional)' : 'Password'}</label>
            <input type="password" id="password" name="password" value={formData.password} onChange={handleChange} placeholder={isEditing ? 'Leave blank to keep current' : ''} />
          </div>
          <div className="form-group">
            <label htmlFor="group_id">Assign to Group (optional)</label>
            <select id="group_id" name="group_id" value={formData.group_id} onChange={handleChange}>
              <option value="">No Group</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1rem', marginTop: '1.5rem' }}>
            <h4 style={{ marginTop: '0', marginBottom: '1rem' }}>Learning Settings</h4>
            <div className="form-group">
              <label htmlFor="daily_question_limit">Daily Question Limit</label>
              <input type="number" id="daily_question_limit" name="daily_question_limit" value={formData.daily_question_limit} onChange={handleChange} min="5" step="5" required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label htmlFor="lexile_min">Lexile Min</label>
                <input type="number" id="lexile_min" name="lexile_min" value={formData.lexile_min} onChange={handleChange} step="10" required />
              </div>
              <div className="form-group">
                <label htmlFor="lexile_max">Lexile Max</label>
                <input type="number" id="lexile_max" name="lexile_max" value={formData.lexile_max} onChange={handleChange} step="10" required />
              </div>
            </div>
          </div>
          {error && <p className="error-message" style={{ color: 'red' }}>{error}</p>}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>Cancel</button>
            <button type="submit">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}
