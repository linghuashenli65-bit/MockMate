/* ========================================
   MockMate.Utils — 工具函数 & 常量
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  // ---- 常量 ----
  M.ROUND_NAMES = {
    written:       '笔试 - 理论基础与知识广度',
    tech_1:        '技术一面 - 工程实践与编码能力',
    tech_2:        '技术二面 - 架构设计与技术深度',
    comprehensive: '综合面 - 综合素质与发展潜力',
    custom:        '自定义练习',
  };

  M.ROUND_TOTALS = {
    written:       20,
    tech_1:        8,
    tech_2:        6,
    comprehensive: 6,
  };

  M.INTERVIEW_TIME = 180;  // 面试每题秒数（默认）
  M.WRITTEN_TIME   = 90;   // 笔试每题秒数

  M.ROUND_TIMES = {
    written:       90,
    tech_1:        300,
    tech_2:        300,
    comprehensive: 300,
  };

  // ---- HTML 转义 ----
  M.esc = function (str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  };

  // ---- 分数颜色 ----
  M.scoreColor = function (v) {
    const n = Number(v) || 0;
    if (n >= 8) return 'var(--green)';
    if (n >= 5) return 'var(--yellow)';
    return 'var(--red)';
  };

  // ---- Toast ----
  let toastTimer;
  M.toast = function (msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
  };

  // ---- Loading helper ----
  M.showLoading = function (containerId, message) {
    const el = document.getElementById(containerId);
    if (el) {
      el.innerHTML = `<div class="loading"><div class="spinner"></div><div style="margin-top:8px">${M.esc(message)}</div></div>`;
    }
  };

  // ---- Button loading state ----
  M.setBtnLoading = function (btn, loading, text) {
    if (loading) {
      btn._origText = btn.textContent;
      btn.disabled = true;
      btn.classList.add('loading');
      btn.textContent = text || '处理中...';
    } else {
      btn.disabled = false;
      btn.classList.remove('loading');
      btn.textContent = btn._origText || text || '提交';
    }
  };

  // ---- localStorage helpers ----
  M.ls = {
    get(key, fallback) {
      try { const v = localStorage.getItem('mockmate_' + key); return v !== null ? v : fallback; }
      catch(e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem('mockmate_' + key, value); }
      catch(e) { /* quota exceeded, ignore */ }
    },
    remove(key) {
      try { localStorage.removeItem('mockmate_' + key); }
      catch(e) { /* ignore */ }
    },
    getJSON(key, fallback) {
      try {
        const v = localStorage.getItem('mockmate_' + key);
        return v ? JSON.parse(v) : fallback;
      } catch(e) { return fallback; }
    },
    setJSON(key, value) {
      try { localStorage.setItem('mockmate_' + key, JSON.stringify(value)); }
      catch(e) { /* ignore */ }
    },
  };

  // ---- API Key 加密存储（AES-GCM via Web Crypto API）----
  M.Crypto = {
    _keyCache: {},  // email -> CryptoKey

    async _deriveKey(email) {
      if (this._keyCache[email]) return this._keyCache[email];
      var encoder = new TextEncoder();
      var keyMaterial = await crypto.subtle.importKey(
        'raw', encoder.encode(email), 'PBKDF2', false, ['deriveKey']
      );
      var key = await crypto.subtle.deriveKey(
        { name: 'PBKDF2', salt: encoder.encode('MockMate-ApiKey-Salt-v1'), iterations: 100000, hash: 'SHA-256' },
        keyMaterial,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
      );
      this._keyCache[email] = key;
      return key;
    },

    async _encrypt(key, plaintext) {
      var encoder = new TextEncoder();
      var iv = crypto.getRandomValues(new Uint8Array(12));
      var ciphertext = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: iv },
        key,
        encoder.encode(plaintext)
      );
      var combined = new Uint8Array(iv.length + ciphertext.byteLength);
      combined.set(iv);
      combined.set(new Uint8Array(ciphertext), iv.length);
      return btoa(String.fromCharCode.apply(null, combined));
    },

    async _decrypt(key, cipherB64) {
      var combined = Uint8Array.from(atob(cipherB64), function(c) { return c.charCodeAt(0); });
      var iv = combined.slice(0, 12);
      var ciphertext = combined.slice(12);
      var decrypted = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: iv },
        key,
        ciphertext
      );
      return new TextDecoder().decode(decrypted);
    },

    async storeApiKey(email, name, value) {
      if (!value) {
        M.ls.remove('enc_' + name);
        return;
      }
      try {
        var key = await this._deriveKey(email);
        var encrypted = await this._encrypt(key, value);
        M.ls.set('enc_' + name, encrypted);
      } catch(e) {
        console.warn('API Key 加密存储失败:', e);
      }
    },

    async loadApiKey(email, name) {
      var encrypted = M.ls.get('enc_' + name);
      if (!encrypted) return '';
      try {
        var key = await this._deriveKey(email);
        return await this._decrypt(key, encrypted);
      } catch(e) {
        console.warn('API Key 解密失败:', e);
        return '';
      }
    },

    async loadAllApiKeys(email) {
      var userEmail = email || M.ls.get('user_email', 'default');
      var mimo = await this.loadApiKey(userEmail, 'mimo_api_key');
      var deepseek = await this.loadApiKey(userEmail, 'deepseek_api_key');
      var provider = M.ls.get('ai_provider', 'mimo');
      return { mimo_api_key: mimo, deepseek_api_key: deepseek, provider: provider };
    },

    async saveAllApiKeys(email, keys) {
      var userEmail = email || M.ls.get('user_email', 'default');
      if (keys.mimo_api_key !== undefined) {
        await this.storeApiKey(userEmail, 'mimo_api_key', keys.mimo_api_key);
      }
      if (keys.deepseek_api_key !== undefined) {
        await this.storeApiKey(userEmail, 'deepseek_api_key', keys.deepseek_api_key);
      }
      if (keys.provider) {
        M.ls.set('ai_provider', keys.provider);
      }
    }
  };

  // ---- API Key 内存缓存（由 app.js 初始化）----
  M.refreshApiKeys = async function (email) {
    try {
      M.state._apiKeys = await M.Crypto.loadAllApiKeys(email);
    } catch(e) {
      console.warn('加载 API Key 失败:', e);
    }
  };

  // ---- Format date ----
  M.formatDate = function (isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${m}/${day}`;
    } catch(e) { return isoStr.slice(0, 10); }
  };

  M.formatDateTime = function (isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const h = String(d.getHours()).padStart(2, '0');
      const min = String(d.getMinutes()).padStart(2, '0');
      return `${y}-${m}-${day} ${h}:${min}`;
    } catch(e) { return isoStr.slice(0, 19); }
  };

  // ---- Difficulty label ----
  M.diffLabel = function (d) {
    const map = { easy: '简单', medium: '中等', hard: '困难' };
    return map[d] || d || '';
  };

})(window.MockMate);
