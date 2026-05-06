/* ========================================
   MockMate.Settings — 设置页面
   API Key 加密存储在浏览器 localStorage
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  var S = {};

  S.init = function () {
    document.getElementById('saveMimoKey').addEventListener('click', S.saveMimoKey);
    document.getElementById('saveDeepseekKey').addEventListener('click', S.saveDeepseekKey);
    document.getElementById('providerSelect').addEventListener('change', S.switchProvider);
    // 页面加载时恢复已存储的 Key（显示占位符）
    S.restoreKeyInputs();
  };

  // ---- 恢复 Key 输入框状态 ----
  S.restoreKeyInputs = async function () {
    var keys = M.state._apiKeys;
    if (keys.mimo_api_key) {
      document.getElementById('mimoKeyInput').placeholder = '已保存（点击修改）';
    }
    if (keys.deepseek_api_key) {
      document.getElementById('deepseekKeyInput').placeholder = '已保存（点击修改）';
    }
    if (keys.provider) {
      var sel = document.getElementById('providerSelect');
      if (sel) sel.value = keys.provider;
    }
  };

  // ---- 保存 MiMo Key ----
  S.saveMimoKey = async function () {
    var key = document.getElementById('mimoKeyInput').value.trim();
    if (!key) { M.toast('请输入 MiMo API Key'); return; }

    var btn = document.getElementById('saveMimoKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      // 加密存储到 localStorage
      await M.Crypto.saveAllApiKeys(null, { mimo_api_key: key });
      // 更新内存缓存
      M.state._apiKeys.mimo_api_key = key;
      // 清空输入框，显示占位符
      document.getElementById('mimoKeyInput').value = '';
      document.getElementById('mimoKeyInput').placeholder = '已保存（点击修改）';
      M.toast('MiMo API Key 已保存到浏览器');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 保存 DeepSeek Key ----
  S.saveDeepseekKey = async function () {
    var key = document.getElementById('deepseekKeyInput').value.trim();
    if (!key) { M.toast('请输入 DeepSeek API Key'); return; }

    var btn = document.getElementById('saveDeepseekKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      await M.Crypto.saveAllApiKeys(null, { deepseek_api_key: key });
      M.state._apiKeys.deepseek_api_key = key;
      document.getElementById('deepseekKeyInput').value = '';
      document.getElementById('deepseekKeyInput').placeholder = '已保存（点击修改）';
      M.toast('DeepSeek API Key 已保存到浏览器');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 切换提供商 ----
  S.switchProvider = async function (e) {
    var provider = e.target.value;
    try {
      await M.Crypto.saveAllApiKeys(null, { provider: provider });
      M.state._apiKeys.provider = provider;
      M.toast('已切换到 ' + (provider === 'mimo' ? 'MiMo' : 'DeepSeek'));
      await M.checkStatus();
    } catch(e) {
      M.toast('切换失败: ' + e.message);
    }
  };

  // ---- 导出 ----
  M.Settings = S;

})(window.MockMate);
