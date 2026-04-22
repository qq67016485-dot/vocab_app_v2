import React, { useState, useEffect } from 'react';
import apiClient from '../api/axiosConfig.js';
import SearchableSelect from './SearchableSelect.jsx';

export default function WordSetForm({ onSave, onCancel, setToEdit }) {
  const [formData, setFormData] = useState({
    title: '', description: '',
    curriculum_id: '', level_id: '', is_public: false,
    target_lexile: 650,
    input_words_text: '', input_source_title: '', input_source_chapter: '',
    custom_curriculum_name: '', custom_level_name: '',
  });
  const [categories, setCategories] = useState({ curriculums: [] });
  const [availableLevels, setAvailableLevels] = useState([]);
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
        setCategories({ curriculums: curriculumsRes.data });
        setAvailableLevels(levelsRes.data);
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
      const wordsText = Array.isArray(setToEdit.input_words)
        ? setToEdit.input_words.join('\n')
        : '';
      setFormData({
        title: setToEdit.title || '',
        description: setToEdit.description || '',
        curriculum_id: setToEdit.curriculum?.id || '',
        level_id: setToEdit.level?.id || '',
        is_public: setToEdit.is_public || false,
        target_lexile: setToEdit.target_lexile || 650,
        input_words_text: wordsText,
        input_source_title: setToEdit.input_source_title || '',
        input_source_chapter: setToEdit.input_source_chapter || '',
        custom_curriculum_name: '', custom_level_name: '',
      });
    }
  }, [setToEdit]);

  // When curriculum changes, reload levels filtered to that curriculum
  useEffect(() => {
    const fetchLevels = async () => {
      const cid = formData.curriculum_id;
      const url = cid && cid !== '__other__' ? `/levels/?curriculum_id=${cid}` : '/levels/';
      try {
        const res = await apiClient.get(url);
        setAvailableLevels(res.data);
      } catch (err) {
        console.error('Error fetching levels:', err);
      }
    };
    fetchLevels();
  }, [formData.curriculum_id]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError('');
    const wordList = formData.input_words_text.split(/[\n,]+/).map(w => w.trim()).filter(Boolean);
    const payload = {
      title: formData.title, description: formData.description, is_public: formData.is_public,
      target_lexile: parseInt(formData.target_lexile, 10) || 650,
      input_words: wordList.length > 0 ? wordList : null,
      input_source_title: formData.input_source_title, input_source_chapter: formData.input_source_chapter,
    };
    if (formData.curriculum_id === '__other__') {
      if (formData.custom_curriculum_name.trim()) payload.curriculum_name = formData.custom_curriculum_name.trim();
    } else if (formData.curriculum_id) {
      payload.curriculum_id = formData.curriculum_id;
    }
    if (formData.level_id === '__other__') {
      if (formData.custom_level_name.trim()) payload.level_name = formData.custom_level_name.trim();
    } else if (formData.level_id) {
      payload.level_id = formData.level_id;
    }
    try {
      const response = setToEdit
        ? await apiClient.patch(`/word-sets/${setToEdit.id}/`, payload)
        : await apiClient.post('/word-sets/', payload);
      onSave(response.data);
    } catch (err) {
      console.error("Error saving word set:", err.response?.data);
      setError(err.response?.data?.detail || "An error occurred while saving.");
    } finally { setIsSubmitting(false); }
  };

  if (isLoadingCategories) {
    return (
      <div className="t-modal-backdrop">
        <div className="t-modal"><p>Loading form...</p></div>
      </div>
    );
  }

  const isLocked = setToEdit && (setToEdit.generation_status === 'GENERATING' || setToEdit.generation_status === 'GENERATED');

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="t-modal">
        <div className="t-modal-title">{setToEdit ? 'Edit Word Set' : 'Create New Word Set'}</div>
        <form onSubmit={handleSubmit}>
          <div className="t-form-row">
            <div className="t-form-group">
              <label className="t-form-label">Word Set Name *</label>
              <input className="t-form-input" name="title" value={formData.title} onChange={handleChange} required />
            </div>
            {!isLocked && (
              <div className="t-form-group">
                <label className="t-form-label">Target Lexile *</label>
                <input className="t-form-input" type="number" name="target_lexile" value={formData.target_lexile} onChange={handleChange} min="100" max="2000" required />
              </div>
            )}
          </div>
          {!isLocked && (
            <>
              <div className="t-form-row">
                <div className="t-form-group">
                  <label className="t-form-label">Source Book Title</label>
                  <input className="t-form-input" name="input_source_title" value={formData.input_source_title} onChange={handleChange} placeholder="e.g., Charlotte's Web" />
                </div>
                <div className="t-form-group">
                  <label className="t-form-label">Source Book Chapter</label>
                  <input className="t-form-input" name="input_source_chapter" value={formData.input_source_chapter} onChange={handleChange} placeholder="e.g., Chapter 3" />
                </div>
              </div>
              <div className="t-form-row">
                <div className="t-form-group">
                  <label className="t-form-label">Program or Series</label>
                  <SearchableSelect
                    options={categories.curriculums}
                    value={formData.curriculum_id}
                    onChange={(id) => setFormData(prev => ({ ...prev, curriculum_id: id, level_id: '', custom_level_name: '' }))}
                    customValue={formData.custom_curriculum_name}
                    onCustomChange={(v) => setFormData(prev => ({ ...prev, custom_curriculum_name: v }))}
                    placeholder="Search or select..."
                    customPlaceholder="e.g., Wonders, Reading A to Z"
                  />
                </div>
                <div className="t-form-group">
                  <label className="t-form-label">Grade or Level</label>
                  <SearchableSelect
                    options={availableLevels}
                    value={formData.level_id}
                    onChange={(id) => setFormData(prev => ({ ...prev, level_id: id }))}
                    customValue={formData.custom_level_name}
                    onCustomChange={(v) => setFormData(prev => ({ ...prev, custom_level_name: v }))}
                    placeholder="Search or select..."
                    customPlaceholder="e.g., Grade 4, Level Q"
                  />
                </div>
              </div>
              <div className="t-form-group">
                <label className="t-form-label">Words (one per line or comma-separated)</label>
                <textarea className="t-form-textarea" name="input_words_text" value={formData.input_words_text} onChange={handleChange} rows="8" placeholder="campaign&#10;philosophy&#10;dedicate" />
                {formData.input_words_text.trim() && (
                  <div className="t-form-hint">{formData.input_words_text.split(/[\n,]+/).map(w => w.trim()).filter(Boolean).length} word(s)</div>
                )}
              </div>
            </>
          )}
          <div className="t-form-group">
            <label className="t-form-label">Teacher's Notes</label>
            <textarea className="t-form-textarea" name="description" value={formData.description} onChange={handleChange} rows="2" placeholder="e.g., Focus on academic vocabulary from the science unit." />
          </div>
          <label className="t-form-checkbox">
            <input type="checkbox" name="is_public" checked={formData.is_public} onChange={handleChange} />
            Make this set public (share with other teachers)
          </label>
          {error && <p style={{ color: 'var(--t-danger)', fontSize: '0.85rem' }}>{error}</p>}
          <div className="t-modal-actions">
            <button type="button" className="t-btn t-btn--secondary" onClick={onCancel} disabled={isSubmitting}>Cancel</button>
            <button type="submit" className="t-btn t-btn--primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : (setToEdit ? 'Save Changes' : 'Create Set')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
