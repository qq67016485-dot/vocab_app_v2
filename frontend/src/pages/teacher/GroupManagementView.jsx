import React, { useState, useEffect, useCallback } from 'react';
import apiClient from '../../api/axiosConfig.js';
import GroupFormModal from '../../components/GroupFormModal.jsx';

export default function GroupManagementView() {
  const [groups, setGroups] = useState([]);
  const [allStudents, setAllStudents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);
  const [actionError, setActionError] = useState('');

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
    } finally { setIsLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleOpenCreateModal = () => { setEditingGroup(null); setIsModalOpen(true); };
  const handleOpenEditModal = (group) => { setEditingGroup(group); setIsModalOpen(true); };
  const handleCloseModal = () => { setIsModalOpen(false); setEditingGroup(null); };

  const handleSave = async (formData) => {
    const isEditing = !!editingGroup;
    const url = isEditing ? `/groups/${editingGroup.id}/` : '/groups/';
    const method = isEditing ? 'patch' : 'post';
    setActionError('');
    try {
      await apiClient[method](url, formData);
      fetchData();
      handleCloseModal();
    } catch (err) {
      console.error('Failed to save group:', err.response?.data);
      const detail = err.response?.data?.name?.[0] || err.response?.data?.detail;
      setActionError(detail || 'Could not save the group. Please try again.');
    }
  };

  const handleDelete = async (groupId) => {
    if (window.confirm('Are you sure you want to delete this group? This action cannot be undone.')) {
      setActionError('');
      try { await apiClient.delete(`/groups/${groupId}/`); fetchData(); }
      catch (err) {
        console.error('Failed to delete group:', err);
        setActionError('Could not delete the group. Please try again.');
      }
    }
  };

  if (isLoading) return <p>Loading groups...</p>;
  if (error) return <p style={{ color: 'var(--t-danger)' }}>{error}</p>;

  return (
    <div>
      <div className="t-page-header">
        <h1 className="t-page-title">Student Groups</h1>
        <button className="t-btn t-btn--primary" onClick={handleOpenCreateModal}>+ Create New Group</button>
      </div>

      {actionError && (
        <div className="t-message t-message--error" style={{ marginBottom: 12 }}>{actionError}</div>
      )}

      {groups.length === 0 ? (
        <div className="t-empty">You haven't created any groups yet. Click "Create New Group" to get started!</div>
      ) : (
        <div>
          {groups.map(group => (
            <div key={group.id} className="t-card" style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ fontSize: '1rem', fontWeight: 600 }}>{group.name}</div>
                  <div className="t-hint" style={{ marginTop: 2 }}>{group.description || 'No description.'}</div>
                  <div className="t-hint" style={{ marginTop: 4 }}>
                    <strong>{group.student_count} students:</strong> {group.students.map(s => s.username).join(', ') || 'None'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => handleOpenEditModal(group)}>Edit</button>
                  <button className="t-btn t-btn--danger t-btn--sm" onClick={() => handleDelete(group.id)}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {isModalOpen && (
        <GroupFormModal isOpen={isModalOpen} onClose={handleCloseModal} onSave={handleSave} group={editingGroup} allStudents={allStudents} />
      )}
    </div>
  );
}
