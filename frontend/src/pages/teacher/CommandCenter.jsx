import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext.jsx';
import apiClient from '../../api/axiosConfig.js';
import StudentFormModal from '../../components/StudentFormModal.jsx';
import BulkStudentFormModal from '../../components/BulkStudentFormModal.jsx';

export default function CommandCenter() {
  const navigate = useNavigate();
  const { user } = useUser();
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
      if (groupId && groupId !== 'all') url += `?group_id=${groupId}`;
      const response = await apiClient.get(url);
      const data = response.data;
      setDashboardData(data);
      if (data.roster && data.roster.length > 0) {
        const currentSelectionExists = data.roster.some(s => s.id === selectedStudentId);
        if (!currentSelectionExists) setSelectedStudentId(data.roster[0].id);
      } else { setSelectedStudentId(null); }
    } catch (e) {
      console.error("Failed to load Command Center data:", e);
      setError('Failed to load dashboard. Please try again.');
      setDashboardData({ groups: [], roster: [] });
    } finally { setIsLoading(false); }
  }, [selectedStudentId]);

  useEffect(() => { fetchDashboardData(selectedGroupId); }, [fetchDashboardData, selectedGroupId]);

  const selectedStudentData = dashboardData.roster.find(s => s.id === selectedStudentId);

  const handleOpenAddModal = () => { setStudentToEdit(null); setIsStudentModalOpen(true); };
  const handleOpenEditModal = (student) => { setStudentToEdit(student); setIsStudentModalOpen(true); };
  const handleCloseStudentModal = () => { setIsStudentModalOpen(false); setStudentToEdit(null); };

  const handleSaveStudent = async (formData) => {
    try {
      if (studentToEdit) { await apiClient.patch(`/teacher/students/${studentToEdit.id}/`, formData); }
      else { await apiClient.post('/teacher/students/', formData); }
      handleCloseStudentModal();
      fetchDashboardData(selectedGroupId);
    } catch (err) {
      const errorMsg = err.response?.data?.username?.[0] || 'An error occurred. Please try again.';
      alert(`Error: ${errorMsg}`);
    }
  };

  const handleBulkCreateSuccess = () => { fetchDashboardData(selectedGroupId); };

  return (
    <div>
      <StudentFormModal isOpen={isStudentModalOpen} onClose={handleCloseStudentModal} onSave={handleSaveStudent} studentToEdit={studentToEdit} groups={dashboardData.groups} />
      <BulkStudentFormModal isOpen={isBulkFormOpen} onClose={() => setIsBulkFormOpen(false)} onSuccess={handleBulkCreateSuccess} groups={dashboardData.groups} />

      <div className="t-page-header">
        <h1 className="t-page-title">Command Center</h1>
      </div>

      <div className="cc-layout">
        <div className="cc-roster">
          <div className="cc-panel-header">
            <span className="cc-panel-title">Class Roster</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="t-btn t-btn--secondary t-btn--sm" onClick={() => setIsBulkFormOpen(true)}>+ Add Multiple</button>
              <button className="t-btn t-btn--primary t-btn--sm" onClick={handleOpenAddModal}>+ Add Student</button>
              <select className="t-select" style={{ fontSize: '0.8rem', padding: '5px 8px' }} value={selectedGroupId} onChange={(e) => setSelectedGroupId(e.target.value)} disabled={isLoading}>
                <option value="all">All Students</option>
                {dashboardData.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
          </div>

          {isLoading ? <p>Loading roster...</p> : error ? <p style={{ color: 'var(--t-danger)' }}>{error}</p> : dashboardData.roster.length === 0 ? (
            <div className="t-empty">No students found for this view.</div>
          ) : (
            <table className="t-table">
              <thead><tr><th>Student Name</th><th>Activity (3 days)</th><th>Actions</th></tr></thead>
              <tbody>
                {dashboardData.roster.map(student => {
                  const low = student.activity_3d.questions_answered === 0;
                  return (
                    <tr key={student.id} className={student.id === selectedStudentId ? 't-row--selected' : ''}>
                      <td onClick={() => setSelectedStudentId(student.id)} style={{ cursor: 'pointer' }}>{student.username}</td>
                      <td onClick={() => setSelectedStudentId(student.id)} style={{ cursor: 'pointer' }}>
                        <span className={`cc-activity-badge${low ? ' cc-activity-badge--low' : ''}`}>
                          {student.activity_3d.questions_answered} questions ({student.activity_3d.accuracy_percent}%)
                        </span>
                      </td>
                      <td><button className="t-btn t-btn--ghost t-btn--sm" onClick={() => handleOpenEditModal(student)}>Edit</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="cc-details">
          <div className="cc-panel-header">
            <span className="cc-panel-title">Snapshot <span style={{ color: 'var(--t-primary)' }}>{selectedStudentData?.username || '\u2014'}</span></span>
          </div>
          {isLoading && selectedStudentId ? <p>Loading snapshot...</p> : !selectedStudentData ? (
            <div className="cc-detail-card"><p className="t-hint">Select a student to view their snapshot.</p></div>
          ) : (
            <>
              <div className="cc-detail-card">
                <h4>Challenging Words</h4>
                <ul className="cc-detail-list">
                  {selectedStudentData.snapshot.challenging_words?.length > 0
                    ? selectedStudentData.snapshot.challenging_words.map((w, i) => <li key={i}>{w}</li>)
                    : <li>No data</li>}
                </ul>
              </div>
              <div className="cc-detail-card">
                <h4>Skills to Develop</h4>
                <ul className="cc-detail-list">
                  {selectedStudentData.snapshot.skills_to_develop?.length > 0
                    ? selectedStudentData.snapshot.skills_to_develop.map((s, i) => <li key={i}>{s}</li>)
                    : <li>No data</li>}
                </ul>
              </div>
              <div className="cc-detail-card">
                <h4>Words Due for Review</h4>
                <div className="cc-due-count">{selectedStudentData.snapshot?.words_due_for_review ?? 'N/A'}</div>
              </div>
              <button className="t-btn t-btn--secondary" style={{ width: '100%', marginTop: 12, justifyContent: 'center' }}
                onClick={() => navigate(`/teacher/students/${selectedStudentData.id}/progress`)} disabled={!selectedStudentData}>
                View Full Activity Report
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
