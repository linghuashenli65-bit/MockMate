/* ========================================
   MockMate.Utils — 工具函数 & 常量
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  // ---- 常量 ----
  M.ROUND_NAMES = {
    written:       '笔试',
    tech_1:        '技术一面',
    tech_2:        '技术二面',
    comprehensive: '综合面',
  };

  M.ROUND_TOTALS = {
    written:       20,
    tech_1:        8,
    tech_2:        6,
    comprehensive: 6,
  };

  M.INTERVIEW_TIME = 180;  // 面试每题秒数
  M.WRITTEN_TIME   = 90;   // 笔试每题秒数

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
