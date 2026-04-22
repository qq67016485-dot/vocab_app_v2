import React, { useState, useEffect } from 'react';
import apiClient from '../api/axiosConfig.js';

export default function AssignSetForm({ wordSet, students, groups, onSuccess, onCancel }) {
  const [selectedStudentIds, setSelectedStudentIds] = useState(new Set());
  const [selectedGroupIds, setSelectedGroupIds] = useState(new Set());
  const [alreadyAssignedStudentIds, setAlreadyAssignedStudentIds] = useState(new Set());
  const [alreadyAssignedGroupIds, setAlreadyAssignedGroupIds] = useState(new Set());
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingAssignments, setIsLoadingAssignments] = useState(true);

  useEffect(() => {
    const fetchAssignments = async () => {
      try {
        const res = await apiClient.get(`/word-sets/${wordSet.id}/assignments/`);
        setAlreadyAssignedStudentIds(new Set(res.data.student_ids));
        setAlreadyAssignedGroupIds(new Set(res.data.group_ids));
      } catch (err) { console.error('Error fetching assignments:', err); }
      finally { setIsLoadingAssignments(false); }
    };
    fetchAssignments();
  }, [wordSet.id]);

  const handleToggle = (id, type) => {
    setMessage('');
    const setter = type === 'student' ? setSelectedStudentIds : setSelectedGroupIds;
    setter(prev => {
      const newSet = new Set(prev);
      newSet.has(id) ? newSet.delete(id) : newSet.add(id);
      return newSet;
    });
  };

  const handleAssign = async () => {
    const finalStudentIds = Array.from(selectedStudentIds);
    const finalGroupIds = Array.from(selectedGroupIds);
    if (finalStudentIds.length === 0 && finalGroupIds.length === 0) {
      setMessage('Error: Please select at least one student or group.');
      return;
    }
    setIsSubmitting(true);
    setMessage('Assigning...');
    try {
      const response = await apiClient.post(`/word-sets/${wordSet.id}/assign/`, {
        student_ids: finalStudentIds, group_ids: finalGroupIds,
      });
      onSuccess(response.data.success);
    } catch (err) {
      console.error("Error assigning set:", err);
      setMessage(`Error: ${err.response?.data?.error || 'An error occurred.'}`);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="t-modal t-modal--wide">
        <div className="t-modal-title">Assign "{wordSet.title}"</div>
        {isLoadingAssignments ? <p>Loading current assignments...</p> : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div className="t-form-group">
              <label className="t-form-label">Assign to Groups</label>
              <div className="t-checklist">
                {groups && groups.length > 0 ? groups.map(group => {
                  const alreadyAssigned = alreadyAssignedGroupIds.has(group.id);
                  return (
                    <div key={group.id} className="t-checklist-item">
                      <input type="checkbox" id={`group-${group.id}`} checked={selectedGroupIds.has(group.id)}
                        onChange={() => handleToggle(group.id, 'group')} disabled={isSubmitting} />
                      <label htmlFor={`group-${group.id}`}>
                        {group.name} ({group.student_count})
                        {alreadyAssigned && <span className="t-assigned-tag">assigned</span>}
                      </label>
                    </div>
                  );
                }) : <p className="t-hint">No groups found.</p>}
              </div>
            </div>
            <div className="t-form-group">
              <label className="t-form-label">Assign to Individual Students</label>
              <div className="t-checklist">
                {students && students.length > 0 ? students.map(student => {
                  const alreadyAssigned = alreadyAssignedStudentIds.has(student.id);
                  return (
                    <div key={student.id} className="t-checklist-item">
                      <input type="checkbox" id={`student-${student.id}`} checked={selectedStudentIds.has(student.id)}
                        onChange={() => handleToggle(student.id, 'student')} disabled={isSubmitting} />
                      <label htmlFor={`student-${student.id}`}>
                        {student.username}
                        {alreadyAssigned && <span className="t-assigned-tag">assigned</span>}
                      </label>
                    </div>
                  );
                }) : <p className="t-hint">No students found.</p>}
              </div>
            </div>
          </div>
        )}
        <div className="t-modal-actions">
          <button type="button" className="t-btn t-btn--secondary" onClick={onCancel} disabled={isSubmitting}>Cancel</button>
          <button type="button" className="t-btn t-btn--primary" onClick={handleAssign} disabled={isSubmitting || isLoadingAssignments}>
            {isSubmitting ? 'Assigning...' : 'Assign to Selected'}
          </button>
        </div>
        {message && <p style={{ marginTop: 12, fontSize: '0.85rem', color: message.startsWith('Error') ? 'var(--t-danger)' : 'var(--t-primary)' }}>{message}</p>}
      </div>
    </div>
  );
}
