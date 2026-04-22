import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import WordSetForm from '../../components/WordSetForm.jsx';
import AssignSetForm from '../../components/AssignSetForm.jsx';

const TABS = [
  { key: 'mine', label: 'My Sets' },
  { key: 'bookmarked', label: 'Bookmarked' },
  { key: 'public', label: 'Public' },
  { key: 'all', label: 'All' },
];

const STATUS_BADGE = {
  DRAFT: { label: 'Draft', cls: 't-badge--draft' },
  TO_GENERATE: { label: 'To Generate', cls: 't-badge--to-generate' },
  GENERATION_REQUESTED: { label: 'Requested', cls: 't-badge--requested' },
  GENERATING: { label: 'Generating...', cls: 't-badge--generating' },
  GENERATED: { label: 'Generated', cls: 't-badge--generated' },
};

export default function WordSetListView() {
  const { user } = useUser();
  const navigate = useNavigate();

  const [wordSets, setWordSets] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [students, setStudents] = useState([]);
  const [groups, setGroups] = useState([]);
  const [curriculums, setCurriculums] = useState([]);
  const [levels, setLevels] = useState([]);

  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCurriculumId, setFilterCurriculumId] = useState('all');
  const [filterLevelId, setFilterLevelId] = useState('all');

  const [showEditForm, setShowEditForm] = useState(false);
  const [setToEdit, setSetToEdit] = useState(null);
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [setToAssign, setSetToAssign] = useState(null);
  const [toast, setToast] = useState(null);

  const fetchInitialData = async () => {
    setIsLoading(true);
    try {
      const [setsRes, studentsRes, groupsRes, curriculumsRes, levelsRes] = await Promise.all([
        apiClient.get('/word-sets/'),
        apiClient.get('/teacher/students/'),
        apiClient.get('/groups/'),
        apiClient.get('/curricula/'),
        apiClient.get('/levels/'),
      ]);
      setWordSets(setsRes.data);
      setStudents(studentsRes.data);
      setGroups(groupsRes.data);
      setCurriculums(curriculumsRes.data);
      setLevels(levelsRes.data);
    } catch (err) {
      console.error("Error fetching initial data:", err);
      setError('Could not load data. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const refetchWordSets = async () => {
    try {
      const response = await apiClient.get('/word-sets/');
      setWordSets(response.data);
    } catch (err) {
      console.error("Error refetching word sets:", err);
    }
  };

  useEffect(() => { fetchInitialData(); }, []);

  const handleCreateClick = () => { setSetToEdit(null); setShowEditForm(true); };
  const handleEditClick = (set) => { setSetToEdit(set); setShowEditForm(true); };
  const handleAssignClick = (set) => { setSetToAssign(set); setShowAssignForm(true); };

  const handleDeleteClick = async (setId, setTitle) => {
    if (window.confirm(`Are you sure you want to delete the set "${setTitle}"? This cannot be undone.`)) {
      try {
        await apiClient.delete(`/word-sets/${setId}/`);
        refetchWordSets();
      } catch (err) {
        console.error("Error deleting word set:", err);
        setError("Could not delete the word set. Please try again.");
      }
    }
  };

  const handleSaveSuccess = () => { setShowEditForm(false); setSetToEdit(null); refetchWordSets(); };
  const handleAssignSuccess = (successMessage) => {
    setShowAssignForm(false);
    setSetToAssign(null);
    setToast({ type: 'success', text: successMessage });
    setTimeout(() => setToast(null), 5000);
  };
  const handleCancel = () => { setShowEditForm(false); setShowAssignForm(false); setSetToEdit(null); setSetToAssign(null); };

  const handleToggleBookmark = useCallback(async (setId) => {
    try {
      const res = await apiClient.post(`/word-sets/${setId}/bookmark/`);
      setWordSets(prev => prev.map(s =>
        s.id === setId ? { ...s, is_bookmarked: res.data.is_bookmarked } : s
      ));
    } catch (err) {
      console.error('Error toggling bookmark:', err);
    }
  }, []);

  const filteredWordSets = useMemo(() => {
    return wordSets.filter(set => {
      if (activeTab === 'mine' && set.creator_username !== user.username) return false;
      if (activeTab === 'bookmarked' && !set.is_bookmarked) return false;
      if (activeTab === 'public' && (!set.is_public || set.creator_username === user.username)) return false;
      if (searchQuery && !set.title.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      if (filterCurriculumId !== 'all' && set.curriculum?.id !== Number(filterCurriculumId)) return false;
      if (filterLevelId !== 'all' && set.level?.id !== Number(filterLevelId)) return false;
      return true;
    });
  }, [wordSets, activeTab, searchQuery, filterCurriculumId, filterLevelId, user.username]);

  if (isLoading) return <p>Loading Word Sets...</p>;
  if (error) return <p style={{ color: 'var(--t-danger)' }}>{error}</p>;

  return (
    <div>
      {toast && <div className={`t-toast t-toast--${toast.type}`}>{toast.text}</div>}
      {showEditForm && <WordSetForm onSave={handleSaveSuccess} onCancel={handleCancel} setToEdit={setToEdit} />}
      {showAssignForm && (
        <AssignSetForm wordSet={setToAssign} students={students} groups={groups}
          onSuccess={handleAssignSuccess} onCancel={handleCancel} />
      )}

      <div className="t-page-header">
        <h1 className="t-page-title">Word Sets</h1>
        <button className="t-btn t-btn--primary" onClick={handleCreateClick}>+ Create New Set</button>
      </div>

      <div className="t-tabs">
        {TABS.map(tab => (
          <button key={tab.key}
            className={`t-tab${activeTab === tab.key ? ' t-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="t-filter-bar">
        <input className="t-input t-input--search" type="text" placeholder="Search by title..."
          value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        <select className="t-select" value={filterCurriculumId} onChange={e => setFilterCurriculumId(e.target.value)}>
          <option value="all">All Programs</option>
          {curriculums.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="t-select" value={filterLevelId} onChange={e => setFilterLevelId(e.target.value)}>
          <option value="all">All Levels</option>
          {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </div>

      {filteredWordSets.length > 0 ? (
        <div>
          {filteredWordSets.map(set => {
            const badge = STATUS_BADGE[set.generation_status];
            return (
              <div key={set.id} className="t-card">
                <button
                  className={`ws-bookmark${set.is_bookmarked ? ' ws-bookmark--active' : ''}`}
                  title={set.is_bookmarked ? 'Remove bookmark' : 'Bookmark this set'}
                  onClick={() => handleToggleBookmark(set.id)}>
                  {set.is_bookmarked ? '\u2605' : '\u2606'}
                </button>
                <div className="ws-card-title" onClick={() => navigate(`/teacher/word-sets/${set.id}`)}>
                  {set.title}
                </div>
                <div className="ws-card-meta">
                  {set.curriculum?.name && <span>{set.curriculum.name}</span>}
                  {set.curriculum?.name && set.level?.name && <span className="sep">&middot;</span>}
                  {set.level?.name && <span>{set.level.name}</span>}
                  {(set.curriculum?.name || set.level?.name) && <span className="sep">&middot;</span>}
                  <span className="ws-word-count">{set.word_count} words</span>
                  {badge && <span className={`t-badge ${badge.cls}`}>{badge.label}</span>}
                  {set.is_public && <span className="t-badge t-badge--public">Public</span>}
                </div>
                {set.input_source_title && (
                  <div className="ws-card-source">
                    {set.input_source_title}{set.input_source_chapter ? ` — ${set.input_source_chapter}` : ''}
                  </div>
                )}
                {set.creator_username !== user.username && (
                  <div className="ws-card-meta" style={{ marginTop: 2 }}>
                    <span className="t-hint">Created by: {set.creator_username}</span>
                  </div>
                )}
                <div className="ws-card-actions">
                  <button className="t-btn t-btn--accent t-btn--sm" onClick={() => handleAssignClick(set)}>Assign</button>
                  {(set.creator_username === user.username || user.role === 'ADMIN') && (
                    <>
                      <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => navigate(`/teacher/word-sets/${set.id}`)}>Manage Words</button>
                      <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => handleEditClick(set)}>Edit Details</button>
                      <button className="t-btn t-btn--danger t-btn--sm" onClick={() => handleDeleteClick(set.id, set.title)}>Delete</button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="t-empty">
          {activeTab === 'bookmarked' ? 'No bookmarked sets yet. Star a set to save it here.'
            : wordSets.length === 0 ? 'No Word Sets found. Create one to get started!'
            : 'No word sets match your filters.'}
        </div>
      )}
    </div>
  );
}
