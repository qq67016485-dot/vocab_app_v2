import React, { useState, useEffect } from 'react';
import apiClient from '../api/axiosConfig.js';

export default function WordSetForm({ onSave, onCancel, setToEdit }) {
  const [formData, setFormData] = useState({
    title: '', unit_or_chapter: '', description: '',
    curriculum_id: '', level_id: '', is_public: false,
  });
  const [categories, setCategories] = useState({ curriculums: [], levels: [] });
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchCategories = async () => {
      setIsLoadingCategories(true);
      try {
        const [curriculumsRes, levelsRes] = await Promise.all([
          apiClient.get('/curricula/'),
          apiClient.get('/levels/'),
        ]);
        setCategories({ curriculums: curriculumsRes.data, levels: levelsRes.data });
      } catch (err) {
        console.error("Error fetching categories:", err);
        setError("Could not load form data. Please try again.");
      } finally {
        setIsLoadingCategories(false);
      }
    };
    fetchCategories();
  }, []);

  useEffect(() => {
    if (setToEdit) {
      setFormData({
        title: setToEdit.title || '',
        unit_or_chapter: setToEdit.unit_or_chapter || '',
        description: setToEdit.description || '',
        curriculum_id: setToEdit.curriculum?.id || '',
        level_id: setToEdit.level?.id || '',
        is_public: setToEdit.is_public || false,
      });
    }
  }, [setToEdit]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError('');
    const payload = { ...formData };
    if (!payload.curriculum_id) delete payload.curriculum_id;
    if (!payload.level_id) delete payload.level_id;

    try {
      const response = setToEdit
        ? await apiClient.patch(`/word-sets/${setToEdit.id}/`, payload)
        : await apiClient.post('/word-sets/', payload);
      onSave(response.data);
    } catch (err) {
      console.error("Error saving word set:", err.response?.data);
      setError(err.response?.data?.detail || "An error occurred while saving.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderForm = () => {
    if (isLoadingCategories) return <p>Loading form...</p>;
    return (
      <form onSubmit={handleSubmit}>
        <label>Title*</label>
        <input name="title" value={formData.title} onChange={handleChange} required />
        <label>Unit or Chapter</label>
        <input name="unit_or_chapter" value={formData.unit_or_chapter} onChange={handleChange} />
        <label>Description</label>
        <textarea name="description" value={formData.description} onChange={handleChange} rows="3" />
        <label>Curriculum</label>
        <select name="curriculum_id" value={formData.curriculum_id} onChange={handleChange}>
          <option value="">-- Select --</option>
          {categories.curriculums.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label>Level</label>
        <select name="level_id" value={formData.level_id} onChange={handleChange}>
          <option value="">-- Select --</option>
          {categories.levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <div style={{ margin: '20px 0', display: 'flex', alignItems: 'center' }}>
          <input type="checkbox" name="is_public" id="is_public" checked={formData.is_public} onChange={handleChange} style={{ width: 'auto', marginRight: '10px' }} />
          <label htmlFor="is_public" style={{ margin: 0 }}>Make this set public (share with other teachers)</label>
        </div>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
          <button type="button" onClick={onCancel} className="logout-button" disabled={isSubmitting}>Cancel</button>
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Saving...' : (setToEdit ? 'Save Changes' : 'Create Set')}
          </button>
        </div>
      </form>
    );
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content">
        <h2>{setToEdit ? 'Edit Word Set' : 'Create New Word Set'}</h2>
        {renderForm()}
      </div>
    </div>
  );
}
