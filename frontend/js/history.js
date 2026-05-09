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
      html += '<div class="chart-container"><h3>各维度走势</h3><div class="chart-wrap"><canvas id="trendLineChart"></canvas></div></div>';
      html += '</div>';

      // 薄弱点分析
      html += H.renderWeaknessAnalysis(sessions);

      // 列表标题 + 导出 PDF
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
        '<h3 style="font-size:14px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin:0">历史记录</h3>' +
        '<button class="btn btn-secondary btn-sm" onclick="window.print()">导出 PDF</button>' +
        '</div>';

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
        H.renderDimTrendChart(sessions);
        const avgDims = H.computeDimAverages(sessions);
        H.renderDimRadarChart('dimRadarChart', avgDims);
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

  // ---- 折线图：各维度走势 ----
  H.renderDimTrendChart = function (sessions) {
    const canvas = document.getElementById('trendLineChart');
    if (!canvas) return;

    const data = sessions.slice(0, 20).reverse();
    const labels = data.map(s => M.formatDate(s.date));

    const dims = [
      { key: 'technical',     label: '技术', color: '#00b894' },
      { key: 'logic',         label: '逻辑', color: '#6c5ce7' },
      { key: 'depth',         label: '深度', color: '#fdcb6e' },
      { key: 'communication', label: '表达', color: '#e17055' },
    ];

    const datasets = [];
    dims.forEach(d => {
      const values = data.map(s => (s.score_breakdown || {})[d.key] ?? null);
      datasets.push({
        label: d.label,
        data: values,
        borderColor: d.color,
        backgroundColor: d.color + '22',
        fill: false,
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: false,
      });
    });

    // 综合分虚线
    const overall = data.map(s => s.overall_score ?? null);
    datasets.push({
      label: '综合',
      data: overall,
      borderColor: '#a29bfe',
      backgroundColor: '#a29bfe22',
      borderDash: [5, 3],
      borderWidth: 2,
      fill: false,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 4,
      spanGaps: false,
    });

    H._charts.trendLine = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 10, ticks: { color: '#8b8fa8', stepSize: 2 } },
          x: { ticks: { color: '#8b8fa8', maxTicksLimit: 10 } },
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#8b8fa8', boxWidth: 12, padding: 12, font: { size: 11 } },
          },
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

  // ---- 辅助：维度平均分 ----
  H.computeDimAverages = function (sessions) {
    const sums = { technical: 0, logic: 0, depth: 0, communication: 0 };
    const counts = { technical: 0, logic: 0, depth: 0, communication: 0 };
    sessions.forEach(s => {
      const sb = s.score_breakdown || {};
      Object.keys(sums).forEach(k => {
        const v = sb[k];
        if (v != null && !isNaN(v)) { sums[k] += v; counts[k]++; }
      });
    });
    const result = {};
    Object.keys(sums).forEach(k => {
      result[k] = counts[k] > 0 ? +(sums[k] / counts[k]).toFixed(1) : 0;
    });
    return result;
  };

  // ---- 辅助：聚合薄弱点 ----
  H.aggregateWeaknesses = function (sessions) {
    const freq = {};
    sessions.forEach(s => {
      (s.weaknesses || []).forEach(w => {
        const key = w.trim();
        if (key) freq[key] = (freq[key] || 0) + 1;
      });
    });
    return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
  };

  // ---- 辅助：聚合建议 ----
  H.aggregateAdvice = function (sessions) {
    const freq = {};
    sessions.forEach(s => {
      (s.preparation_advice || []).forEach(a => {
        const key = a.trim();
        if (key) freq[key] = (freq[key] || 0) + 1;
      });
    });
    return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
  };

  // ---- 雷达图：维度平均分 ----
  H.renderDimRadarChart = function (canvasId, avgDims) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    if (H._charts.dimRadar) H._charts.dimRadar.destroy();

    H._charts.dimRadar = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: ['技术', '逻辑', '深度', '表达'],
        datasets: [{
          label: '平均分',
          data: [avgDims.technical || 0, avgDims.logic || 0, avgDims.depth || 0, avgDims.communication || 0],
          backgroundColor: 'rgba(108,92,231,0.2)',
          borderColor: '#6c5ce7',
          borderWidth: 2,
          pointBackgroundColor: ['#00b894', '#6c5ce7', '#fdcb6e', '#e17055'],
          pointRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        scales: {
          r: {
            min: 0, max: 10,
            ticks: { stepSize: 2, display: false },
            grid: { color: '#2e3348' },
            angleLines: { color: '#2e3348' },
            pointLabels: { color: '#8b8fa8', font: { size: 12 } },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
  };

  // ---- 薄弱点分析 ----
  H.renderWeaknessAnalysis = function (sessions) {
    const valid = sessions.filter(s => s.score_breakdown && Object.keys(s.score_breakdown).length > 0);
    if (valid.length === 0) {
      return '<div class="card" style="margin-bottom:16px">' +
        '<h2>能力分析</h2>' +
        '<p style="font-size:13px;color:var(--text2)">' +
        '暂无足够数据。完成至少一次模拟面试后，将在此展示各维度能力分析和薄弱点总结。' +
        '</p></div>';
    }

    const avg = H.computeDimAverages(valid);
    const weakList = H.aggregateWeaknesses(valid);
    const adviceList = H.aggregateAdvice(valid);

    const dimLabels = { technical: '技术', logic: '逻辑', depth: '深度', communication: '表达' };
    let dimTags = '';
    Object.entries(dimLabels).forEach(([key, label]) => {
      const val = avg[key] || 0;
      dimTags += '<span class="score-tag">' + label +
        ' <span class="val" style="color:' + M.scoreColor(val) + '">' + val + '</span></span>';
    });

    let weakHtml = '';
    if (weakList.length > 0) {
      weakHtml = '<ul class="weakness-list">';
      weakList.forEach(([text, count]) => {
        weakHtml += '<li class="weakness-item"><span class="w-topic">' + M.esc(text) + '</span>' +
          '<span style="color:var(--text2);font-size:12px;flex-shrink:0">' + count + '次</span></li>';
      });
      weakHtml += '</ul>';
    } else {
      weakHtml = '<p style="font-size:13px;color:var(--text2)">暂无数据</p>';
    }

    let advHtml = '';
    if (adviceList.length > 0) {
      advHtml = '<ul class="weakness-list">';
      adviceList.forEach(([text, count]) => {
        advHtml += '<li class="weakness-item"><span class="w-topic">' + M.esc(text) + '</span>' +
          '<span style="color:var(--text2);font-size:12px;flex-shrink:0">' + count + '次</span></li>';
      });
      advHtml += '</ul>';
    } else {
      advHtml = '<p style="font-size:13px;color:var(--text2)">暂无数据</p>';
    }

    return '<div class="analysis-grid" style="display:grid;grid-template-columns:1fr;gap:16px;margin-bottom:16px">' +
      '<div class="card">' +
        '<h2>各维度平均分</h2>' +
        '<div style="max-width:240px;margin:12px auto 0">' +
          '<canvas id="dimRadarChart"></canvas>' +
        '</div>' +
        '<div class="score-row" style="margin-top:12px;justify-content:center">' + dimTags + '</div>' +
      '</div>' +
      '<div class="card">' +
        '<h2>薄弱点与建议</h2>' +
        '<div style="margin-bottom:12px">' +
          '<div style="font-size:13px;font-weight:600;color:var(--yellow);margin-bottom:6px">常见薄弱点</div>' +
          weakHtml +
        '</div>' +
        '<div>' +
          '<div style="font-size:13px;font-weight:600;color:var(--accent2);margin-bottom:6px">复习建议汇总</div>' +
          advHtml +
        '</div>' +
      '</div>' +
    '</div>';
  };

  // ---- 查看单场面试详情 ----
  H.viewSession = async function (sessionId) {
    const container = document.getElementById('historyList');
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div style="margin-top:8px">加载面试详情...</div></div>';

    try {
      const s = await M.API.get('/api/interview/session/' + sessionId);

      let html =
        '<div style="margin-bottom:8px;display:flex;justify-content:space-between">' +
          '<button class="btn btn-secondary btn-sm" onclick="MockMate.History.loadHistory()">\u2190 返回列表</button>' +
          '<button class="btn btn-secondary btn-sm" onclick="window.print()">导出 PDF</button>' +
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

        if (r.final_verdict) html += '<div class="markdown-body" style="font-size:13px;margin-top:8px;line-height:1.6">' + M.md(r.final_verdict) + '</div>';
        if (r.skill_summary) html += '<div class="markdown-body" style="font-size:12px;color:var(--text2);margin-top:4px">' + M.md(r.skill_summary) + '</div>';

        if (r.strengths && r.strengths.length) {
          html += '<div style="margin-top:8px"><strong style="color:var(--green)">优势</strong><br><span style="font-size:13px" class="markdown-body">' + r.strengths.map(function(s){ return M.md(s); }).join('；') + '</span></div>';
        }
        if (r.weaknesses && r.weaknesses.length) {
          html += '<div style="margin-top:4px"><strong style="color:var(--yellow)">待提升</strong><br><span style="font-size:13px" class="markdown-body">' + r.weaknesses.map(function(w){ return M.md(w); }).join('；') + '</span></div>';
        }
        if (r.preparation_advice && r.preparation_advice.length) {
          html += '<div style="margin-top:8px"><strong>复习建议</strong><br><ul style="font-size:13px;padding-left:20px;margin-top:4px">';
          r.preparation_advice.forEach(a => { html += '<li class="markdown-body">' + M.md(a) + '</li>'; });
          html += '</ul></div>';
        }
      }

      // 问答历史
      (s.history || []).forEach((h, i) => {
        const answerSnippet = (h.a || '').slice(0, 200);
        html +=
          '<div style="background:var(--surface2);border-radius:8px;padding:12px;margin-top:8px">' +
            '<div style="font-size:12px;color:var(--accent2)">第 ' + (i+1) + ' 题 · 得分 ' + (h.score?.overall_score || 0) + '</div>' +
            '<div style="font-size:13px;margin:4px 0" class="markdown-body"><strong>问：</strong>' + M.md(h.q || '') + '</div>' +
            '<div style="font-size:13px;color:var(--text2)" class="markdown-body"><strong>答：</strong>' + M.md(answerSnippet) + (h.a && h.a.length > 200 ? '...' : '') + '</div>' +
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
