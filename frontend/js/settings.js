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
    document.getElementById('saveQwenKey').addEventListener('click', S.saveQwenKey);
    document.getElementById('saveQwenReasonerModel').addEventListener('click', S.saveQwenReasonerModel);
    document.getElementById('saveQwenChatModel').addEventListener('click', S.saveQwenChatModel);
    document.getElementById('saveQwenWrittenEvalModel').addEventListener('click', S.saveQwenWrittenEvalModel);
    document.getElementById('saveQwenTtsModel').addEventListener('click', S.saveQwenTtsModel);
    document.getElementById('saveZhipuKey').addEventListener('click', S.saveZhipuKey);
    document.getElementById('saveZhipuReasonerModel').addEventListener('click', S.saveZhipuReasonerModel);
    document.getElementById('saveZhipuChatModel').addEventListener('click', S.saveZhipuChatModel);
    document.getElementById('saveZhipuWrittenEvalModel').addEventListener('click', S.saveZhipuWrittenEvalModel);
    document.getElementById('saveZhipuTtsModel').addEventListener('click', S.saveZhipuTtsModel);
    document.getElementById('providerSelect').addEventListener('change', S.switchProvider);
    document.getElementById('enableTtsToggle').addEventListener('change', S.toggleTts);
    // 页面加载时恢复已存储的 Key（显示占位符）
    S.restoreKeyInputs();
    S.restoreTtsToggle();
    S.restoreQwenReasonerModel();
    S.restoreQwenChatModel();
    S.restoreQwenWrittenEvalModel();
    S.restoreQwenTtsModel();
    S.restoreZhipuReasonerModel();
    S.restoreZhipuChatModel();
    S.restoreZhipuWrittenEvalModel();
    S.restoreZhipuTtsModel();
    S.updateTtsProviderInfo();
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
    if (keys.qwen_api_key) {
      document.getElementById('qwenKeyInput').placeholder = '已保存（点击修改）';
    }
    if (keys.zhipu_api_key) {
      document.getElementById('zhipuKeyInput').placeholder = '已保存（点击修改）';
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

  // ---- 保存 Qwen Key ----
  S.saveQwenKey = async function () {
    var key = document.getElementById('qwenKeyInput').value.trim();
    if (!key) { M.toast('请输入通义千问 API Key'); return; }

    var btn = document.getElementById('saveQwenKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      await M.Crypto.saveAllApiKeys(null, { qwen_api_key: key });
      M.state._apiKeys.qwen_api_key = key;
      document.getElementById('qwenKeyInput').value = '';
      document.getElementById('qwenKeyInput').placeholder = '已保存（点击修改）';
      M.toast('Qwen API Key 已保存到浏览器');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 保存 Zhipu Key ----
  S.saveZhipuKey = async function () {
    var key = document.getElementById('zhipuKeyInput').value.trim();
    if (!key) { M.toast('请输入智谱 API Key'); return; }

    var btn = document.getElementById('saveZhipuKey');
    M.setBtnLoading(btn, true, '保存中...');

    try {
      await M.Crypto.saveAllApiKeys(null, { zhipu_api_key: key });
      M.state._apiKeys.zhipu_api_key = key;
      document.getElementById('zhipuKeyInput').value = '';
      document.getElementById('zhipuKeyInput').placeholder = '已保存（点击修改）';
      M.toast('Zhipu API Key 已保存到浏览器');
      await M.checkStatus();
    } catch(e) {
      M.toast('保存失败: ' + e.message);
    }
    M.setBtnLoading(btn, false, '保存');
  };

  // ---- 保存 Zhipu 模型 ----
  function saveZhipuModel(inputId, storageKey, defaultDesc) {
    var sel = document.getElementById(inputId);
    var model = sel.value;
    if (!model) {
      M.ls.remove(storageKey);
      M.toast('已重置为默认模型 (' + defaultDesc + ')');
    } else {
      M.ls.set(storageKey, model);
      M.toast('智谱模型已设置为 ' + model);
    }
    // 刷新显示：把选中值同步到其他同类型 select（支持联动）
    document.getElementById(inputId).value = model || '';
  }

  function restoreZhipuModel(inputId, storageKey) {
    var model = M.ls.get(storageKey, '');
    if (model) {
      document.getElementById(inputId).value = model;
    }
  }

  S.saveZhipuReasonerModel = function () { saveZhipuModel('zhipuReasonerModelInput', 'zhipu_reasoner_model', 'glm-4.7-flash'); };
  S.saveZhipuChatModel = function () { saveZhipuModel('zhipuChatModelInput', 'zhipu_chat_model', 'glm-4.7-flash'); };
  S.saveZhipuWrittenEvalModel = function () { saveZhipuModel('zhipuWrittenEvalModelInput', 'zhipu_written_eval_model', 'glm-4-flash'); };
  S.saveZhipuTtsModel = function () { saveZhipuModel('zhipuTtsModelInput', 'zhipu_tts_model', 'glm-tts'); };

  S.restoreZhipuReasonerModel = function () { restoreZhipuModel('zhipuReasonerModelInput', 'zhipu_reasoner_model'); };
  S.restoreZhipuChatModel = function () { restoreZhipuModel('zhipuChatModelInput', 'zhipu_chat_model'); };
  S.restoreZhipuWrittenEvalModel = function () { restoreZhipuModel('zhipuWrittenEvalModelInput', 'zhipu_written_eval_model'); };
  S.restoreZhipuTtsModel = function () { restoreZhipuModel('zhipuTtsModelInput', 'zhipu_tts_model'); };

  // ---- 保存 Qwen TTS 模型名 ----
  S.saveQwenTtsModel = function () {
    var sel = document.getElementById('qwenTtsModelInput');
    var model = sel.value;
    if (!model) {
      M.ls.remove('qwen_tts_model');
      M.toast('已重置为默认模型 (cosyvoice-v1)');
    } else {
      M.ls.set('qwen_tts_model', model);
      M.toast('Qwen TTS 模型已设置为 ' + model);
    }
  };

  S.restoreQwenTtsModel = function () {
    var model = M.ls.get('qwen_tts_model', '');
    if (model) {
      document.getElementById('qwenTtsModelInput').value = model;
    }
  };

  // ---- 保存 Qwen 推理/对话/判卷模型名 ----
  function saveQwenModel(inputId, storageKey, defaultName) {
    var sel = document.getElementById(inputId);
    var model = sel.value;
    if (!model) {
      M.ls.remove(storageKey);
      M.toast('已重置为默认模型 (' + defaultName + ')');
    } else {
      M.ls.set(storageKey, model);
      M.toast('Qwen 模型已设置为 ' + model);
    }
  }

  function restoreQwenModel(inputId, storageKey, defaultName) {
    var model = M.ls.get(storageKey, '');
    if (model) {
      document.getElementById(inputId).value = model;
    }
  }

  S.saveQwenReasonerModel = function () {
    saveQwenModel('qwenReasonerModelInput', 'qwen_reasoner_model', 'qwen-plus');
  };
  S.saveQwenChatModel = function () {
    saveQwenModel('qwenChatModelInput', 'qwen_chat_model', 'qwen-plus');
  };
  S.saveQwenWrittenEvalModel = function () {
    saveQwenModel('qwenWrittenEvalModelInput', 'qwen_written_eval_model', 'qwen-turbo');
  };

  S.restoreQwenReasonerModel = function () {
    restoreQwenModel('qwenReasonerModelInput', 'qwen_reasoner_model', 'qwen-plus');
  };
  S.restoreQwenChatModel = function () {
    restoreQwenModel('qwenChatModelInput', 'qwen_chat_model', 'qwen-plus');
  };
  S.restoreQwenWrittenEvalModel = function () {
    restoreQwenModel('qwenWrittenEvalModelInput', 'qwen_written_eval_model', 'qwen-turbo');
  };

  // ---- 语音播报开关 ----
  S.restoreTtsToggle = function () {
    var enabled = localStorage.getItem('mockmate_enable_tts');
    if (enabled === null) enabled = 'true';  // 默认开启
    document.getElementById('enableTtsToggle').checked = enabled === 'true';
    document.getElementById('enableTtsLabel').textContent = enabled === 'true' ? '开启' : '关闭';
    M.state._enableTts = enabled === 'true';
  };

  S.toggleTts = function (e) {
    var enabled = e.target.checked;
    localStorage.setItem('mockmate_enable_tts', enabled);
    document.getElementById('enableTtsLabel').textContent = enabled ? '开启' : '关闭';
    M.state._enableTts = enabled;
    M.toast('语音播报已' + (enabled ? '开启' : '关闭'));
  };

  S.setEnableTts = function (enabled) {
    localStorage.setItem('mockmate_enable_tts', enabled);
    M.state._enableTts = enabled;
  };

  S.getEnableTts = function () {
    if (M.state._enableTts === undefined) {
      var stored = localStorage.getItem('mockmate_enable_tts');
      M.state._enableTts = stored === null ? true : stored === 'true';
    }
    return M.state._enableTts;
  };

  // ---- TTS 提供商信息 ----
  S.ttsProviderName = function (provider) {
    provider = provider || M.state._apiKeys.provider;
    var map = { mimo: 'MiMo API', deepseek: 'DeepSeek（不支持语音）', qwen: '通义千问 CosyVoice', zhipu: '智谱 GLM-TTS' };
    return map[provider] || '未知';
  };

  S.ttsSupported = function (provider) {
    provider = provider || M.state._apiKeys.provider;
    return provider !== 'deepseek';
  };

  S.updateTtsProviderInfo = function () {
    var el = document.getElementById('ttsProviderName');
    var infoEl = document.getElementById('ttsProviderInfo');
    if (!el || !infoEl) return;
    var provider = M.state._apiKeys.provider || 'mimo';
    var name = S.ttsProviderName(provider);
    el.textContent = name;
    el.style.color = S.ttsSupported(provider) ? 'var(--green)' : 'var(--red)';
    infoEl.style.display = 'block';

    // 如果当前提供商不支持 TTS，自动禁用开关
    var toggle = document.getElementById('enableTtsToggle');
    if (toggle) {
      if (!S.ttsSupported(provider)) {
        toggle.checked = false;
        S.setEnableTts(false);
        document.getElementById('enableTtsLabel').textContent = '关闭';
      }
      toggle.disabled = !S.ttsSupported(provider);
      toggle.parentElement.style.opacity = S.ttsSupported(provider) ? '1' : '0.4';
    }
  };

  // ---- 切换提供商 ----
  S.switchProvider = async function (e) {
    var provider = e.target.value;
    try {
      await M.Crypto.saveAllApiKeys(null, { provider: provider });
      M.state._apiKeys.provider = provider;
      S.updateTtsProviderInfo();
      var nameMap = { mimo: 'MiMo', deepseek: 'DeepSeek', qwen: '通义千问', zhipu: '智谱' };
      M.toast('已切换到 ' + (nameMap[provider] || provider));
      await M.checkStatus();
    } catch(e) {
      M.toast('切换失败: ' + e.message);
    }
  };

  // ---- 导出 ----
  M.Settings = S;

})(window.MockMate);
