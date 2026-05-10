# Frontend — 开发文档

## 架构概述

前端是模块化单页应用（SPA），无框架、无构建步骤。所有代码挂载在 `window.MockMate` 命名空间下。

```
frontend/
├── index.html              — HTML 骨架（7 Tab 页面）
├── css/
│   └── style.css           — 全部样式
└── js/
    ├── app.js              — 主入口：初始化、Tab 切换、全局状态、快捷键
    ├── api.js              — API 层（get/post/delete/upload）
    ├── utils.js            — 工具函数（esc、toast、scoreColor、ROUND_NAMES 常量）
    ├── interview.js        — 面试流程（开始→出题→提交→评估→结束→报告）
    ├── research.js         — 岗位画像搜索 + 结果渲染
    ├── history.js          — 历史记录 + Chart.js 图表 + 统计摘要
    ├── favorites.js        — 题目收藏管理
    ├── custom.js           — 自定义题目 CRUD
    ├── settings.js         — API Key 加密存储、Qwen 模型配置、提供商切换
    ├── auth.js             — 用户认证（邮箱验证码登录）
    ├── feedback.js         — 评分反馈（👍/👎 点踩、修正数据提交）
    └── finetune.js         — 训练数据展示（统计、过滤、浏览）
```

### 依赖关系

```
utils.js  ←──  api.js  ←──  app.js  ←──  interview.js
                                        research.js
                                        history.js  (依赖 Chart.js CDN)
                                        favorites.js
                                        custom.js
                                        settings.js
                                        auth.js
                                        feedback.js
                                        finetune.js
```

### 命名空间

所有模块通过 IIFE 挂载到 `window.MockMate`：

```javascript
window.MockMate = window.MockMate || {};
(function (M) {
  // 模块代码
  M.ModuleName = { ... };
})(window.MockMate);
```

- `MockMate.Utils` — 工具函数
- `MockMate.API` — HTTP 请求
- `MockMate.Auth` — 用户认证（邮箱验证码登录）
- `MockMate.App` — 主控制器
- `MockMate.Interview` — 面试逻辑
- `MockMate.Research` — 岗位研究
- `MockMate.History` — 历史记录 & 图表
- `MockMate.Favorites` — 题目收藏
- `MockMate.Custom` — 自定义题目
- `MockMate.Settings` — 设置（API Key + 模型配置）
- `MockMate.Feedback` — 评分反馈
- `MockMate.Finetune` — 训练数据管理

### HTML 加载顺序

```html
<!-- 1. Chart.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<!-- 2. 基础模块（无依赖） -->
<script src="js/utils.js"></script>
<!-- 3. API 层（依赖 utils） -->
<script src="js/api.js"></script>
<!-- 4. 主入口（依赖 api + utils） -->
<script src="js/app.js"></script>
<!-- 5. 业务模块（依赖 app） -->
<script src="js/interview.js"></script>
<script src="js/research.js"></script>
<script src="js/history.js"></script>
<script src="js/favorites.js"></script>
<script src="js/custom.js"></script>
<script src="js/settings.js"></script>
<script src="js/auth.js"></script>
<script src="js/feedback.js"></script>
<script src="js/finetune.js"></script>
```

所有模块在 `DOMContentLoaded` 时通过 `MockMate.init()` 统一初始化。

---

## Tab 系统

```javascript
// 7 个 Tab
"setup"       → 准备面试（填信息+选轮次+开始面试）
"interview"   → 模拟面试（出题+回答+评分）
"history"     → 历史记录（统计+图表+查看过往面试）
"favorites"   → 题目收藏
"custom"      → 自定义题目
"finetune"    → 训练数据管理
"settings"    → 设置（API Key + 提供商切换 + 模型配置）

// 切换逻辑在 app.js 中
MockMate.switchTab(name) → 切换 active class
面试中切 Tab → 确认弹窗保护
```

### 新增 Tab

1. HTML：添加 `<button class="tab" data-tab="mytab">`
2. HTML：添加 `<div class="tab-content" id="tab-mytab">`
3. JS：新建模块文件，在 `init()` 中绑定事件
4. 在 `index.html` 的 `<script>` 标签区引入新文件
5. `switchTab()` 基于 data-tab 属性自动处理

---

## CSS 规范

所有样式在 `css/style.css` 中，按功能分区：

| 分区 | 内容 |
|------|------|
| 主题变量 | `:root { --bg, --surface, --accent, ... }` |
| 基础重置 | `*`, `body`, `.app` |
| Header | 标题、状态指示灯 |
| Card | `.card` 卡片容器 |
| Tabs | 标签导航 |
| Buttons | `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-sm` |
| Forms | `input`, `textarea`, `select`, `.form-group` |
| States | `.empty-state`, `.loading`, `.spinner` |
| Toast | 底部提示 |
| Profile | `.skill-tag`, `.topic-item`, `.focus-tag`, `.profile-grid` |
| Round Selector | 轮次选择器 |
| Interview | 进度条、倒计时、题目框、反馈框、录音按钮 |
| Settings | 设置行布局 |
| History | 统计网格、图表容器、历史卡片、薄弱点 |
| Responsive | 768px / 480px 断点 |

### 主题变量

```css
:root {
  --bg: #0f1117;       /* 背景 */
  --surface: #1a1d29;  /* 卡片底色 */
  --surface2: #232738; /* 次级底色 */
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

- 768px 断点：统计卡片 4列→2列，图表高度缩小
- 480px 断点：单列布局，轮次选择器单列，设置行堆叠，按钮全宽
- 所有操作按钮 `min-height: 44px`（touch target 标准）

---

## 状态管理

全局状态存储在 `MockMate.state` 对象中（定义于 `app.js`）：

```javascript
MockMate.state = {
  currentSessionId:     null,    // 当前面试会话 ID
  currentQuestionIndex: 0,      // 当前题号
  interviewActive:      false,   // 面试是否进行中
  interviewStartTime:   null,    // 面试开始时间戳
  timerInterval:        null,    // 计时器句柄
  isWrittenRound:       false,   // 是否为笔试轮次
  currentRound:         null,    // 当前轮次
  totalQuestions:       0,       // 总题数
  currentProfile:       null,    // 当前岗位画像
  countdownInterval:    null,    // 倒计时句柄
  countdownRemaining:   0,       // 倒计时剩余秒数
  countdownPaused:      false,   // 倒计时是否暂停
  drafts:               {},      // 草稿缓存 { "sessionId_qIndex": "text" }
  suspendedQuestions:   [],      // 跳过/暂挂的题目
  _apiKeys: {                    // API Key 内存缓存
    mimo_api_key: '',
    deepseek_api_key: '',
    qwen_api_key: '',
    provider: 'mimo',
  },
  _enableTts:           true,    // 语音播报开关
  _selectedCustomIds:   [],      // 已选的自定义题目 ID
};
```

表单记忆和草稿使用 `MockMate.Utils.ls` 操作 localStorage。

---

## 关键函数

| 模块 | 函数 | 触发时机 | 职责 |
|------|------|---------|------|
| app | `MockMate.init()` | DOMContentLoaded | 初始化所有模块 |
| app | `MockMate.switchTab(name)` | Tab 点击 | 切换页面，保护面试 |
| app | `MockMate.checkStatus()` | 页面加载 | 获取服务状态，更新指示灯 |
| app | `MockMate.restoreFormMemory()` | 页面加载 | 从 localStorage 恢复表单数据 |
| app | `MockMate.clearLocalData()` | 点击按钮 | 清除所有本地缓存 |
| interview | `I.startInterview()` | 点击"开始模拟面试" | 调 API 创建会话，切到面试 Tab |
| interview | `I.showQuestion(q, idx, audio)` | 收到新题 | 渲染题目 + 进度条 + 倒计时 |
| interview | `I.submitAnswer()` | Ctrl+Enter / 点击提交 | 提交回答，展示评分 |
| interview | `I.endInterview()` | 点击"结束面试" | 生成报告，清理状态 |
| interview | `I.showReport(result)` | 收到报告 | 渲染完整报告 |
| interview | `I.downloadReport(result)` | 点击"下载报告" | 生成 .txt 文件下载 |
| research | `R.doResearch(refresh)` | 点击分析按钮 | 搜索岗位画像 |
| research | `R.renderProfileCard(data)` | 搜索完成 | 渲染完整画像卡片 |
| history | `H.loadHistory()` | 切到历史 Tab | 加载记录列表 + 图表 |
| history | `H.viewSession(id)` | 点击记录 | 查看单条详情 + 雷达图 |
| history | `H.deleteSession(id)` | 点击删除 | 删除记录 |
| history | `H.renderStatsSummary()` | 渲染时 | 统计摘要 4 卡片 |
| history | `H.renderTrendBarChart()` | 渲染时 | Chart.js 柱状图 |
| history | `H.renderTrendLineChart()` | 渲染时 | Chart.js 折线图 |
| history | `H.renderRadarChart()` | 查看详情 | Chart.js 雷达图 |
| settings | `S.saveMimoKey()` | 点击保存 | 更新 MiMo API Key |
| settings | `S.saveDeepseekKey()` | 点击保存 | 更新 DeepSeek API Key |
| settings | `S.saveQwenKey()` | 点击保存 | 更新 Qwen API Key |
| settings | `S.switchProvider()` | 下拉选择 | 切换 AI 提供商 |
| settings | `S.toggleTts()` | 开关切换 | 开启/关闭语音播报 |
| settings | `S.updateTtsProviderInfo()` | 提供商切换 | 显示 TTS 状态 |
| settings | `saveQwenModel()` | 点击保存 | 配置 Qwen 推理/对话/判卷模型 |
| favorites | `F.loadList()` | 切换到收藏 Tab | 加载收藏列表 |
| favorites | `F.addFavorite()` | 点击"收藏" | 收藏当前题目 |
| favorites | `F.deleteFavorite(id)` | 点击"取消收藏" | 删除收藏 |
| custom | `C.loadList()` | 切换到自定义 Tab | 加载自定义题目列表 |
| custom | `C.saveQuestion()` | 提交表单 | 创建/更新自定义题目 |
| custom | `C.deleteQuestion(id)` | 点击删除 | 删除自定义题目 |
| feedback | `F.submitFeedback(sid, qIdx, isGood)` | 点击 👍/👎 | 提交评分反馈 |
| feedback | `F.submitFix(sid, qIdx, fixed)` | 点踩后提交 | 提交修正内容 |
| finetune | `FT.loadStats()` | 切换到微调 Tab | 加载训练数据统计 |
| finetune | `FT.loadRecords()` | 点击刷新/过滤 | 加载训练数据列表 |
| auth | `A.checkAuth()` | 页面加载 | 检查登录状态 |
| auth | `A.login(email)` | 提交邮箱 | 发送验证码 |
| auth | `A.verify(email, code)` | 提交验证码 | 验证登录 |
| auth | `A.logout()` | 点击"退出" | 退出登录 |

---

## 面试流程状态机

```
IDLE → STARTING → QUESTION → ANSWERING → EVALUATING → QUESTION (循环) → REPORT
  │                                                                    │
  └────────────────────────────────────────────────────────────────────┘
  (通过 switchTab 回到 setup)
```

- `MockMate.state.interviewActive = true` 时阻止离开（`beforeunload` 事件）
- 结束面试后重置状态
- 倒计时到 0 自动提交当前 textarea 内容
- 草稿实时保存到 localStorage，刷新后可恢复

---

## Chart.js 图表

### 图表类型

| 图表 | Chart.js 类型 | 位置 | 数据来源 |
|------|-------------|------|---------|
| 分数趋势 | `bar` | 历史 Tab 顶部 | sessions 列表的 `overall_score` |
| 分数走势 | `line` | 历史 Tab 顶部 | sessions 按时间排列的分数 |
| 能力雷达 | `radar` | 面试详情页 | report 的 `score_breakdown` |

### 图表管理

- 实例存储在 `MockMate.History._charts` 对象中
- Tab 切换或重新加载时先 `destroy()` 旧实例
- canvas 容器使用 `max-width: 100%`，Chart.js 自动响应式适配

### 图表交互

- 柱状图：点击柱子跳转到对应面试详情
- 柱状图颜色根据分数动态着色（≥7 绿，4-6 黄，<4 红）
- 折线图：显示分数变化趋势
- 雷达图：五维度（技术/逻辑/深度/表达/综合）可视化

---

## 功能特性

### 面试增强

| 功能 | 说明 |
|------|------|
| 进度条 | CSS transition 进度条，颜色随进度变化 |
| 倒计时 | 笔试 90s / 面试 180s，最后 30s 红闪，到时自动提交 |
| 点击计时器可暂停/继续 |
| 草稿保存 | textarea 内容实时存 localStorage，刷新不丢失 |
| 表单记忆 | 岗位/公司/简历内容自动保存和恢复 |
| 报告下载 | 生成格式化 .txt 文件下载 |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` | 提交回答 |
| `Alt+1/2/3/4/5/6/7` | 切换 Tab |
| `Escape` | 关闭 toast / 聚焦回答输入框 |

---

## 新增功能指南

### 添加新的表单字段

1. 在对应 Tab 的 HTML 中添加 `<div class="form-group">`
2. 在相关 JS 模块中通过 `document.getElementById('xxx').value` 取值
3. 在 API 调用中加入新字段

### 添加新的后端 API

1. 在 `backend/main.py` 添加路由
2. 直接使用 `MockMate.API.get/post/delete/upload`（无需修改前端 API 层）
3. 在对应的 JS 模块中调用 `MockMate.API.post('/api/new-endpoint', data)`

### 添加新的 JS 模块

1. 创建 `frontend/js/mymodule.js`
2. 使用 IIFE 模式挂载到 `MockMate` 命名空间
3. 实现 `init()` 方法绑定事件
4. 在 `index.html` 中引入（注意依赖顺序）
5. 在 `app.js` 的 `init()` 中调用模块的 `init()`

### 修改面试题目展示

编辑 `interview.js` 的 `I.showQuestion()` 函数。题目数据格式：

```javascript
{
  question: "题目内容",
  type: "技术/行为/设计",
  difficulty: "easy/medium/hard",
  topic: "考察主题",
  expected_points: ["要点1", "要点2"],
  options: { "A": "选项A", ... },  // 仅笔试
  correct_answer: "A",              // 仅笔试
}
```

---

## 注意事项

- 所有用户输入在渲染前通过 `MockMate.esc()` 转义（XSS 防护）
- `ROUND_NAMES` 常量定义在 `utils.js`，全局唯一，修改无需同步多处
- localStorage 操作通过 `MockMate.Utils.ls` 统一管理（key 自动加 `mockmate_` 前缀）
- Chart.js 需在 JS 模块之前加载（CDN script 放在最前面）
- 避免在全局作用域直接添加变量，统一使用 `MockMate.state` 或模块内部变量
