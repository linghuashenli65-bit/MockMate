/* ========================================
   MockMate.Interview — 面试全流程
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const I = {};

  // ---- 初始化事件绑定 ----
  I.init = function () {
    var ok = true;
    ['startInterviewBtn','endInterviewBtn','resumeUpload','scoreResumeBtn','resumeInput'].forEach(function(id) {
      if (!document.getElementById(id)) { console.warn('MockMate: missing element', id); ok = false; }
    });
    document.getElementById('startInterviewBtn').addEventListener('click', I.startInterview);
    document.getElementById('endInterviewBtn').addEventListener('click', I.endInterview);
    document.getElementById('resumeUpload').addEventListener('change', I.handleResumeUpload);
    document.getElementById('scoreResumeBtn').addEventListener('click', I.scoreResume);
    document.getElementById('resumeInput').addEventListener('input', I.clearScore);
    if (ok) console.log('MockMate: Interview init OK');
  };

  // ---- 简历上传 ----
  I.handleResumeUpload = async function (e) {
    const file = e.target.files[0];
    if (!file) return;
    const nameEl = document.getElementById('resumeFileName');
    if (nameEl) nameEl.textContent = file.name;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const result = await M.API.upload('/api/resume/parse', formData);
      document.getElementById('resumeInput').value = result.text;
      M.saveFormMemory();
      M.toast('简历已识别');
    } catch(e) {
      M.toast('简历识别失败: ' + e.message);
    }
    I.clearScore();
  };

  // ---- 简历评分 ----
  I.clearScore = function () {
    M.state._resumeScore = null;
    document.getElementById('scoreResult').innerHTML = '';
    document.getElementById('startInterviewBtn').disabled = true;
  };

  I.scoreResume = async function () {
    const resume = document.getElementById('resumeInput').value.trim();
    const profile = M.state.currentProfile;
    if (!resume) { M.toast('请先填写或上传简历'); return; }
    if (!profile || Object.keys(profile).length === 0) { M.toast('请先生成岗位画像'); return; }

    const btn = document.getElementById('scoreResumeBtn');
    M.setBtnLoading(btn, true, '评分中...');
    document.getElementById('scoreResult').innerHTML = '<div style="text-align:center;padding:20px;color:var(--text2)">AI 正在评估简历匹配度...</div>';

    try {
      const result = await M.API.post('/api/resume/score', { resume, profile });
      M.state._resumeScore = result;
      I.renderScore(result);
      if (result.score >= 70) {
        document.getElementById('startInterviewBtn').disabled = false;
        M.toast('简历评分 ' + result.score + ' 分，可以开始面试');
      } else {
        document.getElementById('startInterviewBtn').disabled = true;
        M.toast('简历评分 ' + result.score + ' 分，建议优化后再面试');
      }
    } catch(e) {
      document.getElementById('scoreResult').innerHTML = '<div style="color:var(--red);padding:10px">评分失败: ' + e.message + '</div>';
      M.toast('评分失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '重新评分');
  };

  I.renderScore = function (result) {
    const score = Math.min(100, Math.max(0, result.score));
    let color, label;
    if (score >= 90) { color = 'var(--green)'; label = '非常匹配'; }
    else if (score >= 70) { color = 'var(--green)'; label = '良好匹配'; }
    else if (score >= 60) { color = 'var(--yellow)'; label = '部分匹配'; }
    else if (score >= 50) { color = 'var(--yellow)'; label = '匹配度较低'; }
    else { color = 'var(--red)'; label = '匹配度低'; }

    var strengthsHtml = (result.strengths || []).map(function (s) { return '<li class="strength">' + M.esc(s) + '</li>'; }).join('');
    var weaknessesHtml = (result.weaknesses || []).map(function (s) { return '<li class="weakness">' + M.esc(s) + '</li>'; }).join('');
    var suggestionsHtml = (result.suggestions || []).map(function (s) { return '<li class="suggestion">' + M.esc(s) + '</li>'; }).join('');

    document.getElementById('scoreResult').innerHTML =
      '<div style="padding:16px 0">' +
        '<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">' +
          '<div class="score-number" style="color:' + color + '">' + score + '</div>' +
          '<div>' +
            '<div class="score-label" style="color:' + color + '">' + label + '</div>' +
            '<div class="score-bar">' +
              '<div class="score-bar-fill" style="width:' + score + '%;background:' + color + '"></div>' +
            '</div>' +
          '</div>' +
        '</div>' +
        (strengthsHtml ? '<div class="score-section-title" style="color:var(--green)">优势</div><ul class="score-detail-list">' + strengthsHtml + '</ul>' : '') +
        (weaknessesHtml ? '<div class="score-section-title" style="color:var(--yellow)">不足</div><ul class="score-detail-list">' + weaknessesHtml + '</ul>' : '') +
        (suggestionsHtml ? '<div class="score-section-title" style="color:var(--accent2)">优化建议</div><ul class="score-detail-list">' + suggestionsHtml + '</ul>' : '') +
      '</div>';

    // 点赞/点踩按钮
    if (result._record_id) {
      M.Feedback.renderButtons('score', result._record_id, document.getElementById('scoreResult'));
    }
  };

  // ---- 计时器 ----
  function startTimer() {
    M.state.interviewStartTime = Date.now();
    const el = document.getElementById('interviewTimer');
    clearInterval(M.state.timerInterval);
    M.state.timerInterval = setInterval(() => {
      if (!M.state.interviewStartTime) return;
      const elapsed = Math.floor((Date.now() - M.state.interviewStartTime) / 1000);
      const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const s = String(elapsed % 60).padStart(2, '0');
      el.textContent = m + ':' + s;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(M.state.timerInterval);
    M.state.timerInterval = null;
    M.state.interviewStartTime = null;
    document.getElementById('interviewTimer').textContent = '00:00';
  }

  // ---- 倒计时 ----
  function startCountdown(seconds, onSubmit) {
    M.state.countdownRemaining = seconds;
    M.state.countdownPaused = false;
    clearInterval(M.state.countdownInterval);

    const el = document.getElementById('countdownTimer');
    updateCountdownDisplay(el, seconds);

    M.state.countdownInterval = setInterval(() => {
      if (M.state.countdownPaused) return;
      M.state.countdownRemaining--;
      updateCountdownDisplay(el, M.state.countdownRemaining);

      if (M.state.countdownRemaining <= 0) {
        clearInterval(M.state.countdownInterval);
        if (onSubmit) onSubmit();
      }
    }, 1000);
  }

  function updateCountdownDisplay(el, remaining) {
    const m = String(Math.floor(remaining / 60)).padStart(2, '0');
    const s = String(remaining % 60).padStart(2, '0');
    el.textContent = m + ':' + s;

    if (remaining <= 30 && remaining > 0) {
      el.classList.add('warning');
      el.classList.remove('paused');
    } else if (remaining <= 0) {
      el.classList.remove('warning', 'paused');
      el.textContent = '00:00';
    } else {
      el.classList.remove('warning');
    }

    if (M.state.countdownPaused) {
      el.classList.add('paused');
    } else {
      el.classList.remove('paused');
    }
  }

  function stopCountdown() {
    clearInterval(M.state.countdownInterval);
    M.state.countdownInterval = null;
  }

  // ---- 进度条 ----
  function updateProgress(current, total) {
    const fill = document.getElementById('progressFill');
    const text = document.getElementById('progressText');
    if (!fill || !text) return;
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    fill.style.width = pct + '%';

    // 颜色随进度变化
    if (pct <= 30) fill.style.background = 'var(--green)';
    else if (pct <= 70) fill.style.background = 'var(--yellow)';
    else fill.style.background = 'var(--accent)';

    text.textContent = '第 ' + (current + 1) + ' / ' + total + ' 题';
  }

  // ---- 草稿管理 ----
  function saveDraft(sessionId, qIndex) {
    const ta = document.getElementById('answerInput');
    if (!ta) return;
    const key = 'draft_' + sessionId + '_' + qIndex;
    const text = ta.value;
    if (text.trim()) {
      M.ls.set(key, text);
    }
  }

  function loadDraft(sessionId, qIndex) {
    const key = 'draft_' + sessionId + '_' + qIndex;
    return M.ls.get(key, '');
  }

  function clearDraft(sessionId, qIndex) {
    const key = 'draft_' + sessionId + '_' + qIndex;
    M.ls.remove(key);
  }

  function clearAllDrafts(sessionId) {
    Object.keys(localStorage).forEach(k => {
      if (k.startsWith('mockmate_draft_' + sessionId)) {
        localStorage.removeItem(k);
      }
    });
  }

  // ---- 断点续面 ----
  I.resumeSession = function (session) {
    M.state.currentSessionId = session.id;
    M.state.currentQuestionIndex = session.current_index;
    M.state.interviewActive = true;
    M.state.currentRound = session.round;
    M.state.isWrittenRound = session.round === 'written';
    const customQs = session.custom_questions || [];
    M.state.totalQuestions = customQs.length || M.ROUND_TOTALS[session.round] || 8;

    document.getElementById('roundLabel').textContent =
      M.ROUND_NAMES[session.round] || session.round;

    M.switchTab('interview');
    startTimer();
    I.showQuestion(session.current_question, session.current_index, null);
    M.toast('面试已恢复，继续作答');
  };

  // ---- 开始面试 ----
  I.startInterview = async function () {
    const resume = document.getElementById('resumeInput').value.trim();
    const position = document.getElementById('positionInput').value.trim();
    const company = document.getElementById('companyInput').value.trim();

    if (!resume) { M.toast('请先填写或上传简历'); return; }
    if (!position) { M.toast('请填写目标岗位'); return; }

    // 检查简历评分
    if (!M.state._resumeScore) {
      M.toast('请先对简历进行评分');
      document.getElementById('scoreResumeBtn').scrollIntoView({ behavior: 'smooth' });
      return;
    }
    if (M.state._resumeScore.score < 70) {
      M.toast('简历评分 ' + M.state._resumeScore.score + ' 分，低于 70 分无法开始面试，请优化简历');
      return;
    }

    const selectedRound = document.querySelector('input[name="round"]:checked')?.value || 'tech_1';
    const isWritten = selectedRound === 'written';
    const btn = document.getElementById('startInterviewBtn');

    // 笔试：显示全屏加载动画
    if (isWritten) {
      M.switchTab('interview');
      const area = document.getElementById('interviewArea');
      area.innerHTML =
        '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px">' +
          '<div class="spinner" style="width:48px;height:48px;border-width:5px"></div>' +
          '<div style="margin-top:20px;font-size:16px;font-weight:600;color:var(--text)">正在生成笔试题...</div>' +
          '<div style="margin-top:8px;font-size:13px;color:var(--text2)">AI 正在并行出题，请稍候</div>' +
          '<div style="margin-top:4px;font-size:12px;color:var(--text3)">后续题目将在答题时后台自动生成，无需等待</div>' +
        '</div>';
      document.getElementById('roundLabel').textContent = M.ROUND_NAMES.written;
    } else {
      M.setBtnLoading(btn, true, '正在准备面试...');
    }

    try {
      const useCustom = document.getElementById('useCustomQuestions')?.checked;
      const customIds = useCustom ? M.state._selectedCustomIds || [] : [];

      const result = await M.API.post('/api/interview/start', {
        resume, position, company,
        profile: M.state.currentProfile || {},
        round: selectedRound,
        custom_question_ids: customIds,
        enable_tts: M.Settings.getEnableTts(),
      });

      M.state.currentSessionId = result.session_id;
      M.state.currentQuestionIndex = 0;
      M.state.interviewActive = true;
      M.state.currentRound = result.round;
      M.state.isWrittenRound = result.round === 'written';
      M.state.totalQuestions = customIds.length || M.ROUND_TOTALS[result.round] || 8;
      M.state._ttsEnabled = M.Settings.getEnableTts();

      M.ls.set('active_session', result.session_id);
      startTimer();

      // 设置轮次标签
      document.getElementById('roundLabel').textContent =
        M.ROUND_NAMES[result.round] || result.round;

      // 切换到面试 Tab
      if (!isWritten) M.switchTab('interview');

      I.showQuestion(result.question, 0, result.audio_url);
      M.toast('面试已开始');
    } catch(e) {
      if (!isWritten) M.setBtnLoading(btn, false, '开始模拟面试');
      M.toast('启动面试失败: ' + e.message);
    }
  };

  // ---- 显示题目 ----
  I.showQuestion = function (question, index, audioUrl) {
    const area = document.getElementById('interviewArea');
    const isWritten = M.state.isWrittenRound;
    const total = M.state.totalQuestions;
    const sessionId = M.state.currentSessionId;

    M.state._lastQuestion = question;
    M.state._hintUsed = false;
    updateProgress(index, total);
    I.updateTtsIndicator();
    document.getElementById('questionCount').textContent =
      '第 ' + (index + 1) + ' / ' + total + ' 题';

    // 构建 meta 信息
    let meta = '';
    if (question.difficulty) {
      meta += '<span class="q-meta" style="display:flex;gap:12px;flex-wrap:wrap">' +
        '<span>' + M.esc(question.type || '') + '</span>' +
        '<span>' + M.diffLabel(question.difficulty) + '</span>' +
        '<span>' + M.esc(question.topic || '') + '</span>' +
        '</span>';
    }

    // 语音
    let audioHtml = '';
    if (audioUrl) {
      if (M.state._ttsEnabled) {
        audioHtml = '<div style="margin-top:12px"><audio controls style="width:100%;height:36px"><source src="' +
          audioUrl + '" type="audio/wav"></audio></div>';
      } else {
        audioHtml = '<div style="margin-top:12px">' +
          '<button class="btn btn-sm btn-secondary" onclick="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'" style="font-size:12px">🔊 播放本题语音</button>' +
          '<div style="display:none;margin-top:8px"><audio controls style="width:100%;height:36px"><source src="' +
          audioUrl + '" type="audio/wav"></audio></div>' +
        '</div>';
      }
    }

    // 倒计时显示
    const timeLimit = M.ROUND_TIMES[M.state.currentRound] || (isWritten ? M.WRITTEN_TIME : M.INTERVIEW_TIME);
    const countdownHtml = '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">' +
      '<div class="progress-wrap" style="margin-bottom:0;flex:1">' +
        '<div class="progress-track"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>' +
        '<span class="progress-text" id="progressText">第 ' + (index + 1) + ' / ' + total + ' 题</span>' +
      '</div>' +
      '<span class="countdown" id="countdownTimer">' +
        String(Math.floor(timeLimit / 60)).padStart(2, '0') + ':00' +
      '</span>' +
      '</div>';

    // 选择题/判断题渲染
    let answerHtml;
    if (question.options) {
      let optsHtml = '';
      for (const [key, val] of Object.entries(question.options)) {
        optsHtml += '<label class="written-option" style="display:flex;align-items:center;gap:8px;padding:10px 12px;margin:4px 0;background:var(--surface2);border-radius:8px;cursor:pointer;border:2px solid var(--border);transition:all .2s" onmouseover="this.style.borderColor=\'var(--accent)\'" onmouseout="this.style.borderColor=\'var(--border)\'">' +
          '<input type="radio" name="writtenAnswer" value="' + M.esc(key) + '" style="width:16px;height:16px;accent-color:var(--accent)">' +
          '<span style="font-size:14px"><strong>' + M.esc(key) + '.</strong> ' + M.esc(val) + '</span>' +
          '</label>';
      }
      answerHtml = '<div class="form-group">' +
        '<label>请选择答案</label>' +
        '<div id="optionsContainer">' + optsHtml + '</div>' +
        '</div>' +
        '<div style="display:flex;gap:10px">' +
          '<button class="btn btn-primary" id="submitAnswerBtn" style="flex:1">提交回答</button>' +
          '<button class="btn btn-secondary" id="pauseCountdownBtn" style="flex:0.3">暂停</button>' +
          '<button class="btn btn-secondary" id="skipQuestionBtn" style="flex:0.4">跳过本题</button>' +
        '</div>';
    } else {
      // 恢复草稿
      const draft = loadDraft(sessionId, index);
      answerHtml = '<div class="form-group">' +
        '<label>你的回答</label>' +
        '<div style="display:flex;gap:8px;align-items:flex-start">' +
          '<textarea id="answerInput" rows="5" placeholder="输入你的回答...（Ctrl+Enter 快捷提交）" style="flex:1">' +
          M.esc(draft) +
          '</textarea>' +
          '<button class="record-btn-sm" id="voiceInputBtn" title="语音输入">🎤</button>' +
        '</div>' +
        '<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text2);margin-top:4px">' +
          '<span>Ctrl+Enter 提交 · 自动保存草稿</span>' +
          '<span id="charCount">' + (draft.length || 0) + ' 字</span>' +
        '</div>' +
        '</div>' +
        '<div style="display:flex;gap:10px">' +
          '<button class="btn btn-primary" id="submitAnswerBtn" style="flex:1">提交回答</button>' +
          '<button class="btn btn-secondary" id="pauseCountdownBtn" style="flex:0.3">暂停</button>' +
          '<button class="btn btn-secondary" id="skipQuestionBtn" style="flex:0.4">跳过本题</button>' +
        '</div>';
    }

    const hintBtnHtml = isWritten ? '' :
      '<div style="margin-top:8px;display:flex;gap:8px">' +
        '<button class="btn btn-sm btn-secondary" id="hintBtn">💡 提示</button>' +
      '</div>' +
      '<div id="hintResult" style="margin-top:8px;padding:10px;background:var(--surface2);border-radius:8px;border-left:3px solid var(--accent);display:none;font-size:13px;line-height:1.6"></div>';

    area.innerHTML =
      countdownHtml +
      '<div class="question-box">' +
        '<div class="q-label">' + (isWritten ? '笔试题目' : '面试官提问') + '</div>' +
        '<div class="q-text markdown-body">' + M.md(question.question) + '</div>' +
        meta +
        audioHtml +
      '</div>' +
      hintBtnHtml +
      answerHtml +
      '<div id="evaluationResult"></div>';

    // 倒计时
    startCountdown(timeLimit, I.submitAnswer);

    // 暂停/继续按钮
    const pauseBtn = document.getElementById('pauseCountdownBtn');
    if (pauseBtn) {
      pauseBtn.addEventListener('click', function () {
        M.state.countdownPaused = !M.state.countdownPaused;
        this.textContent = M.state.countdownPaused ? '继续' : '暂停';
        const cdEl = document.getElementById('countdownTimer');
        if (cdEl) {
          if (M.state.countdownPaused) {
            cdEl.classList.add('paused');
          } else {
            cdEl.classList.remove('paused');
          }
        }
      });
    }

    // 提示按钮
    const hintBtn = document.getElementById('hintBtn');
    if (hintBtn) {
      hintBtn.addEventListener('click', async function () {
        if (this.disabled) return;
        this.disabled = true;
        this.textContent = '生成中...';
        try {
          const result = await M.API.post('/api/interview/hint', {
            session_id: M.state.currentSessionId,
            question_index: M.state.currentQuestionIndex,
          });
          const hintEl = document.getElementById('hintResult');
          hintEl.innerHTML = M.md(result.hint);
          hintEl.style.display = 'block';
          this.textContent = '💡 已查看提示';
          M.state._hintUsed = true;
        } catch(e) {
          M.toast('获取提示失败: ' + e.message);
          this.disabled = false;
          this.textContent = '💡 提示';
        }
      });
    }

    // 绑定提交按钮
    const skipBtn = document.getElementById('skipQuestionBtn');
    if (question.options) {
      document.getElementById('submitAnswerBtn').addEventListener('click', I.submitAnswer);
      if (skipBtn) skipBtn.addEventListener('click', I.skipQuestion);
    } else {
      const ta = document.getElementById('answerInput');
      ta.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') I.submitAnswer();
      });
      ta.addEventListener('input', () => {
        document.getElementById('charCount').textContent = ta.value.length + ' 字';
        saveDraft(sessionId, index);
      });
      document.getElementById('submitAnswerBtn').addEventListener('click', I.submitAnswer);
      if (skipBtn) skipBtn.addEventListener('click', I.skipQuestion);
      ta.focus();
      setupVoiceInput();
    }
  };

  // ---- 提交回答 ----
  I.submitAnswer = async function () {
    if (!M.state.interviewActive) return;
    stopCountdown();

    let answer;
    const questionObj = I._lastQuestion = M.state._lastQuestion;

    if (questionObj && questionObj.options) {
      const selected = document.querySelector('input[name="writtenAnswer"]:checked');
      if (!selected) { M.toast('请选择一个答案'); return; }
      answer = selected.value;
    } else {
      answer = document.getElementById('answerInput').value.trim();
      if (!answer) { M.toast('请先输入回答'); return; }
    }

    const btn = document.getElementById('submitAnswerBtn');
    const sessionId = M.state.currentSessionId;
    const qIndex = M.state.currentQuestionIndex;
    M.setBtnLoading(btn, true, '评估中...');

    try {
      const result = await M.API.post('/api/interview/answer', {
        session_id: sessionId,
        question_index: qIndex,
        answer,
        hint_used: M.state._hintUsed || false,
        enable_tts: M.state._ttsEnabled,
      });

      M.state.currentQuestionIndex = result.next_index;
      clearDraft(sessionId, qIndex);

      // 渲染评估结果
      const evalBox = document.getElementById('evaluationResult');
      const ev = result.evaluation;
      M.state._lastEvaluation = ev;
      const evalRecordId = ev._record_id;

      if (M.state.isWrittenRound) {
        const isCorrect = ev.correct;
        const icon = isCorrect ? '\u2714' : '\u2718';
        const color = isCorrect ? 'var(--green)' : 'var(--red)';
        const label = isCorrect ? '回答正确' : '回答错误';
        evalBox.innerHTML =
          '<div class="feedback-box" style="border-left-color:' + color + '">' +
            '<div style="font-size:24px;color:' + color + ';margin-bottom:8px">' +
              icon + ' <span style="font-size:16px;font-weight:600">' + label + '</span>' +
            '</div>' +
            '<div style="font-size:13px;color:var(--text2);margin-bottom:6px"><strong>正确答案：</strong>' + M.md(ev.correct_answer || '') + '</div>' +
            '<div style="font-size:13px;line-height:1.6;padding:10px;background:var(--surface);border-radius:6px" class="markdown-body"><strong>解析：</strong><br>' + M.md(ev.explanation || '') + '</div>' +
          '</div>' +
          '<div style="margin-top:12px;display:flex;gap:10px">' +
            '<button class="btn btn-primary" id="nextQuestionBtn" style="flex:1">下一题</button>' +
            '<button class="btn btn-danger btn-sm" id="endFromFeedbackBtn">结束面试</button>' +
          '</div>';
      } else {
        // 根据轮次显示不同的评分标题
        const roundEvalLabels = {
          'tech_1':        '工程能力评估',
          'tech_2':        '架构深度评估',
          'comprehensive': '综合素质评估',
        };
        const evalTitle = roundEvalLabels[M.state.currentRound] || '面试评估';

        evalBox.innerHTML =
          '<div class="feedback-box">' +
            '<div style="font-size:12px;color:var(--accent2);margin-bottom:8px;font-weight:600">' + evalTitle + '</div>' +
            '<div class="score-row">' +
              buildScoreTag('综合', ev.overall_score) +
              buildScoreTag('技术', ev.technical_score) +
              buildScoreTag('逻辑', ev.logic_score) +
              buildScoreTag('深度', ev.depth_score) +
              buildScoreTag('表达', ev.communication_score) +
            '</div>' +
            '<div style="font-size:13px;line-height:1.6" class="markdown-body">' +
              M.md(ev.summary || '') +
              (ev.strengths && ev.strengths.length ? '<div style="margin-top:8px"><strong>优点：</strong> ' + ev.strengths.map(M.esc).join('、') + '</div>' : '') +
              (ev.improvements && ev.improvements.length ? '<div style="margin-top:4px"><strong>改进建议：</strong> ' + ev.improvements.map(M.esc).join('、') + '</div>' : '') +
              (ev.reference_answer ? '<div style="margin-top:8px;padding:8px;background:var(--surface);border-radius:6px" class="markdown-body"><strong>参考回答：</strong><br>' + M.md(ev.reference_answer) + '</div>' : '') +
            '</div>' +
            '<div style="margin-top:12px;display:flex;gap:10px">' +
              '<button class="btn btn-primary" id="nextQuestionBtn" style="flex:1">下一题</button>' +
              '<button class="btn btn-secondary btn-sm" id="saveFavBtn">收藏此题</button>' +
              '<button class="btn btn-danger btn-sm" id="endFromFeedbackBtn">结束面试</button>' +
            '</div>' +
          '</div>';
      }

      // 点赞/点踩按钮
      if (evalRecordId) {
        M.Feedback.renderButtons('eval', evalRecordId, evalBox);
      }

      document.getElementById('nextQuestionBtn').addEventListener('click', () => {
        showNextQuestion(result.next_question, result.next_index, result.audio_url);
      });
      document.getElementById('endFromFeedbackBtn').addEventListener('click', I.endInterview);
      const saveFavBtn = document.getElementById('saveFavBtn');
      if (saveFavBtn) {
        const qObj = M.state._lastQuestion;
        const answerText = document.getElementById('answerInput')?.value?.trim() || '';
        const scoreVal = ev.overall_score ?? 0;
        const refAnswer = ev.reference_answer || '';
        saveFavBtn.addEventListener('click', () => M.Favorites.saveCurrentQuestion(qObj, answerText, scoreVal, refAnswer));
      }
      btn.style.display = 'none';
    } catch(e) {
      M.toast('评估失败: ' + e.message);
      M.setBtnLoading(btn, false, '提交回答');
    }
  };

  // ---- 跳过本题 ----
  I.skipQuestion = async function () {
    if (!M.state.interviewActive) return;
    stopCountdown();

    const questionObj = M.state._lastQuestion;
    if (!questionObj) return;

    // 保存到暂挂列表
    M.state.suspendedQuestions.push({
      question: questionObj,
      index: M.state.currentQuestionIndex,
    });

    const btn = document.getElementById('skipQuestionBtn');
    const sessionId = M.state.currentSessionId;
    const qIndex = M.state.currentQuestionIndex;
    M.setBtnLoading(btn, true, '跳过中...');

    try {
      const result = await M.API.post('/api/interview/answer', {
        session_id: sessionId,
        question_index: qIndex,
        answer: '',
        enable_tts: M.state._ttsEnabled,
      });

      M.state.currentQuestionIndex = result.next_index;
      clearDraft(sessionId, qIndex);
      showNextQuestion(result.next_question, result.next_index, result.audio_url);
    } catch(e) {
      M.toast('跳过失败: ' + e.message);
      M.setBtnLoading(btn, false, '跳过本题');
    }
  };

  // ---- 语音输入 ----
  function setupVoiceInput() {
    const btn = document.getElementById('voiceInputBtn');
    const ta = document.getElementById('answerInput');
    if (!btn || !ta) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      btn.style.display = 'none';
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.continuous = true;
    recognition.interimResults = true;

    let isRecording = false;

    btn.addEventListener('click', function () {
      if (!isRecording) {
        try { recognition.start(); } catch(e) { /* already started */ }
        btn.classList.add('recording');
        btn.title = '点击停止';
        isRecording = true;
      } else {
        recognition.stop();
        btn.classList.remove('recording');
        btn.title = '语音输入';
        isRecording = false;
      }
    });

    recognition.onresult = function (event) {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          transcript += event.results[i][0].transcript;
        }
      }
      if (transcript) {
        const cursorPos = ta.selectionStart;
        ta.value = ta.value.slice(0, cursorPos) + transcript + ta.value.slice(cursorPos);
        ta.selectionStart = ta.selectionEnd = cursorPos + transcript.length;
        ta.dispatchEvent(new Event('input'));
        ta.focus();
      }
    };

    recognition.onend = function () {
      btn.classList.remove('recording');
      btn.title = '语音输入';
      isRecording = false;
    };

    recognition.onerror = function (event) {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        M.toast('语音识别错误: ' + event.error);
      }
      btn.classList.remove('recording');
      btn.title = '语音输入';
      isRecording = false;
    };
  }

  // ---- 显示下一题（支持暂挂队列）----
  function showNextQuestion(nextQuestion, nextIndex, audioUrl) {
    if (nextQuestion && nextIndex < M.state.totalQuestions) {
      I.showQuestion(nextQuestion, nextIndex, audioUrl);
      return;
    }
    // 主流程结束，检查暂挂题目
    if (M.state.suspendedQuestions.length > 0) {
      const suspended = M.state.suspendedQuestions.shift();
      M.state.totalQuestions += 1;
      M.state.currentQuestionIndex = suspended.index;
      I.showQuestion(suspended.question, suspended.index, null);
      M.toast('这是你之前跳过的第 ' + (suspended.index + 1) + ' 题');
      return;
    }
    // 全部完成
    document.getElementById('questionCount').textContent = '全部完成';
    document.getElementById('evaluationResult').innerHTML =
      '<div style="margin-top:16px;display:flex;gap:10px">' +
        '<button class="btn btn-primary" style="flex:1" id="finishAllBtn">生成报告并结束</button>' +
      '</div>';
    document.getElementById('finishAllBtn').addEventListener('click', I.endInterview);
  }

  function buildScoreTag(label, score) {
    const v = Number(score) || 0;
    return '<span class="score-tag">' + label +
      ' <span class="val" style="color:' + M.scoreColor(v) + '">' + v + '</span></span>';
  }

  // ---- TTS 开关 ----
  I.toggleTts = function () {
    var enabled = !M.state._ttsEnabled;
    M.state._ttsEnabled = enabled;
    M.Settings.setEnableTts(enabled);
    I.updateTtsIndicator();
    M.toast('语音播报已' + (enabled ? '开启' : '关闭'));
  };

  I.updateTtsIndicator = function () {
    var el = document.getElementById('ttsToggle');
    if (!el) return;
    el.textContent = M.state._ttsEnabled ? '🔊 语音开' : '🔇 语音关';
    el.style.borderColor = M.state._ttsEnabled ? 'var(--green)' : 'var(--border)';
    el.title = '点击' + (M.state._ttsEnabled ? '关闭' : '开启') + '语音播报';
  };

  // ---- 结束面试 ----
  I.endInterview = async function () {
    if (!M.state.currentSessionId) return;
    if (!confirm('确定结束面试并生成报告吗？')) return;

    stopCountdown();
    const area = document.getElementById('interviewArea');
    area.innerHTML =
      '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px">' +
        '<div class="spinner" style="width:40px;height:40px;border-width:4px"></div>' +
        '<div style="margin-top:16px;font-size:16px;font-weight:600">正在生成报告...</div>' +
        '<div style="margin-top:8px;font-size:13px;color:var(--text2)">AI 正在评估你的回答并生成面试总结</div>' +
      '</div>';
    document.getElementById('questionCount').textContent = '面试结束';

    try {
      const result = await M.API.post('/api/interview/end', {
        session_id: M.state.currentSessionId,
      });
      I.showReport(result);
      M.toast('面试已结束，报告已生成');
    } catch(e) {
      M.toast('结束面试失败: ' + e.message);
      I.showQuestion(
        { question: '面试已中断，请重新开始', type: '', difficulty: '', topic: '' },
        M.state.currentQuestionIndex,
        null
      );
    }
  };

  // ---- 显示报告 ----
  I.showReport = function (result) {
    const r = result.report || {};
    const area = document.getElementById('interviewArea');
    const historyLen = (result.history || []).length;
    document.getElementById('questionCount').textContent = '面试结束 \u00B7 共 ' + historyLen + ' 题';

    let html =
      '<div class="card" style="border-left:3px solid var(--accent)">' +
      '<h2 style="font-size:18px;text-transform:none;color:var(--text)">面试报告</h2>';

    if (result.round) {
      html += '<div style="font-size:12px;color:var(--accent2);margin-bottom:8px">轮次：' +
        (M.ROUND_NAMES[result.round] || result.round) + '</div>';
    }

    // 分数
    const sc = r.score_breakdown || {};
    html += '<div class="score-row" style="margin:12px 0">' +
      buildScoreTag('总评', r.overall_score) +
      buildScoreTag('技术', sc.technical) +
      buildScoreTag('逻辑', sc.logic) +
      buildScoreTag('深度', sc.depth) +
      buildScoreTag('表达', sc.communication) +
      '</div>';

    if (r.final_verdict) html += '<div class="markdown-body" style="font-size:14px;line-height:1.6;margin-bottom:12px">' + M.md(r.final_verdict) + '</div>';
    if (r.skill_summary) html += '<div class="markdown-body" style="font-size:13px;color:var(--text2);margin-bottom:12px">' + M.md(r.skill_summary) + '</div>';

    if (r.strengths && r.strengths.length) {
      html += '<div style="margin-bottom:8px"><strong style="color:var(--green)">优势</strong><br><span style="font-size:13px" class="markdown-body">' + r.strengths.map(function(s){ return M.md(s); }).join('；') + '</span></div>';
    }
    if (r.weaknesses && r.weaknesses.length) {
      html += '<div style="margin-bottom:8px"><strong style="color:var(--yellow)">待提升</strong><br><span style="font-size:13px" class="markdown-body">' + r.weaknesses.map(function(w){ return M.md(w); }).join('；') + '</span></div>';
    }
    if (r.preparation_advice && r.preparation_advice.length) {
      html += '<div style="margin-bottom:12px"><strong>复习建议</strong><br><ul style="font-size:13px;padding-left:20px;margin-top:4px">';
      r.preparation_advice.forEach(a => { html += '<li class="markdown-body">' + M.md(a) + '</li>'; });
      html += '</ul></div>';
    }
    if (r.recommended_positions && r.recommended_positions.length) {
      html += '<div style="font-size:13px;color:var(--text2)">推荐方向：' + r.recommended_positions.map(M.esc).join('、') + '</div>';
    }

    // 问答回顾
    const history = result.history || [];
    if (history.length) {
      html += '<h2 style="font-size:16px;text-transform:none;color:var(--text);margin-top:20px">问答回顾</h2>';
      history.forEach((h, i) => {
        html += '<div style="background:var(--surface2);border-radius:8px;padding:12px;margin-top:8px">' +
          '<div style="font-size:12px;color:var(--accent2);margin-bottom:4px">第 ' + (i+1) + ' 题 (' + (h.type || '') + ')</div>' +
          '<div style="font-size:13px;margin-bottom:6px" class="markdown-body"><strong>问：</strong>' + M.md(h.q) + '</div>' +
          '<div style="font-size:13px;color:var(--text2);margin-bottom:4px" class="markdown-body"><strong>答：</strong>' + M.md(h.a || '') + '</div>' +
          '<span class="score-tag" style="display:inline-block">得分 ' + (h.score?.overall_score || 0) + '</span>' +
          '</div>';
      });
    }

    // 操作按钮（导出 PDF 按钮添加 id=exportPdfBtn 供 print CSS 隐藏）
    html += '<div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">' +
      '<button class="btn btn-primary" style="flex:1" onclick="MockMate.switchTab(\'setup\')">返回首页</button>' +
      '<button class="btn btn-secondary" id="copyReportBtn">复制报告</button>' +
      '<button class="btn btn-secondary" id="downloadReportBtn">下载报告</button>' +
      '<button class="btn btn-secondary" id="exportPdfReportBtn">导出 PDF</button>' +
      '</div>';
    html += '</div>';

    area.innerHTML = html;

    document.getElementById('copyReportBtn').addEventListener('click', () => I.copyReport(area));
    document.getElementById('downloadReportBtn').addEventListener('click', () => I.downloadReport(result));
    document.getElementById('exportPdfReportBtn').addEventListener('click', () => window.print());

    I.cleanup();
  };

  // ---- 复制报告 ----
  I.copyReport = function (reportEl) {
    const text = reportEl.textContent || reportEl.innerText;
    navigator.clipboard.writeText(text)
      .then(() => M.toast('报告已复制到剪贴板'))
      .catch(() => M.toast('复制失败'));
  };

  // ---- 下载报告 ----
  I.downloadReport = function (result) {
    const r = result.report || {};
    const lines = [];
    lines.push('==========================================');
    lines.push('  MockMate 面试报告');
    lines.push('==========================================');
    lines.push('');
    if (result.round) lines.push('轮次: ' + (M.ROUND_NAMES[result.round] || result.round));
    lines.push('总题数: ' + (result.history || []).length);
    lines.push('总评分数: ' + (r.overall_score || 0));
    if (r.score_breakdown) {
      const sc = r.score_breakdown;
      lines.push('  技术: ' + (sc.technical || 0) + '  逻辑: ' + (sc.logic || 0) + '  深度: ' + (sc.depth || 0) + '  表达: ' + (sc.communication || 0));
    }
    lines.push('');
    if (r.final_verdict) { lines.push('【最终评价】'); lines.push(r.final_verdict); lines.push(''); }
    if (r.skill_summary) { lines.push('【技能总结】'); lines.push(r.skill_summary); lines.push(''); }
    if (r.strengths && r.strengths.length) { lines.push('【优势】'); r.strengths.forEach(s => lines.push('  - ' + s)); lines.push(''); }
    if (r.weaknesses && r.weaknesses.length) { lines.push('【待提升】'); r.weaknesses.forEach(w => lines.push('  - ' + w)); lines.push(''); }
    if (r.preparation_advice && r.preparation_advice.length) {
      lines.push('【复习建议】');
      r.preparation_advice.forEach((a, i) => lines.push('  ' + (i+1) + '. ' + a));
      lines.push('');
    }

    lines.push('--- 问答回顾 ---');
    (result.history || []).forEach((h, i) => {
      lines.push('');
      lines.push('第' + (i+1) + '题 (' + (h.type || '') + ') 得分: ' + (h.score?.overall_score || 0));
      lines.push('问: ' + (h.q || ''));
      lines.push('答: ' + (h.a || ''));
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const pos = (result.round ? M.ROUND_NAMES[result.round] : 'report').replace(/\s/g, '');
    const date = new Date().toISOString().slice(0, 10);
    a.download = 'MockMate_' + pos + '_' + date + '.txt';
    a.click();
    URL.revokeObjectURL(a.href);
    M.toast('报告已下载');
  };

  // ---- 清理状态 ----
  I.cleanup = function () {
    stopTimer();
    stopCountdown();
    if (M.state.currentSessionId) {
      clearAllDrafts(M.state.currentSessionId);
    }
    M.state.interviewActive = false;
    M.state.currentSessionId = null;
    M.state.currentQuestionIndex = 0;
    M.state.currentRound = null;
    M.state.isWrittenRound = false;
    M.state.totalQuestions = 0;
    M.state.suspendedQuestions = [];
    M.ls.remove('active_session');

    // 恢复开始面试按钮
    const btn = document.getElementById('startInterviewBtn');
    if (btn) M.setBtnLoading(btn, false);
  };

  // ---- 导出 ----
  M.Interview = I;

})(window.MockMate);
