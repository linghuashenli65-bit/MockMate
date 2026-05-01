/* ========================================
   MockMate.History — 历史记录 & Chart.js 图表
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const H = {};

  // 图表实例管理
  H._charts = {};

  H.init = function () {
    document.querySelector('[data-tab="history"]').addEventListener('click', () => {
      setTimeout(() => H.loadHistory(), 50);
    });
  };

  // ---- 销毁所有图表 ----
  H.destroyCharts = function () {
    Object.values(H._charts).forEach(c => {
      try { c.destroy(); } catch(e) { /* ignore */ }
    });
    H._charts = {};
  };

  // ---- 加载历史列表 ----
  H.loadHistory = async function () {
    const container = document.getElementById('historyList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div style="margin-top:8px">加载历史记录...</div></div>';

    try {
      const result = await M.API.get('/api/history');
      const sessions = result.sessions || [];

      if (!sessions.length) {
        container.innerHTML = '<div class="empty-state">暂无面试记录<br><span style="font-size:13px">完成一次模拟面试后，记录会出现在这里</span></div>';
        return;
      }

      H.destroyCharts();

      let html = '';

      // 统计摘要
      html += H.renderStatsSummary(sessions);

      // 图表区域
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">';
      html += '<div class="chart-container"><h3>分数趋势</h3><div class="chart-wrap"><canvas id="trendBarChart"></canvas></div></div>';
      html += '<div class="chart-container"><h3>分数走势</h3><div class="chart-wrap"><canvas id="trendLineChart"></canvas></div></div>';
      html += '</div>';

      // 薄弱点分析
      html += H.renderWeaknessAnalysis(sessions);

      // 列表标题
      html += '<h3 style="font-size:14px;font-weight:600;color:var(--text2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">历史记录</h3>';

      // 面试记录列表
      sessions.forEach(s => {
        html +=
          '<div class="history-item">' +
            '<div class="hi-main">' +
              '<div class="hi-info" onclick="MockMate.History.viewSession(\'' + M.esc(s.id) + '\')">' +
                '<div class="hi-position">' + M.esc(s.position) + '</div>' +
                '<div class="hi-meta">' +
                  (s.company ? M.esc(s.company) + ' · ' : '') +
                  (M.ROUND_NAMES[s.round] || s.round || '') +
                  (s.round ? ' · ' : '') +
                  M.esc(M.formatDateTime(s.date)) +
                  ' · ' + s.total_questions + ' 题 · 评分 ' + s.overall_score +
                '</div>' +
              '</div>' +
              '<button class="btn btn-danger btn-sm" style="margin-left:8px;flex-shrink:0" onclick="event.stopPropagation();MockMate.History.deleteSession(\'' + M.esc(s.id) + '\')">删除</button>' +
            '</div>' +
          '</div>';
      });

      container.innerHTML = html;

      // 渲染图表（需要 DOM 就绪后）
      setTimeout(() => {
        H.renderTrendBarChart(sessions);
        H.renderTrendLineChart(sessions);
      }, 100);
    } catch(e) {
      container.innerHTML = '<div style="color:var(--red);font-size:13px">加载失败: ' + M.esc(e.message) + '</div>';
    }
  };

  // ---- 统计摘要 ----
  H.renderStatsSummary = function (sessions) {
    const total = sessions.length;
    const scores = sessions.map(s => s.overall_score || 0).filter(s => s > 0);
    const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
    const maxScore = scores.length > 0 ? Math.max(...scores) : 0;

    // 最近趋势（最近3场）
    let trendHtml = '';
    const recent3 = sessions.slice(0, Math.min(3, sessions.length));
    if (recent3.length >= 2) {
      const latest = recent3[0].overall_score || 0;
      const prev = recent3[recent3.length - 1].overall_score || 0;
      const diff = latest - prev;
      if (diff > 0.3) {
        trendHtml = '<span class="stat-trend up">\u2191 ' + diff.toFixed(1) + '</span>';
      } else if (diff < -0.3) {
        trendHtml = '<span class="stat-trend down">\u2193 ' + Math.abs(diff).toFixed(1) + '</span>';
      } else {
        trendHtml = '<span class="stat-trend flat">\u2192 持平</span>';
      }
    }

    return '<div class="stats-grid">' +
      '<div class="stat-card"><div class="stat-value">' + total + '</div><div class="stat-label">面试次数</div></div>' +
      '<div class="stat-card"><div class="stat-value" style="color:' + M.scoreColor(avgScore) + '">' + avgScore.toFixed(1) + '</div><div class="stat-label">平均分</div></div>' +
      '<div class="stat-card"><div class="stat-value" style="color:' + M.scoreColor(maxScore) + '">' + maxScore.toFixed(1) + '</div><div class="stat-label">最高分</div></div>' +
      '<div class="stat-card"><div class="stat-value">' + trendHtml + '</div><div class="stat-label">最近趋势</div></div>' +
      '</div>';
  };

  // ---- 柱状图：分数趋势 ----
  H.renderTrendBarChart = function (sessions) {
    const canvas = document.getElementById('trendBarChart');
    if (!canvas) return;

    // 取最近 10 场，按时间升序
    const data = sessions.slice(0, 10).reverse();
    const labels = data.map(s => M.formatDate(s.date));
    const scores = data.map(s => s.overall_score || 0);
    const ids = data.map(s => s.id);

    const bgColors = scores.map(v => {
      if (v >= 7) return 'rgba(0,184,148,0.7)';
      if (v >= 4) return 'rgba(253,203,110,0.7)';
      return 'rgba(225,112,85,0.7)';
    });

    H._charts.trendBar = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: '面试评分',
          data: scores,
          backgroundColor: bgColors,
          borderColor: bgColors.map(c => c.replace('0.7', '1')),
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 10, ticks: { color: '#8b8fa8', stepSize: 2 } },
          x: { ticks: { color: '#8b8fa8' } },
        },
        plugins: {
          legend: { display: false },
        },
        onClick: (e, elements) => {
          if (elements.length > 0) {
            const idx = elements[0].index;
            if (ids[idx]) H.viewSession(ids[idx]);
          }
        },
      },
    });
  };

  // ---- 折线图：分数走势 ----
  H.renderTrendLineChart = function (sessions) {
    const canvas = document.getElementById('trendLineChart');
    if (!canvas) return;

    const data = sessions.slice(0, 20).reverse();
    const labels = data.map(s => M.formatDate(s.date));
    const scores = data.map(s => s.overall_score || 0);

    H._charts.trendLine = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: '评分走势',
          data: scores,
          borderColor: '#6c5ce7',
          backgroundColor: 'rgba(108,92,231,0.1)',
          fill: true,
          tension: 0.3,
          pointBackgroundColor: '#6c5ce7',
          pointRadius: 4,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 10, ticks: { color: '#8b8fa8', stepSize: 2 } },
          x: { ticks: { color: '#8b8fa8' } },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
  };

  // ---- 雷达图：五维能力 ----
  H.renderRadarChart = function (canvasId, report) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !report) return;

    const sc = report.score_breakdown || {};
    const data = [
      sc.technical || 0,
      sc.logic || 0,
      sc.depth || 0,
      sc.communication || 0,
      report.overall_score || 0,
    ];

    // 使用 canvasId 作为 key 避免冲突
    const chartKey = 'radar_' + canvasId;
    if (H._charts[chartKey]) H._charts[chartKey].destroy();

    H._charts[chartKey] = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: ['技术', '逻辑', '深度', '表达', '综合'],
        datasets: [{
          label: '能力评估',
          data,
          backgroundColor: 'rgba(108,92,231,0.2)',
          borderColor: '#6c5ce7',
          borderWidth: 2,
          pointBackgroundColor: '#6c5ce7',
          pointRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        scales: {
          r: {
            min: 0,
            max: 10,
            ticks: { stepSize: 2, display: false },
            grid: { color: '#2e3348' },
            angleLines: { color: '#2e3348' },
            pointLabels: { color: '#8b8fa8', font: { size: 12 } },
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
  };

  // ---- 薄弱点分析 ----
  H.renderWeaknessAnalysis = function (sessions) {
    // 聚合所有 topic 得分
    const topicScores = {};
    sessions.forEach(s => {
      // sessions 列表不包含 history 详情，只做简单聚合
      // 如果 sessions 有 _raw 数据可以深入分析
      // 这里基于 overall_score 和 round 做基础分析
    });

    // 从后端获取的 sessions 摘要中没有 history 详情
    // 薄弱点分析在实际面试报告层面更有价值
    // 这里展示一个提示
    return '<div class="card" style="margin-bottom:16px">' +
      '<h2>能力总结</h2>' +
      '<p style="font-size:13px;color:var(--text2)">' +
      '完成更多面试后，点击每条记录可查看详细的五维能力分析和薄弱点诊断。' +
      '建议在不同轮次（技术面/综合面）各进行一次模拟，以获得全面的能力评估。' +
      '</p>' +
      '</div>';
  };

  // ---- 查看单场面试详情 ----
  H.viewSession = async function (sessionId) {
    const container = document.getElementById('historyList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div style="margin-top:8px">加载面试详情...</div></div>';

    try {
      const s = await M.API.get('/api/interview/session/' + sessionId);

      let html =
        '<div style="margin-bottom:8px">' +
          '<button class="btn btn-secondary btn-sm" onclick="MockMate.History.loadHistory()">\u2190 返回列表</button>' +
        '</div>' +
        '<div class="card">' +
          '<h2 style="text-transform:none;color:var(--text)">' + M.esc(s.position || '未知岗位') + '</h2>' +
          '<div style="font-size:13px;color:var(--text2);margin-bottom:12px">' +
            (s.company ? M.esc(s.company) + ' · ' : '') +
            M.esc(M.formatDateTime(s.date)) +
            (s.round ? ' · <span style="color:var(--accent2)">' + (M.ROUND_NAMES[s.round] || s.round) + '</span>' : '') +
          '</div>';

      if (s.report) {
        const r = s.report;
        const sc = r.score_breakdown || {};
        html +=
          '<div class="score-row">' +
            '<span class="score-tag">总评 <span class="val" style="color:' + M.scoreColor(r.overall_score) + '">' + (r.overall_score || 0) + '</span></span>' +
            '<span class="score-tag">技术 <span class="val" style="color:' + M.scoreColor(sc.technical) + '">' + (sc.technical || 0) + '</span></span>' +
            '<span class="score-tag">逻辑 <span class="val" style="color:' + M.scoreColor(sc.logic) + '">' + (sc.logic || 0) + '</span></span>' +
            '<span class="score-tag">深度 <span class="val" style="color:' + M.scoreColor(sc.depth) + '">' + (sc.depth || 0) + '</span></span>' +
            '<span class="score-tag">表达 <span class="val" style="color:' + M.scoreColor(sc.communication) + '">' + (sc.communication || 0) + '</span></span>' +
          '</div>';

        // 雷达图
        html += '<div class="chart-container" style="margin-top:12px"><h3>五维能力雷达</h3><div class="chart-wrap" style="max-width:300px;margin:0 auto"><canvas id="radarChart"></canvas></div></div>';

        if (r.final_verdict) html += '<p style="font-size:13px;margin-top:8px;line-height:1.6">' + M.esc(r.final_verdict) + '</p>';
        if (r.skill_summary) html += '<p style="font-size:12px;color:var(--text2);margin-top:4px">' + M.esc(r.skill_summary) + '</p>';

        if (r.strengths && r.strengths.length) {
          html += '<div style="margin-top:8px"><strong style="color:var(--green)">优势</strong><br><span style="font-size:13px">' + r.strengths.map(M.esc).join('；') + '</span></div>';
        }
        if (r.weaknesses && r.weaknesses.length) {
          html += '<div style="margin-top:4px"><strong style="color:var(--yellow)">待提升</strong><br><span style="font-size:13px">' + r.weaknesses.map(M.esc).join('；') + '</span></div>';
        }
        if (r.preparation_advice && r.preparation_advice.length) {
          html += '<div style="margin-top:8px"><strong>复习建议</strong><br><ul style="font-size:13px;padding-left:20px;margin-top:4px">';
          r.preparation_advice.forEach(a => { html += '<li>' + M.esc(a) + '</li>'; });
          html += '</ul></div>';
        }
      }

      // 问答历史
      (s.history || []).forEach((h, i) => {
        const answerSnippet = (h.a || '').slice(0, 200);
        html +=
          '<div style="background:var(--surface2);border-radius:8px;padding:12px;margin-top:8px">' +
            '<div style="font-size:12px;color:var(--accent2)">第 ' + (i+1) + ' 题 · 得分 ' + (h.score?.overall_score || 0) + '</div>' +
            '<div style="font-size:13px;margin:4px 0"><strong>问：</strong>' + M.esc(h.q || '') + '</div>' +
            '<div style="font-size:13px;color:var(--text2)"><strong>答：</strong>' + M.esc(answerSnippet) + (h.a && h.a.length > 200 ? '...' : '') + '</div>' +
          '</div>';
      });

      html += '</div>';
      container.innerHTML = html;

      // 渲染雷达图
      setTimeout(() => {
        if (s.report) H.renderRadarChart('radarChart', s.report);
      }, 100);
    } catch(e) {
      container.innerHTML = '<div style="color:var(--red);font-size:13px">加载失败: ' + M.esc(e.message) +
        '<br><button class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="MockMate.History.loadHistory()">返回列表</button></div>';
    }
  };

  // ---- 删除记录 ----
  H.deleteSession = async function (sessionId) {
    if (!confirm('确定删除这条面试记录？此操作不可恢复。')) return;
    try {
      await M.API.delete('/api/history/' + sessionId);
      M.toast('已删除');
      H.loadHistory();
    } catch(e) {
      M.toast('删除失败: ' + e.message);
    }
  };

  // ---- 导出 ----
  M.History = H;

})(window.MockMate);
