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
      } catch (err) {
        console.error('Error fetching assignments:', err);
      } finally {
        setIsLoadingAssignments(false);
      }
    };
    fetchAssignments();
  }, [wordSet.id]);

  const handleToggle = (id, type) => {
    setMessage('');
    if (type === 'student') {
      setSelectedStudentIds(prev => {
        const newSet = new Set(prev);
        newSet.has(id) ? newSet.delete(id) : newSet.add(id);
        return newSet;
      });
    } else {
      setSelectedGroupIds(prev => {
        const newSet = new Set(prev);
        newSet.has(id) ? newSet.delete(id) : newSet.add(id);
        return newSet;
      });
    }
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
        student_ids: finalStudentIds,
        group_ids: finalGroupIds,
      });
      onSuccess(response.data.success);
    } catch (err) {
      console.error("Error assigning set:", err);
      setMessage(`Error: ${err.response?.data?.error || 'An error occurred.'}`);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content">
        <h2>Assign "{wordSet.title}"</h2>
        {isLoadingAssignments ? <p>Loading current assignments...</p> : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div className="form-group">
            <label>Assign to Groups</label>
            <div className="student-checklist">
              {groups && groups.length > 0 ? (
                groups.map(group => {
                  const alreadyAssigned = alreadyAssignedGroupIds.has(group.id);
                  return (
                    <div key={group.id} className="checklist-item">
                      <input type="checkbox" id={`group-${group.id}`}
                        checked={selectedGroupIds.has(group.id)}
                        onChange={() => handleToggle(group.id, 'group')}
                        disabled={isSubmitting} />
                      <label htmlFor={`group-${group.id}`}>
                        {group.name} ({group.student_count})
                        {alreadyAssigned && <span style={{ color: '#16a34a', fontSize: '0.8rem', marginLeft: '6px' }}>assigned</span>}
                      </label>
                    </div>
                  );
                })
              ) : <p>No groups found.</p>}
            </div>
          </div>
          <div className="form-group">
            <label>Assign to Individual Students</label>
            <div className="student-checklist">
              {students && students.length > 0 ? (
                students.map(student => {
                  const alreadyAssigned = alreadyAssignedStudentIds.has(student.id);
                  return (
                    <div key={student.id} className="checklist-item">
                      <input type="checkbox" id={`student-${student.id}`}
                        checked={selectedStudentIds.has(student.id)}
                        onChange={() => handleToggle(student.id, 'student')}
                        disabled={isSubmitting} />
                      <label htmlFor={`student-${student.id}`}>
                        {student.username}
                        {alreadyAssigned && <span style={{ color: '#16a34a', fontSize: '0.8rem', marginLeft: '6px' }}>assigned</span>}
                      </label>
                    </div>
                  );
                })
              ) : <p>No students found.</p>}
            </div>
          </div>
        </div>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onCancel} disabled={isSubmitting}>Cancel</button>
          <button type="button" onClick={handleAssign} disabled={isSubmitting || isLoadingAssignments}>
            {isSubmitting ? 'Assigning...' : 'Assign to Selected'}
          </button>
        </div>
        {message && <p style={{ marginTop: '15px', color: message.startsWith('Error') ? 'red' : 'blue' }}>{message}</p>}
      </div>
    </div>
  );
}
