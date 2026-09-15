import axios from 'axios';

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

const apiClient = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

apiClient.interceptors.request.use(config => {
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(config.method.toUpperCase())) {
    const csrfToken = getCookie('csrftoken');
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    }
  }
  return config;
}, error => {
  return Promise.reject(error);
});

// UserContext registers a handler so a mid-session 401 (expired session)
// clears the stale user before we bounce to /login. Kept as a callback so this
// module doesn't import React state.
let onUnauthorized = null;
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

apiClient.interceptors.response.use(
  response => response,
  error => {
    const status = error.response?.status;
    const url = error.config?.url || '';
    // Only 401 means the session is gone: DRF raises NotAuthenticated (401)
    // for anonymous/expired sessions and 403 for authenticated-but-forbidden.
    // Redirecting on 403 would log a user out over a mere permission denial
    // (e.g. a teacher editing someone else's word set). The login POST
    // failing with 401 is a wrong password, not an expired session — never
    // redirect for it (nor when already on /login).
    const isLoginRequest = url.includes('/login');
    if (
      status === 401
      && !isLoginRequest
      && window.location.pathname !== '/login'
    ) {
      onUnauthorized?.();
      window.location.assign('/login');
    }
    return Promise.reject(error);
  },
);

export default apiClient;
