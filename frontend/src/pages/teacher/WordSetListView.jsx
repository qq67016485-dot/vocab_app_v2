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
  DRAFT: { label: 'Draft', color: '#95a5a6' },
  TO_GENERATE: { label: 'To Generate', color: '#e67e22' },
  GENERATION_REQUESTED: { label: 'Requested', color: '#d97706' },
  GENERATING: { label: 'Generating...', color: '#3498db' },
  GENERATED: { label: 'Generated', color: '#27ae60' },
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
  const [toast, setToast] = useState('');

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
    setToast(successMessage);
    setTimeout(() => setToast(''), 5000);
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
      // Tab filter
      if (activeTab === 'mine' && set.creator_username !== user.username) return false;
      if (activeTab === 'bookmarked' && !set.is_bookmarked) return false;
      if (activeTab === 'public' && (!set.is_public || set.creator_username === user.username)) return false;
      // Search + dropdown filters
      if (searchQuery && !set.title.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      if (filterCurriculumId !== 'all' && set.curriculum?.id !== Number(filterCurriculumId)) return false;
      if (filterLevelId !== 'all' && set.level?.id !== Number(filterLevelId)) return false;
      return true;
    });
  }, [wordSets, activeTab, searchQuery, filterCurriculumId, filterLevelId, user.username]);

  const renderContent = () => {
    if (isLoading) return <p>Loading Word Sets...</p>;
    if (error) return <p style={{ color: 'red' }}>{error}</p>;

    return (
      <div>
        <div className="ws-tabs">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`ws-tab${activeTab === tab.key ? ' ws-tab--active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="text" placeholder="Search by title..." value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #ccc', minWidth: '180px', flex: '1' }}
          />
          <select value={filterCurriculumId} onChange={e => setFilterCurriculumId(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #ccc' }}>
            <option value="all">All Curriculums</option>
            {curriculums.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={filterLevelId} onChange={e => setFilterLevelId(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #ccc' }}>
            <option value="all">All Levels</option>
            {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>

        {filteredWordSets.length > 0 ? (
          <ul style={{ padding: 0, listStyleType: 'none' }}>
            {filteredWordSets.map(set => (
              <li key={set.id} className="practice-card" style={{ marginBottom: '15px', position: 'relative' }}>
                <button
                  className={`ws-bookmark-btn${set.is_bookmarked ? ' ws-bookmark-btn--active' : ''}`}
                  title={set.is_bookmarked ? 'Remove bookmark' : 'Bookmark this set'}
                  onClick={() => handleToggleBookmark(set.id)}
                >
                  {set.is_bookmarked ? '\u2605 Bookmarked' : '\u2606 Bookmark'}
                </button>
                <div style={{ fontWeight: 'bold', fontSize: '1.2rem', cursor: 'pointer', color: '#3498db', paddingRight: '32px' }}
                  onClick={() => navigate(`/teacher/word-sets/${set.id}`)}>
                  {set.title}
                </div>
                {set.unit_or_chapter && <div style={{ fontStyle: 'italic', color: '#333' }}>{set.unit_or_chapter}</div>}
                <div style={{ color: '#555', margin: '5px 0 10px' }}>
                  {set.curriculum?.name && <span>{set.curriculum.name}</span>}
                  {set.level?.name && <span> &bull; {set.level.name}</span>}
                </div>
                <small>Created by: {set.creator_username}</small> | <small>{set.word_count} words</small>
                {set.is_public && <small style={{ color: 'green', fontWeight: 'bold' }}> &bull; Public</small>}
                {set.generation_status && STATUS_BADGE[set.generation_status] && (
                  <small style={{
                    marginLeft: '8px', padding: '2px 8px', borderRadius: '10px',
                    backgroundColor: STATUS_BADGE[set.generation_status].color,
                    color: '#fff', fontWeight: 'bold', fontSize: '0.75rem',
                  }}>
                    {STATUS_BADGE[set.generation_status].label}
                  </small>
                )}
                <div style={{ marginTop: '15px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <button onClick={() => handleAssignClick(set)}>Assign</button>
                  {(set.creator_username === user.username || user.role === 'ADMIN') && (
                    <>
                      <button onClick={() => navigate(`/teacher/word-sets/${set.id}`)}>Manage Words</button>
                      <button onClick={() => handleEditClick(set)}>Edit Details</button>
                      <button className="logout-button" onClick={() => handleDeleteClick(set.id, set.title)}>Delete</button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>{activeTab === 'bookmarked' ? 'No bookmarked sets yet. Star a set to save it here.'
            : wordSets.length === 0 ? 'No Word Sets found. Create one to get started!'
            : 'No word sets match your filters.'}</p>
        )}
      </div>
    );
  };

  return (
    <div>
      {toast && (
        <div style={{
          position: 'fixed', top: '20px', right: '20px', zIndex: 2000,
          background: '#16a34a', color: '#fff', padding: '12px 20px',
          borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          fontSize: '0.95rem', maxWidth: '400px',
        }}>
          {toast}
        </div>
      )}
      {showEditForm && <WordSetForm onSave={handleSaveSuccess} onCancel={handleCancel} setToEdit={setToEdit} />}
      {showAssignForm && (
        <AssignSetForm wordSet={setToAssign} students={students} groups={groups}
          onSuccess={handleAssignSuccess} onCancel={handleCancel} />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Word Sets</h2>
        <button onClick={handleCreateClick}>+ Create New Set</button>
      </div>
      <div>{renderContent()}</div>
    </div>
  );
}
