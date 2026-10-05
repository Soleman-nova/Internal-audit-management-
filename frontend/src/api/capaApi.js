import apiClient from './apiClient';
import { unwrapPage } from './paginated';

export const capaApi = {
  getActions: async (params = {}) => {
    // Unwrapped page (not a bare array) so list pages read the server's real
    // total and can page past the first PAGE_SIZE.
    const res = await apiClient.get('/corrective/actions/', { params });
    return unwrapPage(res.data);
  },
  // Single-record fetch — the detail page must not filter the paginated list.
  getAction: async (id) => {
    const res = await apiClient.get(`/corrective/actions/${id}/`);
    return res.data;
  },
  createAction: async (data) => {
    const res = await apiClient.post('/corrective/actions/', data);
    return res.data;
  },
  updateAction: async (id, data) => {
    const res = await apiClient.patch(`/corrective/actions/${id}/`, data);
    return res.data;
  },
  deleteAction: async (id) => {
    const res = await apiClient.delete(`/corrective/actions/${id}/`);
    return res.data;
  },
  addResponse: async (actionId, formData) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/add-response/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
  // Accept the remediation plan and start implementation. Goes through the
  // action (not a status PATCH) so the APPROVE_PLANS gate, the approved_by/at
  // stamps, the audit entry and the owner notification all apply.
  approveAction: async (actionId, data = {}) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/approve/`, data);
    return res.data;
  },
  // Supervisor/manager verification visit. Records scheduled_date, notes and
  // outcome against the action and notifies its owner. Scheduling a visit does
  // not settle anything — `verifyAndClose` is the closing act.
  scheduleFollowup: async (actionId, data) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/schedule-followup/`, data);
    return res.data;
  },
  // The auditor's verification of the remedy, and the closure that follows. One
  // route rather than a follow-up plus a status PATCH: the follow-up record is
  // what proves the verification happened, so the server writes both or neither,
  // closes the action, and cascades the closure to the finding behind it.
  verifyAndClose: async (actionId, data = {}) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/verify-and-close/`, data);
    return res.data;
  },
  // Derived from due_date server-side, so it is correct even before the
  // flag_overdue_actions command has stamped status='overdue'.
  getOverdue: async (params = {}) => {
    const res = await apiClient.get('/corrective/actions/overdue/', { params });
    return unwrapPage(res.data);
  },
  getSummary: async () => {
    const res = await apiClient.get('/corrective/actions/summary/');
    return res.data;
  },
};

export default capaApi;
