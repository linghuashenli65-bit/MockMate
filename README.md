# MockMate — AI 面试模拟陪练

一款基于 FastAPI 的 AI 面试模拟工具。输入简历和目标岗位，AI 面试官出题、评分、生成报告，支持语音问答、断点续面、自定义题目、题目收藏等。

---

## 快速开始

### 安装依赖

```bash
cd MockMate
pip install -r requirements.txt
```

### 配置 API Key

MockMate 支持两个 AI 提供商：

| 提供商 | 支持能力 | 申请地址 |
|--------|---------|---------|
| **MiMo**（小米） | 推理出题、简历图片识别、语音合成 | [https://100t.xiaomimimo.com](https://100t.xiaomimimo.com) |
| **DeepSeek** | 推理出题、对话（不支持图片和语音） | [https://platform.deepseek.com](https://platform.deepseek.com) |

配置方式（二选一）：

**方式一：环境变量**
```bash
set MIMO_API_KEY=your_key_here
set DEEPSEEK_API_KEY=your_key_here
set AI_PROVIDER=mimo    # 或 deepseek
```

**方式二：启动后网页配置**
启动服务后，在浏览器打开设置页面，填入 API Key 并保存。

### 启动

```bash
start.bat        # Windows 双击 或
python run.py    # 直接运行
```

浏览器打开 http://127.0.0.1:18633

---

## 架构

```
┌─────────┐     ┌─────────────────────────────────────┐     ┌───────────┐
│ 浏览器   │────▶│           FastAPI 服务               │────▶│  MiMo API │
│ (SPA)   │     │                                     │     │  DeepSeek │
└─────────┘     │  ┌─────────┐  ┌──────────────────┐  │     └───────────┘
                │  │ 路由层   │─▶│  面试引擎         │  │
                │  │ main.py │  │  interview_engine │  │
                │  └─────────┘  └──────────────────┘  │
                │       │               │             │
                │       ▼               ▼             │
                │  ┌─────────┐  ┌──────────────────┐  │
                │  │ 网页搜索  │  │  统一 AI 客户端   │  │
                │  │web_resea│  │  ai_client        │──│──▶ HTTP API
                │  │ rch.py  │  │  ┌─────┐ ┌──────┐│  │
                │  └─────────┘  │  │MiMo │ │Deep  ││  │
                │       │       │  │Cli  │ │Seek  ││  │
                │       ▼       │  └─────┘ └──────┘│  │
                │  ┌─────────┐  └──────────────────┘  │
                │  │ 数据库    │       │               │
                │  │database │       ▼               │
                │  │ .py     │  ┌──────────────────┐  │
                │  └─────────┘  │  语音合成 TTS     │  │
                │               │  tts.py           │  │
                │               └──────────────────┘  │
                └─────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **入口** | `run.py` | 启动入口 |
| **Web 服务** | `backend/main.py` | FastAPI 应用，路由注册，全局实例管理 |
| **AI 客户端** | `backend/ai_client.py` | 统一接口，双提供商自动路由和 fallback |
| **MiMo 客户端** | `backend/mimoclient.py` | 小米 MiMo API 封装（推理、多模态、TTS） |
| **DeepSeek 客户端** | `backend/deepseek_client.py` | DeepSeek API 封装（推理、对话） |
| **面试引擎** | `backend/interview_engine.py` | 出题、评分、报告生成的 Prompt 编排 |
| **网页搜索** | `backend/web_research.py` | 多引擎并行搜索 + AI 整合成岗位画像 |
| **语音合成** | `backend/tts.py` | 文字转语音 MP3 |
| **数据持久化** | `backend/database.py` | MySQL / JSON 文件双模式存储（会话、缓存、搜索历史） |
| **配置** | `backend/config.py` | 环境变量和常量配置 |
| **前端** | `frontend/` | 模块化 SPA（7 个 JS 模块 + 独立 CSS） |

---

## API 文档

所有接口前缀 `/api`，请求/响应均为 JSON。

### 基础

#### `GET /api/status`
服务状态和配置信息。

```json
{
  "status": "ok",
  "provider": "mimo",
  "mimo_ready": false,
  "deepseek_ready": false,
  "db": "json",
  "cache": { "total": 0, "valid": 0, "expired": 0 }
}
```

#### `POST /api/config`
更新 API Key 或切换提供商。

```json
// 请求
{ "mimo_api_key": "sk-xxx", "deepseek_api_key": "sk-xxx", "provider": "deepseek" }
// 响应
{ "message": "配置已更新" }
```

### 简历

#### `POST /api/resume/parse`
上传简历文件进行解析。

- Content-Type: `multipart/form-data`
- 支持: JPG / PNG / PDF / DOCX / MD
- JPG/PNG 需要 MiMo API Key（多模态能力）

```json
// 响应
{ "text": "识别出的文字内容...", "source": "ocr" }
```

#### `POST /api/resume/analyze`
AI 分析简历文本，提取技能、经验、项目。

```json
// 请求
{ "text": "简历内容..." }
// 响应
{ "skills": ["Python", "FastAPI"], "experience_years": "3年", "projects": [...], "strengths": [...], "weaknesses": [...] }
```

### 岗位研究

#### `POST /api/research`
全网搜索目标岗位的招聘要求和面经，生成结构化岗位画像。结果缓存 90 天。

```json
// 请求
{ "position": "Python后端开发 3年经验" }
// 响应（关键字段）
{
  "position": "Python后端开发",
  "summary": "岗位概述...",
  "required_skills": ["Python", "FastAPI/Django", "MySQL", "Redis"],
  "nice_to_have": ["Docker", "K8s", "消息队列"],
  "tech_stack": ["Python", "FastAPI", "MySQL", "Redis", "Docker"],
  "common_interview_topics": ["...（5-8个常见面试题）"],
  "interview_focus": ["...（3-5个考察重点）"],
  "difficulty": "mid",
  "years_experience": "1-3年"
}
```

### 面试流程

#### `POST /api/interview/start`
开始一场新面试，AI 基于简历和岗位画像生成第一道题。支持选择面试轮次，不同轮次出题风格不同。

| 轮次 | 值 | 说明 |
|------|-----|------|
| 技术一面 | `tech_1` | 项目经验 + 技术基础深入 |
| 技术二面 | `tech_2` | 系统设计 + 架构 + 深度原理 |
| 综合面 | `comprehensive` | 综合素质 + 行为面试 + 职业规划 |
| 笔试 | `written` | 选择题 + 判断题，AI 自动判卷解析 |
| 自定义练习 | `custom` | 使用自定义题目进行练习（需传入 `custom_question_ids`）|

```json
// 请求（普通模式）
{ "resume": "简历内容...", "position": "Python后端开发", "company": "字节跳动", "profile": {}, "round": "tech_1" }
// 请求（自定义题目模式）
{ "resume": "...", "position": "...", "round": "tech_1", "custom_question_ids": [1, 2, 3] }
// 响应
{
  "session_id": "a1b2c3d4e5f6",
  "question": { "question": "题目内容", "type": "技术", "difficulty": "medium", "topic": "项目经验", "expected_points": [...] },
  "question_index": 0,
  "round": "tech_1",
  "audio_url": "/api/audio/a1b2c3d4e5f6_q000.mp3"
}
```

#### `POST /api/interview/answer`
提交回答，获取评分和下一题。

```json
// 请求
{ "session_id": "a1b2c3d4e5f6", "question_index": 0, "answer": "我的回答..." }
// 响应
{
  "evaluation": {
    "technical_score": 8, "technical_comment": "...",
    "logic_score": 7, "logic_comment": "...",
    "depth_score": 6, "depth_comment": "...",
    "communication_score": 8, "communication_comment": "...",
    "overall_score": 7.3,
    "summary": "综合评价...",
    "strengths": ["优点1", "优点2"],
    "improvements": ["建议1", "建议2"],
    "reference_answer": "参考回答要点"
  },
  "next_question": { "question": "下一题...", ... },
  "next_index": 1,
  "audio_url": "/api/audio/a1b2c3d4e5f6_q001.mp3"
}
```

#### `POST /api/interview/end`
结束面试，生成总结报告。

```json
// 请求
{ "session_id": "a1b2c3d4e5f6" }
// 响应
{
  "report": {
    "total_questions": 5,
    "overall_score": 7.2,
    "score_breakdown": { "technical": 7.5, "logic": 7.0, "depth": 6.8, "communication": 7.5 },
    "strengths": ["...", "..."],
    "weaknesses": ["...", "..."],
    "skill_summary": "技能掌握情况总结",
    "preparation_advice": ["复习建议1", "建议2", "建议3"],
    "recommended_positions": ["适合的岗位"],
    "final_verdict": "最终评价"
  },
  "history": [
    { "q": "第一题", "a": "回答", "score": {...}, "type": "技术", "topic": "..." }
  ],
  "round": "tech_1"
}
```

#### `POST /api/interview/hint`
获取当前面试题的解题思路提示（非答案）。使用提示后评估会适当降分。

```json
// 请求
{ "session_id": "a1b2c3d4e5f6", "question_index": 2 }
// 响应
{ "hint": "1. 考察要点：… 2. 思考方向：… 3. 切入点：…" }
```

#### `GET /api/interview/session/{session_id}`
查询历史面试会话详情。返回字段包含 `round` 表示该场面试的轮次。

### 题目收藏

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/favorites` | 收藏题目 |
| GET | `/api/favorites` | 列出所有收藏 |
| DELETE | `/api/favorites/{id}` | 取消收藏 |

```json
// POST /api/favorites
{ "session_id": "...", "question": "题目", "type": "技术", "difficulty": "medium", "topic": "...", "user_answer": "...", "overall_score": 8 }
```

### 自定义题目

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/custom/questions` | 创建题目 |
| GET | `/api/custom/questions` | 列出所有题目 |
| GET | `/api/custom/questions/{id}` | 获取单题 |
| PUT | `/api/custom/questions/{id}` | 更新题目 |
| DELETE | `/api/custom/questions/{id}` | 删除题目 |

### 历史记录 / 缓存

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/audio/{filename}` | 获取语音文件（MP3） |
| GET | `/api/history` | 列出所有面试记录（含各维度分数、薄弱点） |
| DELETE | `/api/history/{session_id}` | 删除指定记录 |
| GET | `/api/cache/stats` | 缓存统计 |
| POST | `/api/cache/clear` | 清空缓存 |
| GET | `/api/search/history` | 搜索历史记录 |

---

## 项目结构

```
MockMate/
├── run.py                      # 启动入口
├── start.bat                   # Windows 启动脚本
├── requirements.txt            # Python 依赖
├── mockmate.sql                # MySQL 建表脚本
├── README.md                   # 本文件
├── .env / .env.example         # 环境配置
├── frontend/
│   ├── index.html              # HTML 骨架
│   ├── README.md               # 前端开发文档
│   ├── css/
│   │   └── style.css           # 全部样式（主题、组件、动画、响应式）
│   └── js/
│       ├── app.js              # 主入口（Tab 切换、快捷键、表单记忆）
│       ├── api.js              # API 请求封装
│       ├── utils.js            # 工具函数 & 常量
│       ├── interview.js        # 面试全流程（出题、答题、评分、报告、断点续面、跳过/暂挂、语音输入）
│       ├── research.js         # 岗位画像搜索
│       ├── history.js          # 历史记录 + Chart.js 图表（多维度趋势、薄弱点分析）
│       ├── favorites.js        # 题目收藏管理
│       ├── custom.js           # 自定义题目 CRUD
│       └── settings.js         # API Key 配置
└── backend/
    ├── __init__.py
    ├── config.py               # 配置（API Key、端口、模型名称）
    ├── main.py                 # FastAPI 服务主程序
    ├── ai_client.py            # 统一 AI 客户端接口
    ├── mimoclient.py           # MiMo API 客户端（异步）
    ├── deepseek_client.py      # DeepSeek API 客户端（异步）
    ├── interview_engine.py     # 面试引擎（出题、评分、报告）
    ├── web_research.py         # 网络搜索 + 岗位画像生成
    ├── tts.py                  # 语音合成
    ├── database.py             # 数据持久化（MySQL / JSON 回退）
    └── data/                   # 运行时数据（自动创建）
        ├── sessions/           # 面试会话 JSON
        ├── audios/             # 语音 MP3 文件
        └── mockmate.log        # 运行日志
```

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_API_KEY` | 空 | 小米 MiMo API Key |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key |
| `AI_PROVIDER` | `mimo` | 默认 AI 提供商 |

### 服务配置 (`backend/config.py`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `18633` | 监听端口 |

### API 超时

| 客户端 | 超时 | 连接池 |
|--------|------|--------|
| MiMo API | 120s | max 10 连接 |
| DeepSeek API | 120s | max 10 连接 |
| 网页搜索 | 15s/请求 | max 10 连接 |

---

## 面试流程

```
用户输入简历 + 目标岗位
        │
        ▼
  ┌─────────────┐
  │ 岗位画像生成  │──▶ 多引擎并行搜索招聘信息+面经
  │ (可选)       │──▶ AI 整合成结构化画像
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │ 开始面试     │──▶ AI 基于简历+画像出第一题
  │             │──▶ 可选生成语音
  └─────────────┘
        │
        ▼
  ┌─────────────┐      ┌─────────────┐
  │ 用户回答     │─────▶│ AI 评分     │──▶ 五维度评分 + 参考回答
  └─────────────┘      └─────────────┘
        │                      │
        ▼                      ▼
  ┌─────────────┐      ┌─────────────┐
  │ AI 出下一题  │◀─────│ 根据评分     │──▶ 评分高→深入追问
  └─────────────┘      │ 动态决策     │──▶ 评分低→换方向
        │              └─────────────┘
        ▼
  ┌─────────────┐
  │ 结束面试     │──▶ 生成总结报告
  │             │──▶ 技能评估 + 复习建议
  └─────────────┘
```

### 评分维度

| 维度 | 范围 | 说明 |
|------|------|------|
| 技术分 | 1-10 | 技术准确性和深度 |
| 逻辑分 | 1-10 | 表达逻辑和结构化 |
| 深度分 | 1-10 | 对项目理解的深度 |
| 表达分 | 1-10 | 沟通表达清晰度 |
| 综合分 | 1-10 | 加权平均 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + uvicorn |
| AI 推理 | MiMo API / DeepSeek API |
| 网页搜索 | Bing + DuckDuckGo（自动 fallback）|
| 图片识别 | MiMo 多模态 API |
| 语音合成 | MiMo TTS |
| 数据存储 | MySQL / JSON 文件双模式 |
| 前端 | 原生 JS SPA（9 模块化文件 + Chart.js 图表） |
| 图表库 | Chart.js v4（CDN 引入） |
| 语音识别 | Web Speech API（Chrome 浏览器语音输入） |
| 依赖管理 | pip + requirements.txt |

---

## 开发指南

### 添加新的 AI 提供商

1. 在 `backend/` 下新建客户端类，参考 `mimoclient.py` 的模式
2. 实现 `reason()`、`chat_standard()`、`written_eval()` 方法
3. 在 `config.py` 添加配置项
4. 在 `ai_client.py` 注册新客户端和 fallback 逻辑

### 修改面试 Prompt

编辑 `backend/interview_engine.py` 中 `_build_*_prompt()` 方法。Prompt 设计要点：
- 每道题要求 AI 输出 JSON 格式，便于解析
- 出题包含 `question/type/difficulty/topic/expected_points`
- 评分包含 5 个维度的分数 + 评语 + 参考回答

### 前端开发

前端是模块化 SPA，所有文件在 `frontend/` 目录：
- `index.html` — HTML 骨架，引入 CSS 和 JS
- `css/style.css` — 全部样式（CSS 变量控制主题）
- `js/app.js` — 主入口，通过 `MockMate.init()` 启动
- 所有模块挂在 `window.MockMate` 命名空间下

各 JS 模块职责和 API 详见 `frontend/README.md`。

### 添加新的前端 Tab 页面

1. 在 `index.html` 添加 `.tab` 按钮 + `.tab-content` 容器
2. 新建对应的 JS 模块文件
3. 在 `index.html` 中按依赖顺序引入
4. 在模块的 `init()` 方法中绑定事件
5. `switchTab()` 自动处理 Tab 切换

### 日志

日志同时输出到控制台和 `backend/data/mockmate.log`，格式：
```
HH:MM:SS [LEVEL] module: message
```
