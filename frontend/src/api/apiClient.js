import axios from 'axios';

// Resolution order: the value saved in Settings, then the build-time Vite env,
// then the dev default. VITE_API_BASE_URL is what a deployed build needs —
// without it every non-local deployment was pinned to localhost:8000.
export const DEFAULT_API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000/api';

export function resolveApiBaseUrl() {
  return localStorage.getItem('apiBaseUrl') || DEFAULT_API_BASE_URL;
}

const apiClient = axios.create({
  baseURL: resolveApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Point the shared client at a new API host without a page reload.
 *
 * The base URL used to be captured once at module load, so saving a new
 * endpoint in Settings showed a success toast while every subsequent request
 * still went to the old host until the user happened to refresh.
 */
export function setApiBaseUrl(url) {
  const next = (url || '').trim() || DEFAULT_API_BASE_URL;
  localStorage.setItem('apiBaseUrl', next);
  apiClient.defaults.baseURL = next;
  return next;
}

/** Drop the signed-in session without touching the user's local preferences.
 *
 * This used to be `localStorage.clear()`, which also destroyed `apiBaseUrl` —
 * the value `setApiBaseUrl` above deliberately persists — along with the theme
 * and language choices. Anyone pointed at a non-default backend was silently
 * reset to localhost every time a session expired.
 */
export function clearSession() {
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('user');
}

function redirectToLogin() {
  clearSession();
  window.location.href = '/login';
}

/** The `payload` segment of a JWT, or null if it is not readable.
 *
 * Base64url, so `-`/`_` are translated back and the padding `atob` insists on is
 * restored. The percent-decode after that turns the byte string `atob` returns
 * into real text: `exp` alone would not need it, but a claim carrying non-ASCII
 * text — an Amharic full name, say — would otherwise come back as mojibake
 * rather than failing loudly, and this helper returns the whole payload.
 *
 * Never throws: a malformed token is a `null`, for the caller to interpret.
 */
function decodeJwtPayload(token) {
  try {
    const segment = String(token).split('.')[1];
    if (!segment) return null;
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const json = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join('')
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/** Whether `token`'s `exp` claim has passed.
 *
 * The leeway keeps a token that expires in the next few seconds from being
 * treated as live, which would send one doomed request before the refresh.
 * A token we cannot read, or one carrying no `exp`, is reported as *not*
 * expired: guessing would lock a user out of a credential the server may well
 * accept, and the server is the real authority either way.
 */
export function isTokenExpired(token, leewaySeconds = 10) {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return false;
  return payload.exp * 1000 <= Date.now() + leewaySeconds * 1000;
}

/** Whether the stored tokens can still produce an authenticated request.
 *
 * True while the access token is live, and *also* true once it has expired but
 * the refresh token has not — the response interceptor below will silently
 * exchange it. Only when both are spent is there nothing left to try.
 *
 * Route guards used to test `localStorage.getItem('accessToken')` for mere
 * presence, so a fully expired session rendered the whole application, fired
 * its requests, and bounced to the login screen on the first 401. This turns
 * that flash into a direct redirect.
 */
export function hasLiveSession() {
  const access = localStorage.getItem('accessToken');
  if (access && !isTokenExpired(access)) return true;
  const refresh = localStorage.getItem('refreshToken');
  return Boolean(refresh && !isTokenExpired(refresh));
}

// Request interceptor to attach JWT token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// In-flight refresh, shared by every request that 401s at the same time.
//
// SIMPLE_JWT sets ROTATE_REFRESH_TOKENS with BLACKLIST_AFTER_ROTATION, so each
// refresh invalidates the token it was given. Without this guard a page that
// loads four endpoints at once fires four refreshes: the first blacklists the
// token the other three are still presenting, and those three 401 straight to
// the login screen.
let refreshPromise = null;

function refreshAccessToken() {
  if (!refreshPromise) {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) return Promise.reject(new Error('No refresh token'));
    // Read the current base URL rather than a module-load snapshot, so a
    // refresh still works after the endpoint is changed in Settings.
    // Bare axios, not apiClient — going through the instance would re-enter
    // this interceptor if the refresh itself 401s.
    refreshPromise = axios
      .post(`${apiClient.defaults.baseURL}/auth/token/refresh/`, { refresh: refreshToken })
      .then((res) => {
        localStorage.setItem('accessToken', res.data.access);
        // Rotation means the response carries a *new* refresh token and the one
        // we just sent is now blacklisted. Dropping it here left the client
        // replaying a dead token on the next expiry, which logged everyone out
        // roughly every two hours.
        if (res.data.refresh) {
          localStorage.setItem('refreshToken', res.data.refresh);
        }
        return res.data.access;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

// Response interceptor to handle token expiry / logout
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      if (!localStorage.getItem('refreshToken')) {
        redirectToLogin();
        return Promise.reject(error);
      }
      try {
        const newToken = await refreshAccessToken();
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch {
        // Refresh token expired, blacklisted, or invalid.
        redirectToLogin();
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (employeeId, password) => {
    const response = await apiClient.post('/auth/login/', { employee_id: employeeId, password });
    if (response.data.access) {
      localStorage.setItem('accessToken', response.data.access);
      localStorage.setItem('refreshToken', response.data.refresh);
      localStorage.setItem('user', JSON.stringify(response.data.user || { employee_id: employeeId, role: 'auditor' }));
    }
    return response.data;
  },
  logout: () => {
    clearSession();
    window.location.href = '/login';
  },
  getCurrentUser: () => {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  },
  changePassword: async (currentPassword, newPassword) => {
    const response = await apiClient.post('/auth/change-password/', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },
  updateProfile: async (profileData) => {
    const response = await apiClient.patch('/auth/profile/', profileData);
    // Update local stored user data
    const current = localStorage.getItem('user');
    if (current) {
      const updated = { ...JSON.parse(current), ...response.data };
      localStorage.setItem('user', JSON.stringify(updated));
    }
    return response.data;
  },
};

export const notificationApi = {
  // List the current user's notifications (newest first, per the backend ordering).
  list: async (params = {}) => {
    const response = await apiClient.get('/notifications/', { params });
    // Support both paginated ({ results: [...] }) and plain-array responses.
    return response.data?.results ?? response.data;
  },
  markRead: async (id) => {
    const response = await apiClient.post(`/notifications/${id}/mark-read/`);
    return response.data;
  },
  markAllRead: async () => {
    const response = await apiClient.post('/notifications/mark-all-read/');
    return response.data;
  },
  unreadCount: async () => {
    const response = await apiClient.get('/notifications/unread-count/');
    return response.data?.unread ?? 0;
  },
};

export default apiClient;
