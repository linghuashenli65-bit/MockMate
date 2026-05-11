/* ========================================
   MockMate.API — 后端接口封装
   自动携带 API Key 请求头和 JWT Token
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  function _buildHeaders(extra) {
    var headers = Object.assign({}, extra || {});
    // JWT Token
    var token = M.state._authToken;
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    // API Key 请求头（从内存缓存读取，无需异步）
    var keys = M.state._apiKeys;
    if (keys) {
      if (keys.mimo_api_key) headers['X-Mimo-Api-Key'] = keys.mimo_api_key;
      if (keys.deepseek_api_key) headers['X-Deepseek-Api-Key'] = keys.deepseek_api_key;
      if (keys.qwen_api_key) headers['X-Qwen-Api-Key'] = keys.qwen_api_key;
      if (keys.zhipu_api_key) headers['X-Zhipu-Api-Key'] = keys.zhipu_api_key;
      if (keys.provider) headers['X-Ai-Provider'] = keys.provider;
    }
    // 非敏感配置直接从 localStorage 读取
    ['qwen', 'zhipu'].forEach(function (p) {
      var tts = M.ls.get(p + '_tts_model', '');
      if (tts) headers['X-' + p.charAt(0).toUpperCase() + p.slice(1) + '-Tts-Model'] = tts;
      var reasoner = M.ls.get(p + '_reasoner_model', '');
      if (reasoner) headers['X-' + p.charAt(0).toUpperCase() + p.slice(1) + '-Model-Reasoner'] = reasoner;
      var chat = M.ls.get(p + '_chat_model', '');
      if (chat) headers['X-' + p.charAt(0).toUpperCase() + p.slice(1) + '-Model-Chat'] = chat;
      var writtenEval = M.ls.get(p + '_written_eval_model', '');
      if (writtenEval) headers['X-' + p.charAt(0).toUpperCase() + p.slice(1) + '-Model-Written-Eval'] = writtenEval;
    });
    return headers;
  }

  var API = {
    async _request(url, options) {
      try {
        var r = await fetch(url, options);
        if (r.status === 401) {
          // Token 过期，清除登录态
          M.state._authToken = null;
          M.ls.remove('auth_token');
          var detail = (await r.json().catch(function() { return {}; })).detail || '登录已过期，请重新登录';
          throw new Error(detail);
        }
        if (!r.ok) {
          var detail2 = (await r.json().catch(function() { return {}; })).detail || r.statusText;
          throw new Error(detail2);
        }
        return r.json();
      } catch (e) {
        if (e instanceof TypeError && e.message === 'Failed to fetch') {
          throw new Error('无法连接到服务器，请确认服务已启动');
        }
        throw e;
      }
    },

    get(url) {
      return this._request(url, {
        method: 'GET',
        headers: _buildHeaders(),
      });
    },

    post(url, data) {
      var headers = _buildHeaders({ 'Content-Type': 'application/json' });
      return this._request(url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(data),
      });
    },

    put(url, data) {
      var headers = _buildHeaders({ 'Content-Type': 'application/json' });
      return this._request(url, {
        method: 'PUT',
        headers: headers,
        body: JSON.stringify(data),
      });
    },

    delete(url) {
      return this._request(url, {
        method: 'DELETE',
        headers: _buildHeaders(),
      });
    },

    async upload(url, formData) {
      try {
        var headers = _buildHeaders();
        // upload 不设 Content-Type，让浏览器自动设置 multipart boundary
        delete headers['Content-Type'];
        var r = await fetch(url, { method: 'POST', body: formData, headers: headers });
        if (!r.ok) {
          var detail = (await r.json().catch(function() { return {}; })).detail || r.statusText;
          throw new Error(detail);
        }
        return r.json();
      } catch (e) {
        if (e instanceof TypeError && e.message === 'Failed to fetch') {
          throw new Error('无法连接到服务器');
        }
        throw e;
      }
    },
  };

  M.API = API;

})(window.MockMate);
