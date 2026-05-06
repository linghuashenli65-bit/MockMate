"""面试引擎

核心功能：
1. 根据简历+岗位画像生成面试题
2. 评估用户回答（多维度评分）
3. 动态决策：追问/换题/升级难度
"""
import json
import logging
import re
from typing import Optional

from .ai_client import AIClient

logger = logging.getLogger(__name__)

# 面试轮次配置
# 每个轮次有独特的面试官角色定位和考察方向，确保轮次间有明显区分度
ROUND_CONFIG = {
    "written": {
        "name": "笔试",
        "desc": "理论基础与知识广度 · 客观题",
        "prompt_extra": """## 【笔试规则 — 必须严格遵守】
你是**笔试考官**，只考核候选人的**理论基础与知识广度**。所有题目必须是**客观题**，有明确的标准答案。

### 严禁出以下题型
- 简答题、论述题、填空题、代码编写题
- 需要主观判断、系统设计、架构讨论的题目
- 行为面试题、软技能题

### 题型要求
- **选择题**：必须提供 4 个选项（A/B/C/D），仅一个正确
- **判断题**：必须提供 2 个选项（"A. 正确" / "B. 错误"）

### 内容要求
- 考察**核心理论基础**：数据结构、网络协议、数据库原理、编程语言特性、操作系统基础
- 重视**原理理解**而非表面术语（如问"为什么"而非"是什么"）
- 干扰项需有迷惑性但可明确判断对错
- 结合岗位画像中的 required_skills 和 tech_stack 出题
- 前几题 easy（基础概念），后面逐渐 medium（应用级理解）

### 输出约束
- 必须包含 correct_answer 和 explanation 字段
- explanation 用 2-3 句话解释为什么正确选项对、错误选项错在哪
- 只输出 JSON，不要额外文字""",
    },
    "tech_1": {
        "name": "技术一面",
        "desc": "工程实践 · 编码能力 · 项目深挖",
        "prompt_extra": """## 【技术一面规则】
你是团队中的**资深工程师（Staff Engineer）**，正在面试一位未来的同事。你的目标是**评估候选人的工程实践能力和代码质量意识**——能不能独立交付高质量、可维护的代码。

### 考察重点（按优先级）
1. **编码与工程实践**：代码质量、可维护性、错误处理、边界情况意识
2. **项目经验深挖**：候选人在项目中具体做了什么、技术选型理由、遇到的坑和解决方案
3. **调试与问题排查**：给出现场场景，看候选人如何分析和定位问题
4. **API 设计与数据库**：接口设计是否合理、SQL 查询优化、数据建模

### 面试风格
- 以**场景题和追问**为主，贴近实际开发工作的日常
- 可以出**代码审查题**（如给一段有问题的代码让候选人 review）
- 可以出**调试题**（如"线上出现 XX 异常，你怎么排查？"）
- **严禁出**大规模系统设计题（留给技术二面）、底层源码分析题
- 难度递进：easy → medium，可到 medium-hard

### 示例问题
- "请 review 这段代码，指出潜在的问题和改进空间"
- "这个接口在高并发下会有什么问题？你会怎么优化？"
- "你的项目中用了 Redis 缓存，能具体说说缓存和数据库的一致性是怎么保证的吗？"
- "如果这个 SQL 查询很慢，你的排查思路是什么？"

只输出 JSON，不要额外文字""",
    },
    "tech_2": {
        "name": "技术二面",
        "desc": "架构设计 · 技术深度 · 权衡决策",
        "prompt_extra": """## 【技术二面规则】
你是团队**架构师 / 技术总监**，正在评估候选人的**架构视野和技术深度**。你要看的是候选人能否设计可扩展的系统、能否做出合理的技术权衡。

### 考察重点（按优先级）
1. **系统设计能力**：面对开放性问题，如何拆分功能、设计数据模型、定义接口
2. **架构思维**：可扩展性、高可用、容错、性能规划、成本意识
3. **技术深度**：底层原理理解、高级特性、异常场景处理、并发控制
4. **技术选型与权衡**：多个方案时如何 Trade-off，能否清晰阐述取舍理由

### 面试风格
- 以**设计题**为主：如"设计一个实时评论系统""短链接服务""秒杀系统"
- 当候选人提到某个组件时，追问其**底层实现原理**
- **挑战候选人的设计决策**，看能否 defend 自己的方案
- **严禁出**基础编码题、简单 API 设计题、行为面试题
- 全程 medium 到 hard，第 1 题即可上中等难度

### 考察维度
- 系统设计：功能拆解 → 数据模型 → 接口契约 → 扩展与容错方案
- 技术深度：源码级理解、性能调优、异常处理、分布式理论
- 架构决策：一致性 vs 可用性、同步 vs 异步、SQL vs NoSQL、垂直 vs 水平扩展

只输出 JSON，不要额外文字""",
    },
    "comprehensive": {
        "name": "综合面",
        "desc": "领导力 · 成长思维 · 跨团队协作",
        "prompt_extra": """## 【综合面规则】
你是**工程副总裁 / HR 负责人**，这是最后一轮面试。**不考察技术细节**，你要评估的是候选人的**综合素质与发展潜力**——这个人能不能在团队中发挥更大影响力。

### 考察重点（按优先级）
1. **领导力与影响力**：有没有推动过跨团队协作、技术决策的落地
2. **冲突解决**：遇到分歧时如何处理、如何说服他人
3. **成长思维**：如何学习新技术、如何从失败中复盘成长
4. **沟通表达**：思路是否清晰、有层次、有逻辑
5. **职业规划**：对未来的规划、技术视野、自我认知

### 面试风格
- 全程**行为面试题（STAR 法则）**，不出任何技术题
  - Situation: 当时的情况是什么
  - Task: 你的任务是什么
  - Action: 你具体采取了什么行动
  - Result: 结果如何
- 多问"你以前具体怎么做的"，而不是"理论上怎么做"
- 适当追问具体细节以验证真实性（公司、角色、量化结果）
- 难度保持 medium，不需要 hard

### 经典问题示例
- "请分享一个你遇到过的最有挑战的项目，你是如何推动团队达成目标的？（STAR）"
- "你和同事/产品经理产生严重意见分歧时，你是怎么处理的？"
- "你过去一年最大的成长是什么？是什么促使了这种成长？"
- "如果让你带领一个新人团队交付一个紧急项目，你会怎么做？"
- "你对未来 3-5 年的职业发展有什么规划？为什么？"

只输出 JSON，不要额外文字""",
    },
}

DEFAULT_ROUND = "tech_1"


# ==================== 备选笔试题库（按岗位分类，AI 出题失败时兜底）====================

_FALLBACK_GENERAL = [
    {"question": "在软件开发中，下列哪种设计模式属于创建型模式？", "type": "选择题", "difficulty": "easy", "topic": "设计模式", "options": {"A": "工厂模式", "B": "观察者模式", "C": "装饰器模式", "D": "策略模式"}, "correct_answer": "A", "explanation": "工厂模式属于创建型模式，用于封装对象的创建过程。观察者、装饰器、策略都属于行为型或结构型模式。"},
    {"question": "HTTP 状态码 404 表示什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "服务器内部错误", "B": "资源未找到", "C": "重定向", "D": "请求超时"}, "correct_answer": "B", "explanation": "404 Not Found 表示服务器无法找到请求的资源。500 为服务器错误，301/302 为重定向，408 为请求超时。"},
    {"question": "以下哪种数据结构是先进后出（LIFO）的？", "type": "选择题", "difficulty": "easy", "topic": "数据结构", "options": {"A": "队列", "B": "栈", "C": "链表", "D": "数组"}, "correct_answer": "B", "explanation": "栈（Stack）是典型的 LIFO 结构，只允许在一端进行插入和删除。队列是 FIFO。"},
    {"question": "关系型数据库中的主键（Primary Key）的主要作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "加快查询速度", "B": "唯一标识一条记录", "C": "建立索引", "D": "保证数据安全性"}, "correct_answer": "B", "explanation": "主键的核心作用是唯一标识表中的每一行记录。自动创建索引加快查询只是副作用。"},
    {"question": "Git 中 git clone 和 git pull 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "版本控制", "options": {"A": "clone 是复制仓库，pull 是更新代码", "B": "两者完全一样", "C": "clone 比 pull 更快", "D": "pull 用于创建新分支"}, "correct_answer": "A", "explanation": "clone 是从远程复制一个完整的仓库到本地，pull 是拉取远程更新并合并到当前分支。"},
    {"question": "面向对象编程中，封装（Encapsulation）的主要目的是什么？", "type": "选择题", "difficulty": "easy", "topic": "编程基础", "options": {"A": "加快程序运行速度", "B": "隐藏内部实现细节，保护数据", "C": "减少代码行数", "D": "实现跨平台兼容"}, "correct_answer": "B", "explanation": "封装通过将数据和操作数据的方法绑定在一起，隐藏对象的内部状态和实现细节，保护数据不被外部随意修改。"},
    {"question": "下列哪个是关系型数据库管理系统？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "MongoDB", "B": "MySQL", "C": "Redis", "D": "Elasticsearch"}, "correct_answer": "B", "explanation": "MySQL 是关系型数据库。MongoDB 是文档数据库，Redis 是键值存储，Elasticsearch 是搜索引擎。"},
    {"question": "TCP 和 UDP 的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "TCP 需要连接，UDP 不需要", "B": "UDP 比 TCP 更安全", "C": "TCP 不支持重传", "D": "两者没有区别"}, "correct_answer": "A", "explanation": "TCP 是面向连接的可靠传输协议（三次握手、重传机制），UDP 是无连接的不可靠传输协议，但延迟更低。"},
]

_FALLBACK_BACKEND = [
    {"question": "在 Python 中，列表（list）和元组（tuple）的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Python基础", "options": {"A": "列表可变，元组不可变", "B": "列表不可变，元组可变", "C": "两者没有区别", "D": "列表只能存储数字"}, "correct_answer": "A", "explanation": "列表创建后可以增删改元素，是可变的；元组创建后不可修改，是不可变的。这是两者最核心的区别。"},
    {"question": "RESTful API 中，获取用户信息的 HTTP 方法是什么？", "type": "选择题", "difficulty": "easy", "topic": "API设计", "options": {"A": "POST", "B": "GET", "C": "PUT", "D": "DELETE"}, "correct_answer": "B", "explanation": "GET 用于获取资源。POST 用于创建，PUT 用于更新，DELETE 用于删除。这是 RESTful 风格的标准约定。"},
    {"question": "MySQL 中哪个关键字用于筛选分组后的结果？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "WHERE", "B": "HAVING", "C": "ORDER BY", "D": "LIMIT"}, "correct_answer": "B", "explanation": "HAVING 用于对 GROUP BY 分组后的结果进行筛选。WHERE 在分组前筛选，ORDER BY 用于排序，LIMIT 用于限制行数。"},
    {"question": "Python 中的装饰器（Decorator）本质上是什么？", "type": "选择题", "difficulty": "medium", "topic": "Python进阶", "options": {"A": "一种类", "B": "一个接受函数并返回新函数的高阶函数", "C": "一种设计模式相关的类", "D": "一种特殊的数据结构"}, "correct_answer": "B", "explanation": "Python 装饰器本质上是高阶函数，它接受一个函数作为参数，并返回一个新的函数来扩展原函数的功能。"},
    {"question": "Redis 中哪种数据结构适合实现消息队列？", "type": "选择题", "difficulty": "medium", "topic": "缓存与队列", "options": {"A": "String", "B": "Set", "C": "List", "D": "Hash"}, "correct_answer": "C", "explanation": "List 支持 LPUSH/RPOP 操作，可以实现先进先出的消息队列。也可以使用 Stream 类型实现更完善的消息队列。"},
    {"question": "在 Docker 中，Dockerfile 的 ENTRYPOINT 和 CMD 指令有什么区别？", "type": "选择题", "difficulty": "medium", "topic": "容器化", "options": {"A": "没有区别", "B": "ENTRYPOINT 可被子容器覆盖，CMD 不可", "C": "CMD 可被 docker run 命令行覆盖，ENTRYPOINT 需要 --entrypoint", "D": "CMD 用于设置环境变量"}, "correct_answer": "C", "explanation": "CMD 设置的默认命令可以被 docker run 后面的命令覆盖，而 ENTRYPOINT 定义的命令不会被覆盖，需要用 --entrypoint 显式指定。"},
    {"question": "数据库事务的 ACID 特性中，I 代表什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "一致性（Consistency）", "B": "隔离性（Isolation）", "C": "持久性（Durability）", "D": "原子性（Atomicity）"}, "correct_answer": "B", "explanation": "ACID: Atomicity(原子性)、Consistency(一致性)、Isolation(隔离性)、Durability(持久性)。I 代表隔离性。"},
    {"question": "Python 中 __init__.py 文件的主要作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "Python基础", "options": {"A": "初始化数据库连接", "B": "将一个目录标记为 Python 包", "C": "定义全局变量", "D": "管理项目依赖"}, "correct_answer": "B", "explanation": "__init__.py 的作用是将一个目录标记为 Python 包（package），使得该目录中的模块可以被 import 导入。"},
]

_FALLBACK_FRONTEND = [
    {"question": "在 CSS 中，Flexbox 中用于设置主轴方向的属性是什么？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": "align-items", "B": "justify-content", "C": "flex-direction", "D": "flex-wrap"}, "correct_answer": "C", "explanation": "flex-direction 用于设置主轴方向（row/column）。justify-content 沿主轴对齐，align-items 沿交叉轴对齐，flex-wrap 控制是否换行。"},
    {"question": "JavaScript 中，let 和 const 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "JavaScript", "options": {"A": "let 可重新赋值，const 不可", "B": "两者完全一样", "C": "const 可重新赋值，let 不可", "D": "let 只能在循环中使用"}, "correct_answer": "A", "explanation": "let 声明的变量可以重新赋值，const 声明的是常量，一旦赋值不能修改（但对象属性可变）。"},
    {"question": "React 中，用于管理组件状态的 Hook 是哪一个？", "type": "选择题", "difficulty": "easy", "topic": "React", "options": {"A": "useEffect", "B": "useState", "C": "useContext", "D": "useMemo"}, "correct_answer": "B", "explanation": "useState 用于在函数组件中管理局部状态。useEffect 处理副作用，useContext 读取上下文，useMemo 缓存计算结果。"},
    {"question": "Vue 中的 v-model 指令实现了什么？", "type": "选择题", "difficulty": "easy", "topic": "Vue", "options": {"A": "条件渲染", "B": "双向数据绑定", "C": "列表渲染", "D": "事件监听"}, "correct_answer": "B", "explanation": "v-model 是 Vue 的双向数据绑定指令，用户输入变化自动更新数据，数据变化自动更新视图。"},
    {"question": "浏览器中，localStorage 和 sessionStorage 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "浏览器API", "options": {"A": "localStorage 容量更大", "B": "sessionStorage 关闭标签页后清除，localStorage 持久存储", "C": "完全没有区别", "D": "sessionStorage 只能在 HTTPS 下使用"}, "correct_answer": "B", "explanation": "sessionStorage 数据在页面会话结束时（关闭标签页）清除，localStorage 数据永久保存直到手动删除。"},
    {"question": "CSS 盒模型中，padding 位于哪个区域？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": "内容（content）和边框（border）之间", "B": "边框（border）之外", "C": "内容（content）内部", "D": "与 margin 相同"}, "correct_answer": "A", "explanation": "CSS 盒模型从内到外为：content → padding → border → margin。padding 在内容和边框之间。"},
    {"question": "在 TypeScript 中，interface 和 type 的主要区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "TypeScript", "options": {"A": "没有区别", "B": "interface 可以被合并（声明合并），type 不可以", "C": "type 更强大", "D": "interface 不能继承"}, "correct_answer": "B", "explanation": "interface 支持声明合并（同名 interface 自动合并），type 则不支持。两者在其他方面的能力基本相同。"},
    {"question": "前端构建工具 Webpack 和 Vite 的核心区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "构建工具", "options": {"A": "Vite 基于原生 ES Module 做开发时热更新，Webpack 需要打包", "B": "Webpack 比 Vite 快很多", "C": "Vite 不支持 TypeScript", "D": "两者完全一样"}, "correct_answer": "A", "explanation": "Vite 开发时利用浏览器原生 ES Module 实现极快的热更新，无需打包；Webpack 需要先打包再提供开发服务。"},
]

_FALLBACK_AI_DATA = [
    {"question": "机器学习的三种主要类型是什么？", "type": "选择题", "difficulty": "easy", "topic": "机器学习", "options": {"A": "监督学习、无监督学习、强化学习", "B": "深度学习、浅层学习、中等学习", "C": "分类、回归、排序", "D": "训练、验证、测试"}, "correct_answer": "A", "explanation": "机器学习三大范式：监督学习（有标签）、无监督学习（无标签）、强化学习（通过奖励信号学习）。"},
    {"question": "在深度学习中，激活函数 ReLU 的输出范围是什么？", "type": "选择题", "difficulty": "easy", "topic": "深度学习", "options": {"A": "(-∞, +∞)", "B": "[0, +∞)", "C": "[0, 1]", "D": "[-1, 1]"}, "correct_answer": "B", "explanation": "ReLU（Rectified Linear Unit）公式为 f(x)=max(0,x)，输入小于0输出0，输入大于0输出x本身。"},
    {"question": "RAG（检索增强生成）系统中，Embedding 模型的主要作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "AI基础概念", "options": {"A": "将用户提问直接翻译成SQL查询", "B": "将文本转换为向量表示，用于语义检索", "C": "对检索到的文档进行摘要生成", "D": "控制大模型回答的格式与长度"}, "correct_answer": "B", "explanation": "Embedding 模型将文本映射为稠密向量，语义相近的文本向量距离也近，从而实现语义检索而非关键词匹配。"},
    {"question": "神经网络中，过拟合（Overfitting）的常见解决方案不包括哪个？", "type": "选择题", "difficulty": "medium", "topic": "机器学习", "options": {"A": "增加 Dropout 层", "B": "增加训练数据量", "C": "增加模型层数使其更复杂", "D": "使用 L1/L2 正则化"}, "correct_answer": "C", "explanation": "增加模型复杂度会加剧过拟合。解决过拟合的方法包括：Dropout、数据增强、正则化（L1/L2）、早停（Early Stopping）、减少模型复杂度。"},
    {"question": "在大模型训练中，LoRA（Low-Rank Adaptation）的核心思想是什么？", "type": "选择题", "difficulty": "medium", "topic": "大模型微调", "options": {"A": "重新训练整个模型", "B": "在预训练权重旁增加低秩矩阵来适配新任务", "C": "直接修改预训练权重", "D": "增加更多的 GP"}, "correct_answer": "B", "explanation": "LoRA 在冻结原始权重的基础上，通过低秩分解矩阵来学习任务特定的增量，大幅减少微调参数量。"},
    {"question": "自然语言处理中，Transformer 模型的核心机制是什么？", "type": "选择题", "difficulty": "medium", "topic": "NLP", "options": {"A": "循环神经网络（RNN）", "B": "自注意力机制（Self-Attention）", "C": "卷积操作（Convolution）", "D": "决策树"}, "correct_answer": "B", "explanation": "Transformer 的核心是 Self-Attention 机制，通过计算序列中每个词与其他词的关系来捕捉上下文信息。"},
    {"question": "数据预处理中，归一化（Normalization）的主要目的是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据处理", "options": {"A": "增加数据量", "B": "消除量纲差异，使不同特征在相同尺度上", "C": "增加模型复杂度", "D": "减少训练时间"}, "correct_answer": "B", "explanation": "归一化将不同量纲的特征缩放到统一范围（如0-1），避免梯度下降时某些特征主导更新方向。"},
    {"question": "SQL 中，用于连接两个表的 JOIN 类型不包括哪个？", "type": "选择题", "difficulty": "easy", "topic": "数据处理", "options": {"A": "INNER JOIN", "B": "LEFT JOIN", "C": "MERGE JOIN", "D": "RIGHT JOIN"}, "correct_answer": "C", "explanation": "标准 SQL JOIN 类型包括 INNER/LEFT/RIGHT/FULL OUTER/CROSS JOIN。MERGE JOIN 不是 SQL JOIN 类型，它是数据库引擎的一种连接算法。"},
]

_FALLBACK_DEVOPS = [
    {"question": "Docker 中，将容器端口映射到宿主机的命令参数是什么？", "type": "选择题", "difficulty": "easy", "topic": "Docker", "options": {"A": "-v", "B": "-p", "C": "-e", "D": "-m"}, "correct_answer": "B", "explanation": "-p（publish）用于端口映射，如 -p 8080:80。-v 挂载卷，-e 设置环境变量，-m 限制内存。"},
    {"question": "Kubernetes 中，Pod 的最小单位是什么？", "type": "选择题", "difficulty": "easy", "topic": "K8s", "options": {"A": "Container", "B": "Pod 本身是最小调度单位", "C": "Node", "D": "Service"}, "correct_answer": "B", "explanation": "Pod 是 Kubernetes 的最小调度和部署单位，一个 Pod 可以包含一个或多个容器。"},
    {"question": "在 Linux 中，哪个命令用于查看系统实时进程状态？", "type": "选择题", "difficulty": "easy", "topic": "Linux", "options": {"A": "ls", "B": "top", "C": "df", "D": "cat"}, "correct_answer": "B", "explanation": "top 实时显示系统进程和资源使用情况。ls 列出文件，df 查看磁盘，cat 查看文件内容。"},
    {"question": "CI/CD 中，CI 的全称是什么？", "type": "选择题", "difficulty": "easy", "topic": "DevOps", "options": {"A": "Code Integration", "B": "Continuous Integration", "C": "Cloud Infrastructure", "D": "Container Image"}, "correct_answer": "B", "explanation": "CI 是持续集成（Continuous Integration），CD 是持续交付/部署（Continuous Delivery/Deployment）。"},
    {"question": "Linux 中 chmod 755 表示什么权限？", "type": "选择题", "difficulty": "medium", "topic": "Linux", "options": {"A": "所有者读写执行，组和其他用户读执行", "B": "所有人完全控制", "C": "只读权限", "D": "所有者只读，组可读写"}, "correct_answer": "A", "explanation": "755 = rwxr-xr-x。所有者(7=rwx)可以读写执行，组(5=r-x)和其他用户(5=r-x)只能读和执行。"},
    {"question": "Nginx 作为反向代理的主要优势是什么？", "type": "选择题", "difficulty": "medium", "topic": "Web服务器", "options": {"A": "只能处理静态文件", "B": "负载均衡、SSL终结、缓存加速", "C": "比 Apache 功能少", "D": "只能用于 Windows"}, "correct_answer": "B", "explanation": "Nginx 作为反向代理可以：负载均衡、SSL/TLS 终结、静态文件加速、缓存、限流、WebSocket 代理等。"},
    {"question": "Git 中，git rebase 和 git merge 的主要区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "版本控制", "options": {"A": "rebase 产生线性历史，merge 保留分支结构", "B": "两者完全一样", "C": "merge 更快", "D": "rebase 更安全"}, "correct_answer": "A", "explanation": "rebase 将当前分支的提交应用到目标分支顶端，产生线性提交历史。merge 创建一个合并提交，保留分支拓扑。"},
    {"question": "监控系统中，Prometheus 的主要数据模型是？", "type": "选择题", "difficulty": "medium", "topic": "监控", "options": {"A": "关系型表", "B": "时序数据（Time Series）", "C": "文档型数据", "D": "图数据"}, "correct_answer": "B", "explanation": "Prometheus 以时序数据为核心模型，每条数据由 metric name + labels + timestamp + value 组成。"},
]

_FALLBACK_TESTING = [
    {"question": "软件测试中，单元测试（Unit Test）的测试对象是什么？", "type": "选择题", "difficulty": "easy", "topic": "测试基础", "options": {"A": "整个系统", "B": "最小的代码单元（函数/方法）", "C": "数据库", "D": "用户界面"}, "correct_answer": "B", "explanation": "单元测试针对最小的可测试代码单元（通常是一个函数或方法）进行，验证其行为是否符合预期。"},
    {"question": "黑盒测试和灰盒测试的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "测试方法论", "options": {"A": "黑盒不了解内部结构，灰盒部分了解", "B": "两者完全一样", "C": "灰盒不知道内部结构", "D": "黑盒更全面"}, "correct_answer": "A", "explanation": "黑盒测试不关注内部实现，只关注输入输出；灰盒测试介于白盒和黑盒之间，对内部结构有部分了解。"},
    {"question": "Selenium 主要用于什么类型的测试？", "type": "选择题", "difficulty": "easy", "topic": "自动化测试", "options": {"A": "单元测试", "B": "Web UI 自动化测试", "C": "性能测试", "D": "API 测试"}, "correct_answer": "B", "explanation": "Selenium 是 Web 浏览器自动化工具，主要用于 Web UI 自动化测试，支持多种浏览器和编程语言。"},
    {"question": "在 Python 测试中，pytest 的 fixture 功能用于什么？", "type": "选择题", "difficulty": "medium", "topic": "测试工具", "options": {"A": "生成测试报告", "B": "准备测试前置条件（如数据库连接、测试数据）", "C": "测量代码覆盖率", "D": "性能分析"}, "correct_answer": "B", "explanation": "pytest fixture 用于设置测试前置条件和清理工作，如创建数据库连接、准备测试数据，并在测试结束后自动清理。"},
    {"question": "什么是回归测试（Regression Testing）？", "type": "选择题", "difficulty": "easy", "topic": "测试基础", "options": {"A": "验证新代码修改没有破坏已有功能", "B": "第一次测试新功能", "C": "性能测试", "D": "用户验收测试"}, "correct_answer": "A", "explanation": "回归测试确保新的代码修改（如新增功能、Bug修复）不会对已有功能产生意外影响，通常通过重跑已有测试用例来验证。"},
    {"question": "API 测试中，HTTP 状态码 201 通常表示什么？", "type": "选择题", "difficulty": "easy", "topic": "API测试", "options": {"A": "请求成功", "B": "资源已创建", "C": "未授权", "D": "服务器错误"}, "correct_answer": "B", "explanation": "201 Created 表示请求成功并且服务器创建了新资源。200 是一般成功，401 是未授权，500 是服务器错误。"},
    {"question": "测试用例设计中，边界值分析法（Boundary Value Analysis）关注什么？", "type": "选择题", "difficulty": "medium", "topic": "测试用例设计", "options": {"A": "函数内部的实现细节", "B": "输入范围的边界值（最小值、最大值、接近边界的值）", "C": "用户界面美观度", "D": "代码注释质量"}, "correct_answer": "B", "explanation": "边界值分析关注输入域的边界，因为边界附近往往最容易出现 Bug。通常测试最小值、最大值、min±1、max±1 等。"},
    {"question": "测试金字塔中，最底层（数量最多）的测试类型是什么？", "type": "选择题", "difficulty": "easy", "topic": "测试策略", "options": {"A": "E2E 端到端测试", "B": "集成测试", "C": "单元测试", "D": "手工测试"}, "correct_answer": "C", "explanation": "测试金字塔从底到顶：单元测试（最多、最快）→ 集成测试 → E2E端到端测试（最少、最慢）。底层测试成本低、反馈快。"},
]


class InterviewEngine:
    """面试引擎，管理面试流程和 AI 交互"""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client

    async def generate_first_question(
        self, resume: str, profile: dict,
        round_name: str = DEFAULT_ROUND, question_type: str = "mixed",
    ) -> dict:
        """生成第一道面试题"""
        if round_name == "written":
            prompt = self._build_opening_prompt_written(resume, profile)
            result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        else:
            prompt = self._build_opening_prompt(resume, profile, round_name, question_type)
            result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        return self._parse_question(result, 1, round_name, profile)

    async def generate_next_question(
        self, history: list[dict], resume: str, profile: dict,
        round_name: str = DEFAULT_ROUND,
    ) -> dict:
        """根据对话历史生成下一题"""
        if round_name == "written":
            prompt = self._build_next_prompt_written(history, resume, profile)
            result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        else:
            prompt = self._build_next_prompt(history, resume, profile, round_name)
            result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        question_num = len(history) + 1
        return self._parse_question(result, question_num, round_name, profile)

    async def evaluate_answer(self, question: str, answer: str, context: dict, round_name: str = "", question_data: dict = None) -> dict:
        """评估用户的回答，根据轮次使用差异化的评估标准"""
        if round_name == "written":
            return self._evaluate_written_direct(answer, question_data or {})

        # 根据轮次选择对应的评估提示词
        if round_name == "tech_1":
            prompt = self._build_evaluation_prompt_tech_1(question, answer, context)
        elif round_name == "tech_2":
            prompt = self._build_evaluation_prompt_tech_2(question, answer, context)
        elif round_name == "comprehensive":
            prompt = self._build_evaluation_prompt_comprehensive(question, answer, context)
        else:
            prompt = self._build_evaluation_prompt(question, answer, context)

        result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        return self._parse_evaluation(result)

    async def generate_hint(self, question: str, q_type: str, q_topic: str) -> str:
        """为面试题生成解题思路提示"""
        prompt = f"""你是一名面试辅导专家。请为以下面试题提供解题思路提示。

要求：
- 只给思考方向和要点，不要直接给出完整答案
- 提示应包含：考察点分析、思考框架、可能的切入点
- 保持简洁，3-5 个要点

题目类型：{q_type}
题目主题：{q_topic}
题目：{question}

提示："""
        result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=512)
        return result.strip()

    async def end_interview(self, history: list[dict], profile: dict, round_name: str = "") -> dict:
        """结束面试，生成总结报告（根据轮次调整评价侧重点）"""
        prompt = self._build_report_prompt(history, profile, round_name)
        result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=2048)
        return self._parse_report(result, history)

    # ==================== Prompt 构建 ====================

    def _get_round_config(self, round_name: str) -> dict:
        """获取轮次配置，未知轮次默认返回 tech_1"""
        return ROUND_CONFIG.get(round_name, ROUND_CONFIG[DEFAULT_ROUND])

    def _build_opening_prompt(self, resume: str, profile: dict, round_name: str, qtype: str) -> str:
        rc = self._get_round_config(round_name)
        profile_str = json.dumps(profile, ensure_ascii=False, indent=2)
        return f"""你是一个专业的面试官，正在进行{rc['name']}（{rc['desc']}）。这是第 1 题。

== 目标岗位画像（核心考察依据）==
{profile_str}

== 候选人简历（参考项目背景）==
{resume[:2000]}

{rc['prompt_extra']}

难度要求（第1题必须简单热身）：
- 第1题：easy
- 从岗位画像中的 required_skills 和 tech_stack 选择考察范围
- 结合候选人简历中的项目经验找到切入点
- 优先覆盖目标岗位的核心技能，而非简历中提到的所有技能

岗位核心技能：{', '.join(profile.get('required_skills', []))}
核心技术栈：{', '.join(profile.get('tech_stack', []))}

只输出 JSON:
{{"question": "题目", "type": "技术/行为/设计", "difficulty": "easy", "topic": "考察主题", "expected_points": ["要点1", "要点2"]}}"""

    def _build_opening_prompt_written(self, resume: str, profile: dict) -> str:
        rc = self._get_round_config("written")
        profile_str = json.dumps(profile, ensure_ascii=False, indent=2)
        return f"""你是一个专业的笔试考官，正在出{rc['name']}。这是第 1 题。

== 目标岗位画像（核心考察依据）==
{profile_str}

== 候选人简历（参考项目背景）==
{resume[:2000]}

{rc['prompt_extra']}

难度要求：第1题必须简单热身，考察基础概念。

绝对不要出简答题、论述题、填空题或任何需要用户手动输入文字的题目！
每道题必须包含 options 字段，选择题必须有 4 个选项（A/B/C/D），判断题必须有 2 个选项（A. 正确 / B. 错误）。

【重要】correct_answer 是你确认正确的选项字母。explanation 是解析（2-3句话）。这两个字段是判卷的唯一依据，必须准确无误！

只输出 JSON:
{{"question": "题目", "type": "选择题/判断题", "difficulty": "easy", "topic": "考察主题", "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}}, "correct_answer": "正确选项字母", "explanation": "解析（2-3句话，解释为什么正确）"}}"""

    def _build_next_prompt(self, history: list[dict], resume: str, profile: dict, round_name: str) -> str:
        rc = self._get_round_config(round_name)
        history_str = ""
        for i, h in enumerate(history, 1):
            score_str = json.dumps(h.get("score", {}), ensure_ascii=False)
            history_str += f"\n第{i}题: {h['q']}\n回答: {h['a'][:500]}\n评分: {score_str}\n"

        current_q = len(history) + 1

        # 根据题号决定难度
        if current_q <= 2:
            expected_difficulty = "easy 或 medium"
            difficulty_hint = "保持基础难度，如果上一题答得好可以稍微加深"
        elif current_q <= 4:
            expected_difficulty = "medium"
            difficulty_hint = "中等难度场景题"
        elif current_q <= 6:
            expected_difficulty = "medium 或 hard"
            difficulty_hint = "较深的技术原理题"
        else:
            expected_difficulty = "hard"
            difficulty_hint = "综合性设计题或开放性问题"

        return f"""你是一个专业的面试官，正在进行{rc['name']}（{rc['desc']}）。这是第 {current_q} 题。

== 岗位画像（核心考察依据）==
{json.dumps(profile, ensure_ascii=False, indent=2)[:1000]}

== 候选人简历（参考项目背景）==
{resume[:1500]}

== 面试历史 ==
{history_str}

{rc['prompt_extra']}

难度要求：{expected_difficulty}
说明：{difficulty_hint}

动态调整：
- 上一题得分 ≥ 7 → 加深难度
- 上一题得分 4-6 → 保持当前，换方向
- 上一题得分 < 4 → 降低难度
- 不要连续问同一个 topic

注意：以岗位画像中的 required_skills / tech_stack / common_interview_topics 为核心考察，简历只作参考背景

只输出 JSON:
{{"question": "题目", "type": "技术/行为/设计", "difficulty": "easy/medium/hard", "topic": "考察主题", "expected_points": ["要点1", "要点2"], "reason": "为什么出这题"}}"""

    def _build_next_prompt_written(self, history: list[dict], resume: str, profile: dict) -> str:
        rc = self._get_round_config("written")
        history_str = ""
        for i, h in enumerate(history, 1):
            score_str = json.dumps(h.get("score", {}), ensure_ascii=False)
            history_str += f"\n第{i}题: {h['q']}\n用户答案: {h['a'][:200]}\n评分: {score_str}\n"

        current_q = len(history) + 1

        if current_q <= 2:
            expected_difficulty = "easy"
            difficulty_hint = "基础题"
        elif current_q <= 4:
            expected_difficulty = "easy 或 medium"
            difficulty_hint = "过渡到中等难度"
        elif current_q <= 6:
            expected_difficulty = "medium"
            difficulty_hint = "中等难度"
        else:
            expected_difficulty = "medium 或 hard"
            difficulty_hint = "较难题目"

        return f"""你是一个专业的笔试考官，正在出{rc['name']}。这是第 {current_q} 题。

== 岗位画像（核心考察依据）==
{json.dumps(profile, ensure_ascii=False, indent=2)[:1000]}

== 候选人简历（参考项目背景）==
{resume[:1500]}

== 笔试历史 ==
{history_str}

{rc['prompt_extra']}

难度要求：{expected_difficulty}（{difficulty_hint}）

动态调整：
- 上一题正确 → 加深难度
- 上一题错误 → 换知识点，保持或降低难度
- 不要连续考同一个 topic

注意：以岗位画像中的 required_skills 和 tech_stack 为核心考察范围

绝对不要出简答题、论述题、填空题或任何需要用户手动输入文字的题目！
每道题必须包含 options 字段，选择题必须有 4 个选项（A/B/C/D），判断题必须有 2 个选项（A. 正确 / B. 错误）。

【重要】correct_answer 必须是题目客观正确的答案。你必须仔细确认正确选项后再填写，绝对不能随意填写！这是判卷的唯一依据，填错会导致误判。

只输出 JSON:
{{"question": "题目", "type": "选择题/判断题", "difficulty": "easy/medium/hard", "topic": "考察主题", "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}}, "correct_answer": "正确选项字母", "explanation": "解析（2-3句话，解释为什么正确）"}}"""

    def _evaluate_written_direct(self, user_answer: str, question_data: dict) -> dict:
        """直接比对答案，不走 AI"""
        correct = question_data.get("correct_answer", "").strip().upper()
        user = user_answer.strip().upper()
        is_correct = (user == correct)

        return {
            "correct": is_correct,
            "correct_answer": correct,
            "explanation": question_data.get("explanation", ""),
            "score": 10 if is_correct else 0,
        }

    def _build_evaluation_prompt(self, question: str, answer: str, context: dict) -> str:
        hint_note = ""
        if context.get("hint_used"):
            hint_note = "\n注意：候选人在回答此题前使用了提示，说明独立思考能力不足，各项评分应适当降低。"
        return f"""你是一名资深面试官，请评估候选人的回答并输出 JSON。

面试题: {question}

回答: {answer[:2000]}

岗位信息: {json.dumps(context.get("profile", {}), ensure_ascii=False)[:500]}

{hint_note}
评分标准（10 分制，请充分利用 1-10 全范围）：
- 10 分：完美回答，超出预期
- 8-9 分：很好的回答，略有瑕疵
- 6-7 分：合格回答，有提升空间
- 4-5 分：基本回答，明显不足
- 1-3 分：较差回答

只输出 JSON：
{{"technical_score": 10, "technical_comment": "评价", "logic_score": 10, "logic_comment": "评价", "depth_score": 10, "depth_comment": "评价", "communication_score": 10, "communication_comment": "评价", "overall_score": 10, "summary": "综合评价", "strengths": ["优点"], "improvements": ["建议"], "reference_answer": "参考回答"}}"""

    def _build_evaluation_prompt_tech_1(self, question: str, answer: str, context: dict) -> str:
        """技术一面评估：侧重工程实践、代码质量、调试能力"""
        hint_note = ""
        if context.get("hint_used"):
            hint_note = "\n注意：候选人在回答此题前使用了提示，说明独立思考能力不足，各项评分应适当降低。"
        return f"""你是一名资深技术面试官（高级工程师），请从**工程实践能力**角度评估候选人的回答。

## 评估维度权重（按重要性排序）
1. **技术能力（权重 40%）** — 技术方案是否合理、工程判断是否准确、是否考虑到边界情况和错误处理
2. **逻辑思维（权重 30%）** — 分析问题的思路是否清晰、排查是否有条理
3. **深度（权重 15%）** — 是否主动考虑了性能、安全、可维护性等非功能需求
4. **沟通表达（权重 15%）** — 能否清晰地解释技术方案

面试题: {question}

回答: {answer[:2000]}

岗位信息: {json.dumps(context.get("profile", {}), ensure_ascii=False)[:500]}

{hint_note}
评分标准（10 分制，请充分利用 1-10 全范围）：
- 10 分：完美回答，代码级思考超出预期
- 8-9 分：很好的回答，工程意识强
- 6-7 分：合格回答，有基本工程判断
- 4-5 分：基本回答，有明显不足
- 1-3 分：较差回答

只输出 JSON：
{{"technical_score": 10, "technical_comment": "评价", "logic_score": 10, "logic_comment": "评价", "depth_score": 10, "depth_comment": "评价", "communication_score": 10, "communication_comment": "评价", "overall_score": 10, "summary": "综合评价（突出工程实践能力表现）", "strengths": ["优点"], "improvements": ["建议"], "reference_answer": "参考回答"}}"""

    def _build_evaluation_prompt_tech_2(self, question: str, answer: str, context: dict) -> str:
        """技术二面评估：侧重架构设计、技术深度、权衡分析"""
        hint_note = ""
        if context.get("hint_used"):
            hint_note = "\n注意：候选人在回答此题前使用了提示，说明独立思考能力不足，各项评分应适当降低。"
        return f"""你是一名资深技术面试官（架构师），请从**架构设计与技术深度**角度评估候选人的回答。

## 评估维度权重（按重要性排序）
1. **深度（权重 40%）** — 对底层原理的理解是否到位、是否考虑了异常场景和边界情况
2. **技术能力（权重 30%）** — 方案是否合理、技术选型是否恰当、是否做了必要的取舍分析
3. **逻辑思维（权重 20%）** — 系统拆解是否有条理、数据模型是否合理、接口设计是否清晰
4. **沟通表达（权重 10%）** — 能否清晰地阐述设计决策理由

面试题: {question}

回答: {answer[:2000]}

岗位信息: {json.dumps(context.get("profile", {}), ensure_ascii=False)[:500]}

{hint_note}
评分标准（10 分制，请充分利用 1-10 全范围）：
- 10 分：完美回答，架构视野开阔，深度和广度兼备
- 8-9 分：很好的回答，有清晰的架构思维
- 6-7 分：合格回答，能完成基本设计但缺乏深度
- 4-5 分：基本回答，设计上有明显漏洞
- 1-3 分：较差回答

只输出 JSON：
{{"technical_score": 10, "technical_comment": "评价", "logic_score": 10, "logic_comment": "评价", "depth_score": 10, "depth_comment": "评价（重点分析架构和技术深度表现）", "communication_score": 10, "communication_comment": "评价", "overall_score": 10, "summary": "综合评价（突出架构设计能力）", "strengths": ["优点"], "improvements": ["建议"], "reference_answer": "参考回答"}}"""

    def _build_evaluation_prompt_comprehensive(self, question: str, answer: str, context: dict) -> str:
        """综合面评估：侧重软素质、领导力、成长思维"""
        hint_note = ""
        if context.get("hint_used"):
            hint_note = "\n注意：候选人在回答此题前使用了提示，说明独立思考能力不足，各项评分应适当降低。"
        return f"""你是一名资深 HR 负责人/技术 VP，请从**综合素质与发展潜力**角度评估候选人的回答。

## 评估维度权重（按重要性排序）
1. **沟通表达（权重 40%）** — 是否使用 STAR 结构、表达是否清晰有条理、是否具体而非空泛
2. **逻辑思维（权重 25%）** — 故事是否有因果链条、反思是否深入、归因是否合理
3. **深度（权重 20%）** — 自我认知是否清晰、是否能从经历中提炼可迁移的经验
4. **技术能力（权重 15%）** — 对技术角色的理解、行业认知（此项为软性参考，不要求技术深度）

面试题: {question}

回答: {answer[:2000]}

岗位信息: {json.dumps(context.get("profile", {}), ensure_ascii=False)[:500]}

{hint_note}
评分标准（10 分制，请充分利用 1-10 全范围）：
- 10 分：完美的 STAR 表达，展现优秀的领导力和成长思维
- 8-9 分：很好的回答，有具体案例和深入反思
- 6-7 分：合格回答，能说清楚经历但缺乏深度反思
- 4-5 分：基本回答，故事不够具体或逻辑不够清晰
- 1-3 分：较差回答

只输出 JSON：
{{"technical_score": 10, "technical_comment": "评价（软性参考）", "logic_score": 10, "logic_comment": "评价", "depth_score": 10, "depth_comment": "评价（重点分析自我认知和反思深度）", "communication_score": 10, "communication_comment": "评价（重点分析 STAR 结构和表达）", "overall_score": 10, "summary": "综合评价（突出综合素质和发展潜力）", "strengths": ["优点"], "improvements": ["建议"], "reference_answer": "参考回答"}}"""

    def _build_report_prompt(self, history: list[dict], profile: dict, round_name: str = "") -> str:
        history_str = ""
        for i, h in enumerate(history, 1):
            score = h.get("score", {})
            history_str += f"\nQ{i}: {h['q']}\nA{i}: {h['a'][:300]}\n评分: {json.dumps(score, ensure_ascii=False)}\n"

        # 根据轮次生成差异化的报告框架
        rc = self._get_round_config(round_name)
        round_focus_map = {
            "tech_1": "本次面试侧重考察**工程实践能力**（代码质量、调试能力、工程判断）。请重点评价候选人的编码素养和独立交付能力。",
            "tech_2": "本次面试侧重考察**架构设计与技术深度**（系统设计、底层原理、技术权衡）。请重点评价候选人的架构视野和深度思考能力。",
            "comprehensive": "本次面试侧重考察**综合素质与发展潜力**（领导力、沟通协作、成长思维、职业规划）。请重点评价候选人的软素质和潜力。",
        }
        round_focus = round_focus_map.get(round_name, "")

        return f"""请根据以下完整的面试记录，生成一份面试总结报告。

== 轮次信息 ==
面试轮次：{rc['name']}（{rc['desc']}）
{round_focus}

== 岗位画像 ==
{json.dumps(profile, ensure_ascii=False)[:500]}

== 面试记录 ==
{history_str}

输出 JSON:
{{
  "total_questions": 0,
  "overall_score": 0,
  "score_breakdown": {{"technical": 0, "logic": 0, "depth": 0, "communication": 0}},
  "strengths": ["整体优势1", "优势2"],
  "weaknesses": ["待提升1", "待提升2"],
  "skill_summary": "技能掌握情况总结（结合轮次考察重点给出针对性评价）",
  "preparation_advice": ["复习建议1", "建议2", "建议3"],
  "recommended_positions": ["适合的岗位1", "岗位2"],
  "final_verdict": "最终评价（2-3句话，结合该轮次的考察方向）"
}}"""

    # ==================== 解析器 ====================

    def _parse_question(self, raw: Optional[str], num: int, round_name: str = "", profile: dict = None) -> dict:
        if not raw:
            return self._make_fallback(num, round_name, profile)
        try:
            data = json.loads(raw)
            if "question" in data:
                if round_name == "written":
                    return self._validate_written_question(data, num, profile)
                return data
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    if "question" in data:
                        if round_name == "written":
                            return self._validate_written_question(data, num, profile)
                        return data
                except json.JSONDecodeError:
                    pass
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.startswith("{") and not l.startswith("}")]
        if round_name == "written":
            return self._make_written_fallback(num, profile)
        question_text = lines[0] if lines else f"请结合你的项目经验，谈谈你在 {num} 个项目中的技术挑战和解决方案。"
        return {"question": question_text, "type": "技术", "difficulty": "medium", "topic": "综合", "expected_points": []}

    def _validate_written_question(self, data: dict, num: int, profile: dict = None) -> dict:
        """校验笔试题目必须包含 options 字段，不符合则返回备选题"""
        options = data.get("options")
        if options and isinstance(options, dict) and len(options) >= 2:
            return data
        logger.warning(f"笔试第{num}题缺少 options 字段，使用备选题。原始数据: {json.dumps(data, ensure_ascii=False)[:200]}")
        return self._make_written_fallback(num, profile)

    def _make_written_fallback(self, num: int, profile: dict = None) -> dict:
        """生成笔试备选选择题 — 根据岗位信息匹配相关题库，AI 出题失败时兜底"""
        profiles_str = json.dumps(profile or {}, ensure_ascii=False).lower()

        # 根据岗位关键词匹配题库
        if any(kw in profiles_str for kw in ["python", "django", "flask", "fastapi", "后端"]):
            pool = _FALLBACK_BACKEND
        elif any(kw in profiles_str for kw in ["前端", "frontend", "javascript", "vue", "react", "css", "html"]):
            pool = _FALLBACK_FRONTEND
        elif any(kw in profiles_str for kw in ["数据", "算法", "机器学习", "ai", "大模型", "nlp", "cv"]):
            pool = _FALLBACK_AI_DATA
        elif any(kw in profiles_str for kw in ["运维", "devops", "docker", "k8s", "linux", "云"]):
            pool = _FALLBACK_DEVOPS
        elif any(kw in profiles_str for kw in ["测试", "qa", "质量"]):
            pool = _FALLBACK_TESTING
        else:
            pool = _FALLBACK_GENERAL

        return pool[(num - 1) % len(pool)]

    def _make_fallback(self, num: int, round_name: str = "", profile: dict = None) -> dict:
        if round_name == "written":
            return self._make_written_fallback(num, profile)
        return {"question": f"请介绍一下你在最近项目中的技术选型和架构设计。", "type": "技术", "difficulty": "medium", "topic": "项目经验", "expected_points": []}

    def _parse_evaluation(self, raw: Optional[str]) -> dict:
        default = {
            "technical_score": 0, "technical_comment": "",
            "logic_score": 0, "logic_comment": "",
            "depth_score": 0, "depth_comment": "",
            "communication_score": 0, "communication_comment": "",
            "overall_score": 0, "summary": "", "strengths": [], "improvements": [], "reference_answer": "",
        }
        if not raw:
            logger.warning("AI 评估返回空")
            return default

        # 1. 尝试完整 JSON 解析
        try:
            data = json.loads(raw)
            return {**default, **data}
        except json.JSONDecodeError:
            pass

        # 2. 尝试提取 JSON 块
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                data = json.loads(match.group())
                return {**default, **data}
            except json.JSONDecodeError:
                pass

        # 3. 从文本中提取各维度评分（支持 10 分制或 100 分制）
        scores = {}
        dims = {
            "技术": "technical_score", "逻辑": "logic_score",
            "深度": "depth_score", "表达": "communication_score",
            "综合": "overall_score", "总体": "overall_score",
            "technical": "technical_score", "logic": "logic_score",
            "depth": "depth_score", "communication": "communication_score",
            "overall": "overall_score",
        }
        for cn, en in dims.items():
            m = re.search(rf'{cn}.*?(\d+(?:\.\d+)?)', raw)
            if m:
                val = float(m.group(1))
                val = round(val / 10, 1) if val > 10 else val  # 100分制→10分制
                scores[en] = val

        if scores:
            result = {**default, **scores}
            logger.info(f"从文本提取评分: {result}")
            return result

        logger.warning(f"评估解析失败，AI 返回: {raw[:200]}")
        return default

    def _parse_report(self, raw: Optional[str], history: list[dict]) -> dict:
        default = {
            "total_questions": len(history),
            "overall_score": 0,
            "score_breakdown": {"technical": 0, "logic": 0, "depth": 0, "communication": 0},
            "strengths": [], "weaknesses": [],
            "skill_summary": "", "preparation_advice": [],
            "recommended_positions": [], "final_verdict": "",
        }
        if not raw:
            return default
        try:
            data = json.loads(raw)
            return {**default, **data}
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return {**default, **json.loads(match.group())}
                except json.JSONDecodeError:
                    pass
        return default
