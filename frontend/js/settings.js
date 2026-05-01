/* ========================================
   MockMate.Settings — 设置页面
   ======================================== */

window.MockMate = window.MockMate || {};

(function (M) {

  const S = {};

  S.init = function () {
    document.getElementById('saveMimoKey').addEventListener('click', S.saveMimoKey);
    document.getElementById('saveDeepseekKey').addEventListener('click', S.saveDeepseekKey);
    document.getElementById('providerSelect').addEventListener('change', S.switchProvider);
  };

  // ---- 保存 MiMo Key ----
  S.saveMimoKey = async function () {
    const key = document.getElementById('mimoKeyInput').value.trim();
    if (!key) { M.toast('请输入 MiMo API Key'); return; }

    const btn = document.getElementById('saveMimoKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      await M.API.post('/api/config', { mimo_api_key: key });
      M.toast('MiMo API Key 已保存');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 保存 DeepSeek Key ----
  S.saveDeepseekKey = async function () {
    const key = document.getElementById('deepseekKeyInput').value.trim();
    if (!key) { M.toast('请输入 DeepSeek API Key'); return; }

    const btn = document.getElementById('saveDeepseekKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      await M.API.post('/api/config', { deepseek_api_key: key });
      M.toast('DeepSeek API Key 已保存');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 切换提供商 ----
  S.switchProvider = async function (e) {
    const provider = e.target.value;
    try {
      await M.API.post('/api/config', { provider });
      M.toast('已切换到 ' + (provider === 'mimo' ? 'MiMo' : 'DeepSeek'));
      await M.checkStatus();
    } catch(e) {
      M.toast('切换失败: ' + e.message);
    }
  };

  // ---- 导出 ----
  M.Settings = S;

})(window.MockMate);
