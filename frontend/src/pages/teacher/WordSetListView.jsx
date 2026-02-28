import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import { useUser } from '../../context/UserContext.jsx';
import WordSetForm from '../../components/WordSetForm.jsx';
import AssignSetForm from '../../components/AssignSetForm.jsx';

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

  const [searchQuery, setSearchQuery] = useState('');
  const [filterCurriculumId, setFilterCurriculumId] = useState('all');
  const [filterLevelId, setFilterLevelId] = useState('all');

  const [showEditForm, setShowEditForm] = useState(false);
  const [setToEdit, setSetToEdit] = useState(null);
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [setToAssign, setSetToAssign] = useState(null);

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
  const handleAssignSuccess = (successMessage) => { setShowAssignForm(false); setSetToAssign(null); alert(successMessage); };
  const handleCancel = () => { setShowEditForm(false); setShowAssignForm(false); setSetToEdit(null); setSetToAssign(null); };

  const filteredWordSets = useMemo(() => {
    return wordSets.filter(set => {
      if (searchQuery && !set.title.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      if (filterCurriculumId !== 'all' && set.curriculum?.id !== Number(filterCurriculumId)) return false;
      if (filterLevelId !== 'all' && set.level?.id !== Number(filterLevelId)) return false;
      return true;
    });
  }, [wordSets, searchQuery, filterCurriculumId, filterLevelId]);

  const renderContent = () => {
    if (isLoading) return <p>Loading Word Sets...</p>;
    if (error) return <p style={{ color: 'red' }}>{error}</p>;

    return (
      <div>
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
              <li key={set.id} className="practice-card" style={{ marginBottom: '15px' }}>
                <div style={{ fontWeight: 'bold', fontSize: '1.2rem' }}>{set.title}</div>
                {set.unit_or_chapter && <div style={{ fontStyle: 'italic', color: '#333' }}>{set.unit_or_chapter}</div>}
                <div style={{ color: '#555', margin: '5px 0 10px' }}>
                  {set.curriculum?.name && <span>{set.curriculum.name}</span>}
                  {set.level?.name && <span> &bull; {set.level.name}</span>}
                </div>
                <small>Created by: {set.creator_username}</small> | <small>{set.word_count} words</small>
                {set.is_public && <small style={{ color: 'green', fontWeight: 'bold' }}> &bull; Public</small>}
                <div style={{ marginTop: '15px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <button onClick={() => handleAssignClick(set)}>Assign</button>
                  {set.creator_username === user.username && (
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
          <p>{wordSets.length === 0 ? 'No Word Sets found. Create one to get started!' : 'No word sets match your filters.'}</p>
        )}
      </div>
    );
  };

  return (
    <div>
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
