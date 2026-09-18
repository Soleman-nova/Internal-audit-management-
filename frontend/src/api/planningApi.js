import apiClient from './apiClient';
import { unwrapPage } from './paginated';

export const planningApi = {
  getUniverse: async (params = {}) => {
    // The audit universe is a complete reference directory, not a stream to be
    // browsed, so default to one large page instead of DRF's PAGE_SIZE = 20.
    // Callers that genuinely want a page can still pass page/page_size.
    const res = await apiClient.get('/planning/universe/', { params: { page_size: 1000, ...params } });
    return unwrapPage(res.data);
  },
  createUniverse: async (data) => {
    const res = await apiClient.post('/planning/universe/', data);
    return res.data;
  },
  updateUniverse: async (id, data) => {
    const res = await apiClient.patch(`/planning/universe/${id}/`, data);
    return res.data;
  },
  getProjects: async (params = {}) => {
    // The PPM project registry is a short reference list backing the universe
    // form's project dropdown, so default to one large page like getUniverse.
    const res = await apiClient.get('/planning/projects/', { params: { page_size: 1000, ...params } });
    return res.data?.results ?? res.data;
  },
  createProject: async (data) => {
    const res = await apiClient.post('/planning/projects/', data);
    return res.data;
  },
  // Same authenticated-blob pattern as reportsApi.downloadReport / the working
  // paper download: fetch through apiClient so the JWT is attached, then hand
  // the bytes to the browser. A window.open on the export URL sends no
  // Authorization header and 401s.
  exportUniverse: async (format = 'xlsx') => {
    const res = await apiClient.get('/planning/universe/export/', {
      // Named filetype, not format: DRF reserves a ?format= query param for its
      // URL-format override and 404s when the value matches no renderer.
      params: { filetype: format },
      responseType: 'blob',
    });
    const disposition = res.headers['content-disposition'] || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const name = match ? match[1] : `audit_universe.${format}`;

    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  importUniverse: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post('/planning/universe/import/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
  getDueForReAudit: async (params = {}) => {
    // Unwrapped page (not a bare array) so the "N due for re-audit" badge reads
    // the server's real total instead of truncating to the first page's length.
    const res = await apiClient.get('/planning/universe/due-for-re-audit/', { params });
    return unwrapPage(res.data);
  },
  getPlans: async (params = {}) => {
    // Default to one large page like getUniverse so callers that want the whole
    // catalogue (org chart, modal dropdowns) actually get it — a bare call used
    // to silently stop at DRF's PAGE_SIZE = 20. Paged callers override with an
    // explicit page/page_size.
    const res = await apiClient.get('/planning/plans/', { params: { page_size: 1000, ...params } });
    return unwrapPage(res.data);
  },
  createPlan: async (data) => {
    const res = await apiClient.post('/planning/plans/', data);
    return res.data;
  },
  updatePlan: async (id, data) => {
    const res = await apiClient.patch(`/planning/plans/${id}/`, data);
    return res.data;
  },
  submitPlan: async (id) => {
    const res = await apiClient.post(`/planning/plans/${id}/submit/`);
    return res.data;
  },
  approvePlan: async (id) => {
    const res = await apiClient.post(`/planning/plans/${id}/approve/`);
    return res.data;
  },
  // Returns { items, count, hasMore } rather than a bare array: PlanningPage
  // shows the engagement total, which was capped at PAGE_SIZE before.
  // Defaults to one large page like getPlans, because the engagement *pickers*
  // on Execution, Findings and Reports want the whole list — a bare call there
  // stopped at DRF's PAGE_SIZE = 20, so engagements past the twentieth were
  // simply missing from the dropdown. Paged callers (PlanningPage's table)
  // override with an explicit page/page_size.
  getEngagements: async (params = {}) => {
    const res = await apiClient.get('/planning/engagements/', { params: { page_size: 1000, ...params } });
    return unwrapPage(res.data);
  },
  getEngagement: async (id) => {
    const res = await apiClient.get(`/planning/engagements/${id}/`);
    return res.data;
  },
  createEngagement: async (data) => {
    const res = await apiClient.post('/planning/engagements/', data);
    return res.data;
  },
  updateEngagement: async (id, data) => {
    const res = await apiClient.patch(`/planning/engagements/${id}/`, data);
    return res.data;
  },
  updateEngagementStatus: async (id, status) => {
    const res = await apiClient.post(`/planning/engagements/${id}/update-status/`, { status });
    return res.data;
  },
  addTeamMember: async (id, memberData) => {
    const res = await apiClient.post(`/planning/engagements/${id}/add-member/`, memberData);
    return res.data;
  },
};

export default planningApi;