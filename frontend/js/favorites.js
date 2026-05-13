/* ========================================
   MockMate.Favorites — 题目收藏
   分页 + 搜索 + 展开/折叠
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const F = {};
  const state = {
    page: 1,
    pageSize: 10,
    search: '',
    loading: false,
    requestId: 0,
    totalPages: 0,
  };

  let searchTimer = null;

  /* -------- 初始化 -------- */
  F.init = function () {
    document.querySelector('[data-tab="favorites"]').addEventListener('click', () => {
      setTimeout(() => F.loadFavorites(1), 50);
    });

    const input = document.getElementById('favSearch');
    if (input) {
      input.addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
          state.search = this.value.trim();
          F.loadFavorites(1);
        }, 300);
      });
    }
  };

  /* -------- 加载收藏列表 -------- */
  F.loadFavorites = async function (page) {
    const container = document.getElementById('favoritesList');
    if (!container) return;

    const id = ++state.requestId;
    state.loading = true;
    state.page = page || 1;

    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    const paginationEl = document.getElementById('favPagination');
    if (paginationEl) paginationEl.innerHTML = '';

    try {
      const params = new URLSearchParams({
        page: state.page,
        page_size: state.pageSize,
        search: state.search,
      });

      const result = await M.API.get('/api/favorites?' + params.toString());
      if (id !== state.requestId) return; // 旧请求丢弃

      const items = result.items || [];
      const pag = result.pagination || {};
      state.totalPages = pag.total_pages || 0;

      if (!items.length) {
        const msg = state.search ? '没有找到匹配的收藏题目' : '还没有收藏的题目';
        container.innerHTML = '<div class="empty-state">' + msg + '</div>';
        return;
      }

      let html = '';
      items.forEach(function (item, i) {
        const num = (state.page - 1) * state.pageSize + i + 1;
        var diffLabel = M.diffLabel(item.difficulty);
        var hasAnswer = item.user_answer && item.user_answer.length > 0;
        var hasRef = item.reference_answer && item.reference_answer.length > 0;
        var time = M.formatDateTime(item.saved_at);
        var scoreColor = M.scoreColor(item.overall_score);

        html +=
          '<div class="fav-item" data-id="' + item.id + '">' +
            '<div class="fav-main">' +
              '<div class="fav-question markdown-body">' + M.md(item.question) + '</div>' +
              '<div class="fav-info">' +
                '<div class="fav-meta">' +
                  (item.type ? '<span class="fav-tag">' + M.esc(item.type) + '</span>' : '') +
                  diffLabel +
                  (item.topic ? '<span class="fav-tag">' + M.esc(item.topic) + '</span>' : '') +
                  '<span class="fav-score" style="color:' + scoreColor + '">' + item.overall_score + '分</span>' +
                '</div>' +
                '<div class="fav-actions">' +
                  '<span class="fav-time">' + time + '</span>' +
                  '<button class="expand-btn">展开回答</button>' +
                  '<button class="btn btn-danger btn-sm" onclick="MockMate.Favorites.deleteFavorite(' + item.id + ')">删除</button>' +
                '</div>' +
              '</div>' +
            '</div>' +
            '<div class="fav-body">' +
              (hasAnswer ? '<div class="fav-answer markdown-body"><strong>我的回答：</strong><br>' + M.md(item.user_answer) + '</div>' : '') +
              (hasRef ? '<div class="fav-ref markdown-body"><strong>参考回答：</strong><br>' + M.md(item.reference_answer) + '</div>' : '') +
            '</div>' +
          '</div>';
      });

      container.innerHTML = html;

      // 绑定展开按钮
      Array.from(container.querySelectorAll('.expand-btn')).forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var item = this.closest('.fav-item');
          var expanded = item.classList.toggle('expanded');
          this.textContent = expanded ? '收起' : '展开回答';
        });
      });

      F.renderPagination();

    } catch (e) {
      if (id !== state.requestId) return;
      container.innerHTML =
        '<div class="empty-state" style="color:var(--red)">加载失败: ' + M.esc(e.message) +
        '<br><button class="btn btn-sm btn-secondary" style="margin-top:8px" ' +
        'onclick="MockMate.Favorites.loadFavorites(' + state.page + ')">重试</button></div>';
    } finally {
      if (id === state.requestId) state.loading = false;
    }
  };

  /* -------- 渲染分页 -------- */
  F.renderPagination = function () {
    var el = document.getElementById('favPagination');
    if (!el) return;

    var total = state.totalPages;
    var cur = state.page;

    if (total <= 1) { el.innerHTML = ''; return; }

    var html = '';

    // 上一页
    html += '<button class="page-btn"' +
      (cur <= 1 ? ' disabled' : ' onclick="MockMate.Favorites.loadFavorites(' + (cur - 1) + ')"') +
      '>‹</button>';

    var pages = [];
    if (total <= 7) {
      for (var i = 1; i <= total; i++) pages.push(i);
    } else {
      pages.push(1);
      if (cur > 4) pages.push('...');
      var start = Math.max(2, cur - 2);
      var end = Math.min(total - 1, cur + 2);
      for (var i = start; i <= end; i++) pages.push(i);
      if (cur < total - 3) pages.push('...');
      pages.push(total);
    }

    pages.forEach(function (p) {
      if (p === '...') {
        html += '<span class="page-dots">…</span>';
      } else {
        html += '<button class="page-btn' + (p === cur ? ' active' : '') +
          '" onclick="MockMate.Favorites.loadFavorites(' + p + ')">' + p + '</button>';
      }
    });

    // 下一页
    html += '<button class="page-btn"' +
      (cur >= total ? ' disabled' : ' onclick="MockMate.Favorites.loadFavorites(' + (cur + 1) + ')"') +
      '>›</button>';

    el.innerHTML = html;
  };

  /* -------- 删除收藏 -------- */
  F.deleteFavorite = async function (favId) {
    if (!confirm('确定删除这条收藏吗？')) return;
    try {
      await M.API.delete('/api/favorites/' + favId);
      M.toast('已取消收藏');
      F.loadFavorites(state.page);
    } catch (e) {
      M.toast('删除失败: ' + e.message);
    }
  };

  /* -------- 收藏当前题目（从 interview.js 调用）-------- */
  F.saveCurrentQuestion = async function (question, answer, score, referenceAnswer) {
    try {
      await M.API.post('/api/favorites', {
        session_id: M.state.currentSessionId || '',
        question: question.question || '',
        type: question.type || '',
        difficulty: question.difficulty || '',
        topic: question.topic || '',
        user_answer: answer || '',
        overall_score: score || 0,
        reference_answer: referenceAnswer || '',
      });
      M.toast('已收藏题目');
    } catch (e) {
      M.toast('收藏失败: ' + e.message);
    }
  };

  M.Favorites = F;

})(window.MockMate);
