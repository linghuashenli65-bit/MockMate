/* ========================================
   MockMate.Custom — 自定义题目管理
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const C = {};

  C.init = function () {
    document.querySelector('[data-tab="custom"]').addEventListener('click', () => {
      setTimeout(() => C.loadQuestions(), 50);
    });
    document.getElementById('addCustomQuestionBtn').addEventListener('click', () => {
      C.showEditor(null);
    });
  };

  C.loadQuestions = async function () {
    const container = document.getElementById('customQuestionsList');

    try {
      const result = await M.API.get('/api/custom/questions');
      const items = result.questions || [];

      if (!items.length) {
        container.innerHTML = '<div class="empty-state">还没有自定义题目，点击上方按钮添加</div>';
        return;
      }

      let html = '';
      items.forEach((item) => {
        const diffLabel = M.diffLabel(item.difficulty);
        const qTrunc = (item.question || '').length > 80
          ? (item.question || '').slice(0, 80) + '...'
          : (item.question || '');

        html +=
          '<div class="history-item" style="margin-bottom:8px">' +
            '<div class="hi-main">' +
              '<div class="hi-info" style="flex:1">' +
                '<div class="hi-position">' +
                  (item.type ? M.esc(item.type) : '技术') +
                  (diffLabel ? ' · ' + diffLabel : '') +
                  (item.topic ? ' · ' + M.esc(item.topic) : '') +
                  (item.tags ? ' · ' + M.esc(item.tags) : '') +
                '</div>' +
                '<div class="hi-meta" style="margin-top:4px;font-size:13px;line-height:1.5">' +
                  M.esc(qTrunc) +
                '</div>' +
              '</div>' +
              '<div style="display:flex;gap:6px">' +
                '<button class="btn btn-secondary btn-sm" onclick="MockMate.Custom.showEditor(' + item.id + ')">编辑</button>' +
                '<button class="btn btn-danger btn-sm" onclick="MockMate.Custom.deleteQuestion(' + item.id + ')">删除</button>' +
              '</div>' +
            '</div>' +
          '</div>';
      });

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = '<div class="empty-state" style="color:var(--red)">加载失败: ' + M.esc(e.message) + '</div>';
    }
  };

  C.showEditor = async function (qid) {
    const container = document.getElementById('customQuestionsList');

    let questionData = { question: '', type: '技术', difficulty: 'medium', topic: '', expected_points: [], tags: '' };

    if (qid) {
      try {
        const resp = await M.API.get('/api/custom/questions/' + qid);
        questionData = resp;
      } catch (e) {
        M.toast('加载题目失败');
        return;
      }
    }

    const ptsStr = (questionData.expected_points || []).join('\n');

    container.innerHTML =
      '<div class="card" style="border-left:3px solid var(--accent)">' +
        '<h2 style="font-size:16px;text-transform:none;color:var(--text)">' + (qid ? '编辑题目' : '添加新题目') + '</h2>' +
        '<div class="form-group">' +
          '<label>题目内容</label>' +
          '<textarea id="editorQuestion" rows="4" placeholder="输入面试题目...">' + M.esc(questionData.question) + '</textarea>' +
        '</div>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">' +
          '<div class="form-group">' +
            '<label>类型</label>' +
            '<select id="editorType">' +
              '<option value="技术"' + (questionData.type === '技术' ? ' selected' : '') + '>技术</option>' +
              '<option value="行为"' + (questionData.type === '行为' ? ' selected' : '') + '>行为</option>' +
              '<option value="设计"' + (questionData.type === '设计' ? ' selected' : '') + '>设计</option>' +
              '<option value="项目"' + (questionData.type === '项目' ? ' selected' : '') + '>项目</option>' +
            '</select>' +
          '</div>' +
          '<div class="form-group">' +
            '<label>难度</label>' +
            '<select id="editorDifficulty">' +
              '<option value="easy"' + (questionData.difficulty === 'easy' ? ' selected' : '') + '>简单</option>' +
              '<option value="medium"' + (questionData.difficulty === 'medium' ? ' selected' : '') + '>中等</option>' +
              '<option value="hard"' + (questionData.difficulty === 'hard' ? ' selected' : '') + '>困难</option>' +
            '</select>' +
          '</div>' +
          '<div class="form-group">' +
            '<label>主题</label>' +
            '<input type="text" id="editorTopic" placeholder="如：系统设计" value="' + M.esc(questionData.topic || '') + '">' +
          '</div>' +
        '</div>' +
        '<div class="form-group">' +
          '<label>考察要点（每行一个）</label>' +
          '<textarea id="editorPoints" rows="3" placeholder="每行一个考察要点...">' + M.esc(ptsStr) + '</textarea>' +
        '</div>' +
        '<div class="form-group">' +
          '<label>标签（逗号分隔）</label>' +
          '<input type="text" id="editorTags" placeholder="如：Redis, 缓存, 高并发" value="' + M.esc(questionData.tags || '') + '">' +
        '</div>' +
        '<div style="display:flex;gap:10px;margin-top:12px">' +
          '<button class="btn btn-primary" id="editorSaveBtn">保存</button>' +
          '<button class="btn btn-secondary" id="editorCancelBtn">取消</button>' +
        '</div>' +
      '</div>';

    document.getElementById('editorSaveBtn').addEventListener('click', () => C.saveQuestion(qid));
    document.getElementById('editorCancelBtn').addEventListener('click', () => C.loadQuestions());
  };

  C.saveQuestion = async function (qid) {
    const question = document.getElementById('editorQuestion').value.trim();
    if (!question) { M.toast('请输入题目内容'); return; }

    const data = {
      question,
      type: document.getElementById('editorType').value,
      difficulty: document.getElementById('editorDifficulty').value,
      topic: document.getElementById('editorTopic').value.trim(),
      expected_points: document.getElementById('editorPoints').value.split('\n').filter(s => s.trim()),
      tags: document.getElementById('editorTags').value.trim(),
    };

    try {
      if (qid) {
        await M.API.put('/api/custom/questions/' + qid, data);
        M.toast('题目已更新');
      } else {
        await M.API.post('/api/custom/questions', data);
        M.toast('题目已创建');
      }
      C.loadQuestions();
    } catch (e) {
      M.toast('保存失败: ' + e.message);
    }
  };

  C.deleteQuestion = async function (qid) {
    if (!confirm('确定删除这道题目吗？')) return;
    try {
      await M.API.delete('/api/custom/questions/' + qid);
      M.toast('题目已删除');
      C.loadQuestions();
    } catch (e) {
      M.toast('删除失败: ' + e.message);
    }
  };

  M.Custom = C;

})(window.MockMate);
