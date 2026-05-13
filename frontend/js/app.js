/* ========================================
   MockMate.App — 主入口 & 全局状态
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  // ---- 全局状态 ----
  M.state = {
    currentSessionId: null,
    currentQuestionIndex: 0,
    interviewActive: false,
    interviewStartTime: null,
    timerInterval: null,
    isWrittenRound: false,
    currentRound: null,
    totalQuestions: 0,
    currentProfile: null,    // 当前岗位画像
    countdownInterval: null, // 倒计时句柄
    countdownRemaining: 0,   // 倒计时剩余秒数
    countdownPaused: false,
    drafts: {},              // 草稿缓存 { "sessionId_qIndex": "text" }
    suspendedQuestions: [],  // 跳过/暂挂的题目
    _apiKeys: {              // API Key 内存缓存（解密后的明文）
      mimo_api_key: '',
      deepseek_api_key: '',
      qwen_api_key: '',
      zhipu_api_key: '',
      provider: 'mimo',
    },
  };

  // ---- Tab 切换 ----
  M.switchTab = function (name) {
    // 面试进行中保护
    if (M.state.interviewActive && name !== 'interview') {
      if (!confirm('面试进行中，切换页面将中断面试，确定吗？')) return;
      M.Interview.cleanup();
    }

    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    const tabBtn = document.querySelector(`[data-tab="${name}"]`);
    const tabContent = document.getElementById('tab-' + name);
    if (tabBtn) tabBtn.classList.add('active');
    if (tabContent) tabContent.classList.add('active');

    // 切换到历史时自动加载
    if (name === 'history') {
      setTimeout(() => M.History.loadHistory(), 50);
    }
    // 切换到收藏时自动加载
    if (name === 'favorites') {
      setTimeout(() => M.Favorites.loadFavorites(1), 50);
    }
  };

  // ---- 服务状态 ----
  M.checkStatus = async function () {
    try {
      var s = await M.API.get('/api/status');
      var dot = document.getElementById('statusDot');
      var txt = document.getElementById('statusText');
      var keys = M.state._apiKeys || {};
      var selected = keys.provider || 'mimo';

      console.log('[Status]', JSON.stringify(s), 'selected=', selected, 'zhipu_key=', !!keys.zhipu_api_key);

      // 按用户选择的提供商判断
      var readyMap = { mimo: s.mimo_ready, deepseek: s.deepseek_ready, qwen: s.qwen_ready, zhipu: s.zhipu_ready };
      var nameMap = { mimo: 'MiMo', deepseek: 'DeepSeek', qwen: '通义千问', zhipu: '智谱' };

      if (readyMap[selected]) {
        dot.className = 'dot green';
        txt.textContent = (nameMap[selected] || selected) + ' 已连接';
      } else if (s.zhipu_ready || s.qwen_ready || s.mimo_ready || s.deepseek_ready) {
        dot.className = 'dot yellow';
        // 显示哪个就绪但未选中
        var altProvider = s.zhipu_ready ? '智谱' : (s.qwen_ready ? '通义千问' : (s.mimo_ready ? 'MiMo' : 'DeepSeek'));
        txt.textContent = (nameMap[selected] || selected) + ' 未就绪（' + altProvider + ' 可用）';
      } else {
        dot.className = 'dot red';
        txt.textContent = '未配置 API';
      }

      var sel = document.getElementById('providerSelect');
      if (sel) sel.value = s.provider;
    } catch(e) {
      document.getElementById('statusDot').className = 'dot red';
      document.getElementById('statusText').textContent = '未连接';
    }
  };

  // ---- 表单记忆 ----
  M.restoreFormMemory = function () {
    const pos = M.ls.get('position', '');
    const company = M.ls.get('company', '');
    const resume = M.ls.get('resume', '');
    if (pos) document.getElementById('positionInput').value = pos;
    if (company) document.getElementById('companyInput').value = company;
    if (resume) document.getElementById('resumeInput').value = resume;
  };

  M.saveFormMemory = function () {
    M.ls.set('position', document.getElementById('positionInput').value);
    M.ls.set('company', document.getElementById('companyInput').value);
    M.ls.set('resume', document.getElementById('resumeInput').value);
  };

  // ---- 快捷键 ----
  M.registerShortcuts = function () {
    document.addEventListener('keydown', (e) => {
      // Alt+1/2/3/4 切换 Tab
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const tabMap = { '1': 'setup', '2': 'interview', '3': 'history', '4': 'settings', '5': 'favorites', '6': 'custom', '7': 'finetune' };
        const tab = tabMap[e.key];
        if (tab) {
          e.preventDefault();
          M.switchTab(tab);
        }
      }

      // Escape — 关闭 toast 或聚焦输入框
      if (e.key === 'Escape' && !e.ctrlKey && !e.altKey && !e.metaKey) {
        document.getElementById('toast').classList.remove('show');
        const answerInput = document.getElementById('answerInput');
        if (answerInput && document.activeElement !== answerInput) {
          e.preventDefault();
          answerInput.focus();
        }
      }
    });
  };

  // ---- 输入变化监听（表单记忆）----
  M.bindFormMemory = function () {
    ['positionInput', 'companyInput', 'resumeInput'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('input', () => M.saveFormMemory());
      }
    });
  };

  // ---- 断点续面 ----
  M.checkResumeSession = async function () {
    const sessionId = M.ls.get('active_session', '');
    if (!sessionId) return;
    try {
      const session = await M.API.get('/api/interview/session/' + sessionId);
      if (!session || session.report || !session.current_question) {
        M.ls.remove('active_session');
        return;
      }
      M.Interview.resumeSession(session);
    } catch(e) {
      M.ls.remove('active_session');
    }
  };

  // ---- 清除缓存 ----
  M.clearLocalData = function () {
    const keys = ['position', 'company', 'resume'];
    keys.forEach(k => M.ls.remove(k));
    // 清除所有草稿
    Object.keys(localStorage).forEach(k => {
      if (k.startsWith('mockmate_draft_')) localStorage.removeItem(k);
    });
    document.getElementById('positionInput').value = '';
    document.getElementById('companyInput').value = '';
    document.getElementById('resumeInput').value = '';
    M.toast('本地缓存已清除');
  };

  // ---- 入口 ----
  M.init = function () {
    // Tab 点击事件
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => M.switchTab(tab.dataset.tab));
    });

    // 轮次选择器
    document.querySelectorAll('.round-option').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.round-option').forEach(o => o.classList.remove('selected'));
        el.classList.add('selected');
        el.querySelector('input').checked = true;
      });
    });
    // 默认选中技术一面
    const defaultRound = document.querySelector('.round-option[data-round="tech_1"]');
    if (defaultRound) defaultRound.classList.add('selected');

    // 自定义题目选择器
    M.state._selectedCustomIds = [];
    const useCustomCb = document.getElementById('useCustomQuestions');
    const customSel = document.getElementById('customQuestionSelector');
    if (useCustomCb) {
      useCustomCb.addEventListener('change', async function () {
        if (this.checked) {
          try {
            const res = await M.API.get('/api/custom/questions');
            const qs = res.questions || [];
            if (!qs.length) {
              M.toast('请先在「自定义题目」标签页添加题目');
              this.checked = false;
              return;
            }
            let html = '<div style="font-size:12px;color:var(--text2);margin-bottom:6px">选择要练习的题目：</div>';
            qs.forEach(q => {
              const qShort = (q.question || '').length > 50 ? (q.question || '').slice(0, 50) + '...' : (q.question || '');
              html +=
                '<label style="display:flex;align-items:center;cursor:pointer;font-size:13px;justify-content:space-between;padding:3px 0">' +
                  '<span>' + M.esc(qShort) + '</span>' +
                  '<input type="checkbox" class="custom-checkbox custom-q-checkbox" value="' + q.id + '" checked>' +
                '</label>';
            });
            customSel.innerHTML = html;
            customSel.style.display = 'block';
            M.updateSelectedCustomIds();
            customSel.querySelectorAll('.custom-q-checkbox').forEach(cb => {
              cb.addEventListener('change', M.updateSelectedCustomIds);
            });
          } catch (e) {
            M.toast('加载自定义题目失败');
            this.checked = false;
          }
        } else {
          customSel.style.display = 'none';
          M.state._selectedCustomIds = [];
        }
      });
    }

    M.updateSelectedCustomIds = function () {
      const cbs = document.querySelectorAll('.custom-q-checkbox:checked');
      M.state._selectedCustomIds = Array.from(cbs).map(cb => parseInt(cb.value));
    };

    // 面试中离开保护
    window.addEventListener('beforeunload', (e) => {
      if (M.state.interviewActive) {
        M.saveFormMemory();
        e.preventDefault();
        e.returnValue = '';
      }
    });

    // 页面卸载前保存表单
    window.addEventListener('pagehide', () => M.saveFormMemory());

    // 初始化
    M.restoreFormMemory();
    M.bindFormMemory();
    M.registerShortcuts();

    // 检查登录状态（未登录会自动跳转到 login.html）
    var userEmail = M.Auth.checkAuth();
    if (!userEmail) return;  // checkAuth 会 redirect，这里只是兜底

    // 加载加密存储的 API Key 到内存（异步，不阻塞界面）
    M.refreshApiKeys(userEmail).then(function() {
      M.checkStatus();
    });

    // 绑定各个模块的事件
    M.Research.init();
    M.Interview.init();
    M.History.init();
    M.Favorites.init();
    M.Custom.init();
    M.Settings.init();

    // 检查是否有未完成的面试（断点续面）
    M.checkResumeSession();

    console.log('MockMate initialized');
  };

  // DOM 就绪后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => M.init());
  } else {
    M.init();
  }

})(window.MockMate);
