# Backend — 开发文档

## 目录结构

```
backend/
├── main.py              # FastAPI 主服务，路由注册
├── ai_client.py         # 统一 AI 客户端接口（双提供商路由）
├── mimoclient.py        # MiMo API 封装
├── deepseek_client.py   # DeepSeek API 封装
├── interview_engine.py  # 面试引擎（Prompt 编排 + 输出解析）
├── web_research.py      # 岗位信息搜索 + 画像生成
├── tts.py               # 语音合成
├── report.py            # 报告生成
├── database.py          # 数据持久化（MySQL / JSON 回退）
├── cache.py             # 岗位画像缓存
├── config.py            # 环境变量和常量
└── data/                # 运行时数据
    ├── sessions/        # 面试会话 JSON
    ├── audios/          # 语音 MP3
    └── mockmate.log     # 运行日志
```

## 核心模块说明

### 1. AI 客户端体系 (`ai_client.py`)

统一接口，屏蔽 MiMo / DeepSeek 差异：

```
AIClient
  ├── .reason(messages)    → 推理/对话（主入口）
  ├── .extract_text_from_image(bytes) → OCR（仅 MiMo）
  ├── .text_to_speech(text) → TTS（仅 MiMo）
  └── 自动 fallback：主提供商失败 → 切换到另一个
```

**添加新提供商**：在 `config.py` 加配置项 → 新建客户端类（实现 `reason()`）→ 在 `ai_client.py` 注册。

### 2. 面试引擎 (`interview_engine.py`)

基于 Prompt 编排，核心方法链：

```
start_interview()
  └── generate_first_question(resume, profile, round)
       └── _build_opening_prompt() → AI → _parse_question()

submit_answer()
  ├── evaluate_answer(question, answer, context)
  │    └── _build_evaluation_prompt() → AI → _parse_evaluation()
  └── generate_next_question(history, resume, profile, round)
       └── _build_next_prompt() → AI → _parse_question()

end_interview()
  └── end_interview(history, profile)
       └── _build_report_prompt() → AI → _parse_report()
```

#### 轮次系统 (`ROUND_CONFIG`)

| Key | 名称 | 难度曲线 | Prompt 侧重 |
|-----|------|---------|-------------|
| `written` | 笔试 | Easy→Medium | 标准答案题、选择题、填空题 |
| `tech_1` | 技术一面 | Easy→Medium | 项目经验、技术基础 |
| `tech_2` | 技术二面 | Medium→Hard | 系统设计、架构、原理深度 |
| `comprehensive` | 综合面 | Easy→Hard | 行为面试、综合素质、职业规划 |

默认轮次：`tech_1`。前端不传轮次时使用此值。

#### 出题策略

- 第 1 题：Easy，热身
- 第 2-3 题：Medium，难度爬坡
- 第 4+ 题：视得分动态调整
  - 上一题 ≥ 7 分 → 加深难度
  - 上一题 4-6 分 → 保持当前，换方向
  - 上一题 < 4 分 → 降低难度

#### AI 输出格式

所有 Prompt 要求 AI 输出严格 JSON，引擎通过 `_parse_*()` 方法解析：

- `_parse_question()` — JSON → `{question, type, difficulty, topic, expected_points}`
- `_parse_evaluation()` — JSON → `{technical_score, logic_score, depth_score, communication_score, overall_score, summary, strengths, improvements, reference_answer}`
- `_parse_report()` — JSON → `{total_questions, overall_score, score_breakdown, strengths, weaknesses, final_verdict, ...}`

解析失败时自动降级（正则提取 → 文本框提取 → 默认值）。

### 3. Web Research (`web_research.py`)

并行多引擎搜索策略：

```
search_position(position)
  ├── 任务 1: DuckDuckGo 搜索招聘要求
  ├── 任务 2: DuckDuckGo 搜索面经
  ├── 任务 3: Bing 搜索（备选）
  └── AI 整合 → 结构化岗位画像
```

失败降级：搜索全部失败 → 使用 AI 自身知识。

### 4. 数据持久化 (`database.py`)

双模式存储：

- **MySQL 模式**：通过 aiomysql 连接，自动建表
- **JSON 回退模式**：MySQL 不可用时使用 `data/sessions/` 目录下的 JSON 文件

#### Sessions 表结构

```sql
CREATE TABLE sessions (
    id              VARCHAR(12) PRIMARY KEY,
    position        VARCHAR(255),
    company         VARCHAR(255),
    round           VARCHAR(20) DEFAULT '',
    resume          LONGTEXT,
    profile         JSON,
    history         JSON,
    report          JSON,
    current_question JSON,
    current_index   INT DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

#### Research Cache 表结构

```sql
CREATE TABLE research_cache (
    position    VARCHAR(255) PRIMARY KEY,
    data        JSON,
    summary     VARCHAR(500),
    skill_count INT,
    topic_count INT,
    expires_at  DATETIME,
    cached_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## API 路由

路由都在 `main.py` 中，按功能分组：

| 分组 | 路由 | 方法 |
|------|------|------|
| 基础 | `/api/status`, `/api/config` | GET, POST |
| 简历 | `/api/resume/parse`, `/api/resume/analyze` | POST |
| 岗位研究 | `/api/research`, `/api/cache/*`, `/api/search/history` | POST, GET |
| 面试 | `/api/interview/start`, `/api/interview/answer`, `/api/interview/end`, `/api/interview/session/{id}` | POST, GET |
| 语音 | `/api/audio/{filename}` | GET |
| 历史 | `/api/history`, `/api/history/{id}` | GET, DELETE |

## 配置

### 环境变量（`.env`）

```env
MIMO_API_KEY=        # 小米 MiMo API Key
DEEPSEEK_API_KEY=    # DeepSeek API Key
AI_PROVIDER=mimo     # 默认提供商
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=mockmate
```

### `config.py` 常量

| 常量 | 默认值 | 说明 |
|------|--------|------|
| HOST | 127.0.0.1 | 监听地址 |
| PORT | 18633 | 监听端口 |
| MIMO_API_BASE | https://api.mimo.xiaomi.com/v1 | MiMo API 地址 |
| DEEPSEEK_API_BASE | https://api.deepseek.com/v1 | DeepSeek API 地址 |
| CACHE_TTL_DAYS | 90 | 岗位画像缓存天数 |

## 错误处理

- API 错误统一返回 `{"detail": "错误描述"}` + HTTP 状态码
- AI 调用失败自动 fallback 到另一个提供商
- AI 输出解析失败使用默认降级值（不会中断流程）
- JSON 文件写入失败记录 warning 日志，不影响主流程

## 日志

```python
# 格式
HH:MM:SS [LEVEL] module: message

# 日志文件
backend/data/mockmate.log
```

日志级别：INFO（控制台 + 文件），通过 `logging.getLogger(name)` 获取 logger。
