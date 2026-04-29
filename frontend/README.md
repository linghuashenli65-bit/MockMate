# Frontend — 开发文档

## 架构概述

前端是单页应用（SPA），全部代码在单个 `index.html` 文件中，无构建步骤、无框架依赖。

```
index.html
  ├── <style>      → 全部 CSS（暗色主题，CSS 变量）
  ├── <body>       → HTML 结构
  │   ├── header   → 标题 + 状态指示
  │   ├── .tabs    → 导航标签（准备面试/模拟面试/历史记录/设置）
  │   └── .tab-content × 4 → 每个标签页的内容
  └── <script>     → 全部 JavaScript
```

## Tab 系统

```javascript
// 4 个 Tab
"setup"       → 准备面试（填信息+选轮次+开始面试）
"interview"   → 模拟面试（出题+回答+评分）
"history"     → 历史记录（查看过往面试）
"settings"    → 设置（API Key + 提供商切换）

// 切换逻辑
switchTab(name) → 切换 active class
面试中切 Tab → 确认弹窗保护
```

### 新增 Tab

1. HTML 添加 `<button class="tab" data-tab="mytab">`
2. HTML 添加 `<div class="tab-content" id="tab-mytab">`
3. JS 中 `switchTab()` 自动处理（基于 data-tab 属性）

## CSS 规范

### 主题变量

```css
:root {
  --bg: #0f1117;       /* 背景 */
  --surface: #1a1d29;  /* 卡片底色 */
  --surface2: #232738;  /* 次级底色 */
  --border: #2e3348;   /* 边框 */
  --text: #e4e6f0;     /* 主文字 */
  --text2: #8b8fa8;    /* 辅助文字 */
  --accent: #6c5ce7;   /* 主色（紫色） */
  --accent2: #a29bfe;  /* 辅色 */
  --green: #00b894;    /* 高分 */
  --yellow: #fdcb6e;   /* 中分 */
  --red: #e17055;      /* 低分/危险 */
  --radius: 10px;      /* 圆角 */
}
```

### 通用组件

| Class | 用途 |
|-------|------|
| `.card` | 内容卡片容器 |
| `.btn` / `.btn-primary` / `.btn-secondary` / `.btn-danger` / `.btn-sm` | 按钮 |
| `.form-group` | 表单字段组 |
| `.skill-tag` | 技能标签 |
| `.spinner` | 加载动画 |
| `.score-tag` | 评分标签 |
| `.empty-state` | 空状态占位 |
| `.toast` | 底部提示条 |

### 响应式

- 640px 断点：单列布局
- `#roundSelector` 在移动端切换为单列

## API 层

```javascript
const API = {
  get(url)      → fetch GET → JSON
  post(url, data) → fetch POST (JSON body) → JSON
  delete(url)   → fetch DELETE → JSON
  upload(url, formData) → fetch POST (multipart) → JSON
};
```

所有请求自动处理错误，非 2xx 响应抛出 `Error(detail)`。

## 状态管理

全局变量（在 `<script>` 顶部）：

```javascript
currentSessionId     // 当前面试会话 ID
currentQuestionIndex // 当前题号
interviewActive      // 面试是否进行中
interviewStartTime   // 面试开始时间
timerInterval        // 计时器句柄
_window._currentProfile // 当前岗位画像数据
```

### 关键函数

| 函数 | 触发时机 | 职责 |
|------|---------|------|
| `checkStatus()` | 页面加载 | 获取服务状态，更新指示灯 |
| `switchTab(name)` | Tab 点击 | 切换页面，保护进行中的面试 |
| `startInterview()` | 点击"开始模拟面试" | 调 API 创建会话，切到面试 Tab |
| `showQuestion(question, index, audioUrl)` | 收到新题 | 渲染题目 UI |
| `submitAnswer()` | Ctrl+Enter 或点击提交 | 提交回答，展示评分 |
| `endInterview()` | 点击"结束面试" | 生成报告，清理状态 |
| `showReport(result)` | 收到报告 | 渲染完整报告 |
| `loadHistory()` | 切到历史 Tab | 加载面试记录列表 |
| `viewSession(id)` | 点击记录 | 查看单条记录详情 |
| `copyReport()` | 点击"复制报告" | 报告内容复制到剪贴板 |
| `refreshResearch()` | 点击"重新分析" | 跳过缓存重新分析岗位 |

## 面试流程状态机

```
IDLE → STARTING → QUESTION → ANSWERING → EVALUATING → QUESTION (循环) → REPORT
  │                                                                    │
  └────────────────────────────────────────────────────────────────────┘
  (通过 switchTab 回到 setup)
```

- `interviewActive = true` 时阻止意外离开（`beforeunload` 事件）
- 结束面试后 `interviewActive = false`

## 轮次选择器

```html
<!-- 4 个 radio，网格布局 2×2 -->
round-option[data-round="tech_1"]         → 技术一面
round-option[data-round="tech_2"]         → 技术二面
round-option[data-round="comprehensive"]  → 综合面
round-option[data-round="written"]        → 笔试
```

选中高亮：`.round-option.selected { border-color: var(--accent); }`

默认选中：技术一面（`tech_1`）

### 轮次名称映射

```javascript
const roundNames = {
  'written': '笔试',
  'tech_1': '技术一面',
  'tech_2': '技术二面',
  'comprehensive': '综合面',
};
```

此映射在 `showReport`、`loadHistory`、`viewSession` 三处都有定义（各自独立作用域）。

## 快捷键

| 快捷键 | 动作 |
|--------|------|
| Ctrl+Enter | 提交回答 |

注册方式：

```javascript
ta.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') submitAnswer();
});
```

## 新增功能指南

### 添加新的表单字段

1. 在对应 Tab 的 HTML 中添加 `<div class="form-group">`
2. 在 JS 中通过 `document.getElementById('xxx').value` 取值
3. 在 API 调用中加入新字段

### 添加新的后端 API

1. 在 `backend/main.py` 添加路由
2. 在 `frontend/index.html` 的 `API` 对象不用修改（`get/post/delete/upload` 已通用）
3. 在 JS 中调用 `API.get('/api/new-endpoint')` 或 `API.post('/api/new-endpoint', data)`

### 添加新的 Tab 页面

1. HTML：添加 `.tab` 按钮 + `.tab-content` 容器
2. JS：`switchTab()` 自动处理，无需额外注册
3. 如果新 Tab 需要加载数据，在 Tab 的点击事件中用 `setTimeout(loadFn, 100)` 调用

### 修改面试题目展示

编辑 `showQuestion()` 函数中的 HTML 模板字符串，题目数据格式：

```javascript
{
  question: "题目内容",
  type: "技术/行为/设计",
  difficulty: "easy/medium/hard",
  topic: "考察主题",
  expected_points: ["要点1", "要点2"]
}
```

## 注意

- 所有用户输入在渲染前通过 `esc()` 转义（基于 `textContent` + `innerHTML`），防止 XSS
- `roundNames` 映射在多个函数中分别定义（非全局），修改时需同步更新
- 避免在全局作用域添加变量，优先使用 `window._xxx` 或函数内局部变量
- 模板字符串中 JS 表达式注意 `||` 运算符优先级，复杂表达式用括号包裹
