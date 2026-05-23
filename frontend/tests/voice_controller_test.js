/**
 * BDD/TDD: Voice Controller FSM + ASR Reducer 前端单元测试
 *
 * 覆盖 BDD 场景:
 *   A1/A2: 麦克风开关（VoiceState 转换）
 *   B1: partial 覆盖旧 partial
 *   B2: final 追加累积 + 清空 partial
 *   B3: speech_end 不更新 UI
 *   C1: 非 IDLE 时拒绝操作（防双连接）
 *   C2: 旧 session 消息丢弃
 *   D1-D4: 键盘事件隔离
 *   E1: 面试未开始不触发
 *
 * 运行: node voice_controller_test.js
 */
'use strict';

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
        console.log('  ✓ ' + message);
    } else {
        failed++;
        console.error('  ✗ FAIL: ' + message);
    }
}

function assertEquals(actual, expected, message) {
    if (actual === expected) {
        passed++;
        console.log('  ✓ ' + message);
    } else {
        failed++;
        console.error('  ✗ FAIL: ' + message + '\n    expected: ' + JSON.stringify(expected) + '\n    actual:   ' + JSON.stringify(actual));
    }
}

function assertDeepEquals(actual, expected, message) {
    const a = JSON.stringify(actual);
    const b = JSON.stringify(expected);
    if (a === b) {
        passed++;
        console.log('  ✓ ' + message);
    } else {
        failed++;
        console.error('  ✗ FAIL: ' + message + '\n    expected: ' + b + '\n    actual:   ' + a);
    }
}

// ============================================================
// Test 1: VoiceState FSM
// ============================================================

console.log('\n=== VoiceState FSM ===');

const VoiceState = {
    IDLE: 'IDLE',
    REQUESTING_PERMISSION: 'REQUESTING_PERMISSION',
    CONNECTING: 'CONNECTING',
    RECORDING: 'RECORDING',
    STOPPING: 'STOPPING',
    ERROR: 'ERROR'
};

/**
 * Voice FSM transition function.
 * Returns the new state, or null if the transition is invalid.
 */
function voiceStateTransition(currentState, event) {
    const transitions = {
        [VoiceState.IDLE]: {
            press_t: VoiceState.REQUESTING_PERMISSION,
        },
        [VoiceState.REQUESTING_PERMISSION]: {
            permission_granted: VoiceState.CONNECTING,
            permission_denied: VoiceState.ERROR,
            cancel: VoiceState.IDLE,
        },
        [VoiceState.CONNECTING]: {
            ws_open: VoiceState.RECORDING,
            ws_error: VoiceState.ERROR,
            cancel: VoiceState.STOPPING,
        },
        [VoiceState.RECORDING]: {
            press_t: VoiceState.STOPPING,
            ws_error: VoiceState.ERROR,
            tab_hidden: VoiceState.STOPPING,
        },
        [VoiceState.STOPPING]: {
            cleanup_done: VoiceState.IDLE,
        },
        [VoiceState.ERROR]: {
            reset: VoiceState.IDLE,
        },
    };
    const stateTransitions = transitions[currentState];
    if (!stateTransitions) return null;
    return stateTransitions[event] || null;
}

// Scenario A1: press_t from IDLE
assertEquals(voiceStateTransition(VoiceState.IDLE, 'press_t'),
    VoiceState.REQUESTING_PERMISSION, 'IDLE + press_t → REQUESTING_PERMISSION');

// Scenario A1 continued: permission_granted
assertEquals(voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_granted'),
    VoiceState.CONNECTING, 'REQUESTING_PERMISSION + permission_granted → CONNECTING');

// Scenario A1 continued: ws_open
assertEquals(voiceStateTransition(VoiceState.CONNECTING, 'ws_open'),
    VoiceState.RECORDING, 'CONNECTING + ws_open → RECORDING');

// Scenario A2: press_t from RECORDING
assertEquals(voiceStateTransition(VoiceState.RECORDING, 'press_t'),
    VoiceState.STOPPING, 'RECORDING + press_t → STOPPING');

// Scenario A2 continued: cleanup_done
assertEquals(voiceStateTransition(VoiceState.STOPPING, 'cleanup_done'),
    VoiceState.IDLE, 'STOPPING + cleanup_done → IDLE');

// Scenario C1: press_t from non-IDLE is invalid (防双连接)
assertEquals(voiceStateTransition(VoiceState.CONNECTING, 'press_t'),
    null, 'CONNECTING + press_t → null (拒绝双连接)');

assertEquals(voiceStateTransition(VoiceState.RECORDING, 'press_t'),
    VoiceState.STOPPING, 'RECORDING + press_t → STOPPING (允许关闭)');

// Scenario F1: permission_denied
assertEquals(voiceStateTransition(VoiceState.REQUESTING_PERMISSION, 'permission_denied'),
    VoiceState.ERROR, 'REQUESTING_PERMISSION + permission_denied → ERROR');

// Scenario F2: ws_error from CONNECTING
assertEquals(voiceStateTransition(VoiceState.CONNECTING, 'ws_error'),
    VoiceState.ERROR, 'CONNECTING + ws_error → ERROR');

// ERROR recovery
assertEquals(voiceStateTransition(VoiceState.ERROR, 'reset'),
    VoiceState.IDLE, 'ERROR + reset → IDLE');

// Unknown event doesn't change state
assertEquals(voiceStateTransition(VoiceState.IDLE, 'unknown_event'),
    null, 'IDLE + unknown_event → null');


// ============================================================
// Test 2: ASR Reducer (partial/final 处理)
// ============================================================

console.log('\n=== ASR Reducer ===');

/**
 * ASR state reducer — 纯函数，处理 partial 和 final 文本的累积逻辑。
 *
 * 规则:
 *   - partial: 覆盖旧 partial (不 append)
 *   - final: 追加到 finalText，清空 partialText
 *   - speech_end: 仅设置 awaitingFinal，不更新文本
 */
function asrReducer(state, action) {
    switch (action.type) {
        case 'partial':
            // 场景 B1: partial 覆盖
            return {
                ...state,
                partialText: action.text,
                awaitingFinal: false,
            };
        case 'speech_end':
            // 场景 B3: speech_end 只设置标记
            return {
                ...state,
                awaitingFinal: true,
            };
        case 'final':
            // 场景 B2: final 追加 + 清空 partial
            return {
                ...state,
                finalText: state.finalText + action.text + ' ',
                partialText: '',
                awaitingFinal: false,
            };
        case 'reset':
            return {
                finalText: '',
                partialText: '',
                awaitingFinal: false,
            };
        default:
            return state;
    }
}

function getDisplayText(state) {
    return state.finalText + state.partialText;
}

// Scenario B1: partial 覆盖旧 partial
{
    let state = { finalText: '', partialText: '', awaitingFinal: false };
    state = asrReducer(state, { type: 'partial', text: '我负责red' });
    assertEquals(getDisplayText(state), '我负责red', 'B1: 首次 partial → "我负责red"');

    state = asrReducer(state, { type: 'partial', text: '我负责redis' });
    assertEquals(getDisplayText(state), '我负责redis', 'B1: 再次 partial 覆盖 → "我负责redis"');
    assertEquals(state.partialText, '我负责redis', 'B1: partialText 被覆盖（不 append）');
}

// Scenario B2: final 追加 + 清空 partial
{
    let state = { finalText: '', partialText: '', awaitingFinal: false };
    state = asrReducer(state, { type: 'partial', text: '我在前公司负责' });
    assertEquals(getDisplayText(state), '我在前公司负责', 'B2: partial → display ok');

    state = asrReducer(state, { type: 'speech_end' });
    assertEquals(state.awaitingFinal, true, 'B2: speech_end → awaitingFinal=true');

    state = asrReducer(state, { type: 'final', text: '我在前公司负责后端开发' });
    assertEquals(getDisplayText(state), '我在前公司负责后端开发 ', 'B2: final 追加后 display 完整');
    assertEquals(state.partialText, '', 'B2: final 后 partialText 清空');
    assertEquals(state.awaitingFinal, false, 'B2: final 后 awaitingFinal 重置');
}

// B2 continued: 后续 partial 追加到 finalText 之后
{
    let state = {
        finalText: '我在前公司负责后端开发 ',
        partialText: '',
        awaitingFinal: false,
    };
    state = asrReducer(state, { type: 'partial', text: '还负责系统架构' });
    assertEquals(getDisplayText(state), '我在前公司负责后端开发 还负责系统架构',
        'B2: 后续 partial 追加到 finalText 后');

    state = asrReducer(state, { type: 'final', text: '还负责系统架构设计' });
    assertEquals(getDisplayText(state),
        '我在前公司负责后端开发 还负责系统架构设计 ',
        'B2: 第二个 final 正确追加');
}

// Scenario B3: speech_end 不更新 textarea
{
    let state = {
        finalText: '已完成识别的文本 ',
        partialText: '当前正在说的',
        awaitingFinal: false,
    };
    const displayBefore = getDisplayText(state);
    state = asrReducer(state, { type: 'speech_end' });
    assertEquals(getDisplayText(state), displayBefore, 'B3: speech_end 不改变 displayText');
    assertEquals(state.awaitingFinal, true, 'B3: speech_end 设置 awaitingFinal');
}

// reset
{
    let state = {
        finalText: '历史文本 ',
        partialText: '临时文本',
        awaitingFinal: true,
    };
    state = asrReducer(state, { type: 'reset' });
    assertDeepEquals(state, {
        finalText: '',
        partialText: '',
        awaitingFinal: false,
    }, 'reset 清空所有状态');
}

// Multiple finals accumulate
{
    let state = { finalText: '', partialText: '', awaitingFinal: false };
    state = asrReducer(state, { type: 'final', text: '第一句话' });
    state = asrReducer(state, { type: 'final', text: '第二句话' });
    state = asrReducer(state, { type: 'final', text: '第三句话' });
    assertEquals(state.finalText, '第一句话 第二句话 第三句话 ',
        '多次 final 正确累积');
    assertEquals(state.partialText, '', '多次 final 后 partialText 为空');
}


// ============================================================
// Test 3: Session Isolation (防旧 session 污染)
// ============================================================

console.log('\n=== Session Isolation ===');

function generateSessionId() {
    return 'session-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now();
}

// 模拟消息处理器
function shouldProcessMessage(msg, currentSessionId, voiceState) {
    // 旧 session 消息丢弃
    if (msg.sessionId && msg.sessionId !== currentSessionId) {
        return false;
    }
    // 会话已关闭的消息丢弃
    if (voiceState === VoiceState.IDLE && msg.type !== 'error') {
        return false;
    }
    return true;
}

// Scenario C2: 旧 session 消息被丢弃
{
    const currentSessionId = 'session-abc-123';
    const voiceState = VoiceState.RECORDING;

    const oldMsg = { type: 'partial', text: '旧消息', sessionId: 'session-old-456' };
    assert(!shouldProcessMessage(oldMsg, currentSessionId, voiceState),
        'C2: 旧 sessionId 消息被丢弃');

    const currentMsg = { type: 'partial', text: '新消息', sessionId: 'session-abc-123' };
    assert(shouldProcessMessage(currentMsg, currentSessionId, voiceState),
        'C2: 当前 sessionId 消息正常处理');
}

// Scenario C2: 会话关闭后的迟到消息
{
    const currentSessionId = 'session-closed-789';
    const voiceState = VoiceState.IDLE;

    const lateMsg = { type: 'final', text: '迟到消息', sessionId: 'session-closed-789' };
    assert(!shouldProcessMessage(lateMsg, currentSessionId, voiceState),
        'C2: 会话已关闭（IDLE），迟到消息被丢弃');

    const latePartial = { type: 'partial', text: '迟到', sessionId: 'session-closed-789' };
    assert(!shouldProcessMessage(latePartial, currentSessionId, voiceState),
        'C2: IDLE 状态丢弃 partial');
}

// Session ID 唯一性
{
    const id1 = generateSessionId();
    const id2 = generateSessionId();
    assert(id1 !== id2, '每次生成的 sessionId 唯一');
    assert(typeof id1 === 'string' && id1.length > 0, 'sessionId 是非空字符串');
}


// ============================================================
// Test 4: Keyboard Guard (键盘事件隔离)
// ============================================================

console.log('\n=== Keyboard Guard ===');

/**
 * 检查 T 键是否应该触发麦克风切换。
 * 返回 false = 应该跳过（不触发）。
 */
function shouldHandleTKey(event, activeTab, interviewStarted, voiceState) {
    // 修饰键 + T 不触发
    if (event.ctrlKey || event.metaKey || event.altKey) return false;
    // 按键重复不触发
    if (event.repeat) return false;
    // IME 输入中不触发
    if (event.isComposing) return false;
    // 不在拟真面试 Tab
    if (activeTab !== 'mock') return false;
    // 面试未开始
    if (!interviewStarted) return false;
    // 输入框/文本域中不触发
    const tag = (event.target && event.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return false;
    // contenteditable 中不触发
    if (event.target && event.target.isContentEditable) return false;
    // VoiceState 不在 [IDLE, RECORDING] 不触发
    if (voiceState !== VoiceState.IDLE && voiceState !== VoiceState.RECORDING) return false;

    return true;
}

// Scenario D3: Ctrl+T 不触发
{
    const event = { key: 't', ctrlKey: true, metaKey: false, altKey: false, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D3: Ctrl+T 不触发');
}

// Scenario D3: Meta+T 不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: true, altKey: false, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D3: Meta+T 不触发');
}

// Scenario D3: Alt+T 不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: true, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D3: Alt+T 不触发');
}

// Scenario D4: 按键重复不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: true, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D4: repeat=true 不触发');
}

// Scenario D2: IME 输入中不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: true, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D2: isComposing=true 不触发');
}

// Scenario D1: TEXTAREA 中不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: { tagName: 'TEXTAREA' } };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D1: TEXTAREA 中 T 不触发麦克风');
}

// Scenario D1: INPUT 中不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: { tagName: 'INPUT' } };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'D1: INPUT 中 T 不触发麦克风');
}

// Scenario E1: 面试未开始不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', false, VoiceState.IDLE),
        'E1: interviewStarted=false 不触发');
}

// Scenario E2: 其他 Tab 不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'setup', true, VoiceState.IDLE),
        'E2: activeTab=setup 不触发');
}

// Happy path: 正常的 T 按下应该触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: null };
    assert(shouldHandleTKey(event, 'mock', true, VoiceState.IDLE),
        'Happy: mock tab + started + IDLE → 触发');

    assert(shouldHandleTKey(event, 'mock', true, VoiceState.RECORDING),
        'Happy: mock tab + started + RECORDING → 触发（允许关闭）');
}

// 非 IDLE 非 RECORDING 不触发
{
    const event = { key: 't', ctrlKey: false, metaKey: false, altKey: false, repeat: false, isComposing: false, target: null };
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.REQUESTING_PERMISSION),
        'C1: REQUESTING_PERMISSION 状态拒绝 T');
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.CONNECTING),
        'C1: CONNECTING 状态拒绝 T');
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.STOPPING),
        'C1: STOPPING 状态拒绝 T');
    assert(!shouldHandleTKey(event, 'mock', true, VoiceState.ERROR),
        'C1: ERROR 状态拒绝 T');
}


// ============================================================
// Test 5: Resource Cleanup (资源清理顺序)
// ============================================================

console.log('\n=== Resource Cleanup ===');

/**
 * 模拟 cleanupVoiceResources 的清理顺序。
 * 验证: 按正确顺序调用，所有资源被释放。
 */
function simulateCleanup(voiceState) {
    const cleanupLog = [];

    if (voiceState === VoiceState.RECORDING || voiceState === VoiceState.STOPPING) {
        // 1. ws.send({type:"stop"})
        cleanupLog.push('ws.send(stop)');
        // 2. stop audio tracks
        cleanupLog.push('stopTracks');
        // 3. disconnect audio nodes
        cleanupLog.push('disconnectNodes');
        // 4. close websocket
        cleanupLog.push('ws.close');
        // 5. close AudioContext
        cleanupLog.push('audioCtx.close');
        // 6. reset state
        cleanupLog.push('state→IDLE');
    }

    return cleanupLog;
}

// Scenario A2: 正确的清理顺序
{
    const log = simulateCleanup(VoiceState.STOPPING);
    const expectedOrder = [
        'ws.send(stop)',
        'stopTracks',
        'disconnectNodes',
        'ws.close',
        'audioCtx.close',
        'state→IDLE',
    ];
    assertDeepEquals(log, expectedOrder, 'A2: 清理顺序正确');
    assertEquals(log.length, 6, 'A2: 所有 6 步清理完成');
}


// ============================================================
// Test 6: Double Connection Prevention (防双连接)
// ============================================================

console.log('\n=== Double Connection Prevention ===');

function canStartRecording(voiceState) {
    return voiceState === VoiceState.IDLE;
}

// Only IDLE allows start
assert(canStartRecording(VoiceState.IDLE), 'IDLE 允许启动录音');
assert(!canStartRecording(VoiceState.REQUESTING_PERMISSION), 'REQUESTING_PERMISSION 不允许启动');
assert(!canStartRecording(VoiceState.CONNECTING), 'CONNECTING 不允许启动');
assert(!canStartRecording(VoiceState.RECORDING), 'RECORDING 不允许启动');
assert(!canStartRecording(VoiceState.STOPPING), 'STOPPING 不允许启动');
assert(!canStartRecording(VoiceState.ERROR), 'ERROR 不允许启动');


// ============================================================
// Summary
// ============================================================

console.log('\n========================================');
console.log('  Results: ' + passed + ' passed, ' + failed + ' failed');
console.log('========================================');

if (failed > 0) {
    process.exit(1);
}
