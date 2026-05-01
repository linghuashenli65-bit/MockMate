/* ========================================
   MockMate.API — 后端接口封装
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const API = {
    async _request(url, options = {}) {
      try {
        const r = await fetch(url, options);
        if (!r.ok) {
          const detail = (await r.json().catch(() => ({}))).detail || r.statusText;
          throw new Error(detail);
        }
        return r.json();
      } catch (e) {
        // 网络错误特殊处理
        if (e instanceof TypeError && e.message === 'Failed to fetch') {
          throw new Error('无法连接到服务器，请确认服务已启动');
        }
        throw e;
      }
    },

    get(url) {
      return this._request(url);
    },

    post(url, data) {
      return this._request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    delete(url) {
      return this._request(url, { method: 'DELETE' });
    },

    async upload(url, formData) {
      try {
        const r = await fetch(url, { method: 'POST', body: formData });
        if (!r.ok) {
          const detail = (await r.json().catch(() => ({}))).detail || r.statusText;
          throw new Error(detail);
        }
        return r.json();
      } catch (e) {
        if (e instanceof TypeError && e.message === 'Failed to fetch') {
          throw new Error('无法连接到服务器');
        }
        throw e;
      }
    },
  };

  M.API = API;

})(window.MockMate);
