import apiClient from './apiClient';

export const riskApi = {
  getParameters: async () => {
    const res = await apiClient.get('/risk/parameters/');
    return res.data?.results ?? res.data;
  },
  getAssessments: async (params = {}) => {
    const res = await apiClient.get('/risk/assessments/', { params });
    return res.data?.results ?? res.data;
  },
  getHeatmap: async (params = {}) => {
    const res = await apiClient.get('/risk/assessments/heatmap/', { params });
    return res.data;
  },
  getSummary: async () => {
    const res = await apiClient.get('/risk/assessments/summary/');
    return res.data;
  },
  // The parameter policy currently in force: its digest, the weight sum and
  // uplift those weights produce, and how many stored assessments were scored
  // under a *different* digest (i.e. went stale when a parameter was edited).
  getPolicy: async () => {
    const res = await apiClient.get('/risk/parameters/policy/');
    return res.data;
  },
  // Re-score every assessment whose digest no longer matches the active policy.
  // Returns { updated, total }.
  recomputeAssessments: async () => {
    const res = await apiClient.post('/risk/assessments/recompute/');
    return res.data;
  },
  createAssessment: async (data) => {
    const res = await apiClient.post('/risk/assessments/', data);
    return res.data;
  },
  updateAssessment: async (id, data) => {
    const res = await apiClient.patch(`/risk/assessments/${id}/`, data);
    return res.data;
  },
  // The approval workflow. Each must go through its action rather than a status
  // PATCH: the capability gate, the reviewer/timestamp stamps, the audit entry
  // and the score's propagation onto the auditable entity all live server-side.
  submitAssessment: async (id) => {
    const res = await apiClient.post(`/risk/assessments/${id}/submit/`);
    return res.data;
  },
  approveAssessment: async (id, reviewNotes = '') => {
    const res = await apiClient.post(`/risk/assessments/${id}/approve/`, { review_notes: reviewNotes });
    return res.data;
  },
  rejectAssessment: async (id, reviewNotes = '') => {
    const res = await apiClient.post(`/risk/assessments/${id}/reject/`, { review_notes: reviewNotes });
    return res.data;
  },
  getSelfAssessments: async (params = {}) => {
    const res = await apiClient.get('/risk/self-assessments/', { params });
    return res.data?.results ?? res.data;
  },
  createSelfAssessment: async (data) => {
    const res = await apiClient.post('/risk/self-assessments/', data);
    return res.data;
  },
  updateSelfAssessment: async (id, data) => {
    const res = await apiClient.patch(`/risk/self-assessments/${id}/`, data);
    return res.data;
  },
  // Marking a self-assessment reviewed must go through this action, not a
  // status PATCH: the backend gate (APPROVE_PLANS), reviewed_by/reviewed_at
  // stamps, audit log and submitter notification all live here.
  //
  // `options` carries the review's other two inputs: `adopt_self_values` re-scores
  // the parent assessment from the auditee's figures instead of the manager's,
  // and `note` records why.
  reviewSelfAssessment: async (id, comments = '', options = {}) => {
    const res = await apiClient.post(`/risk/self-assessments/${id}/review/`, { comments, ...options });
    return res.data;
  },
  deleteSelfAssessment: async (id) => {
    const res = await apiClient.delete(`/risk/self-assessments/${id}/`);
    return res.data;
  },
};

export default riskApi;
