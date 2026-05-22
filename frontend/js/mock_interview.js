/* ========================================
   MockMate.MockInterview — 拟真面试模块
   多面试官角色管理 + 拟真面试会话
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  var MI = {};

  // ---- 工具函数 ----

  function parseFocusArea(v) {
    return String(v || '')
      .split(/[,，、]/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function getAvatarChar(name) {
    return (name || '?').charAt(0);
  }

  var _editingId = null;        // 编辑中的面试官 ID
  var _sessionId = null;        // 当前会话 ID
  var _ws = null;               // WebSocket 连接
  var _timerInterval = null;    // 计时器
  var _elapsedSeconds = 0;      // 已用秒数
  var _maxDuration = 0;         // 面试总时长（秒）
  var _isRecording = false;     // 是否正在录音
  var _mediaRecorder = null;    // 录音器
  var _audioChunks = [];        // 录音数据
  var _stream = null;           // 麦克风流
  var _submitTime = 0;          // 最后一次提交时间戳 (ms)
  var _thinkingTimeout = null;  // 思考态延迟定时器
  var _thinkingDotTimer = null; // 思考态 dots 动画定时器
  var _fromSetupTab = false;    // 是否从准备页面进入（禁止直接访问）
  var _interviewers = [];       // 选中面试官的 id 列表（按选中顺序）
  var _questionCounter = 0;     // 当前题目计数
  var _switchInProgress = false; // 面试官切换中（音频流开始前标记）

  // ---- 流式音频播放状态 ----
  var _streamingAudioActive = false; // 是否正在流式播放
  var _audioMediaSource = null;      // MediaSource 实例
  var _audioSourceBuffer = null;     // SourceBuffer
  var _audioChunkQueue = [];         // 待追加的音频 chunk 队列
  var _streamingAudioEl = null;      // 流式播放 <audio> 元素

  // ---- 初始化 ----
  MI.init = function () {
    console.log('MockMate: MockInterview init OK');

    // 事件委托：面试官管理列表（编辑/删除/添加预设）
    var listEl = document.getElementById('mockInterviewerList');
    if (listEl) {
      listEl.addEventListener('click', function (e) {
        var editBtn = e.target.closest('[data-action="edit"]');
        if (editBtn) { MI.editInterviewer(editBtn.dataset.id); return; }
        var deleteBtn = e.target.closest('[data-action="delete"]');
        if (deleteBtn) { MI.deleteInterviewer(deleteBtn.dataset.id); return; }
        var presetsBtn = e.target.closest('[data-action="add-presets"]');
        if (presetsBtn) { MI.addPresets(); return; }
      });
    }

    // 事件委托：面试官选择列表（卡片点击切换选中）
    var selectEl = document.getElementById('mockInterviewerSelect');
    if (selectEl) {
      selectEl.addEventListener('click', function (e) {
        var card = e.target.closest('.mock-iv-select-item');
        if (!card) return;
        var cb = card.querySelector('.mock-iv-checkbox');
        if (!cb) return;
        cb.checked = !cb.checked;
        card.classList.toggle('selected', cb.checked);
        MI.updateStartButtonState();
      });
    }
  };

  // ==================== 面试官 CRUD ====================

  // 预设面试官（带行为建模属性）
  var PRESET_INTERVIEWERS = [
    {
      name: '张工',
      role: '资深工程师',
      style: '严谨深入',
      focus_area: ['编码能力', '项目深挖', '技术原理'],
      voice_style: '稳重男声',
      aggressiveness: 0.5,
      follow_up_depth: 0.8,
      interruption_rate: 0.15,
      preferred_stages: ['intro', 'resume', 'general_tech'],
      prompt_template: '你是一位资深工程师，面试风格严谨深入。你善于从一个技术点层层深入，考察候选人对技术原理的掌握程度。\n\n你的核心考察方向是：编码能力、项目深挖、技术原理。\n\n注意事项：\n- 保持严谨深入的风格\n- 聚焦考察编码能力、项目深挖、技术原理\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容',
    },
    {
      name: '李总',
      role: '技术总监',
      style: '宏观开放',
      focus_area: ['架构设计', '系统设计', '技术决策'],
      voice_style: '阳光男声',
      aggressiveness: 0.4,
      follow_up_depth: 0.6,
      interruption_rate: 0.1,
      preferred_stages: ['general_tech', 'deep_dive', 'project'],
      prompt_template: '你是一位技术总监，面试风格宏观开放。你关注候选人的技术视野和架构能力，喜欢讨论系统设计的权衡取舍。\n\n你的核心考察方向是：架构设计、系统设计、技术决策。\n\n注意事项：\n- 保持宏观开放的风格\n- 聚焦考察架构设计、系统设计、技术决策\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容',
    },
    {
      name: '王老师',
      role: 'HR 负责人',
      style: '温和引导',
      focus_area: ['软技能', '文化匹配', '职业规划'],
      voice_style: '温柔女声',
      aggressiveness: 0.1,
      follow_up_depth: 0.2,
      interruption_rate: 0.0,
      preferred_stages: ['intro', 'hr', 'qna', 'end'],
      prompt_template: '你是一位 HR 负责人，面试风格温和引导。你关注候选人的职业规划、团队协作能力和文化契合度。\n\n你的核心考察方向是：软技能、文化匹配、职业规划。\n\n注意事项：\n- 保持温和引导的风格\n- 聚焦考察软技能、文化匹配、职业规划\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容',
    },
    {
      name: '刘博',
      role: '算法专家',
      style: '尖锐深入',
      focus_area: ['算法与数据结构', '代码优化', '数学基础'],
      voice_style: '深沉男声',
      aggressiveness: 0.8,
      follow_up_depth: 0.9,
      interruption_rate: 0.3,
      preferred_stages: ['deep_dive', 'pressure'],
      prompt_template: '你是一位算法专家，面试风格尖锐深入。你擅长考察算法思维和代码优化能力，喜欢挑战候选人的逻辑极限。\n\n你的核心考察方向是：算法与数据结构、代码优化、数学基础。\n\n注意事项：\n- 保持尖锐深入的风格\n- 聚焦考察算法与数据结构、代码优化、数学基础\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容',
    },
    {
      name: '陈总',
      role: '业务负责人',
      style: '实战导向',
      focus_area: ['业务理解', '项目落地', '沟通协作'],
      voice_style: '干练男声',
      aggressiveness: 0.6,
      follow_up_depth: 0.5,
      interruption_rate: 0.2,
      preferred_stages: ['project', 'pressure'],
      prompt_template: '你是一位业务负责人，面试风格实战导向。你关注候选人将技术转化为业务价值的能力，以及跨团队协作的实战经验。\n\n你的核心考察方向是：业务理解、项目落地、沟通协作。\n\n注意事项：\n- 保持实战导向的风格\n- 聚焦考察业务理解、项目落地、沟通协作\n- 根据候选人的回答质量自然追问，不要一次性问多个问题\n- 不要重复其他面试官已经问过的内容',
    },
  ];

  MI.addPresets = async function () {
    if (!confirm('将一键添加 5 种预设面试官角色（资深工程师、技术总监、HR、算法专家、业务负责人），是否继续？')) return;

    var btns = document.querySelectorAll('.mock-presets-btn, [onclick*="addPresets"]');
    var btn = btns.length > 0 ? btns[0] : null;
    var originalText = btn ? btn.textContent : '';
    if (btn) { btn.textContent = '添加中...'; btn.disabled = true; }

    try {
      var count = 0;
      for (var i = 0; i < PRESET_INTERVIEWERS.length; i++) {
        var p = PRESET_INTERVIEWERS[i];
        // 检查是否已存在同名的面试官
        var existing = await M.API.mockListInterviewers();
        var hasName = (existing.interviewers || []).some(function (iv) { return iv.name === p.name; });
        if (hasName) continue;
        await M.API.mockCreateInterviewer(p);
        count++;
      }
      M.toast('成功添加 ' + count + ' 位预设面试官');
      MI.loadInterviewers();
    } catch (e) {
      M.toast('添加预设失败: ' + e.message);
    }

    if (btn) { btn.textContent = originalText; btn.disabled = false; }
  };

  MI.loadInterviewers = async function () {
    try {
      var res = await M.API.mockListInterviewers();
      MI.renderInterviewerList(res.interviewers || []);
      MI.renderInterviewerSelect(res.interviewers || []);
    } catch (e) {
      console.error('加载面试官失败:', e);
    }
  };

  MI.renderInterviewerList = function (interviewers) {
    var el = document.getElementById('mockInterviewerList');
    if (!el) return;

    if (!interviewers || interviewers.length === 0) {
      el.innerHTML = '<div class="mock-empty-state">还没有面试官<br>' +
        '<button class="btn btn-sm btn-primary" data-action="add-presets">添加预设角色</button>' +
        '</div>';
      return;
    }

    el.innerHTML = interviewers.map(function (iv) {
      var tags = parseFocusArea(iv.focus_area).map(function (f) {
        return '<span class="mock-iv-tag">' + M.esc(f) + '</span>';
      }).join('');
      var avatarChar = getAvatarChar(iv.name);
      return '<div class="mock-iv-card" data-id="' + iv.id + '">' +
        '<div class="mock-iv-avatar">' + M.esc(avatarChar) + '</div>' +
        '<div class="mock-iv-info">' +
          '<div class="mock-iv-name">' + M.esc(iv.name || '') + '</div>' +
          '<div class="mock-iv-role">' + M.esc(iv.role || '') + ' · ' + M.esc(iv.style || '') + '</div>' +
          '<div class="mock-iv-tags">' + tags + '</div>' +
        '</div>' +
        '<div class="mock-iv-actions">' +
          '<button class="btn btn-sm btn-secondary" data-action="edit" data-id="' + iv.id + '">编辑</button>' +
          '<button class="btn btn-sm btn-danger" data-action="delete" data-id="' + iv.id + '">删除</button>' +
        '</div>' +
      '</div>';
    }).join('');
  };

  MI.renderInterviewerSelect = function (interviewers) {
    var el = document.getElementById('mockInterviewerSelect');
    if (!el) return;

    if (!interviewers || interviewers.length === 0) {
      el.innerHTML = '<div class="mock-empty-state">请先在上方添加面试官</div>';
      document.getElementById('mockStartBtn').disabled = true;
      return;
    }

    el.innerHTML = interviewers.map(function (iv) {
      var tags = parseFocusArea(iv.focus_area).map(function (f) {
        return '<span class="mock-iv-tag">' + M.esc(f) + '</span>';
      }).join('');
      var avatarChar = getAvatarChar(iv.name);
      return '<div class="mock-iv-select-item selected" data-id="' + iv.id + '" data-voice="' + M.esc(iv.voice_style || '') + '">' +
        '<input type="checkbox" class="mock-iv-checkbox" value="' + iv.id + '" checked>' +
        '<span class="check-mark">✓</span>' +
        '<div class="mock-iv-avatar" style="margin-right:4px">' + M.esc(avatarChar) + '</div>' +
        '<div style="flex:1;min-width:0">' +
          '<strong class="mock-iv-name">' + M.esc(iv.name || '') + '</strong>' +
          '<span class="mock-iv-role" style="font-size:12px;color:var(--text2);margin-left:8px">' + M.esc(iv.role || '') + '</span>' +
          '<div class="mock-iv-tags">' + tags + '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    MI.updateStartButtonState();
  };

  MI.updateStartButtonState = function () {
    var anyChecked = document.querySelectorAll('.mock-iv-checkbox:checked').length > 0;
    document.getElementById('mockStartBtn').disabled = !anyChecked;
  };

  MI.showAddDialog = function () {
    _editingId = null;
    document.getElementById('mockIvDialogTitle').textContent = '添加面试官';
    document.getElementById('mockIvName').value = '';
    document.getElementById('mockIvRole').value = '';
    document.getElementById('mockIvStyle').value = '';
    document.getElementById('mockIvFocus').value = '';
    document.getElementById('mockIvVoice').value = '';
    document.getElementById('mockIvPrompt').value = '';
    document.getElementById('mockIvDialog').style.display = 'flex';
  };

  MI.hideAddDialog = function () {
    document.getElementById('mockIvDialog').style.display = 'none';
  };

  MI.saveInterviewer = async function () {
    var name = document.getElementById('mockIvName').value.trim();
    var role = document.getElementById('mockIvRole').value.trim();
    var style = document.getElementById('mockIvStyle').value.trim();
    var focusStr = document.getElementById('mockIvFocus').value.trim();

    if (!name) { M.toast('请填写面试官姓名'); return; }
    if (!role) { M.toast('请填写面试官角色'); return; }
    if (!style) { M.toast('请填写面试风格'); return; }

    var focusArea = focusStr ? focusStr.split(/[,，、]/).map(function (s) { return s.trim(); }).filter(Boolean) : [role];

    var data = { name: name, role: role, style: style, focus_area: focusArea };
    var voice = document.getElementById('mockIvVoice').value.trim();
    if (voice) data.voice_style = voice;
    var prompt = document.getElementById('mockIvPrompt').value.trim();
    if (prompt) data.prompt_template = prompt;

    try {
      if (_editingId) {
        await M.API.mockUpdateInterviewer(_editingId, data);
        M.toast('面试官已更新');
      } else {
        await M.API.mockCreateInterviewer(data);
        M.toast('面试官已添加');
      }
      MI.hideAddDialog();
      MI.loadInterviewers();
    } catch (e) {
      M.toast('保存失败: ' + e.message);
    }
  };

  MI.editInterviewer = async function (id) {
    try {
      var res = await M.API.mockGetInterviewer(id);
      var iv = res.interviewer;
      _editingId = id;
      document.getElementById('mockIvDialogTitle').textContent = '编辑面试官';
      document.getElementById('mockIvName').value = iv.name || '';
      document.getElementById('mockIvRole').value = iv.role || '';
      document.getElementById('mockIvStyle').value = iv.style || '';
      var focusStr = Array.isArray(iv.focus_area) ? iv.focus_area.join(', ') : (iv.focus_area || '');
      document.getElementById('mockIvFocus').value = focusStr;
      document.getElementById('mockIvVoice').value = iv.voice_style || '';
      document.getElementById('mockIvPrompt').value = iv.prompt_template || '';
      document.getElementById('mockIvDialog').style.display = 'flex';
    } catch (e) {
      M.toast('获取面试官信息失败: ' + e.message);
    }
  };

  MI.deleteInterviewer = async function (id) {
    if (!confirm('确定要删除这个面试官吗？')) return;
    try {
      await M.API.mockDeleteInterviewer(id);
      M.toast('面试官已删除');
      MI.loadInterviewers();
    } catch (e) {
      M.toast('删除失败: ' + e.message);
    }
  };

  // ==================== 拟真面试会话 ====================

  /** 从「准备面试」标签页跳转到拟真面试页 */
  MI.goToMockTab = function () {
    // 标记从准备页面进入
    _fromSetupTab = true;
    // 检查是否满足前置条件（简历评分）
    var btnEl = document.getElementById('startMockInterviewBtn');
    if (btnEl && btnEl.getAttribute('data-disabled') !== 'false') {
      var score = M.state._resumeScore;
      if (!score) {
        M.toast('请先完成简历评分（第3步）后再开始拟真面试');
      } else if (score.score < 70) {
        M.toast('简历评分 ' + score.score + ' 分，低于 70 分无法开始面试，请优化简历');
      }
      return;
    }

    // 切换到拟真面试标签页
    M.switchTab('mock-interview');
    M.toast('请选择面试官并点击"开始拟真面试"');
  };

  MI.startInterview = async function () {
    // 必须从准备页面进入
    if (!_fromSetupTab) {
      M.toast('请从「准备面试」标签页进入拟真面试');
      M.switchTab('setup');
      document.getElementById('startMockInterviewBtn').scrollIntoView({ behavior: 'smooth' });
      return;
    }

    // 清除上次报告和流式音频状态
    var reportEl = document.getElementById('mockReportContainer');
    if (reportEl) reportEl.remove();
    _streamingAudioActive = false;

    // 重建 mock-main 内容（终版结构：panel + 问题区 + 输入区）
    var mainArea = document.querySelector('.mock-main');
    if (mainArea) {
      mainArea.innerHTML =
        '<div class="mock-panel" id="mockPanel"></div>' +
        '<div class="mock-question-area" id="mockQuestionArea">' +
          '<div class="mock-question-text" id="mockQuestionText" style="display:none"></div>' +
        '</div>' +
        '<div class="mock-input-area" id="mockInputArea">' +
          '<textarea id="mockAnswerInput" placeholder="沉稳作答..." rows="4"></textarea>' +
          '<div class="mock-input-actions">' +
            '<button class="mock-voice-btn" id="mockVoiceBtn" onclick="MockMate.MockInterview.toggleRecording()">🎤</button>' +
            '<button class="mock-submit-btn" id="mockSubmitBtn" onclick="MockMate.MockInterview.submitAnswer()">提交回答</button>' +
            '<span class="mock-submit-hint" id="mockSubmitHint"></span>' +
          '</div>' +
          '<div class="mock-recording-status" id="mockRecordingStatus" style="font-size:12px;color:#8B94A7;margin-top:4px;text-align:center"></div>' +
          '<div class="mock-anti-chat" id="mockAntiChat" style="opacity:0"></div>' +
        '</div>';
    }
    // 重置 end 按钮显示
    var endBtn = document.getElementById('mockEndBtn');
    if (endBtn) endBtn.style.display = '';

    // 检查简历评分
    if (!M.state._resumeScore) {
      M.toast('请先在「准备面试」标签页完成简历评分');
      M.switchTab('setup');
      document.getElementById('scoreResumeBtn').scrollIntoView({ behavior: 'smooth' });
      return;
    }
    if (M.state._resumeScore.score < 70) {
      M.toast('简历评分 ' + M.state._resumeScore.score + ' 分，低于 70 分无法开始面试，请优化简历');
      return;
    }

    // 获取选中的面试官（含姓名和角色用于席位卡片）
    var checked = document.querySelectorAll('.mock-iv-checkbox:checked');
    if (checked.length === 0) {
      M.toast('请至少选择一位面试官');
      return;
    }

    var interviewerIds = [];
    var interviewerInfos = [];
    Array.from(checked).forEach(function (cb) {
      interviewerIds.push(cb.value);
      var card = cb.closest('.mock-iv-select-item');
      interviewerInfos.push({
        id: cb.value,
        name: card ? (card.querySelector('.mock-iv-name') ? card.querySelector('.mock-iv-name').textContent : '面试官') : '面试官',
        role: card ? (card.querySelector('.mock-iv-role') ? card.querySelector('.mock-iv-role').textContent : '') : '',
        voice_style: card ? (card.getAttribute('data-voice') || '') : '',
      });
    });

    var duration = parseInt(document.getElementById('mockDurationRange').value) || 40;
    _maxDuration = duration * 60;

    M.setBtnLoading(document.getElementById('mockStartBtn'), true, '启动中...');

    try {
      // 从准备页读取简历和岗位信息
      var resume = document.getElementById('resumeInput').value.trim();
      var position = document.getElementById('positionInput').value.trim();
      var company = document.getElementById('companyInput').value.trim();
      var profile = { position: position };
      if (company) profile.company = company;

      var res = await M.API.mockStartInterview({
        interviewer_ids: interviewerIds,
        max_duration: duration,
        resume: resume || undefined,
        profile: profile,
      });

      _sessionId = res.session_id;
      _elapsedSeconds = 0;
      _submitTime = 0;
      M.state.mockInterviewActive = true;

      // 隐藏配置区，进入全屏沉浸模式
      document.getElementById('mockInterviewerSection').style.display = 'none';
      document.getElementById('mockStartSection').style.display = 'none';
      document.getElementById('mockSessionSection').classList.add('active');

      // 设置岗位标签
      var posLabel = document.getElementById('mockPositionLabel');
      if (posLabel) posLabel.textContent = position || '技术面试';

      // 重置 UI
      document.getElementById('mockQuestionText').style.display = 'none';
      document.getElementById('mockAntiChat').style.opacity = '0';
      document.getElementById('mockSubmitHint').textContent = '';
      var submitBtn = document.getElementById('mockSubmitBtn');
      submitBtn.textContent = '提交回答';
      submitBtn.className = 'mock-submit-btn';
      submitBtn.disabled = false;
      var ta = document.getElementById('mockAnswerInput');
      ta.readOnly = false;
      ta.value = '';
      ta.disabled = false;

      // 渲染面试官席位卡片
      MI._initInterviewerQueue(interviewerInfos);

      // 显示第一个问题
      MI.displayQuestion(res);

      // 启动倒计时
      MI.startTimer();

      // 连接 WebSocket
      MI.connectWebSocket();

      M.toast('拟真面试已开始');
    } catch (e) {
      M.toast('启动失败: ' + e.message);
    }

    M.setBtnLoading(document.getElementById('mockStartBtn'), false, '开始拟真面试');
  };

  var _pendingSubmit = false;

  MI.submitAnswer = async function () {
    if (_pendingSubmit) { return; }

    var ta = document.getElementById('mockAnswerInput');
    var answerText = ta.value.trim();
    if (!answerText) { M.toast('请先输入回答'); return; }

    // 防闲聊：检测明显无关输入
    if (/^(你好|您好|哈哈|呵呵|嗯|哦|不知道|不会|谢谢|hi|hello|test|测试|\.\.\.|你猜|你说)$/i.test(answerText)) {
      ta.value = '';
      MI.showAntiChat();
      return;
    }

    _pendingSubmit = true;
    _submitTime = Date.now();

    // 锁定输入（readonly 而非 disabled，保留视觉内容）
    ta.readOnly = true;
    ta.value = '';  // 提交后立即清空答题框
    var btn = document.getElementById('mockSubmitBtn');
    btn.textContent = '已提交';
    btn.className = 'mock-submit-btn submitted';
    btn.disabled = true;
    document.getElementById('mockSubmitHint').textContent = '已提交当前回答';

    // 显示思考态
    MI.showThinking();

    try {
      if (_ws && _ws.readyState === WebSocket.OPEN) {
        _ws.send(JSON.stringify({
          type: 'answer', text: answerText,
          elapsed_minutes: Math.floor(_elapsedSeconds / 60),
        }));
        // 60 秒超时降级到 REST API
        var fallbackTimer = setTimeout(async function () {
          if (!_pendingSubmit) return;
          console.warn('WebSocket 响应超时，降级 REST API');
          _pendingSubmit = false;
          try {
            ta.readOnly = false;
            ta.value = '';
            var res = await M.API.mockSubmitAnswer({
              session_id: _sessionId, answer: answerText,
              elapsed_minutes: Math.floor(_elapsedSeconds / 60),
            });
            if (res.completed) MI.handleInterviewEnd(res);
            else if (res.next_question_text) MI.displayQuestion(res);
          } catch (e) { M.toast('提交失败: ' + e.message); }
          btn.textContent = '提交回答';
          btn.className = 'mock-submit-btn';
          btn.disabled = false;
        }, 60000);
        _ws._answerFallbackTimer = fallbackTimer;
        _ws._pendingAnswerText = answerText;
      } else {
        // REST API 路径
        ta.value = '';
        var res = await M.API.mockSubmitAnswer({
          session_id: _sessionId, answer: answerText,
          elapsed_minutes: Math.floor(_elapsedSeconds / 60),
        });
        if (res.completed) MI.handleInterviewEnd(res);
        else if (res.next_question_text) MI.displayQuestion(res);
        MI._clearPendingSubmit();
      }
    } catch (e) {
      M.toast('提交失败: ' + e.message);
      MI._clearPendingSubmit();
    }
  };

  /** 初始化面试官席位 */
  MI._initInterviewerQueue = function (infos) {
    _interviewers = infos || [];
    _questionCounter = 0;

    var panel = document.getElementById('mockPanel');
    if (!panel) return;

    if (_interviewers.length === 0) {
      panel.innerHTML = '';
      return;
    }

    panel.innerHTML = _interviewers.map(function (iv, idx) {
      var voiceLabel = iv.voice_style ? '<span class="mock-iv-voice-badge">' + M.esc(iv.voice_style) + '</span>' : '';
      return '<div class="mock-panel-card' + (idx === 0 ? ' current' : '') + '" data-idx="' + idx + '">' +
        '<div class="mock-panel-card-badge">● 当前提问</div>' +
        '<div class="mock-iv-card-name">' + M.esc(iv.name || '面试官') + '</div>' +
        '<div class="mock-iv-card-role">' + M.esc(iv.role || '') + '</div>' +
        '<div class="mock-iv-card-status">' + (idx === 0 ? '正在发问' : '待发言') + ' ' + voiceLabel + '</div>' +
        '</div>';
    }).join('');
  };

  /** 显示思考态 */
  MI.showThinking = function () {
    var qEl = document.getElementById('mockQuestionText');
    qEl.style.display = 'none';
    var area = document.getElementById('mockQuestionArea');
    area.innerHTML = '<div class="mock-thinking">面试官正在思考<span class="thinking-dots"></span></div>';
    // 动态循环 ...
    var dotsEl = area.querySelector('.thinking-dots');
    if (dotsEl) {
      var dotCount = 0;
      _thinkingDotTimer = setInterval(function () {
        dotCount = (dotCount + 1) % 4;
        dotsEl.textContent = '.'.repeat(dotCount) + '\u00A0'.repeat(3 - dotCount);
      }, 400);
    }
  };

  /** 面试官切换（卡片动画 + 过渡文字） */
  MI.showSwitchTransition = function (fromName, toName) {
    // 重置流式音频状态，让 displayQuestion 能触发 playAudio 为新面试官播放语音
    _streamingAudioActive = false;

    // 显示过渡文字
    var area = document.getElementById('mockQuestionArea');
    area.innerHTML = '<div class="mock-switch-text">' + M.esc(fromName) + ' 的问题问完了。接下来由 ' + M.esc(toName) + ' 继续。</div>';

    // 卡片切换：当前面试官退出
    var cards = document.querySelectorAll('.mock-panel-card');
    cards.forEach(function (card) {
      // 先移除所有卡片的呼吸灯，防止旧卡呼吸灯残留
      card.classList.remove('speaking');
      var nameEl = card.querySelector('.mock-iv-card-name');
      if (!nameEl) return;
      var name = nameEl.textContent;
      if (name === fromName) {
        card.classList.remove('current');
        card.classList.add('exiting');
        setTimeout(function () { card.classList.remove('exiting'); }, 500);
      } else if (name === toName) {
        // 等待当前退出动画完成后接管
        setTimeout(function () {
          card.classList.add('current');
          // 接管后立即点亮呼吸灯，因为新题的音频已在流式阶段完成播放
          card.classList.add('speaking');
        }, 400);
      }
    });
  };

  /** 防闲聊：显示系统提示 */
  MI.showAntiChat = function () {
    var el = document.getElementById('mockAntiChat');
    el.textContent = '[ 系统提示：当前为面试环境，请针对问题作答 ]';
    el.style.opacity = '1';
    // 3 秒后淡出
    setTimeout(function () {
      el.style.opacity = '0';
    }, 3000);
  };

  /** 流式文本缓冲区 */
  var _streamingText = '';

  MI.displayQuestion = function (data) {
    var qText = data.question_text || data.next_question_text || '';
    _questionCounter++;

    // 重置流式缓冲区
    _streamingText = qText;

    // 重建问题文本元素（思考态/切换态可能已移除旧的）
    var area = document.getElementById('mockQuestionArea');
    area.innerHTML = '';
    var qEl = document.createElement('div');
    qEl.id = 'mockQuestionText';
    qEl.className = 'mock-question-text';
    qEl.textContent = qText;
    area.appendChild(qEl);

    // 自动播放语音（用卡片呼吸灯效指示）
    // 如果已经通过流式音频播放，不再重复播放
    if (data.audio_url && !_streamingAudioActive) {
      setTimeout(function () { MI.playAudio(data.audio_url); }, 300);
    }
    // 重置流式音频状态
    _streamingAudioActive = false;

    // 解锁输入
    var ta = document.getElementById('mockAnswerInput');
    ta.readOnly = false;
    ta.disabled = false;
    var submitBtn = document.getElementById('mockSubmitBtn');
    submitBtn.textContent = '提交回答';
    submitBtn.className = 'mock-submit-btn';
    submitBtn.disabled = false;
    document.getElementById('mockSubmitHint').textContent = '';

    // 聚焦
    setTimeout(function () {
      ta.focus();
    }, 300);
  };

  /** 播放语音（卡片呼吸灯效），自动播放失败时显示手动按钮 */
  MI.playAudio = function (url) {
    if (!url) return;
    var card = document.querySelector('.mock-panel-card.current');
    if (card) card.classList.add('speaking');
    var audio = new Audio(url);
    audio.onended = function () {
      if (card) card.classList.remove('speaking');
    };
    audio.onerror = function () {
      if (card) card.classList.remove('speaking');
    };
    audio.play().catch(function () {
      // 自动播放被浏览器阻止 → 卡片显示可点击播放的提示
      if (card) card.classList.remove('speaking');
      // 在卡片右上角加一个扬声器按钮
      if (card && !card.querySelector('.mock-card-play-btn')) {
        var btn = document.createElement('button');
        btn.className = 'mock-card-play-btn';
        btn.textContent = '🔊';
        btn.title = '点击播放语音';
        btn.onclick = function (e) {
          e.stopPropagation();
          card.classList.add('speaking');
          audio.play().then(function () {
            btn.remove();
          }).catch(function () {
            card.classList.remove('speaking');
          });
        };
        card.appendChild(btn);
      }
    });
  };

  // ==================== 流式音频播放（MediaSource）====================

  /** 初始化流式音频播放器（MediaSource）
   *  @return {boolean} 是否成功创建 MediaSource
   */
  MI._initAudioStream = function () {
    _audioChunkQueue = [];

    _streamingAudioEl = document.getElementById('mockStreamAudio');
    if (!_streamingAudioEl) {
      _streamingAudioEl = document.createElement('audio');
      _streamingAudioEl.id = 'mockStreamAudio';
      _streamingAudioEl.style.display = 'none';
      document.body.appendChild(_streamingAudioEl);
    }

    // 音频播放结束后移除呼吸灯
    _streamingAudioEl.onended = function () {
      var card = document.querySelector('.mock-panel-card.current');
      if (card) card.classList.remove('speaking');
    };
    _streamingAudioEl.onerror = function () {
      var card = document.querySelector('.mock-panel-card.current');
      if (card) card.classList.remove('speaking');
    };

    // 尝试创建 MediaSource
    try {
      if (!window.MediaSource) {
        console.warn('浏览器不支持 MediaSource');
        return false;
      }
      _audioMediaSource = new MediaSource();
      _audioMediaSource.addEventListener('sourceopen', function () {
        try {
          _audioSourceBuffer = _audioMediaSource.addSourceBuffer('audio/mpeg');
          _audioSourceBuffer.addEventListener('updateend', function () {
            if (_audioChunkQueue.length > 0 && !_audioSourceBuffer.updating) {
              var next = _audioChunkQueue.shift();
              try { _audioSourceBuffer.appendBuffer(next); }
              catch (e) { console.warn('追加音频 chunk 失败:', e); }
            }
          });
          // 追加已排队的缓冲数据
          while (_audioChunkQueue.length > 0 && _audioSourceBuffer && !_audioSourceBuffer.updating) {
            var chunk = _audioChunkQueue.shift();
            _audioSourceBuffer.appendBuffer(chunk);
          }
        } catch (e) {
          console.warn('SourceBuffer 创建失败:', e);
          _audioSourceBuffer = null;
        }
      });

      _streamingAudioEl.src = URL.createObjectURL(_audioMediaSource);
      _streamingAudioEl.play().catch(function (e) {
        // 自动播放被阻止是预期的，稍后用户交互后会自动继续
        console.warn('流式音频启动（可忽略）:', e.message);
      });
      return true;
    } catch (e) {
      console.warn('MediaSource 初始化失败:', e);
      _audioMediaSource = null;
      return false;
    }
  };

  /** 解码 base64 并追加到音频缓冲区 */
  MI._feedAudioChunk = function (base64Data) {
    try {
      var binary = atob(base64Data);
      var len = binary.length;
      var bytes = new Uint8Array(len);
      for (var i = 0; i < len; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      var buffer = bytes.buffer;

      if (_audioSourceBuffer && !_audioSourceBuffer.updating) {
        _audioSourceBuffer.appendBuffer(buffer);
      } else if (_audioSourceBuffer) {
        _audioChunkQueue.push(buffer);
      } else {
        // MediaSource 未就绪，排队等待
        _audioChunkQueue.push(buffer);
      }
    } catch (e) {
      console.warn('音频 chunk 解码失败:', e);
    }
  };

  /** 结束音频流 */
  MI._finalizeAudioStream = function (fallbackUrl) {
    if (_audioMediaSource && _audioMediaSource.readyState === 'open') {
      try {
        _audioMediaSource.endOfStream();
      } catch (e) {
        console.warn('endOfStream 失败:', e);
      }
    }
    // 如果 MediaSource 没有成功缓冲数据（格式不支持等），降级到 URL 播放
    if (fallbackUrl) {
      var hasBuffered = _audioSourceBuffer && _audioSourceBuffer.buffered && _audioSourceBuffer.buffered.length > 0;
      if (!hasBuffered) {
        console.warn('MediaSource 未缓冲数据，降级到 URL 播放');
        setTimeout(function () { MI.playAudio(fallbackUrl); }, 300);
      }
    }
    _streamingAudioActive = false;
  };

  /** 停止当前音频流（新题开始时调用） */
  MI._stopAudioStream = function () {
    // 停止 MediaSource 流式播放
    if (_audioMediaSource) {
      try {
        if (_audioMediaSource.readyState === 'open') {
          _audioMediaSource.endOfStream();
        }
      } catch (e) { /* ignore */ }
      _audioMediaSource = null;
    }
    _audioSourceBuffer = null;
    _audioChunkQueue = [];
    // 停止并清理 audio 元素
    if (_streamingAudioEl) {
      _streamingAudioEl.pause();
      _streamingAudioEl.removeAttribute('src');
      _streamingAudioEl.load();
    }
    // 移除所有卡片的呼吸灯（防止切换过程中旧卡残留呼吸灯）
    document.querySelectorAll('.mock-panel-card').forEach(function (c) {
      c.classList.remove('speaking');
    });
    // 重置状态
    _streamingAudioActive = false;
  };

  // ==================== WebSocket ====================

  MI.connectWebSocket = function () {
    if (!_sessionId) return;

    var wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = wsProto + '//' + window.location.host + '/api/mock/interview/ws/' + _sessionId;

    try {
      _ws = new WebSocket(wsUrl);

      _ws.onmessage = function (event) {
        try {
          var msg = JSON.parse(event.data);
          MI.handleWsMessage(msg);
        } catch (e) {
          console.error('WebSocket 消息解析失败:', e);
        }
      };

      _ws.onclose = function () {
        console.log('WebSocket 已断开');
        _ws = null;
      };

      _ws.onerror = function (err) {
        console.error('WebSocket 错误:', err);
      };
    } catch (e) {
      console.warn('WebSocket 连接失败，将使用 REST API:', e);
      _ws = null;
    }
  };

  /** 清除 WebSocket 提交等待状态 */
  MI._clearPendingSubmit = function () {
    _pendingSubmit = false;
    if (_thinkingTimeout) {
      clearTimeout(_thinkingTimeout);
      _thinkingTimeout = null;
    }
    if (_thinkingDotTimer) {
      clearInterval(_thinkingDotTimer);
      _thinkingDotTimer = null;
    }
    var btn = document.getElementById('mockSubmitBtn');
    if (btn) { btn.disabled = false; btn.textContent = '提交回答'; btn.className = 'mock-submit-btn'; }
    // 清除 WebSocket 上的超时定时器
    if (_ws && _ws._answerFallbackTimer) {
      clearTimeout(_ws._answerFallbackTimer);
      _ws._answerFallbackTimer = null;
      _ws._pendingAnswerText = null;
    }
    var ta = document.getElementById('mockAnswerInput');
    ta.readOnly = false;
    ta.disabled = false;
    ta.value = '';
  };

  /** 延迟显示下一题（确保最小思考时间 2.5s） */
  MI._scheduleNextQuestion = function (data) {
    // 清除思考态定时器
    if (_thinkingTimeout) {
      clearTimeout(_thinkingTimeout);
      _thinkingTimeout = null;
    }
    var elapsed = Date.now() - _submitTime;
    var minThink = 2500; // 最小思考时间 2.5s
    var delay = Math.max(0, minThink - elapsed);

    MI._clearPendingSubmit();
    if (delay > 0) {
      _thinkingTimeout = setTimeout(function () {
        _thinkingTimeout = null;
        MI.displayQuestion(data);
      }, delay);
    } else {
      MI.displayQuestion(data);
    }
  };

  /** 流式题目完成：用服务端最终文本覆盖流式文本（含脱敏），解锁输入 */
  MI._finalizeQuestion = function (data) {
    MI._clearPendingSubmit();

    // 用服务端返回的最终文本覆盖流式累积文本（确保脱敏版本生效）
    var finalText = data.next_question_text || data.question_text || '';
    if (finalText) {
      var qEl = document.getElementById('mockQuestionText');
      if (qEl) qEl.textContent = finalText;
    }
    _streamingText = '';

    // 如果有 audio_url 且没有流式音频播放，降级播放
    if (data.audio_url && !_streamingAudioActive) {
      setTimeout(function () { MI.playAudio(data.audio_url); }, 300);
    }
    _streamingAudioActive = false;
  };

  MI.handleWsMessage = function (msg) {
    switch (msg.type) {
      case 'switch_interviewer':
        // 面试官切换信号（来自 handle_answer_stream 的 switch_interviewer 阶段）
        // 在音频流开始前发送，确保先显示切换动画再播音频
        _switchInProgress = true;
        MI.showSwitchTransition(msg.from, msg.to);
        // 清空流式缓冲区，防止旧题的 token 残留在新题中
        _streamingText = '';
        break;

      case 'question':
        // 发现有面试官切换（interviewer_index 变化或 msg 含 switch_from）
        if (msg.switch_from && msg.switch_to) {
          if (_switchInProgress) {
            // 切换动画已由 switch_interviewer 消息触发，直接显示下一题
            _switchInProgress = false;
            MI._scheduleNextQuestion(msg);
          } else {
            // 降级路径（无 WebSocket 流式切换信号）
            MI.showSwitchTransition(msg.switch_from, msg.switch_to);
            var switchDelay = 2000;
            setTimeout(function () {
              MI._scheduleNextQuestion(msg);
            }, switchDelay);
          }
        } else if (msg.streamed) {
          // 文本已通过 question_token 流式显示，只需要解锁输入
          MI._finalizeQuestion(msg);
        } else {
          MI._scheduleNextQuestion(msg);
        }
        break;

      case 'question_token':
        // 流式追加问题文本
        if (typeof msg.token === 'string') {
          var qEl = document.getElementById('mockQuestionText');
          if (!qEl) {
            var area = document.getElementById('mockQuestionArea');
            if (area) {
              // 第一个 token：移除"面试官正在思考..."提示
              var thinkingEl = area.querySelector('.mock-thinking');
              if (thinkingEl) thinkingEl.remove();

              qEl = document.createElement('div');
              qEl.id = 'mockQuestionText';
              qEl.className = 'mock-question-text';
              area.appendChild(qEl);
            }
          }
          if (qEl) {
            _streamingText += msg.token;
            qEl.textContent = _streamingText;
          }
        }
        break;

      case 'audio_chunk':
        // 流式音频 chunk
        if (!_streamingAudioActive) {
          var msOk = MI._initAudioStream();
          if (!msOk) {
            // MediaSource 不支持，降级：displayQuestion 会使用 URL 播放
            break;
          }
          _streamingAudioActive = true;
          // 当前面试官卡片呼吸灯
          var card = document.querySelector('.mock-panel-card.current');
          if (card) card.classList.add('speaking');
        }
        if (msg.data) MI._feedAudioChunk(msg.data);
        break;

      case 'audio_done':
        // 音频流结束（提供 fallback URL 给 MediaSource 降级用）
        MI._finalizeAudioStream(msg.audio_url);
        break;

      case 'clear_audio':
        // 新题开始，停止当前音频播放并清空缓冲
        MI._stopAudioStream();
        // 重置流式缓冲区 — 确保新题的文本 token 不会累加到旧题上
        _streamingText = '';
        break;

      case 'eval_token':
        break;

      case 'evaluation':
        // 静默消费：评估仅在报告中展示
        break;

      case 'end':
        MI._clearPendingSubmit();
        MI.handleInterviewEnd(msg);
        break;

      case 'error':
        _pendingSubmit = false;
        M.toast('错误: ' + (msg.message || '未知错误'));
        break;

      case 'pong':
        break;
    }
  };

  // ==================== 倒计时 ====================

  MI.startTimer = function () {
    if (_timerInterval) clearInterval(_timerInterval);
    _timerInterval = setInterval(function () {
      _elapsedSeconds++;
      var remaining = Math.max(0, _maxDuration - _elapsedSeconds);
      var h = String(Math.floor(remaining / 3600)).padStart(2, '0');
      var m = String(Math.floor((remaining % 3600) / 60)).padStart(2, '0');
      var s = String(remaining % 60).padStart(2, '0');
      var el = document.getElementById('mockTimer');
      if (el) {
        el.textContent = h + ':' + m + ':' + s;
        // 最后 5 分钟警告
        el.className = 'mock-countdown' +
          (remaining <= 300 ? ' warning' : '');
      }
    }, 1000);
  };

  MI.stopTimer = function () {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
  };

  // ==================== 结束面试 ====================

  MI.endInterview = function () {
    if (!confirm('确定要结束当前面试吗？')) return;

    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'end_request', reason: 'user_request' }));
    } else {
      MI.doEndInterview();
    }
  };

  MI.doEndInterview = async function () {
    try {
      var res = await M.API.mockEndInterview(_sessionId);
      MI.handleInterviewEnd(res);
    } catch (e) {
      M.toast('结束面试失败: ' + e.message);
    }
  };

  MI.handleInterviewEnd = function (data) {
    MI.stopTimer();
    _fromSetupTab = false; // 重置入口标记，下次必须从准备页面进入
    _pendingSubmit = false;
    M.state.mockInterviewActive = false;
    if (_thinkingTimeout) { clearTimeout(_thinkingTimeout); _thinkingTimeout = null; }
    if (_thinkingDotTimer) { clearInterval(_thinkingDotTimer); _thinkingDotTimer = null; }
    if (_ws) { try { _ws.close(); } catch (e) {} _ws = null; }
    if (_stream) { _stream.getTracks().forEach(function (t) { t.stop(); }); _stream = null; }

    var sessionId = data.session_id || _sessionId;
    var coverage = data.coverage || {};
    var total = data.total_questions || _questionCounter;

    // 显示结束过渡
    var area = document.getElementById('mockQuestionArea');
    area.innerHTML = '<div class="mock-switch-text">面试结束</div>';

    // 锁定界面
    document.getElementById('mockEndBtn').style.display = 'none';

    // 1.5s 后加载报告
    setTimeout(function () {
      // 在沉浸模式下显示报告
      var mainArea = document.querySelector('.mock-main');
      mainArea.innerHTML = ''; // 清除问题区和输入区
      var container = document.createElement('div');
      container.className = 'mock-report-container';
      container.id = 'mockReportContainer';
      mainArea.appendChild(container);

      // 恢复显示配置区（非沉浸模式）
      document.getElementById('mockInterviewerSection').style.display = '';
      document.getElementById('mockStartSection').style.display = '';

      // 获取完整报告
      if (sessionId) {
        MI._fetchReport(sessionId);
      } else {
        M.toast('面试已结束');
      }
    }, 1500);
  };

  /** 获取并渲染完整面试报告 */
  MI._fetchReport = async function (sessionId) {
    try {
      var res = await M.API.mockGetReport(sessionId);
      MI.showMockReport(res);
      M.toast('面试已结束，报告已生成');
    } catch (e) {
      console.error('获取面试报告失败:', e);
      M.toast('面试已结束');
    }
  };

  /** 渲染拟真面试报告 */
  MI.showMockReport = function (data) {
    var history = data.history || [];
    var coverage = data.coverage || {};
    var totalQ = data.total_questions || 0;

    // 从 history 提取问答对
    var qaPairs = [];
    var currentQ = null;
    for (var i = 0; i < history.length; i++) {
      var entry = history[i];
      if (entry.type === 'question') {
        if (currentQ) qaPairs.push(currentQ);
        currentQ = { question: entry, answer: null };
      } else if (entry.type === 'answer' && currentQ) {
        currentQ.answer = entry;
        qaPairs.push(currentQ);
        currentQ = null;
      }
    }
    if (currentQ) qaPairs.push(currentQ);

    // 计算平均分
    var scores = [];
    for (var j = 0; j < qaPairs.length; j++) {
      if (qaPairs[j].answer && qaPairs[j].answer.score != null) {
        scores.push(qaPairs[j].answer.score);
      }
    }
    var avgScore = scores.length > 0
      ? Math.round(scores.reduce(function (a, b) { return a + b; }, 0) / scores.length)
      : null;

    // 按面试官分组
    var byInterviewer = {};
    for (var k = 0; k < qaPairs.length; k++) {
      var pair = qaPairs[k];
      var name = pair.question.interviewer_name || '未知';
      if (!byInterviewer[name]) byInterviewer[name] = { questions: [], scores: [] };
      byInterviewer[name].questions.push(pair);
      if (pair.answer && pair.answer.score != null) {
        byInterviewer[name].scores.push(pair.answer.score);
      }
    }

    var reportEl = document.getElementById('mockReportContainer');
    if (!reportEl) {
      reportEl = document.createElement('div');
      reportEl.id = 'mockReportContainer';
      reportEl.className = 'mock-report-container';
      var mainArea = document.querySelector('.mock-main');
      if (mainArea) mainArea.appendChild(reportEl);
    }

    var html = '';

    // ====== 顶部摘要 ======
    html += '<div class="card" style="border-left:3px solid var(--accent)">';
    html += '<h2 style="font-size:18px;text-transform:none;color:var(--text)">拟真面试报告</h2>';

    // 分数行
    html += '<div class="score-row" style="margin:12px 0">';
    if (avgScore !== null) {
      html += '<span class="score-tag">综合评分 <span class="val" style="color:' + M.scoreColor(avgScore) + '">' + avgScore + '</span></span>';
    }
    // 各面试官平均分
    for (var name in byInterviewer) {
      var ivData = byInterviewer[name];
      if (ivData.scores.length > 0) {
        var ivAvg = Math.round(ivData.scores.reduce(function (a, b) { return a + b; }, 0) / ivData.scores.length);
        html += '<span class="score-tag">' + M.esc(name) + ' <span class="val" style="color:' + M.scoreColor(ivAvg) + '">' + ivAvg + '</span></span>';
      }
    }
    html += '</div>';

    // 考察覆盖
    html += '<div style="font-size:13px;color:var(--text2);margin-bottom:4px">' +
      '共提问 <strong>' + totalQ + '</strong> 题，考察覆盖 <strong>' + (coverage.covered || 0) + '/' + (coverage.total || 0) + '</strong>';

    if (coverage.remaining && coverage.remaining.length > 0) {
      html += '，未覆盖：' + coverage.remaining.map(M.esc).join('、');
    }
    html += '</div>';

    html += '</div>';

    // ====== 问答详情 ======
    if (qaPairs.length > 0) {
      html += '<h2 style="font-size:16px;text-transform:none;color:var(--text);margin-top:20px">问答回顾</h2>';

      for (var idx = 0; idx < qaPairs.length; idx++) {
        var p = qaPairs[idx];
        var qText = p.question.question || '';
        var ivName = p.question.interviewer_name || '';
        var answerText = p.answer ? p.answer.answer || '' : '';
        var score = p.answer && p.answer.score != null ? p.answer.score : null;
        var evaluation = p.answer ? p.answer.evaluation || '' : '';

        html += '<div class="card" style="margin-top:10px;padding:14px">';
        html += '<div style="font-size:11px;color:var(--accent2);margin-bottom:6px">' +
          '第 ' + (idx + 1) + ' 题 · ' + M.esc(ivName) +
          (score !== null ? ' · 得分 <strong style="color:' + M.scoreColor(score) + '">' + score + '</strong>' : ' · 未评分') +
          '</div>';
        html += '<div style="font-size:14px;margin-bottom:8px;padding:8px 10px;background:var(--surface);border-radius:6px"><strong>问：</strong>' + M.esc(qText) + '</div>';

        if (answerText) {
          html += '<div style="font-size:13px;color:var(--text2);margin-bottom:6px;padding:8px 10px;background:var(--surface2);border-radius:6px"><strong>答：</strong>' + M.esc(answerText) + '</div>';
        } else {
          html += '<div style="font-size:13px;color:var(--text2);margin-bottom:6px;font-style:italic">（未回答）</div>';
        }

        if (evaluation) {
          html += '<div style="font-size:12px;color:var(--text2);padding:8px 10px;background:var(--surface);border-radius:6px;border-left:2px solid var(--accent2)">' +
            M.esc(evaluation) + '</div>';
        }

        html += '</div>';
      }
    }

    // ====== 操作按钮 ======
    html += '<div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">' +
      '<button class="btn btn-primary" style="flex:1" onclick="MockMate.switchTab(\'setup\')">返回首页</button>' +
      '<button class="btn btn-secondary" id="mockCopyReportBtn">复制报告</button>' +
      '</div>';

    reportEl.innerHTML = html;

    document.getElementById('mockCopyReportBtn').addEventListener('click', function () {
      var text = reportEl.textContent || reportEl.innerText;
      navigator.clipboard.writeText(text)
        .then(function () { M.toast('报告已复制到剪贴板'); })
        .catch(function () { M.toast('复制失败'); });
    });
  };

  // ==================== 语音录制 ====================

  MI.toggleRecording = async function () {
    if (_isRecording) {
      MI.stopRecording();
    } else {
      await MI.startRecording();
    }
  };

  /** 检测麦克风 API 是否可用（需要在安全上下文中） */
  function _checkMediaDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      var hint = '';
      if (location.protocol === 'file:') {
        hint = '请通过 http://localhost:18633 访问页面，不要直接打开 HTML 文件。';
      } else if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
        hint = '麦克风需要 localhost 或 HTTPS 访问。请使用 http://localhost:18633。';
      } else {
        hint = '当前浏览器不支持麦克风 API，请更换最新版 Chrome/Edge。';
      }
      M.toast('麦克风不可用: ' + hint);
      return false;
    }
    return true;
  }

  MI.startRecording = async function () {
    if (!_checkMediaDevices()) return;
    try {
      _stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _mediaRecorder = new MediaRecorder(_stream);
      _audioChunks = [];

      _mediaRecorder.ondataavailable = function (event) {
        if (event.data.size > 0) {
          _audioChunks.push(event.data);
        }
      };

      _mediaRecorder.onstop = function () {
        var blob = new Blob(_audioChunks, { type: 'audio/webm' });
        document.getElementById('mockRecordingStatus').textContent =
          '🔄 识别中... (' + (blob.size / 1024).toFixed(0) + 'KB)';

        // 调用 ASR 转文字
        var formData = new FormData();
        formData.append('file', blob, 'recording.webm');
        fetch('/api/mock/voice/asr', { method: 'POST', body: formData })
          .then(function (r) {
            if (!r.ok) throw new Error('ASR 请求失败');
            return r.json();
          })
          .then(function (data) {
            if (data.transcription) {
              var ta = document.getElementById('mockAnswerInput');
              if (ta) {
                ta.value = data.transcription;
                ta.focus();
                // 触发 input 事件，让可能的字数统计等更新
                ta.dispatchEvent(new Event('input'));
              }
              document.getElementById('mockRecordingStatus').textContent =
                '🎤 ' + data.transcription.slice(0, 50) + (data.transcription.length > 50 ? '...' : '');
              M.toast('语音识别完成');
            } else {
              document.getElementById('mockRecordingStatus').textContent = '🎤 未能识别出文字';
              M.toast('未能识别出文字，请重试或手动输入');
            }
          })
          .catch(function (err) {
            document.getElementById('mockRecordingStatus').textContent = '🎤 识别失败';
            M.toast('语音识别失败: ' + err.message);
          });

        _stream.getTracks().forEach(function (t) { t.stop(); });
        _stream = null;
      };

      _mediaRecorder.start();
      _isRecording = true;
      document.getElementById('mockRecordingStatus').textContent = '🔴 录音中...';
      document.getElementById('mockVoiceBtn').textContent = '⏹ 停止录音';
    } catch (e) {
      M.toast('无法访问麦克风: ' + e.message);
    }
  };

  MI.stopRecording = function () {
    if (_mediaRecorder && _mediaRecorder.state !== 'inactive') {
      _mediaRecorder.stop();
    }
    _isRecording = false;
    document.getElementById('mockVoiceBtn').textContent = '🎤 语音回答';
  };

  // ==================== 语音测试浮动按钮 ====================

  var _vtLongPress = false;
  var _vtPressTimer = null;
  var _vtRecorder = null;
  var _vtStream = null;
  var _vtChunks = [];

  /** 显示语音测试反馈文字 */
  function vtShowFeedback(text, type) {
    var el = document.getElementById('mockVtfFeedback');
    if (!el) return;
    el.textContent = text;
    el.className = 'mock-vtf-feedback show ' + (type || 'info');
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(function () { el.classList.remove('show'); }, 4000);
  }

  /** 测试语音合成：播放测试音频 */
  function vtTestTts() {
    var btn = document.getElementById('mockVtf');
    if (!btn) return;
    btn.classList.add('testing');
    vtShowFeedback('正在测试语音合成...', 'info');

    fetch('/api/mock/voice/tts')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.audio_url) {
          var audio = new Audio(data.audio_url);
          audio.onended = function () {
            btn.classList.remove('testing');
            vtShowFeedback('语音合成正常 ✓', 'success');
          };
          audio.onerror = function () {
            btn.classList.remove('testing');
            vtShowFeedback('语音播放失败', 'error');
          };
          audio.play().catch(function () {
            btn.classList.remove('testing');
            vtShowFeedback('语音播放失败', 'error');
          });
          vtShowFeedback('播放测试音频...', 'info');
        } else {
          btn.classList.remove('testing');
          vtShowFeedback('语音合成服务不可用', 'error');
        }
      })
      .catch(function () {
        btn.classList.remove('testing');
        vtShowFeedback('语音测试请求失败', 'error');
      });
  }

  /** 开始 ASR 录音测试 */
  function vtStartAsr() {
    var container = document.getElementById('mockVtf');
    if (!container) return;
    if (!_checkMediaDevices()) return;
    container.classList.add('recording');
    vtShowFeedback('录音中...松开结束', 'info');

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function (stream) {
        _vtStream = stream;
        _vtChunks = [];
        _vtRecorder = new MediaRecorder(stream);
        _vtRecorder.ondataavailable = function (e) {
          if (e.data.size > 0) _vtChunks.push(e.data);
        };
        _vtRecorder.onstop = function () {
          container.classList.remove('recording');
          vtShowFeedback('识别中...', 'info');
          var blob = new Blob(_vtChunks, { type: 'audio/webm' });
          var formData = new FormData();
          formData.append('file', blob, 'test_audio.webm');
          fetch('/api/mock/voice/asr', { method: 'POST', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data.transcription) {
                vtShowFeedback('识别结果: "' + data.transcription + '"', 'success');
              } else {
                vtShowFeedback('识别无结果', 'error');
              }
            })
            .catch(function () {
              vtShowFeedback('识别请求失败', 'error');
            })
            .finally(function () {
              if (_vtStream) {
                _vtStream.getTracks().forEach(function (t) { t.stop(); });
                _vtStream = null;
              }
            });
        };
        _vtRecorder.start();
      })
      .catch(function (err) {
        container.classList.remove('recording');
        vtShowFeedback('麦克风访问失败: ' + err.message, 'error');
      });
  }

  /** 停止 ASR 录音 */
  function vtStopAsr() {
    if (_vtRecorder && _vtRecorder.state !== 'inactive') {
      _vtRecorder.stop();
    }
    _vtRecorder = null;
  }

  /** 初始化语音测试按钮事件 */
  function vtInit() {
    var btn = document.getElementById('mockVtfBtn');
    if (!btn) return;

    // 防止移动端 touch 后合成 mouse 事件导致重复触发
    var _vtTouchFired = false;

    // 触摸事件（移动端优先）
    btn.addEventListener('touchstart', function (e) {
      _vtTouchFired = true;
      _vtLongPress = false;
      _vtPressTimer = setTimeout(function () {
        _vtLongPress = true;
        vtStartAsr();
      }, 400);
    }, { passive: true });

    btn.addEventListener('touchend', function (e) {
      clearTimeout(_vtPressTimer);
      if (_vtLongPress) {
        vtStopAsr();
      } else {
        vtTestTts();
      }
    }, { passive: true });

    // 鼠标事件（仅当不是由触摸触发时处理）
    btn.addEventListener('mousedown', function (e) {
      if (_vtTouchFired) { _vtTouchFired = false; return; }
      e.preventDefault();
      _vtLongPress = false;
      _vtPressTimer = setTimeout(function () {
        _vtLongPress = true;
        vtStartAsr();
      }, 400);
    });

    btn.addEventListener('mouseup', function () {
      if (_vtTouchFired) { _vtTouchFired = false; return; }
      clearTimeout(_vtPressTimer);
      if (_vtLongPress) {
        vtStopAsr();
      } else {
        vtTestTts();
      }
    });

    btn.addEventListener('mouseleave', function () {
      if (_vtTouchFired) { _vtTouchFired = false; return; }
      clearTimeout(_vtPressTimer);
      if (_vtLongPress) {
        vtStopAsr();
      }
    });
  }

  // 页面加载完成后初始化语音测试按钮
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', vtInit);
  } else {
    vtInit();
  }

  // ==================== 模态框点击外部关闭 ====================

  document.addEventListener('click', function (e) {
    var dialog = document.getElementById('mockIvDialog');
    if (dialog && e.target === dialog) {
      MI.hideAddDialog();
    }
  });

  // ==================== 时长滑块联动 ====================

  document.addEventListener('input', function (e) {
    if (e.target.id === 'mockDurationRange') {
      var label = document.getElementById('mockDurationLabel');
      if (label) label.textContent = e.target.value;
    }
  });

  // ==================== 暴露接口 ====================

  M.MockInterview = MI;

})(window.MockMate);
