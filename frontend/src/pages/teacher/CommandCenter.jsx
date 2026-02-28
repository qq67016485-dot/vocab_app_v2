import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/axiosConfig.js';
import StudentFormModal from '../../components/StudentFormModal.jsx';
import BulkStudentFormModal from '../../components/BulkStudentFormModal.jsx';

export default function CommandCenter() {
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState({ groups: [], roster: [] });
  const [selectedGroupId, setSelectedGroupId] = useState('all');
  const [selectedStudentId, setSelectedStudentId] = useState(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [isStudentModalOpen, setIsStudentModalOpen] = useState(false);
  const [studentToEdit, setStudentToEdit] = useState(null);
  const [isBulkFormOpen, setIsBulkFormOpen] = useState(false);

  const fetchDashboardData = useCallback(async (groupId) => {
    setIsLoading(true);
    setError('');
    try {
      let url = '/teacher/roster/';
      if (groupId && groupId !== 'all') {
        url += `?group_id=${groupId}`;
      }
      const response = await apiClient.get(url);
      const data = response.data;
      setDashboardData(data);

      if (data.roster && data.roster.length > 0) {
        const currentSelectionExists = data.roster.some(s => s.id === selectedStudentId);
        if (!currentSelectionExists) {
          setSelectedStudentId(data.roster[0].id);
        }
      } else {
        setSelectedStudentId(null);
      }
    } catch (e) {
      console.error("Failed to load Command Center data:", e);
      setError('Failed to load dashboard. Please try again.');
      setDashboardData({ groups: [], roster: [] });
    } finally {
      setIsLoading(false);
    }
  }, [selectedStudentId]);

  useEffect(() => {
    fetchDashboardData(selectedGroupId);
  }, [fetchDashboardData, selectedGroupId]);

  const selectedStudentData = dashboardData.roster.find(s => s.id === selectedStudentId);

  const handleOpenAddModal = () => {
    setStudentToEdit(null);
    setIsStudentModalOpen(true);
  };

  const handleOpenEditModal = (student) => {
    setStudentToEdit(student);
    setIsStudentModalOpen(true);
  };

  const handleCloseStudentModal = () => {
    setIsStudentModalOpen(false);
    setStudentToEdit(null);
  };

  const handleSaveStudent = async (formData) => {
    try {
      if (studentToEdit) {
        await apiClient.patch(`/teacher/students/${studentToEdit.id}/`, formData);
      } else {
        await apiClient.post('/teacher/students/', formData);
      }
      handleCloseStudentModal();
      fetchDashboardData(selectedGroupId);
    } catch (err) {
      const errorMsg = err.response?.data?.username?.[0] || 'An error occurred. Please try again.';
      alert(`Error: ${errorMsg}`);
    }
  };

  const handleBulkCreateSuccess = () => {
    fetchDashboardData(selectedGroupId);
  };

  return (
    <div className="cc-root">
      <StudentFormModal
        isOpen={isStudentModalOpen}
        onClose={handleCloseStudentModal}
        onSave={handleSaveStudent}
        studentToEdit={studentToEdit}
        groups={dashboardData.groups}
      />
      <BulkStudentFormModal
        isOpen={isBulkFormOpen}
        onClose={() => setIsBulkFormOpen(false)}
        onSuccess={handleBulkCreateSuccess}
        groups={dashboardData.groups}
      />

      <div className="page-container">
        <aside className="sidebar">
          <h2>Action Center</h2>
          <ul className="action-menu">
            <li><button onClick={() => navigate('/teacher/word-sets')}>Manage Word Sets</button></li>
            <li><button onClick={() => navigate('/teacher/groups')}>Manage Student Groups</button></li>
            <li><button className="active">View Class Roster &amp; Progress</button></li>
          </ul>
        </aside>

        <main className="main-content">
          <div className="roster-panel">
            <div className="panel-header">
              <h2>Class Roster</h2>
              <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <button onClick={() => setIsBulkFormOpen(true)} className="secondary-button">
                  + Add Multiple
                </button>
                <button onClick={handleOpenAddModal}>+ Add Student</button>
                <div>
                  <label htmlFor="group-filter" style={{ marginRight: '0.5rem', fontSize: '0.9rem' }}>
                    Filter:
                  </label>
                  <select
                    id="group-filter"
                    value={selectedGroupId}
                    onChange={(e) => setSelectedGroupId(e.target.value)}
                    disabled={isLoading}
                  >
                    <option value="all">All Students</option>
                    {dashboardData.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {isLoading ? (
              <p>Loading roster...</p>
            ) : error ? (
              <p style={{ color: 'red' }}>{error}</p>
            ) : dashboardData.roster.length === 0 ? (
              <p>No students found for this view.</p>
            ) : (
              <table className="roster-table">
                <thead>
                  <tr>
                    <th>Student Name</th>
                    <th>Activity (3 days)</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboardData.roster.map(student => {
                    const low = student.activity_3d.questions_answered === 0;
                    return (
                      <tr key={student.id} className={student.id === selectedStudentId ? 'selected' : ''}>
                        <td onClick={() => setSelectedStudentId(student.id)}>{student.username}</td>
                        <td onClick={() => setSelectedStudentId(student.id)}>
                          <span className={`activity-badge ${low ? 'low' : ''}`}>
                            {student.activity_3d.questions_answered} questions ({student.activity_3d.accuracy_percent}%)
                          </span>
                        </td>
                        <td>
                          <button className="small-button" onClick={() => handleOpenEditModal(student)}>Edit</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="details-panel">
            <div className="panel-header">
              <h2>Snapshot <span className="student-name">{selectedStudentData?.username || '\u2014'}</span></h2>
            </div>

            {isLoading && selectedStudentId ? (
              <p>Loading snapshot...</p>
            ) : !selectedStudentData ? (
              <div className="details-card"><p>Select a student to view their snapshot.</p></div>
            ) : (
              <>
                <div className="details-card">
                  <h3>Challenging Words</h3>
                  <ul className="details-list">
                    {selectedStudentData.snapshot.challenging_words?.length > 0
                      ? selectedStudentData.snapshot.challenging_words.map((w, i) => <li key={i}>{w}</li>)
                      : <li>No data</li>}
                  </ul>
                </div>
                <div className="details-card">
                  <h3>Skills to Develop</h3>
                  <ul className="details-list">
                    {selectedStudentData.snapshot.skills_to_develop?.length > 0
                      ? selectedStudentData.snapshot.skills_to_develop.map((s, i) => <li key={i}>{s}</li>)
                      : <li>No data</li>}
                  </ul>
                </div>
                <div className="details-card">
                  <h3>Words Due for Review</h3>
                  <div className="due-count-display">
                    {selectedStudentData.snapshot?.words_due_for_review ?? 'N/A'}
                  </div>
                </div>
                <div className="details-actions">
                  <button
                    className="cc-details-button"
                    onClick={() => navigate(`/teacher/students/${selectedStudentData.id}/progress`)}
                    disabled={!selectedStudentData}
                  >
                    View Full Activity Report
                  </button>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
