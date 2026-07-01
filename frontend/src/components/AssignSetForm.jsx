import React, { useState, useEffect } from 'react';
import apiClient from '../api/axiosConfig.js';

export default function AssignSetForm({ wordSet, students, groups, onSuccess, onCancel }) {
  const [selectedStudentIds, setSelectedStudentIds] = useState(new Set());
  const [selectedGroupIds, setSelectedGroupIds] = useState(new Set());
  const [alreadyAssignedStudentIds, setAlreadyAssignedStudentIds] = useState(new Set());
  const [alreadyAssignedGroupIds, setAlreadyAssignedGroupIds] = useState(new Set());
  const [contentType, setContentType] = useState('graphic_novel');
  // Which content types have a published (is_selected) candidate in any pack
  const [availableContentTypes, setAvailableContentTypes] = useState(null); // null = still loading
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingAssignments, setIsLoadingAssignments] = useState(true);

  useEffect(() => {
    const fetchAssignments = async () => {
      try {
        const res = await apiClient.get(`/word-sets/${wordSet.id}/assignments/`);
        setAlreadyAssignedStudentIds(new Set(res.data.student_ids));
        setAlreadyAssignedGroupIds(new Set(res.data.group_ids));

        const available = res.data.available_content_types ?? [];
        setAvailableContentTypes(available);

        // Prefill with the most-common existing content type, but only if it is
        // still available.  If the prefilled type was unpublished since the last
        // assignment, fall back to the first available type.
        const prefilled = res.data.content_type;
        if (prefilled && available.includes(prefilled)) {
          setContentType(prefilled);
        } else if (available.length > 0) {
          setContentType(available[0]);
        }
      } catch (err) {
        console.error('Error fetching assignments:', err);
        setAvailableContentTypes([]);
      } finally {
        setIsLoadingAssignments(false);
      }
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
        content_type: contentType,
      });
      onSuccess(response.data.success);
    } catch (err) {
      console.error("Error assigning set:", err);
      setMessage(`Error: ${err.response?.data?.error || 'An error occurred.'}`);
      setIsSubmitting(false);
    }
  };

  const LABEL = { graphic_novel: 'Graphic novel', infographic: 'Infographic' };
  const noneAvailable = availableContentTypes !== null && availableContentTypes.length === 0;

  return (
    <div className="t-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="t-modal t-modal--wide">
        <div className="t-modal-title">Assign "{wordSet.title}"</div>

        {noneAvailable ? (
          /* ── Blocking state: no published content ── */
          <>
            <p style={{ margin: '16px 0 8px', color: 'var(--t-danger)', fontWeight: 500 }}>
              This word set cannot be assigned yet.
            </p>
            <p className="t-hint">
              No graphic novel or infographic has been generated and selected for this
              word set. Ask an admin to run the generation pipeline and pick a candidate
              before assigning it to students.
            </p>
            <div className="t-modal-actions">
              <button type="button" className="t-btn t-btn--secondary" onClick={onCancel}>Close</button>
            </div>
          </>
        ) : (
          /* ── Normal assignment form ── */
          <>
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

            {/* Content type selector — only rendered when the data is loaded,
                and only shows options that are actually published */}
            {!isLoadingAssignments && availableContentTypes !== null && (
              <div className="t-form-group" style={{ marginTop: 16 }}>
                <label className="t-form-label">Instructional content format</label>
                {availableContentTypes.length > 1 ? (
                  <>
                    <div style={{ display: 'flex', gap: 20, marginTop: 4 }}>
                      {availableContentTypes.map(ct => (
                        <label key={ct} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                          <input type="radio" name="content_type" value={ct}
                            checked={contentType === ct}
                            onChange={() => setContentType(ct)} disabled={isSubmitting} />
                          {LABEL[ct] ?? ct}
                        </label>
                      ))}
                    </div>
                    <p className="t-hint" style={{ marginTop: 4 }}>
                      Both formats are published. Choose which one students will see for this word set.
                    </p>
                  </>
                ) : (
                  /* Only one type available — show it as read-only */
                  <p style={{ marginTop: 4 }}>
                    <strong>{LABEL[availableContentTypes[0]] ?? availableContentTypes[0]}</strong>
                    <span className="t-hint" style={{ marginLeft: 8 }}>
                      (only published format for this word set)
                    </span>
                  </p>
                )}
              </div>
            )}

            <div className="t-modal-actions">
              <button type="button" className="t-btn t-btn--secondary" onClick={onCancel} disabled={isSubmitting}>Cancel</button>
              <button type="button" className="t-btn t-btn--primary" onClick={handleAssign}
                disabled={isSubmitting || isLoadingAssignments}>
                {isSubmitting ? 'Assigning...' : 'Assign to Selected'}
              </button>
            </div>
            {message && (
              <p style={{ marginTop: 12, fontSize: '0.85rem', color: message.startsWith('Error') ? 'var(--t-danger)' : 'var(--t-primary)' }}>
                {message}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
