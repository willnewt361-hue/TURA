/** TURA API client — CSRF, credentials, error handling */
(function (global) {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }

  async function ensureCsrf() {
    let csrf = getCookie('tura_csrf');
    if (!csrf) {
      const r = await fetch('/api/auth/csrf', { credentials: 'include' });
      const j = await r.json();
      csrf = j.csrf;
    }
    return csrf;
  }

  async function api(path, options = {}) {
    const opts = {
      credentials: 'include',
      headers: Object.assign({ 'Accept': 'application/json' }, options.headers || {}),
      ...options,
    };
    const method = (opts.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      const csrf = await ensureCsrf();
      opts.headers['X-CSRF-Token'] = csrf;
      if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
      }
    }
    const res = await fetch(path, opts);
    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      data = await res.json();
    } else if (res.ok) {
      data = await res.blob();
    }
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || res.statusText;
      const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  global.TuraAPI = { api, ensureCsrf, getCookie, uuid };
})(window);
