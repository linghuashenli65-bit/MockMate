# MockMate 前端（Vue 3）

当前版本的前端工程，基于 Vue 3 + Vite，替代旧版原生 JS 前端（`frontend/`，已废弃）。

## 技术栈

- Vue 3（`<script setup>`）+ Vite
- Pinia（状态管理）
- Vue Router（history 模式）
- Chart.js v4 / marked（npm 包引入）
- Vitest + @vue/test-utils（组件测试）

## 开发

```bash
npm install
npm run dev      # 开发服务器 http://localhost:5173（/api 代理到 18633）
npm run build    # 构建到 dist/（由后端 FastAPI 自动托管）
npm test         # vitest 组件测试
```

## 目录结构

```
src/
├── main.js             # 应用入口
├── App.vue             # 布局壳 + 顶部导航
├── router/index.js     # 路由（7 个顶层页面）
├── stores/
│   ├── settings.js     # 用户设置（服务端存储）与登录态
│   └── prep.js         # 面试准备状态（简历/画像/评分/会话）
├── services/
│   ├── api.js          # HTTP 封装
│   └── asr.js          # 实时语音识别引擎（FSM + 噪声门）
├── components/
│   └── FeedbackButtons.vue  # 点赞/点踩 + 修正弹窗
├── views/              # 页面组件
└── assets/main.css     # 全局样式
```

## 页面导航

顶层 7 个 Tab：准备面试 / 拟真面试 / 模拟面试 / 题目收藏 / 自定义题目 / 微调 / 设置。

拟真面试与模拟面试页内各含「开始面试 / 历史记录」子导航，历史记录按面试类型分别展示。

## 测试与诊断脚本

`scripts/` 下提供浏览器端诊断脚本：

- `diag-pages.mjs` — 逐页巡检（登录后访问各路由并断言关键内容）
- `diag-shots.mjs` / `diag-shots-token.mjs` — 页面截图
- `diag-settings.mjs` — 设置页回归（CDP 抓取控制台）
- `diag-history-console.mjs` — 历史页控制台/图表检查
