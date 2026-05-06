/* ========================================
   MockMate.Auth — 认证管理（页面跳转版）
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  var A = {};

  // ---- 检查登录状态 ----
  // 返回 email（已登录）或 null（未登录）
  A.checkAuth = function () {
    var token = M.ls.get('auth_token');
    var email = M.ls.get('user_email');
    var nickname = M.ls.get('user_nickname');

    if (token && email) {
      M.state._authToken = token;
      // 显示用户信息
      var infoEl = document.getElementById('userInfo');
      var nameEl = document.getElementById('userNickname');
      if (infoEl) infoEl.style.display = 'flex';
      if (nameEl) nameEl.textContent = nickname || email;
      return email;
    }

    // 未登录 → 跳转到登录页面
    window.location.href = '/login.html';
    return null;
  };

  // ---- 退出 ----
  A.logout = function () {
    M.state._authToken = null;
    M.ls.remove('auth_token');
    M.ls.remove('user_email');
    M.ls.remove('user_nickname');
    window.location.href = '/login.html';
  };

  // ---- 导出 ----
  M.Auth = A;

})(window.MockMate);
