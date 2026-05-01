/* ========================================
   MockMate.Research — 岗位画像搜索
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const R = {};

  R.init = function () {
    document.getElementById('researchBtn').addEventListener('click', () => R.doResearch(false));
  };

  // ---- 执行搜索 ----
  R.doResearch = async function (refresh) {
    const pos = document.getElementById('positionInput').value.trim();
    if (!pos) { M.toast('请先输入目标岗位'); return; }

    const btn = document.getElementById('researchBtn');
    M.setBtnLoading(btn, true, '分析中...');
    M.showLoading('researchResult', 'AI 正在分析岗位要求...\n约需 15-30 秒');

    try {
      const data = await M.API.post('/api/research', { position: pos, refresh });
      M.state.currentProfile = data;
      R.renderProfileCard(data, pos);
      M.toast(refresh ? '重新分析完成' : '岗位分析完成');
    } catch(e) {
      document.getElementById('researchResult').innerHTML =
        '<div style="color:var(--red);font-size:13px;margin-top:8px">分析失败: ' + M.esc(e.message) + '</div>';
    }
    M.setBtnLoading(btn, false, '开始分析岗位');
  };

  // ---- 渲染岗位画像卡片 ----
  R.renderProfileCard = function (data, position) {
    let html = '<div style="background:var(--surface2);border-radius:var(--radius);padding:16px;margin-top:8px">';

    // 标题
    html += '<div style="font-weight:600;font-size:16px;margin-bottom:8px">' + M.esc(data.position || position) + '</div>';

    // 概述
    if (data.summary) {
      html += '<p style="font-size:13px;color:var(--text2);margin-bottom:8px">' + M.esc(data.summary) + '</p>';
    }

    // 必备技能标签
    if (data.required_skills && data.required_skills.length) {
      html += '<div style="margin-bottom:6px"><strong style="font-size:13px">必备技能：</strong><br>';
      html += data.required_skills.map(s => '<span class="skill-tag">' + M.esc(s) + '</span>').join('');
      html += '</div>';
    }

    // 加分技能
    if (data.nice_to_have && data.nice_to_have.length) {
      html += '<div style="margin-bottom:6px"><strong style="font-size:13px">加分项：</strong><br>';
      html += data.nice_to_have.map(s => '<span class="skill-tag">' + M.esc(s) + '</span>').join('');
      html += '</div>';
    }

    // 技术栈
    if (data.tech_stack && data.tech_stack.length) {
      html += '<div style="font-size:13px;color:var(--text2);margin-bottom:6px"><strong>技术栈：</strong>' +
        data.tech_stack.map(s => M.esc(s)).join('、') + '</div>';
    }

    // 工作职责
    if (data.responsibilities && data.responsibilities.length) {
      html += '<div style="margin-bottom:8px"><strong style="font-size:13px">主要职责：</strong><br>';
      data.responsibilities.forEach(r => {
        html += '<div style="font-size:12px;color:var(--text2);padding-left:12px">- ' + M.esc(r) + '</div>';
      });
      html += '</div>';
    }

    // 常见面试题
    if (data.common_interview_topics && data.common_interview_topics.length) {
      html += '<div style="margin-bottom:8px"><strong style="font-size:13px">常见面试题：</strong><br>';
      data.common_interview_topics.forEach(t => {
        html += '<div class="topic-item">' + M.esc(t) + '</div>';
      });
      html += '</div>';
    }

    // 考察重点
    if (data.interview_focus && data.interview_focus.length) {
      html += '<div style="margin-bottom:8px"><strong style="font-size:13px">考察重点：</strong><br>';
      html += data.interview_focus.map(f => '<span class="focus-tag">' + M.esc(f) + '</span>').join('');
      html += '</div>';
    }

    // 难度 & 经验
    if (data.difficulty || data.years_experience) {
      html += '<div style="font-size:12px;color:var(--text2);margin-bottom:4px">';
      const diffMap = { junior: '初级', mid: '中级', senior: '高级' };
      if (data.difficulty) html += '难度级别：' + (diffMap[data.difficulty] || data.difficulty) + ' · ';
      if (data.years_experience) html += '经验要求：' + M.esc(data.years_experience);
      html += '</div>';
    }

    // 行业洞察
    if (data.industry_insights) {
      html += '<div style="font-size:12px;color:var(--text2);margin-top:6px;padding:8px;background:var(--surface);border-radius:6px">' +
        M.esc(data.industry_insights) + '</div>';
    }

    // 重新分析按钮
    html += '<div style="margin-top:8px"><button class="btn btn-secondary btn-sm" id="refreshResearchBtn">重新分析</button></div>';
    html += '</div>';

    document.getElementById('researchResult').innerHTML = html;
    document.getElementById('refreshResearchBtn').addEventListener('click', () => R.doResearch(true));
  };

  // ---- 导出 ----
  M.Research = R;

})(window.MockMate);
