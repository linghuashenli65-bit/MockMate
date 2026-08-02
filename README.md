# MockMate — AI 面试模拟陪练

基于 FastAPI + Vue 3 多 Agent 协同的拟真 AI 面试平台，支持多面试官切换、实时语音交互与 9 阶段面试流程，内置 5 层安全防护。

---

## 界面预览

**准备面试** — 填写简历、选择面试轮次、生成岗位画像

![准备面试页](images/准备面试页.png)

**岗位画像分析** — AI 搜索岗位招聘要求，生成结构化画像

![岗位画像分析](images/岗位画像分析.png)

**模拟面试** — AI 面试官出题，支持语音、倒计时、提示

![模拟面试页](images/模拟面试页.png)

**历史记录** — 多维度趋势图表、薄弱点分析

![历史记录页](images/历史记录页.png)

**历史记录详情** — 雷达图评分、逐题回顾

![历史记录详情页](images/历史记录详情页.png)

---

## 快速开始

### 安装依赖

```bash
cd MockMate
pip install -r requirements.txt
cd frontend-vue
npm install
npm run build      # 构建前端产物到 frontend-vue/dist
cd ..
```

### 配置 API Key

MockMate 支持四个 AI 提供商（可在网页端运行时切换）：

| 提供商 | 支持能力 | 申请地址 |
|--------|---------|---------|
| **MiMo**（小米） | 推理出题、简历图片识别、语音合成 | [https://100t.xiaomimimo.com](https://100t.xiaomimimo.com) |
| **DeepSeek** | 推理出题、对话（不支持图片和语音） | [https://platform.deepseek.com](https://platform.deepseek.com) |
| **通义千问 (Qwen)** | 推理出题、对话、图片识别（vl）、语音合成（CosyVoice） | [https://help.aliyun.com/zh/model-studio](https://help.aliyun.com/zh/model-studio) |
| **智谱 (Zhipu)** | 推理出题、对话（GLM-4 系列） | [https://open.bigmodel.cn](https://open.bigmodel.cn) |

配置方式（二选一）：

**方式一：环境变量（全局 Key，供匿名/共享模式使用）**

```bash
set MIMO_API_KEY=your_key_here
set DEEPSEEK_API_KEY=your_key_here
set AI_PROVIDER=mimo    # 或 deepseek / qwen / zhipu
```

**方式二：登录后网页配置（推荐，服务端加密存储）**

登录后在「设置」页配置各提供商 API Key。Key 会加密保存在服务端账号下（Fernet 加密，接口只返回掩码），换设备自动同步；模型能力映射（推理/对话/判卷/TTS）默认使用各提供商默认模型，留空即可。

### 启动

```bash
python run.py    # 后端（自动托管 frontend-vue/dist）
```

浏览器打开 http://127.0.0.1:18633

> **HTTPS 支持**：启动后会自动生成自签名 SSL 证书，局域网其他设备可通过 `https://<LAN-IP>:18633` 访问并使用麦克风（首次访问需信任自签名证书）。

> **前端开发模式**：`cd frontend-vue && npm run dev` 启动 Vite 开发服务器（5173 端口，自动代理 `/api` 到后端）。

---

## 架构

```
┌──────────────┐      ┌─────────────────────────────────────┐      ┌────────────┐
│ 浏览器 (SPA)  │─────▶│           FastAPI 服务               │─────▶│  MiMo API  │
│  Vue 3 + Vite│      │                                     │      │  DeepSeek  │
└──────────────┘      │  路由层 / 拟真面试引擎 / 用户设置      │      │  Qwen API  │
   │                  │  安全层 (InputGuard → OutputGuard)   │      │  Zhipu API │
   │                  └─────────────────────────────────────┘      └────────────┘
   └───── frontend-vue/dist（构建产物，由 FastAPI 静态托管）
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **前端入口** | `frontend-vue/` | Vue 3 + Vite SPA，Pinia 状态、Vue Router 路由 |
| **前端服务层** | `frontend-vue/src/services/api.js` | HTTP 封装（JWT + 设置请求头） |
| **ASR 引擎** | `frontend-vue/src/services/asr.js` | 实时语音识别（FSM + 自适应噪声门，复用语音识别页/拟真面试） |
| **面试准备** | `frontend-vue/src/views/SetupView.vue` | 简历上传解析、岗位画像、简历评分、开始面试 |
| **模拟面试** | `frontend-vue/src/views/InterviewView.vue` | 传统面试全流程 + 内嵌历史记录子页 |
| **拟真面试** | `frontend-vue/src/views/MockInterviewView.vue` | 多面试官 WebSocket 流式面试 + 内嵌拟真历史子页 |
| **Web 服务** | `backend/main.py` | FastAPI 应用、路由注册、前端静态托管（SPA 回退） |
| **AI 客户端** | `backend/ai_client.py` | 统一接口，四提供商自动路由和 fallback |
| **用户设置** | `backend/settings_crypto.py` + `backend/database.py` | API Key 加密存储、模型配置、TTS 开关（/api/settings） |
| **拟真面试引擎** | `backend/mock_interview/mock_engine.py` | 流式出题、评估、报告（含评分持久化） |
| **拟真面试路由** | `backend/mock_interview/api_router.py` | 会话生命周期、WebSocket 流式消息 |
| **安全层** | `backend/mock_interview/security.py` | 5 层安全防护（注入检测、输出扫描、状态校验等） |
| **数据持久化** | `backend/database.py` | MySQL / JSON 双模式，用户设置、会话、收藏等 |
| **训练数据** | `backend/finetune/` | 数据采集、LoRA 微调脚本（开发中） |

---

## 安全架构

```
InputGuard → OutputGuard → StateVerifier → MemoryGuard
    │             │             │              │
 注入检测       泄漏扫描      状态机校验      记忆污染
```

拟真面试系统内置 5 层安全防护，覆盖 8 种攻击类型：

| 安全层 | 职责 | 防护目标 |
|--------|------|---------|
| **InputGuard** | 用户输入注入检测 | Prompt 注入、越狱、角色逃逸、权限提升 |
| **Prompt Isolation** | 系统提示与用户数据隔离 | 数据污染、交叉会话干扰 |
| **OutputGuard** | AI 输出关键词扫描 | 系统提示泄漏、敏感信息泄露 |
| **StateVerifier** | 状态机转移校验 | 越权操作、状态异常跳转 |
| **MemoryGuard** | 上下文记忆污染检测 | 长期记忆投毒、历史篡改 |

核心原则：

1. **LLM 只负责生成语言**，不负责任何系统控制决策
2. **用户输入永远不能直接影响系统控制逻辑**
3. **多层防御**，不依赖单层 Prompt 安全
4. 所有安全事件记录详细日志，支持审计追踪

---

## API 文档

所有接口前缀 `/api`，请求/响应均为 JSON。

### 基础

#### `GET /api/status`
服务状态和配置信息（匿名可访问，展示全局或当前用户配置的提供商就绪状态）。

```json
{
  "status": "ok",
  "provider": "mimo",
  "mimo_ready": false,
  "deepseek_ready": false,
  "qwen_ready": false,
  "zhipu_ready": false,
  "db": "mysql",
  "cache": { "total": 0, "valid": 0, "expired": 0 }
}
```

#### `GET /api/settings` / `PUT /api/settings`（需登录）
获取/更新当前用户的 AI 设置（服务端加密存储）。

- `GET` 返回 `{ provider, keys(掩码), configured, models, tts_enabled }`
- `PUT` 部分更新：`{ provider?, keys?: {mimo?: "新key" | ""}, models?, tts_enabled? }`，Key 空串表示清除

#### `POST /api/config`（兼容旧版）
切换 AI 提供商（仅 provider 字段）。

### 简历

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/resume/parse` | 上传简历文件解析（JPG/PNG/PDF/DOCX/MD） |
| POST | `/api/resume/analyze` | AI 分析简历文本，提取技能/经验/项目 |
| POST | `/api/resume/score` | 简历匹配度评分（需先生成岗位画像） |

### 岗位研究

#### `POST /api/research`
全网搜索目标岗位的招聘要求和面经，生成结构化岗位画像。结果缓存 90 天。

支持 `company` 字段（目标公司定向查询）：

```json
{ "position": "Python后端开发", "company": "字节跳动", "refresh": false }
```

指定公司时追加公司维度搜索（招聘 JD / 薪资待遇 / 官网招聘 / 面经），画像额外输出 `hiring_status`（招聘状态）、`salary_range`（薪酬范围）、`company_insights`（公司洞察）、`sources`（参考来源）；缓存按「岗位@公司」隔离。未查到该公司专属信息时如实降级为市场概况，不编造。

### 传统面试

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/interview/start` | 开始面试（支持笔试/技术一面/技术二面/综合面/自定义） |
| POST | `/api/interview/answer` | 提交回答，返回评分和下一题 |
| POST | `/api/interview/end` | 结束面试，生成总结报告 |
| POST | `/api/interview/hint` | 获取解题提示 |
| GET | `/api/interview/session/{session_id}` | 获取会话详情（含报告与问答） |

### 拟真面试（多面试官）

#### 面试官管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | `/api/mock/interviewers` | 创建 / 列出面试官角色 |
| GET/PUT/DELETE | `/api/mock/interviewers/{id}` | 查看 / 更新 / 删除面试官 |

#### 面试会话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/mock/interview/start` | 创建拟真面试会话（持久化空壳记录） |
| POST | `/api/mock/interview/end/{session_id}` | 结束并持久化报告（含逐题评分与问答） |
| GET | `/api/mock/interview/state/{session_id}` | 获取当前会话状态 |
| GET | `/api/mock/interview/report/{session_id}` | 获取报告（内存引擎优先，服务重启后回退数据库） |
| GET | `/api/mock/interview/history` | 拟真面试历史列表（带均分/覆盖度） |
| WS | `/api/mock/interview/ws/{session_id}` | WebSocket 流式出题/音频/评估 |

WebSocket 消息（服务端 → 客户端）：

| 类型 | 说明 |
|------|------|
| `question_token` | 流式题目文本 |
| `audio_chunk` / `audio_done` | 流式音频 |
| `switch_interviewer` | 面试官切换（先于音频到达） |
| `evaluation` / `eval_token` | 评估结果 |
| `end` | 面试结束 |

### 题目收藏 / 自定义题目

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | `/api/favorites` | 收藏 / 列出题目（分页 + 搜索） |
| DELETE | `/api/favorites/{id}` | 取消收藏 |
| POST/GET | `/api/custom/questions` | 创建 / 列出自定义题目 |
| PUT/DELETE | `/api/custom/questions/{id}` | 更新 / 删除自定义题目 |

### 历史记录 / 缓存

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history` | 列出当前用户面试记录（普通面试；拟真记录 type=mock） |
| DELETE | `/api/history/{session_id}` | 删除记录 |
| GET | `/api/audio/{filename}` | 获取语音文件（WAV） |
| GET | `/api/cache/stats` | 缓存统计 |
| POST | `/api/cache/clear` | 清空缓存 |

### 训练数据 / 反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/training/data` | 训练数据列表（按类型/质量/来源过滤） |
| GET | `/api/training/stats` | 训练数据统计 |
| POST | `/api/feedback/submit` | 点赞/点踩 + 评分修正反馈 |

---

## 项目结构

```
MockMate/
├── run.py                      # 启动入口
├── requirements.txt            # Python 依赖
├── mockmate.sql                # MySQL 建表脚本
├── CHANGELOG.md                # 版本变更日志
├── README.md                   # 本文件
├── frontend-vue/               # ★ 前端工程（Vue 3 + Vite）
│   ├── index.html              # SPA 入口
│   ├── vite.config.js          # Vite 配置（dev 代理 /api）
│   ├── package.json
│   ├── scripts/                # 浏览器诊断脚本（截图/巡检/回归）
│   └── src/
│       ├── main.js             # 应用入口
│       ├── App.vue             # 布局壳 + 导航
│       ├── router/index.js     # 路由（7 个页面）
│       ├── stores/             # Pinia（settings / prep）
│       ├── services/           # api / asr
│       ├── components/         # FeedbackButtons 等
│       ├── views/              # 9 个页面组件
│       └── assets/main.css     # 全局样式
├── frontend/                   # 旧版原生 JS 前端（已废弃，保留作参考）
├── backend/
│   ├── main.py                 # FastAPI 服务 + 前端托管
│   ├── ai_client.py            # 统一 AI 客户端
│   ├── settings_crypto.py      # API Key 加密/掩码
│   ├── database.py             # MySQL / JSON 持久化
│   ├── mock_interview/         # 拟真面试引擎 / 状态 / 路由 / 安全
│   ├── finetune/               # 训练数据采集 + LoRA 微调脚本
│   └── data/                   # 运行时数据（会话/音频/日志）
└── models/                     # LoRA 微调产物（未提交）
```

---

## 拟真面试流程

### 9 阶段面试流程

```
面试开始
  └─▶ intro（破冰与自我介绍）
  └─▶ resume（简历细节确认）
  └─▶ general_tech（技术广度考察）
  └─▶ deep_dive（技术深度挖掘）
  └─▶ project（项目经验拷问，STAR 法则）
  └─▶ pressure（场景压力测试）
  └─▶ hr（HR 综合素质面）
  └─▶ qna（候选人反问环节）
  └─▶ end（面试收尾）
```

### 质量驱动的阶段推进

不再使用固定题数阈值，而是根据多维信号动态决策：综合评分（≥75 分）、回答长度（≥150 字）、时间压力（>70%）、面试官追问深度等。支持追问深度抵抗（`follow_up_depth` ≥0.6 且评分 <70 时推迟推进）。

### 面试官路由评分

每道题后系统根据阶段匹配权重 + 追问加成 + 短回答加成 + 时间压力 + 随机扰动选择下一位面试官。

### 评分维度

普通面试以 5 维度评分（技术/逻辑/深度/表达/综合，各轮次权重不同）；拟真面试以逐题 0-100 评分，报告按面试官聚合均分并展示考察覆盖度。

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_API_KEY` / `DEEPSEEK_API_KEY` / `QWEN_API_KEY` / `ZHIPU_API_KEY` | 空 | 各提供商全局 API Key |
| `AI_PROVIDER` | `mimo` | 默认 AI 提供商 |
| `ALLOW_SHARED_API_KEY` | `false` | 未配置 Key 的用户是否回退使用全局 Key |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | 127.0.0.1:3306 | MySQL 连接（不可用时回退 JSON 文件） |
| `SECRET_KEY` | 开发默认值 | JWT 签名 + API Key 加密派生 |
| `SMTP_USER` / `SMTP_PASSWORD` | 空 | 邮箱验证码发送 |

### 模型配置

各提供商能力模型默认值定义在 `backend/config.py`，登录用户可在「设置 → 高级模型配置」覆盖（推理/对话/判卷/TTS）。

### 服务配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `18633` | 监听端口 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Vite |
| 前端状态/路由 | Pinia + Vue Router |
| 图表 | Chart.js v4（npm 包） |
| Markdown | marked（npm 包） |
| 后端框架 | FastAPI + uvicorn |
| AI 推理 | MiMo / DeepSeek / 通义千问 / 智谱 |
| 语音 | WebSocket 流式 ASR + CosyVoice TTS |
| 数据存储 | MySQL / JSON 双模式 |
| 安全 | 5 层防御体系（注入/泄漏/状态/记忆） |

---

## 开发指南

### 前端开发（Vue 3）

```bash
cd frontend-vue
npm install
npm run dev      # 开发服务器 http://localhost:5173（代理 /api）
npm run build    # 构建到 dist（后端自动托管）
npm test         # vitest 组件测试
```

- 页面组件在 `src/views/`，路由在 `src/router/index.js`，导航在 `App.vue`
- 全局状态用 Pinia（`src/stores/`），接口调用统一走 `src/services/api.js`
- 实时语音识别复用 `src/services/asr.js`（状态机 + 噪声门）
- `scripts/` 下有浏览器端诊断脚本（截图/逐页巡检/回归），修改 UI 后可复跑

### 添加新的 AI 提供商

1. 在 `backend/` 新建客户端类，参照 `qwen_client.py` 的模式
2. 实现 `reason()` / `chat_standard()` / `written_eval()` 等方法
3. 在 `config.py` 添加配置项
4. 在 `ai_client.py` 注册客户端和 fallback 逻辑

### 日志

日志同时输出到控制台和 `backend/data/mockmate.log`，格式：`HH:MM:SS [LEVEL] module: message`。
