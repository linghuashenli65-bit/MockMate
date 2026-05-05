/* ========================================
   MockMate.Favorites — 题目收藏
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const F = {};

  F.init = function () {
    document.querySelector('[data-tab="favorites"]').addEventListener('click', () => {
      setTimeout(() => F.loadFavorites(), 50);
    });
  };

  F.loadFavorites = async function () {
    const container = document.getElementById('favoritesList');

    try {
      const result = await M.API.get('/api/favorites');
      const items = result.favorites || [];

      if (!items.length) {
        container.innerHTML = '<div class="empty-state">还没有收藏的题目</div>';
        return;
      }

      let html = '';
      items.forEach((item, i) => {
        const diffLabel = M.diffLabel(item.difficulty);
        const answerTrunc = (item.user_answer || '').length > 100
          ? (item.user_answer || '').slice(0, 100) + '...'
          : (item.user_answer || '');

        html +=
          '<div class="history-item" style="margin-bottom:8px">' +
            '<div class="hi-main">' +
              '<div class="hi-info" style="flex:1">' +
                '<div class="hi-position">第 ' + (i + 1) + ' 题' +
                  (item.type ? ' · ' + M.esc(item.type) : '') +
                  (diffLabel ? ' · ' + diffLabel : '') +
                  (item.topic ? ' · ' + M.esc(item.topic) : '') +
                '</div>' +
                '<div class="hi-meta" style="margin-top:4px;font-size:13px;line-height:1.5">' +
                  M.esc(item.question) +
                '</div>' +
                (answerTrunc ? '<div style="margin-top:6px;font-size:12px;color:var(--text2);padding:6px;background:var(--surface);border-radius:6px">答：' + M.esc(answerTrunc) + '</div>' : '') +
                '<div style="margin-top:4px;font-size:12px">' +
                  '得分：<span style="color:' + M.scoreColor(item.overall_score) + ';font-weight:600">' + item.overall_score + '</span>' +
                  ' · ' + M.formatDateTime(item.saved_at) +
                '</div>' +
              '</div>' +
              '<button class="btn btn-danger btn-sm" onclick="MockMate.Favorites.deleteFavorite(' + item.id + ')">删除</button>' +
            '</div>' +
          '</div>';
      });

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = '<div class="empty-state" style="color:var(--red)">加载失败: ' + M.esc(e.message) + '</div>';
    }
  };

  F.deleteFavorite = async function (favId) {
    if (!confirm('确定删除这条收藏吗？')) return;
    try {
      await M.API.delete('/api/favorites/' + favId);
      M.toast('已取消收藏');
      F.loadFavorites();
    } catch (e) {
      M.toast('删除失败: ' + e.message);
    }
  };

  F.saveCurrentQuestion = async function (question, answer, score) {
    try {
      await M.API.post('/api/favorites', {
        session_id: M.state.currentSessionId || '',
        question: question.question || '',
        type: question.type || '',
        difficulty: question.difficulty || '',
        topic: question.topic || '',
        user_answer: answer || '',
        overall_score: score || 0,
      });
      M.toast('已收藏题目');
    } catch (e) {
      M.toast('收藏失败: ' + e.message);
    }
  };

  M.Favorites = F;

})(window.MockMate);
