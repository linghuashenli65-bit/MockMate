/* 微调管理页面 */

window.MockMate = window.MockMate || {};

(function (M) {

  var FT = {};

  /* 加载统计数据 */
  FT.loadStats = async function () {
    try {
      var stats = await M.API.get('/api/training/stats');
      document.getElementById('statTotal').textContent = stats.total_raw || 0;
      document.getElementById('statEvals').textContent = stats.evaluations || 0;
      document.getElementById('statScores').textContent = stats.scores || 0;
      document.getElementById('statReviewed').textContent = stats.reviewed || 0;
      document.getElementById('statGood').textContent = stats.quality_good || 0;
      document.getElementById('statBad').textContent = stats.quality_bad || 0;
    } catch(e) {
      console.error('加载统计数据失败', e);
    }
  };

  /* 加载数据列表 */
  FT.loadRecords = async function () {
    var type = document.getElementById('filterType').value;
    var quality = document.getElementById('filterQuality').value;
    var source = document.getElementById('filterSource').value;

    if (quality === '__pending__') quality = null;

    try {
      var resp = await M.API.post('/api/training/data', {
        record_type: type || null,
        quality: quality || null,
        source: source,
      });
      FT.renderRecords(resp.records || []);
    } catch(e) {
      console.error('加载训练数据失败', e);
      document.getElementById('trainingRecords').innerHTML = '<div class="empty-state">加载失败</div>';
    }
  };

  /* 渲染数据列表 */
  FT.renderRecords = function (records) {
    var container = document.getElementById('trainingRecords');
    if (!records.length) {
      container.innerHTML = '<div class="empty-state">暂无数据</div>';
      return;
    }

    var html = '';
    records.forEach(function (r) {
      var isEval = r.type === 'eval';
      var typeLabel = isEval ? '面试评分' : '简历评分';
      var qualityIcon = r.quality === 'good' ? '👍' : (r.quality === 'bad' ? '👎' : '⏳');
      var reviewedBadge = r.reviewed ? '<span style="font-size:11px;color:var(--accent2);margin-left:6px">[已修正]</span>' : '';

      var question = isEval ? (r.question || '').slice(0, 60) : '简历评分';
      var answer = isEval ? (r.answer || '').slice(0, 80) : '';

      html += '<div class="feedback-item" style="padding:10px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">' +
          '<span style="font-size:12px;color:var(--accent2);font-weight:600">' + typeLabel + '</span>' +
          '<span style="font-size:12px;color:var(--text2)">' + qualityIcon + ' ' + r.timestamp.slice(0, 16).replace('T', ' ') + reviewedBadge + '</span>' +
        '</div>' +
        '<div style="font-size:13px;margin-bottom:4px;color:var(--text1)"><strong>题目：</strong>' + M.esc(question) + '</div>' +
        (answer ? '<div style="font-size:12px;color:var(--text2);margin-bottom:4px"><strong>回答：</strong>' + M.esc(answer) + '</div>' : '') +
        '<div style="font-size:12px;color:var(--text2)">' +
          (isEval ? '综合评分：' + (r.result?.overall_score ?? '-') : '匹配度：' + (r.result?.score ?? '-') + '/100') +
        '</div>' +
      '</div>';
    });

    container.innerHTML = html;
  };

  /* 初始化 */
  FT.init = function () {
    document.getElementById('refreshDataBtn').addEventListener('click', function () {
      FT.loadStats();
      FT.loadRecords();
    });

    // 切换到微调 tab 时自动加载
    var origSwitch = M.switchTab;
    M.switchTab = function (name) {
      origSwitch.call(M, name);
      if (name === 'finetune') {
        FT.loadStats();
        FT.loadRecords();
      }
    };

    // 如果当前 tab 就是微调，直接加载
    if (document.getElementById('tab-finetune').classList.contains('active')) {
      FT.loadStats();
      FT.loadRecords();
    }
  };

  M.FineTune = FT;

  // 页面加载后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', FT.init);
  } else {
    FT.init();
  }

})(window.MockMate);
