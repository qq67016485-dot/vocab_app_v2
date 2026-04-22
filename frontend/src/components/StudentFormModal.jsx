import React, { useState, useEffect } from 'react';

export default function StudentFormModal({ isOpen, onClose, onSave, studentToEdit, groups }) {
  const isEditing = !!studentToEdit;
  const getInitialState = () => ({ username: '', password: '', first_name: '', last_name: '', group_id: '', daily_goal_min: 20, daily_question_limit: 30, daily_goal_max: 50, lexile_min: 0, lexile_max: 1200 });
  const [formData, setFormData] = useState(getInitialState());
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      if (isEditing && studentToEdit) {
        setFormData({ username: studentToEdit.username || '', password: '', first_name: studentToEdit.first_name || '', last_name: studentToEdit.last_name || '', group_id: '', daily_goal_min: studentToEdit.daily_goal_min ?? 20, daily_question_limit: studentToEdit.daily_question_limit || 30, daily_goal_max: studentToEdit.daily_goal_max ?? 50, lexile_min: studentToEdit.lexile_min || 0, lexile_max: studentToEdit.lexile_max || 1200 });
      } else { setFormData(getInitialState()); }
      setError('');
    }
  }, [isOpen, studentToEdit, isEditing]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: e.target.type === 'number' ? parseInt(value, 10) : value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isEditing && !formData.password) { setError('Password is required for new students.'); return; }
    if (formData.daily_goal_min > formData.daily_goal_max) { setError('Goal min cannot exceed goal max.'); return; }
    if (formData.daily_question_limit < formData.daily_goal_min || formData.daily_question_limit > formData.daily_goal_max) { setError('Daily question limit must be between goal min and max.'); return; }
    const dataToSave = { ...formData };
    if (!dataToSave.password) delete dataToSave.password;
    if (dataToSave.group_id === '') dataToSave.group_id = null;
    onSave(dataToSave);
  };

  if (!isOpen) return null;

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="t-modal">
        <div className="t-modal-title">{isEditing ? `Edit ${studentToEdit.username}` : 'Add New Student'}</div>
        <form onSubmit={handleSubmit}>
          <div className="t-form-group">
            <label className="t-form-label">Username</label>
            <input className="t-form-input" type="text" name="username" value={formData.username} onChange={handleChange} required readOnly={isEditing} />
          </div>
          <div className="t-form-row">
            <div className="t-form-group">
              <label className="t-form-label">First Name</label>
              <input className="t-form-input" type="text" name="first_name" value={formData.first_name} onChange={handleChange} placeholder="e.g., Alex" />
            </div>
            <div className="t-form-group">
              <label className="t-form-label">Last Name</label>
              <input className="t-form-input" type="text" name="last_name" value={formData.last_name} onChange={handleChange} placeholder="e.g., Chen" />
            </div>
          </div>
          <div className="t-form-group">
            <label className="t-form-label">{isEditing ? 'Reset Password (optional)' : 'Password'}</label>
            <input className="t-form-input" type="password" name="password" value={formData.password} onChange={handleChange} placeholder={isEditing ? 'Leave blank to keep current' : ''} />
          </div>
          <div className="t-form-group">
            <label className="t-form-label">Assign to Group (optional)</label>
            <select className="t-form-select" name="group_id" value={formData.group_id} onChange={handleChange}>
              <option value="">No Group</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div style={{ borderTop: '1px solid var(--t-border-light)', paddingTop: 12, marginTop: 16 }}>
            <div className="t-form-label" style={{ marginBottom: 10, fontSize: '0.78rem' }}>Daily Practice Goal</div>
            <div className="t-form-row">
              <div className="t-form-group">
                <label className="t-form-label">Goal Min</label>
                <input className="t-form-input" type="number" name="daily_goal_min" value={formData.daily_goal_min} onChange={handleChange} min="10" step="5" required />
              </div>
              <div className="t-form-group">
                <label className="t-form-label">Baseline</label>
                <input className="t-form-input" type="number" name="daily_question_limit" value={formData.daily_question_limit} onChange={handleChange} min="10" step="5" required />
              </div>
              <div className="t-form-group">
                <label className="t-form-label">Goal Max</label>
                <input className="t-form-input" type="number" name="daily_goal_max" value={formData.daily_goal_max} onChange={handleChange} min="10" step="5" required />
              </div>
            </div>
            <div className="t-form-label" style={{ marginBottom: 10, marginTop: 8, fontSize: '0.78rem' }}>Lexile Range</div>
            <div className="t-form-row">
              <div className="t-form-group">
                <label className="t-form-label">Lexile Min</label>
                <input className="t-form-input" type="number" name="lexile_min" value={formData.lexile_min} onChange={handleChange} step="10" required />
              </div>
              <div className="t-form-group">
                <label className="t-form-label">Lexile Max</label>
                <input className="t-form-input" type="number" name="lexile_max" value={formData.lexile_max} onChange={handleChange} step="10" required />
              </div>
            </div>
          </div>
          {error && <p style={{ color: 'var(--t-danger)', fontSize: '0.85rem' }}>{error}</p>}
          <div className="t-modal-actions">
            <button type="button" className="t-btn t-btn--secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="t-btn t-btn--primary">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}
