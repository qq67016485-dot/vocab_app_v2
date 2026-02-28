import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import GroupFormModal from '../../components/GroupFormModal.jsx';

export default function GroupManagementView() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [allStudents, setAllStudents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const [groupsResponse, studentsResponse] = await Promise.all([
        apiClient.get('/groups/'),
        apiClient.get('/teacher/students/'),
      ]);
      setGroups(groupsResponse.data);
      setAllStudents(studentsResponse.data);
    } catch (err) {
      console.error("Error fetching data:", err);
      setError('Failed to load data. Please refresh the page.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleOpenCreateModal = () => { setEditingGroup(null); setIsModalOpen(true); };
  const handleOpenEditModal = (group) => { setEditingGroup(group); setIsModalOpen(true); };
  const handleCloseModal = () => { setIsModalOpen(false); setEditingGroup(null); };

  const handleSave = async (formData) => {
    const isEditing = !!editingGroup;
    const url = isEditing ? `/groups/${editingGroup.id}/` : '/groups/';
    const method = isEditing ? 'patch' : 'post';
    try {
      await apiClient[method](url, formData);
      fetchData();
      handleCloseModal();
    } catch (err) {
      console.error('Failed to save group:', err.response?.data);
      alert(`Error: ${JSON.stringify(err.response?.data) || 'Could not save the group.'}`);
    }
  };

  const handleDelete = async (groupId) => {
    if (window.confirm('Are you sure you want to delete this group? This action cannot be undone.')) {
      try {
        await apiClient.delete(`/groups/${groupId}/`);
        fetchData();
      } catch (err) {
        console.error('Failed to delete group:', err);
        alert('Could not delete the group.');
      }
    }
  };

  if (isLoading) return <p>Loading groups...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Manage Student Groups</h2>
        <button onClick={handleOpenCreateModal}>+ Create New Group</button>
      </div>

      {groups.length === 0 ? (
        <div className="practice-card" style={{ marginTop: '20px', textAlign: 'center' }}>
          <p>You haven't created any groups yet.</p>
          <p>Click "Create New Group" to get started!</p>
        </div>
      ) : (
        <div style={{ marginTop: '20px' }}>
          {groups.map(group => (
            <div key={group.id} className="practice-card" style={{ marginBottom: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <h3 style={{ marginTop: 0 }}>{group.name}</h3>
                  <p style={{ color: '#555' }}>{group.description || <em>No description.</em>}</p>
                  <p><strong>Students ({group.student_count}):</strong> {group.students.map(s => s.username).join(', ') || 'None'}</p>
                </div>
                <div>
                  <button className="secondary-button" onClick={() => handleOpenEditModal(group)}>Edit</button>
                  <button className="danger-button" onClick={() => handleDelete(group.id)} style={{ marginLeft: '10px' }}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {isModalOpen && (
        <GroupFormModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          onSave={handleSave}
          group={editingGroup}
          allStudents={allStudents}
        />
      )}
    </div>
  );
}
