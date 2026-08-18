import apiClient from './apiClient';

export const findingsApi = {
  getFindings: async (params = {}) => {
    const res = await apiClient.get('/findings/findings/', { params });
    return res.data?.results ?? res.data;
  },
  // Single-record fetch. The detail page must not filter the list client-side:
  // the list is paginated at 20, so anything past page 1 would look missing.
  getFinding: async (id) => {
    const res = await apiClient.get(`/findings/findings/${id}/`);
    return res.data;
  },
  createFinding: async (data) => {
    const res = await apiClient.post('/findings/findings/', data);
    return res.data;
  },
  updateFinding: async (id, data) => {
    const res = await apiClient.patch(`/findings/findings/${id}/`, data);
    return res.data;
  },
  deleteFinding: async (id) => {
    const res = await apiClient.delete(`/findings/findings/${id}/`);
    return res.data;
  },

  /* ── Discussion & evidence ─────────────────────────────────────────── */
  addComment: async (id, comment) => {
    const res = await apiClient.post(`/findings/findings/${id}/add-comment/`, { comment });
    return res.data;
  },
  uploadEvidence: async (id, formData) => {
    const res = await apiClient.post(`/findings/findings/${id}/upload-evidence/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /* ── Lifecycle transitions ─────────────────────────────────────────── */
  // Each of these stamps dates, writes the audit trail and notifies the
  // relevant party server-side, so never emulate them with a status PATCH.
  resolveFinding: async (id) => {
    const res = await apiClient.post(`/findings/findings/${id}/resolve/`);
    return res.data;
  },
  closeFinding: async (id) => {
    const res = await apiClient.post(`/findings/findings/${id}/close/`);
    return res.data;
  },
  disputeFinding: async (id) => {
    const res = await apiClient.post(`/findings/findings/${id}/dispute/`);
    return res.data;
  },
  reopenFinding: async (id) => {
    const res = await apiClient.post(`/findings/findings/${id}/reopen/`);
    return res.data;
  },
};

export default findingsApi;
