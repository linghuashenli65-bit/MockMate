/* 点赞/点踩反馈模块 */

window.MockMate = window.MockMate || {};

(function (M) {

  M.Feedback = {
    /* 提交点赞/点踩 */
    async submit(recordType, recordId, rating, corrections) {
      try {
        const r = await M.API.post('/api/feedback/submit', {
          record_type: recordType,
          record_id: recordId,
          rating: rating,
          corrections: corrections || null
        });
        return r;
      } catch(e) {
        console.error('反馈提交失败:', e);
        M.toast('反馈提交失败');
        return null;
      }
    },

    /* 渲染点赞/点踩按钮组 */
    renderButtons(recordType, recordId, containerEl) {
      if (!recordId) return;

      const wrap = document.createElement('div');
      wrap.className = 'feedback-buttons';
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:10px;padding-top:8px;border-top:1px solid var(--border);';

      var label = document.createElement('span');
      label.textContent = '这个评分准确吗？';
      label.style.cssText = 'font-size:12px;color:var(--text2);margin-right:4px;';
      wrap.appendChild(label);

      var btnUp = this._makeBtn('👍 准确', 'up', recordType, recordId, wrap);
      var btnDown = this._makeBtn('👎 不准确', 'down', recordType, recordId, wrap);

      wrap.appendChild(btnUp);
      wrap.appendChild(btnDown);
      containerEl.appendChild(wrap);
    },

    /* 创建修正弹窗 */
    showCorrectionModal(recordType, recordId, currentData) {
      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';

      var modal = document.createElement('div');
      modal.style.cssText = 'background:var(--card);border-radius:12px;padding:24px;max-width:560px;width:90%;max-height:80vh;overflow-y:auto;';

      var title = document.createElement('h3');
      title.textContent = '修正评分';
      title.style.cssText = 'margin:0 0 16px 0;font-size:16px;';
      modal.appendChild(title);

      var fields = [];
      if (recordType === 'score') {
        fields = this._buildScoreCorrectionForm(modal, currentData);
      } else {
        fields = this._buildEvalCorrectionForm(modal, currentData);
      }

      // 按钮
      var btnWrap = document.createElement('div');
      btnWrap.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:16px;';

      var cancelBtn = document.createElement('button');
      cancelBtn.textContent = '取消';
      cancelBtn.className = 'btn btn-secondary';
      cancelBtn.onclick = function() { document.body.removeChild(overlay); };
      btnWrap.appendChild(cancelBtn);

      var saveBtn = document.createElement('button');
      saveBtn.textContent = '提交修正';
      saveBtn.className = 'btn btn-primary';
      btnWrap.appendChild(saveBtn);

      modal.appendChild(btnWrap);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      var self = this;
      saveBtn.onclick = async function() {
        var corrections = {};
        fields.forEach(function(f) {
          var el = document.getElementById('fb_' + f.key);
          if (el) corrections[f.key] = el.value;
        });

        saveBtn.disabled = true;
        saveBtn.textContent = '提交中...';

        var ok = await self.submit(recordType, recordId, 'down', corrections);
        if (ok) {
          M.toast('感谢反馈，评分已修正');
          document.body.removeChild(overlay);
        } else {
          saveBtn.disabled = false;
          saveBtn.textContent = '提交修正';
        }
      };
    },

    /* 简历评分修正表单 */
    _buildScoreCorrectionForm(modal, data) {
      var fields = [
        { key: 'score', label: '综合评分（0-100）', value: data.score || 0, type: 'number' },
      ];
      (data.strengths || []).forEach(function(s, i) {
        fields.push({ key: 'strength_' + i, label: '优点', value: s });
      });
      (data.weaknesses || []).forEach(function(s, i) {
        fields.push({ key: 'weakness_' + i, label: '不足', value: s });
      });
      (data.suggestions || []).forEach(function(s, i) {
        fields.push({ key: 'suggestion_' + i, label: '优化建议', value: s });
      });

      this._renderFormFields(modal, fields);
      return fields;
    },

    /* 面试评分修正表单 */
    _buildEvalCorrectionForm(modal, data) {
      var fields = [
        { key: 'technical_score', label: '技术评分（0-10）', value: data.technical_score ?? 0, type: 'number' },
        { key: 'logic_score', label: '逻辑评分（0-10）', value: data.logic_score ?? 0, type: 'number' },
        { key: 'depth_score', label: '深度评分（0-10）', value: data.depth_score ?? 0, type: 'number' },
        { key: 'communication_score', label: '表达评分（0-10）', value: data.communication_score ?? 0, type: 'number' },
        { key: 'overall_score', label: '综合评分（0-10）', value: data.overall_score ?? 0, type: 'number' },
        { key: 'summary', label: '评语', value: data.summary || '', type: 'textarea' },
        { key: 'strengths', label: '优点（逗号分隔）', value: (data.strengths || []).join('、') },
        { key: 'improvements', label: '改进建议（逗号分隔）', value: (data.improvements || []).join('、') },
        { key: 'reference_answer', label: '参考回答', value: data.reference_answer || '', type: 'textarea' },
      ];

      this._renderFormFields(modal, fields);
      return fields;
    },

    _renderFormFields(modal, fields) {
      fields.forEach(function(f) {
        var label = document.createElement('label');
        label.htmlFor = 'fb_' + f.key;
        label.textContent = f.label;
        label.style.cssText = 'display:block;font-size:13px;color:var(--text2);margin:8px 0 4px;';

        var input;
        if (f.type === 'textarea') {
          input = document.createElement('textarea');
          input.style.cssText = 'width:100%;min-height:60px;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text1);font-size:13px;resize:vertical;box-sizing:border-box;';
        } else if (f.type === 'number') {
          input = document.createElement('input');
          input.type = 'number';
          input.style.cssText = 'width:100px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text1);font-size:13px;';
        } else {
          input = document.createElement('input');
          input.type = 'text';
          input.style.cssText = 'width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text1);font-size:13px;box-sizing:border-box;';
        }
        input.id = 'fb_' + f.key;
        input.value = f.value;
        modal.appendChild(label);
        modal.appendChild(input);
      });
    },

    /* 创建按钮 */
    _makeBtn(text, rating, recordType, recordId, wrap) {
      var btn = document.createElement('button');
      btn.textContent = text;
      btn.style.cssText = 'font-size:12px;padding:4px 10px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text2);cursor:pointer;';

      var self = this;
      btn.onclick = async function() {
        if (rating === 'up') {
          await self.submit(recordType, recordId, 'up');
          btn.textContent = '✅ 已采纳';
          btn.disabled = true;
          btn.style.opacity = '0.6';
          var allBtns = wrap.querySelectorAll('button');
          allBtns.forEach(function(b) { if (b !== btn) b.disabled = true; });
          M.toast('感谢反馈！');
        } else {
          var currentData = {};
          if (recordType === 'score') {
            currentData = M.state._resumeScore || {};
          } else {
            currentData = M.state._lastEvaluation || {};
          }
          self.showCorrectionModal(recordType, recordId, currentData);
        }
      };

      return btn;
    }
  };

})(window.MockMate);
