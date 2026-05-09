"""面试引擎

核心功能：
1. 根据简历+岗位画像生成面试题
2. 评估用户回答（多维度评分）
3. 动态决策：追问/换题/升级难度
"""
import asyncio
import json
import logging
import re
import time
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


# ==================== 备选笔试题库（按岗位分类，AI 出题失败时兜底）
# 每个题库至少 25 题以上，确保一次笔试（20 题）内不会因 modulo 循环而重复
# ====================

_FALLBACK_GENERAL = [
    {"question": "在软件开发中，下列哪种设计模式属于创建型模式？", "type": "选择题", "difficulty": "easy", "topic": "设计模式", "options": {"A": "工厂模式", "B": "观察者模式", "C": "装饰器模式", "D": "策略模式"}, "correct_answer": "A", "explanation": "工厂模式属于创建型模式，用于封装对象的创建过程。观察者、装饰器、策略都属于行为型或结构型模式。"},
    {"question": "HTTP 状态码 404 表示什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "服务器内部错误", "B": "资源未找到", "C": "重定向", "D": "请求超时"}, "correct_answer": "B", "explanation": "404 Not Found 表示服务器无法找到请求的资源。500 为服务器错误，301/302 为重定向，408 为请求超时。"},
    {"question": "以下哪种数据结构是先进后出（LIFO）的？", "type": "选择题", "difficulty": "easy", "topic": "数据结构", "options": {"A": "队列", "B": "栈", "C": "链表", "D": "数组"}, "correct_answer": "B", "explanation": "栈（Stack）是典型的 LIFO 结构，只允许在一端进行插入和删除。队列是 FIFO。"},
    {"question": "关系型数据库中的主键（Primary Key）的主要作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "加快查询速度", "B": "唯一标识一条记录", "C": "建立索引", "D": "保证数据安全性"}, "correct_answer": "B", "explanation": "主键的核心作用是唯一标识表中的每一行记录。自动创建索引加快查询只是副作用。"},
    {"question": "Git 中 git clone 和 git pull 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "版本控制", "options": {"A": "clone 是复制仓库，pull 是更新代码", "B": "两者完全一样", "C": "clone 比 pull 更快", "D": "pull 用于创建新分支"}, "correct_answer": "A", "explanation": "clone 是从远程复制一个完整的仓库到本地，pull 是拉取远程更新并合并到当前分支。"},
    {"question": "面向对象编程中，封装（Encapsulation）的主要目的是什么？", "type": "选择题", "difficulty": "easy", "topic": "编程基础", "options": {"A": "加快程序运行速度", "B": "隐藏内部实现细节，保护数据", "C": "减少代码行数", "D": "实现跨平台兼容"}, "correct_answer": "B", "explanation": "封装通过将数据和操作数据的方法绑定在一起，隐藏对象的内部状态和实现细节，保护数据不被外部随意修改。"},
    {"question": "下列哪个是关系型数据库管理系统？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "MongoDB", "B": "MySQL", "C": "Redis", "D": "Elasticsearch"}, "correct_answer": "B", "explanation": "MySQL 是关系型数据库。MongoDB 是文档数据库，Redis 是键值存储，Elasticsearch 是搜索引擎。"},
    {"question": "TCP 和 UDP 的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "TCP 需要连接，UDP 不需要", "B": "UDP 比 TCP 更安全", "C": "TCP 不支持重传", "D": "两者没有区别"}, "correct_answer": "A", "explanation": "TCP 是面向连接的可靠传输协议（三次握手、重传机制），UDP 是无连接的不可靠传输协议，但延迟更低。"},
    {"question": "计算机中，1 GB 等于多少字节？", "type": "选择题", "difficulty": "easy", "topic": "计算机基础", "options": {"A": "1000^3", "B": "1024^3", "C": "1000^2", "D": "1024^2"}, "correct_answer": "B", "explanation": "计算机中 1 GB = 1024^3 字节（2^30），即以二进制定义。硬盘厂商常用 1000^3 表示，但计算机内存等采用二进制。"},
    {"question": "进程和线程的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "操作系统", "options": {"A": "进程是资源分配单位，线程是 CPU 调度单位", "B": "线程有自己的独立地址空间", "C": "进程不能创建子进程", "D": "线程之间完全隔离"}, "correct_answer": "A", "explanation": "进程拥有独立的地址空间和资源，是资源分配的基本单位；线程是 CPU 调度的基本单位，同一进程下的线程共享地址空间。"},
    {"question": "OSI 七层模型中，TCP 协议工作在哪一层？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "应用层", "B": "传输层", "C": "网络层", "D": "数据链路层"}, "correct_answer": "B", "explanation": "TCP 工作在传输层（第4层），提供可靠的端到端通信。IP 协议工作在网络层。"},
    {"question": "对称加密和非对称加密的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "网络安全", "options": {"A": "对称加密加解密用同一密钥，非对称用不同密钥", "B": "对称加密更安全", "C": "非对称加密速度更快", "D": "两者没有区别"}, "correct_answer": "A", "explanation": "对称加密使用同一密钥加解密（如 AES），速度快；非对称加密使用公私钥对（如 RSA），速度慢但解决了密钥分发问题。"},
    {"question": "在 Linux 中，哪个命令用于修改文件权限？", "type": "选择题", "difficulty": "easy", "topic": "操作系统", "options": {"A": "chmod", "B": "chown", "C": "chgrp", "D": "chattr"}, "correct_answer": "A", "explanation": "chmod 修改文件权限（读/写/执行）。chown 修改所有者，chgrp 修改所属组，chattr 修改文件属性。"},
    {"question": "关系型数据库中，外键（Foreign Key）的作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "加快查询速度", "B": "维护表与表之间的引用完整性", "C": "唯一标识一条记录", "D": "创建索引"}, "correct_answer": "B", "explanation": "外键用于维护表之间的引用完整性，确保子表中的某列值必须在父表中存在。它同样会创建索引加速关联查询。"},
    {"question": "在编译型语言中，编译器（Compiler）和解释器（Interpreter）的主要区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "编程基础", "options": {"A": "编译器一次性翻译后执行，解释器逐行翻译执行", "B": "解释器运行速度更快", "C": "编译器不能做优化", "D": "两者没有区别"}, "correct_answer": "A", "explanation": "编译器将源代码一次性全部翻译成机器码再执行（如 C/C++）；解释器逐行翻译并立即执行（如 Python/JavaScript 的传统模式）。"},
    {"question": "HTTP 和 HTTPS 的核心区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "HTTPS 使用 SSL/TLS 加密传输", "B": "HTTPS 速度更快", "C": "HTTP 更安全", "D": "HTTP 使用 443 端口"}, "correct_answer": "A", "explanation": "HTTPS 在 HTTP 基础上增加了 SSL/TLS 加密层，保证数据在传输过程中不被窃听和篡改。HTTPS 默认使用 443 端口，HTTP 使用 80 端口。"},
    {"question": "数据库索引（Index）的主要目的是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "保证数据唯一性", "B": "加快数据查询速度", "C": "减少存储空间", "D": "实现数据备份"}, "correct_answer": "B", "explanation": "索引通过创建额外的数据结构（如 B+树）来加速数据查询，但会占用额外的存储空间并降低写入速度。"},
    {"question": "在面向对象编程中，多态（Polymorphism）指的是什么？", "type": "选择题", "difficulty": "easy", "topic": "编程基础", "options": {"A": "一个类可以继承多个父类", "B": "同一操作作用于不同对象可以有不同的实现", "C": "将数据和方法封装在一起", "D": "隐藏内部实现细节"}, "correct_answer": "B", "explanation": "多态允许不同类的对象对同一消息做出不同的响应。在 Java/C++ 中通过虚函数实现，在 Python 中通过鸭子类型实现。"},
    {"question": "缓存（Cache）技术的基本原理是什么？", "type": "选择题", "difficulty": "easy", "topic": "计算机基础", "options": {"A": "用空间换时间，将频繁访问的数据放在更快的存储中", "B": "压缩数据以减少存储", "C": "用备份数据防止丢失", "D": "分布式存储数据"}, "correct_answer": "A", "explanation": "缓存利用局部性原理，将频繁访问的数据存储在高速介质中（如内存），从而减少访问慢速介质（如磁盘）的次数，是以空间换时间的典型策略。"},
    {"question": "Hash 冲突（哈希碰撞）的常见解决方案有哪些？", "type": "选择题", "difficulty": "medium", "topic": "数据结构", "options": {"A": "链地址法和开放地址法", "B": "仅能扩容", "C": "改用数组存储", "D": "使用二分查找"}, "correct_answer": "A", "explanation": "常见的 Hash 冲突解决方案有链地址法（同一个槽位用链表存储多个元素）和开放地址法（冲突时寻找下一个空位）。"},
    {"question": "在 RESTful API 设计中，PUT 和 PATCH 的区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "API设计", "options": {"A": "PUT 全量更新，PATCH 部分更新", "B": "两者完全一样", "C": "PATCH 更慢", "D": "PUT 只能用于创建"}, "correct_answer": "A", "explanation": "PUT 是幂等的，客户端发送完整的资源表示进行全量替换；PATCH 用于部分更新，只发送要修改的字段，可能非幂等。"},
    {"question": "死锁（Deadlock）产生的四个必要条件是什么？", "type": "选择题", "difficulty": "medium", "topic": "操作系统", "options": {"A": "互斥、请求与保持、不可剥夺、循环等待", "B": "互斥、共享、剥夺、循环", "C": "互斥、饥饿、等待、循环", "D": "共享、保持、等待、循环"}, "correct_answer": "A", "explanation": "死锁产生的四个必要条件：互斥（资源一次只能被一个进程使用）、请求与保持、不可剥夺、循环等待。破坏任意一个即可预防死锁。"},
    {"question": "B+ 树相比 B 树的优势是什么？", "type": "选择题", "difficulty": "medium", "topic": "数据结构", "options": {"A": "非叶子节点不存储数据，可以存储更多键，树更矮", "B": "B+ 树查询更快", "C": "B+ 树实现更简单", "D": "B+ 树占用更少内存"}, "correct_answer": "A", "explanation": "B+ 树的非叶子节点只存储键值不存储数据，因此同样大小的节点可以存储更多键，降低了树的高度。所有数据在叶子节点且形成有序链表，适合范围查询。"},
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
    {"question": "Python 中深拷贝（deep copy）和浅拷贝（shallow copy）的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Python基础", "options": {"A": "浅拷贝只复制引用，深拷贝递归复制所有对象", "B": "两者没有区别", "C": "深拷贝只复制引用", "D": "浅拷贝更安全"}, "correct_answer": "A", "explanation": "浅拷贝创建新对象但只复制第一层引用，内部对象仍共享；深拷贝递归复制所有层级，新对象与原对象完全独立。"},
    {"question": "FastAPI 中路径参数和查询参数的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Web框架", "options": {"A": "路径参数在 URL 路径中，查询参数在 ? 后面", "B": "两者完全一样", "C": "查询参数更安全", "D": "路径参数只能用于 GET 请求"}, "correct_answer": "A", "explanation": "路径参数是 URL 路径的一部分（如 /users/{id}），查询参数在 ? 后面（如 ?page=1）。FastAPI 通过类型注解自动识别。"},
    {"question": "SELECT ... FOR UPDATE 的作用是什么？", "type": "选择题", "difficulty": "medium", "topic": "数据库", "options": {"A": "锁定读取的行，防止其他事务修改", "B": "强制更新数据", "C": "加快查询速度", "D": "删除数据"}, "correct_answer": "A", "explanation": "SELECT ... FOR UPDATE 对查询结果集的行加行级排他锁，阻止其他事务修改或加锁这些行，常用于实现悲观锁。"},
    {"question": "RESTful API 推荐如何设计资源路径？", "type": "选择题", "difficulty": "easy", "topic": "API设计", "options": {"A": "使用名词复数表示资源", "B": "使用动词表示操作", "C": "使用大写字母", "D": "使用中文路径"}, "correct_answer": "A", "explanation": "RESTful 规范推荐使用名词复数表示资源（如 /users、/articles），用 HTTP 方法表示操作（GET 获取、POST 创建等）。"},
    {"question": "Celery 中，任务队列的 Broker 和 Backend 分别用于什么？", "type": "选择题", "difficulty": "medium", "topic": "异步任务", "options": {"A": "Broker 存储任务，Backend 存储结果", "B": "两者功能相同", "C": "Backend 调度任务", "D": "Broker 存储结果"}, "correct_answer": "A", "explanation": "Broker（消息中间件如 Redis/RabbitMQ）接收和分发任务；Backend（结果存储）保存任务执行结果，供调用方查询。"},
    {"question": "ORM 中的 N+1 查询问题指的是什么？", "type": "选择题", "difficulty": "medium", "topic": "数据库", "options": {"A": "查询主表后循环访问关联表，产生大量查询", "B": "查询速度慢 N+1 倍", "C": "SQL 语法错误", "D": "索引失效导致全表扫描"}, "correct_answer": "A", "explanation": "N+1 问题指查询出 N 条主记录后，循环访问每条记录的关联数据，产生 N+1 次查询。解决方案是使用 JOIN 或批量加载（如 SQLAlchemy 的 joinedload）。"},
    {"question": "Python 中 with 语句的上下文管理器协议是什么？", "type": "选择题", "difficulty": "easy", "topic": "Python基础", "options": {"A": "__enter__ 和 __exit__ 方法", "B": "open 和 close 方法", "C": "start 和 stop 方法", "D": "begin 和 end 方法"}, "correct_answer": "A", "explanation": "上下文管理器需要实现 __enter__（进入 with 块时调用，返回值赋给 as 变量）和 __exit__（退出时调用，处理异常和清理）。"},
    {"question": "在 MySQL 中，VARCHAR 和 CHAR 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据库", "options": {"A": "VARCHAR 变长，CHAR 定长", "B": "两者完全一样", "C": "CHAR 更节省空间", "D": "VARCHAR 不能创建索引"}, "correct_answer": "A", "explanation": "VARCHAR 存储变长字符串，按实际长度+1~2 字节存储；CHAR 固定长度，不足时补空格，适合定长字段（如手机号）。"},
    {"question": "Django 中 QuerySet 是惰性求值的吗？", "type": "选择题", "difficulty": "easy", "topic": "Web框架", "options": {"A": "是，QuerySet 在求值前不会执行 SQL", "B": "否，创建即执行", "C": "部分情况执行", "D": "取决于数据库类型"}, "correct_answer": "A", "explanation": "Django 的 QuerySet 是惰性的，只有在迭代、切片、调用 len()/list() 或 bool() 等操作时才会真正执行 SQL 查询。"},
    {"question": "SQL 注入攻击的防范措施不包括哪个？", "type": "选择题", "difficulty": "easy", "topic": "安全", "options": {"A": "使用参数化查询 / 预编译语句", "B": "对用户输入做黑名单过滤", "C": "使用 ORM 框架", "D": "对输入做转义处理"}, "correct_answer": "B", "explanation": "黑名单过滤容易被绕过。推荐使用参数化查询/预编译语句（如 ? 占位符），这是防止 SQL 注入最有效的手段。"},
    {"question": "Git rebase 和 Git merge 的区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "版本控制", "options": {"A": "rebase 重写提交历史产生线性结构，merge 保留分支拓扑", "B": "两者结果完全一样", "C": "merge 不允许冲突", "D": "rebase 只能用于本地分支"}, "correct_answer": "A", "explanation": "rebase 将当前分支的提交依次应用到目标分支顶端，产生干净的线性历史；merge 创建一个合并提交，保留完整的分支拓扑。"},
    {"question": "Linux 进程间通信（IPC）的方式不包括哪个？", "type": "选择题", "difficulty": "medium", "topic": "操作系统", "options": {"A": "管道（Pipe）", "B": "消息队列", "C": "共享内存", "D": "GPU 计算"}, "correct_answer": "D", "explanation": "常见的 IPC 方式包括：管道（Pipe/FIFO）、消息队列、共享内存、信号量、Socket 等。GPU 计算不是 IPC 方式。"},
    {"question": "HTTPS 建立连接时，SSL/TLS 握手的第一步是什么？", "type": "选择题", "difficulty": "medium", "topic": "网络基础", "options": {"A": "客户端发送 ClientHello（支持的加密套件列表）", "B": "服务器发送证书", "C": "生成会话密钥", "D": "开始加密传输"}, "correct_answer": "A", "explanation": "SSL/TLS 握手第一步是客户端发送 ClientHello，包含支持的 TLS 版本、加密套件列表和随机数。服务端回复 ServerHello 选择加密套件并发送证书。"},
    {"question": "Flask 和 FastAPI 的核心区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Web框架", "options": {"A": "FastAPI 原生支持异步，Flask 默认同步", "B": "Flask 更快", "C": "FastAPI 不支持 RESTful", "D": "两者完全一样"}, "correct_answer": "A", "explanation": "FastAPI 基于 Starlette 和 Pydantic，原生支持 async/await 异步；Flask 默认同步（可通过插件支持异步）。FastAPI 还自动生成 OpenAPI 文档。"},
    {"question": "Python 中 GIL（全局解释器锁）的影响是什么？", "type": "选择题", "difficulty": "medium", "topic": "Python进阶", "options": {"A": "同一进程的多线程无法并行执行 CPU 密集型任务", "B": "Python 无法实现多线程", "C": "GIL 已从 Python 3 中移除", "D": "多核 CPU 对 Python 无提升"}, "correct_answer": "A", "explanation": "GIL 保证同一时刻只有一个线程执行 Python 字节码，因此多线程对 CPU 密集型任务无帮助。但 I/O 密集型任务仍能受益，因 GIL 在 I/O 等待时释放。"},
    {"question": "Redis 中 RDB 和 AOF 两种持久化方式的主要区别？", "type": "选择题", "difficulty": "medium", "topic": "缓存与队列", "options": {"A": "RDB 是快照，AOF 是操作日志追加", "B": "两者完全一样", "C": "RDB 更安全", "D": "AOF 重启恢复更快"}, "correct_answer": "A", "explanation": "RDB 按时间间隔生成全量快照（文件小、恢复快），AOF 记录每条写命令（数据更安全但文件大）。实际可两者同时使用。"},
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
    {"question": "CSS 中 position 属性哪些值会让元素脱离文档流？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": "absolute 和 fixed", "B": "relative 和 static", "C": "sticky 和 relative", "D": "static 和 fixed"}, "correct_answer": "A", "explanation": "position: absolute 和 fixed 使元素脱离文档流，不再占据原有空间。relative 和 static 不脱离文档流，sticky 是相对和固定的混合。"},
    {"question": "JavaScript 闭包（Closure）的核心特征是什么？", "type": "选择题", "difficulty": "easy", "topic": "JavaScript", "options": {"A": "内部函数可以访问外部函数的变量，即使外部函数已返回", "B": "函数不能嵌套", "C": "函数只能访问全局变量", "D": "闭包会立即执行"}, "correct_answer": "A", "explanation": "闭包是函数与其词法环境的组合。即使外部函数已经执行完毕，内部函数仍然可以访问外部函数的变量。"},
    {"question": "React 中 useEffect 的依赖数组为空 [] 时，effect 何时执行？", "type": "选择题", "difficulty": "easy", "topic": "React", "options": {"A": "组件挂载时执行一次", "B": "每次渲染都执行", "C": "从不执行", "D": "组件卸载时执行"}, "correct_answer": "A", "explanation": "useEffect 依赖数组为 [] 时，effect 只在组件首次挂载后执行一次，相当于 componentDidMount。有依赖项时在依赖变化时执行。"},
    {"question": "Vue3 中 ref 和 reactive 的核心区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "Vue", "options": {"A": "ref 包装基本类型用 .value 访问，reactive 直接操作对象", "B": "两者完全一样", "C": "reactive 不能用于对象", "D": "ref 性能更好"}, "correct_answer": "A", "explanation": "ref 可包装任何类型，用 .value 访问/修改，模板中自动解包；reactive 只能用于对象/数组，直接访问属性，但重新赋值会失去响应。"},
    {"question": "HTML5 中新引入的语义化标签不包括哪个？", "type": "选择题", "difficulty": "easy", "topic": "HTML", "options": {"A": "div", "B": "article", "C": "section", "D": "nav"}, "correct_answer": "A", "explanation": "div 是 HTML4 就有的无语义容器。article、section、nav、header、footer、aside 等是 HTML5 引入的语义化标签。"},
    {"question": "CSS 选择器 .foo .bar 和 .foo.bar 的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": ".foo .bar 是后代选择器，.foo.bar 选择同时有这两个类的元素", "B": "两者完全一样", "C": ".foo.bar 是后代选择器", "D": ".foo .bar 选择同时有这两个类的元素"}, "correct_answer": "A", "explanation": ".foo .bar（空格）是后代选择器，选择 .foo 内部的所有 .bar；.foo.bar（无空格）是交集选择器，选择同时拥有 foo 和 bar 类的元素。"},
    {"question": "JavaScript 事件冒泡和事件捕获的执行顺序是什么？", "type": "选择题", "difficulty": "easy", "topic": "JavaScript", "options": {"A": "先捕获后冒泡", "B": "先冒泡后捕获", "C": "同时执行", "D": "取决于浏览器"}, "correct_answer": "A", "explanation": "DOM 事件流分三个阶段：捕获阶段（从根到目标）→ 目标阶段 → 冒泡阶段（从目标到根）。addEventListener 第三个参数控制监听阶段。"},
    {"question": "CSS 中 display: none 和 visibility: hidden 的区别？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": "display: none 不占空间，visibility: hidden 仍占空间", "B": "两者完全一样", "C": "visibility: hidden 不占空间", "D": "display: none 仍占空间"}, "correct_answer": "A", "explanation": "display: none 从文档流中移除元素，不占据空间；visibility: hidden 隐藏元素但仍占据原有空间位置。"},
    {"question": "JavaScript 中 'use strict' 严格模式的作用不包括哪个？", "type": "选择题", "difficulty": "medium", "topic": "JavaScript", "options": {"A": "消除 this 的强制转型", "B": "禁止使用未声明的变量", "C": "消除静默失败转为抛出异常", "D": "自动提升变量到全局作用域"}, "correct_answer": "D", "explanation": "严格模式禁止变量未声明就使用、禁止 delete 不可删除属性、禁止 this 强制转型为全局对象等，但不改变变量提升规则。"},
    {"question": "Webpack 中 loader 和 plugin 的区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "构建工具", "options": {"A": "loader 处理模块转换，plugin 做构建生命周期扩展", "B": "两者完全一样", "C": "plugin 只能处理 CSS", "D": "loader 只能处理 JS"}, "correct_answer": "A", "explanation": "loader 用于在 import 时对模块源码进行转换（如 babel-loader 转译 JSX）；plugin 监听 webpack 构建生命周期事件，做更广泛的操作（如打包优化、资源管理）。"},
    {"question": "ES6 箭头函数和普通函数的核心区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "JavaScript", "options": {"A": "箭头函数没有自己的 this，继承外层作用域", "B": "箭头函数不能定义参数", "C": "箭头函数性能更差", "D": "两者没有区别"}, "correct_answer": "A", "explanation": "箭头函数不绑定自己的 this、arguments、super，this 继承自外围作用域。因此箭头函数不能用做构造函数，不能使用 call/apply 改变 this。"},
    {"question": "CSS 变量（自定义属性）的声明方式是什么？", "type": "选择题", "difficulty": "easy", "topic": "CSS", "options": {"A": "--var-name: value", "B": "$var-name: value", "C": "@var-name: value", "D": "var-name: value"}, "correct_answer": "A", "explanation": "CSS 自定义属性以 -- 开头声明（如 --primary-color: #333），用 var() 函数引用（如 color: var(--primary-color)）。"},
    {"question": "React 中 key 属性的作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "React", "options": {"A": "帮助 React 识别哪些元素改变、添加或删除", "B": "设置 CSS 样式", "C": "定义元素的唯一 ID", "D": "加速渲染"}, "correct_answer": "A", "explanation": "key 帮助 React 的 Diff 算法识别列表中的哪些元素发生了变更。使用唯一且稳定的 key（如 item.id）可以优化重渲染性能。"},
    {"question": "Promise.all 和 Promise.allSettled 的区别？", "type": "选择题", "difficulty": "medium", "topic": "JavaScript", "options": {"A": "Promise.all 一个失败就整体失败，allSettled 等待全部完成", "B": "两者完全一样", "C": "allSettled 性能更好", "D": "Promise.all 不能处理并行请求"}, "correct_answer": "A", "explanation": "Promise.all 任意一个 Promise rejected 就整体 reject；Promise.allSettled 等待所有 Promise 完成（无论 fulfilled 还是 rejected），返回每个的结果状态。"},
]

_FALLBACK_AI_DATA = [
    {"question": "机器学习的三种主要类型是什么？", "type": "选择题", "difficulty": "easy", "topic": "机器学习", "options": {"A": "监督学习、无监督学习、强化学习", "B": "深度学习、浅层学习、中等学习", "C": "分类、回归、排序", "D": "训练、验证、测试"}, "correct_answer": "A", "explanation": "机器学习三大范式：监督学习（有标签）、无监督学习（无标签）、强化学习（通过奖励信号学习）。"},
    {"question": "在深度学习中，激活函数 ReLU 的输出范围是什么？", "type": "选择题", "difficulty": "easy", "topic": "深度学习", "options": {"A": "(-∞, +∞)", "B": "[0, +∞)", "C": "[0, 1]", "D": "[-1, 1]"}, "correct_answer": "B", "explanation": "ReLU（Rectified Linear Unit）公式为 f(x)=max(0,x)，输入小于0输出0，输入大于0输出x本身。"},
    {"question": "RAG（检索增强生成）系统中，Embedding 模型的主要作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "AI基础概念", "options": {"A": "将用户提问直接翻译成SQL查询", "B": "将文本转换为向量表示，用于语义检索", "C": "对检索到的文档进行摘要生成", "D": "控制大模型回答的格式与长度"}, "correct_answer": "B", "explanation": "Embedding 模型将文本映射为稠密向量，语义相近的文本向量距离也近，从而实现语义检索而非关键词匹配。"},
    {"question": "神经网络中，过拟合（Overfitting）的常见解决方案不包括哪个？", "type": "选择题", "difficulty": "medium", "topic": "机器学习", "options": {"A": "增加 Dropout 层", "B": "增加训练数据量", "C": "增加模型层数使其更复杂", "D": "使用 L1/L2 正则化"}, "correct_answer": "C", "explanation": "增加模型复杂度会加剧过拟合。解决过拟合的方法包括：Dropout、数据增强、正则化（L1/L2）、早停（Early Stopping）、减少模型复杂度。"},
    {"question": "在大模型训练中，LoRA（Low-Rank Adaptation）的核心思想是什么？", "type": "选择题", "difficulty": "medium", "topic": "大模型微调", "options": {"A": "重新训练整个模型", "B": "在预训练权重旁增加低秩矩阵来适配新任务", "C": "直接修改预训练权重", "D": "增加更多的 GPU"}, "correct_answer": "B", "explanation": "LoRA 在冻结原始权重的基础上，通过低秩分解矩阵来学习任务特定的增量，大幅减少微调参数量。"},
    {"question": "自然语言处理中，Transformer 模型的核心机制是什么？", "type": "选择题", "difficulty": "medium", "topic": "NLP", "options": {"A": "循环神经网络（RNN）", "B": "自注意力机制（Self-Attention）", "C": "卷积操作（Convolution）", "D": "决策树"}, "correct_answer": "B", "explanation": "Transformer 的核心是 Self-Attention 机制，通过计算序列中每个词与其他词的关系来捕捉上下文信息。"},
    {"question": "数据预处理中，归一化（Normalization）的主要目的是什么？", "type": "选择题", "difficulty": "easy", "topic": "数据处理", "options": {"A": "增加数据量", "B": "消除量纲差异，使不同特征在相同尺度上", "C": "增加模型复杂度", "D": "减少训练时间"}, "correct_answer": "B", "explanation": "归一化将不同量纲的特征缩放到统一范围（如0-1），避免梯度下降时某些特征主导更新方向。"},
    {"question": "SQL 中，用于连接两个表的 JOIN 类型不包括哪个？", "type": "选择题", "difficulty": "easy", "topic": "数据处理", "options": {"A": "INNER JOIN", "B": "LEFT JOIN", "C": "MERGE JOIN", "D": "RIGHT JOIN"}, "correct_answer": "C", "explanation": "标准 SQL JOIN 类型包括 INNER/LEFT/RIGHT/FULL OUTER/CROSS JOIN。MERGE JOIN 不是 SQL JOIN 类型，它是数据库引擎的一种连接算法。"},
    {"question": "分词（Tokenization）在 NLP 中的作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "NLP", "options": {"A": "将文本分割成最小语义单元（词或子词）", "B": "将文本翻译成英文", "C": "删除停用词", "D": "对文本进行情感分类"}, "correct_answer": "A", "explanation": "分词将连续的文本切分为模型可处理的 token（词或子词）。BERT 使用 WordPiece，GPT 使用 BPE（Byte Pair Encoding）。"},
    {"question": "AI 模型中的「温度（Temperature）」参数控制什么？", "type": "选择题", "difficulty": "easy", "topic": "AI基础概念", "options": {"A": "控制生成结果的随机性和创造性", "B": "控制模型运行时的温度", "C": "控制模型的上下文长度", "D": "控制模型的训练速度"}, "correct_answer": "A", "explanation": "Temperature 控制 softmax 输出概率分布的平滑程度。温度高（>1）→ 输出更随机/有创造性；温度低（<1）→ 输出更确定/保守。0 表示每次都选最高概率。"},
    {"question": "batch_size 对模型训练的影响是什么？", "type": "选择题", "difficulty": "easy", "topic": "深度学习", "options": {"A": "batch_size 越大，梯度估计越准确但内存占用越大", "B": "batch_size 不影响训练", "C": "batch_size 越小模型效果越好", "D": "batch_size 只影响推理速度"}, "correct_answer": "A", "explanation": "较大的 batch_size 提供更准确的梯度估计和更好的并行利用，但需要更多内存；较小 batch_size 收敛更快但梯度噪声更大，有时反而能帮助跳出局部最优。"},
    {"question": "交叉熵损失函数（Cross-Entropy Loss）常用于什么任务？", "type": "选择题", "difficulty": "easy", "topic": "机器学习", "options": {"A": "分类任务", "B": "回归任务", "C": "聚类任务", "D": "降维任务"}, "correct_answer": "A", "explanation": "交叉熵损失常用于分类任务，衡量预测概率分布与真实分布之间的差异。值越小说明预测越接近真实标签。"},
    {"question": "在 Transformer 中，多头注意力（Multi-Head Attention）的优点是什么？", "type": "选择题", "difficulty": "medium", "topic": "深度学习", "options": {"A": "多个头从不同的表示子空间关注信息", "B": "并行计算加速", "C": "减少参数量", "D": "消除注意力机制"}, "correct_answer": "A", "explanation": "多头注意力将 Query/Key/Value 投影到多个子空间，每个头学习不同角度的关注模式，最后拼接整合，增强了模型的表达能力。"},
    {"question": "模型微调（Fine-tuning）和训练（Training）的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "大模型微调", "options": {"A": "微调基于预训练权重做增量训练，训练从零开始", "B": "两者完全一样", "C": "微调从零开始训练", "D": "训练不需要数据"}, "correct_answer": "A", "explanation": "训练（预训练）从随机初始化开始，在大量数据上学习通用知识；微调在预训练权重基础上，用少量标注数据适配特定任务，成本低、收敛快。"},
    {"question": "K 折交叉验证（K-fold Cross Validation）的主要用途是什么？", "type": "选择题", "difficulty": "easy", "topic": "机器学习", "options": {"A": "更稳定地评估模型性能，减少单次划分的偏差", "B": "加速模型训练", "C": "增加训练数据量", "D": "可视化数据分布"}, "correct_answer": "A", "explanation": "K 折交叉验证将数据分成 K 份，轮流用 K-1 份训练、1 份验证，取 K 次结果的平均作为最终评估，比单次划分更稳定可靠。"},
    {"question": "梯度消失（Vanishing Gradient）问题在哪种网络中最为常见？", "type": "选择题", "difficulty": "medium", "topic": "深度学习", "options": {"A": "深层前馈网络和循环神经网络（RNN）", "B": "单层感知机", "C": "卷积网络第一层", "D": "Dropout 层"}, "correct_answer": "A", "explanation": "梯度消失在深层网络和 RNN 中最为常见。深层网络用链式法则反向传播，靠前的层梯度连乘变小；RNN 时间步太长也会导致梯度消失。ResNet 和 LSTM 是常见解决方案。"},
    {"question": "在 LLM 中，上下文窗口（Context Window）指的是什么？", "type": "选择题", "difficulty": "easy", "topic": "大模型", "options": {"A": "模型一次能处理的最大 token 数量", "B": "用户界面的对话框大小", "C": "模型的缓存大小", "D": "训练数据的时间范围"}, "correct_answer": "A", "explanation": "上下文窗口指模型单次推理能处理的最大 token 数（包括输入+输出）。GPT-4 支持 8K/32K/128K，Claude 支持 200K。"},
    {"question": "Prompt Engineering 中，Chain-of-Thought（思维链）的核心思想是什么？", "type": "选择题", "difficulty": "medium", "topic": "Prompt工程", "options": {"A": "引导模型逐步推理，中间步骤可见", "B": "将多个 prompt 串联执行", "C": "自动生成 prompt 模板", "D": "压缩 prompt 长度"}, "correct_answer": "A", "explanation": "Chain-of-Thought 通过在 prompt 中加入中间推理步骤的示例（如「第一步...第二步...」），引导大模型生成类似的推理链，显著提升复杂任务的准确性。"},
    {"question": "在监督学习中，欠拟合（Underfitting）通常如何解决？", "type": "选择题", "difficulty": "easy", "topic": "机器学习", "options": {"A": "增加模型复杂度或更多特征", "B": "减少模型参数", "C": "增加正则化强度", "D": "减少训练数据"}, "correct_answer": "A", "explanation": "欠拟合意味着模型未能充分学习数据模式。解决方案：增加模型复杂度（更多层/更多参数）、增加更多有效特征、减少正则化、训练更长时间。"},
    {"question": "Attention Is All You Need 论文提出的改进不包括哪个？", "type": "选择题", "difficulty": "medium", "topic": "NLP", "options": {"A": "使用 RNN 作为编码器", "B": "自注意力机制", "C": "位置编码", "D": "多头注意力"}, "correct_answer": "A", "explanation": "该论文的核心创新是完全抛弃 RNN，仅使用自注意力机制（Self-Attention）和位置编码（Positional Encoding），并提出多头注意力（Multi-Head Attention）架构。"},
    {"question": "目标检测任务中，NMS（非极大值抑制）的作用是什么？", "type": "选择题", "difficulty": "medium", "topic": "计算机视觉", "options": {"A": "对同一对象的多个重叠检测框去重，保留最可靠的", "B": "归一化图像尺寸", "C": "数据增强", "D": "加速推理"}, "correct_answer": "A", "explanation": "NMS 在目标检测后处理阶段使用，对同一目标产生的多个候选框，保留得分最高的框，删除与其 IoU 超过阈值的其他框。"},
    {"question": "强化学习中，折扣因子 γ（gamma）接近 0 时代表什么？", "type": "选择题", "difficulty": "medium", "topic": "机器学习", "options": {"A": "模型只看重短期回报，几乎不考虑长期收益", "B": "模型只看重长期回报", "C": "模型完全随机", "D": "训练无法收敛"}, "correct_answer": "A", "explanation": "折扣因子 γ 决定智能体对长期回报的重视程度。γ 接近 0 时，只看重即时回报（短视）；γ 接近 1 时，几乎同等待远期回报。"},
    {"question": "对比学习（Contrastive Learning）的训练目标是什么？", "type": "选择题", "difficulty": "medium", "topic": "机器学习", "options": {"A": "让相似样本在表示空间中靠近，不相似样本远离", "B": "最小化预测与标签的差异", "C": "最大化模型的不确定性", "D": "对数据进行降维"}, "correct_answer": "A", "explanation": "对比学习的目标是学习一个表示空间，使得正样本对（如同一图片的不同增强）在空间中的距离近，负样本对（不同图片）的距离远。SimCLR、MoCo 是代表方法。"},
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
    {"question": "Dockerfile 中 COPY 和 ADD 指令的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Docker", "options": {"A": "ADD 支持自动解压 tar 和 URL 下载，COPY 仅复制", "B": "两者完全一样", "C": "COPY 支持 URL 下载", "D": "ADD 不能复制本地文件"}, "correct_answer": "A", "explanation": "COPY 仅从构建上下文复制文件和目录；ADD 额外支持自动解压 tar 文件和使用远程 URL。官方推荐优先使用 COPY（更透明）。"},
    {"question": "Kubernetes 中 Service 有哪几种类型？", "type": "选择题", "difficulty": "medium", "topic": "K8s", "options": {"A": "ClusterIP、NodePort、LoadBalancer、ExternalName", "B": "仅 ClusterIP", "C": "Internal、External、Public", "D": "TCP、UDP、SCTP"}, "correct_answer": "A", "explanation": "K8s Service 类型：ClusterIP（集群内访问）、NodePort（节点端口映射）、LoadBalancer（云负载均衡器）、ExternalName（DNS 映射）。"},
    {"question": "Docker Compose 和 Kubernetes 的主要区别在哪里？", "type": "选择题", "difficulty": "medium", "topic": "容器编排", "options": {"A": "Compose 单机编排多容器，K8s 集群级编排", "B": "两者完全一样", "C": "Compose 功能比 K8s 多", "D": "K8s 不能管理多个容器"}, "correct_answer": "A", "explanation": "Docker Compose 适用于单机场景定义和运行多容器应用；Kubernetes 是集群级的容器编排平台，提供自动扩缩、服务发现、滚动更新等生产级能力。"},
    {"question": "Docker 镜像构建时，多阶段构建（Multi-stage Build）的优点是什么？", "type": "选择题", "difficulty": "medium", "topic": "Docker", "options": {"A": "在单个 Dockerfile 中用多阶段分离构建环境和运行环境，减小镜像体积", "B": "并行构建多个镜像", "C": "自动回滚版本", "D": "提高构建速度"}, "correct_answer": "A", "explanation": "多阶段构建在同一个 Dockerfile 中使用多个 FROM 语句，前一阶段放构建工具链（大体积），后一阶段只复制最终的产物到精简镜像，显著减小生产镜像体积。"},
    {"question": "Ansible 和 Terraform 的核心区别是什么？", "type": "选择题", "difficulty": "medium", "topic": "自动化运维", "options": {"A": "Ansible 是配置管理工具，Terraform 是基础设施即代码", "B": "两者完全一样", "C": "Terraform 不能管理云资源", "D": "Ansible 有状态管理"}, "correct_answer": "A", "explanation": "Ansible 侧重配置管理和应用部署（安装软件、修改配置等），Terraform 侧重基础设施的声明式编排（创建/管理云资源），两者常配合使用。"},
    {"question": "iptables 在 Linux 中的作用是什么？", "type": "选择题", "difficulty": "easy", "topic": "Linux", "options": {"A": "配置内核网络包过滤和 NAT 规则", "B": "管理进程", "C": "查看磁盘使用", "D": "编译内核模块"}, "correct_answer": "A", "explanation": "iptables 是 Linux 内核的包过滤防火墙工具，用于配置网络规则（过滤、NAT、端口转发等）。Docker 和 K8s 底层大量依赖 iptables/nftables。"},
    {"question": "HTTP 反向代理和正向代理的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "网络基础", "options": {"A": "正向代理代表客户端，反向代理代表服务器端", "B": "两者完全一样", "C": "反向代理代表客户端", "D": "正向代理只能用于内网"}, "correct_answer": "A", "explanation": "正向代理（如 VPN）隐藏客户端，代表客户端向后端请求；反向代理（如 Nginx）隐藏服务端，代表服务器接收请求并负载均衡到后端。"},
    {"question": "Docker 中 docker save 和 docker export 的区别？", "type": "选择题", "difficulty": "medium", "topic": "Docker", "options": {"A": "save 保存镜像，export 导出容器的文件系统", "B": "两者完全一样", "C": "export 保存镜像", "D": "save 导出容器的文件系统"}, "correct_answer": "A", "explanation": "docker save 将镜像（包含各层元数据）保存为 tar 文件，可 load 恢复；docker export 将正在运行的容器的文件系统导出为 tar（丢失历史层和元数据）。"},
    {"question": "Linux 中硬链接和软链接的区别是什么？", "type": "选择题", "difficulty": "easy", "topic": "Linux", "options": {"A": "硬链接共享 inode（同一文件），软链接是独立文件指向另一个路径", "B": "两者完全一样", "C": "软链接共享 inode", "D": "硬链接可以跨越文件系统"}, "correct_answer": "A", "explanation": "硬链接与原始文件共享同一个 inode，互为别名，删除任一不影响其他；软链接是一个独立文件，内容是指向目标的路径，可跨文件系统。"},
    {"question": "HashiCorp Vault 的主要用途是什么？", "type": "选择题", "difficulty": "medium", "topic": "安全", "options": {"A": "密钥管理和访问控制（密钥/密文/证书的存储和轮换）", "B": "日志收集分析", "C": "容器运行时管理", "D": "包管理器"}, "correct_answer": "A", "explanation": "Vault 是密钥管理工具，支持动态密钥生成、密钥轮换、审计日志和细粒度访问控制，广泛应用于云原生环境中的密钥管理。"},
    {"question": "ELK Stack（Elasticsearch, Logstash, Kibana）中 Logstash 的作用？", "type": "选择题", "difficulty": "easy", "topic": "监控", "options": {"A": "日志采集、解析和转发", "B": "日志存储和搜索", "C": "可视化展示", "D": "告警通知"}, "correct_answer": "A", "explanation": "Logstash 负责从多种来源采集日志数据，进行过滤、解析和转换后发送到 Elasticsearch。Elasticsearch 负责存储和搜索，Kibana 负责可视化。"},
    {"question": "Docker 的网络模式（bridge/host/none）中，默认模式是哪个？", "type": "选择题", "difficulty": "easy", "topic": "Docker", "options": {"A": "bridge（桥接模式）", "B": "host（主机模式）", "C": "none（无网络）", "D": "overlay（覆盖网络）"}, "correct_answer": "A", "explanation": "Docker 默认 bridge 模式，容器通过 docker0 网桥与外网通信。host 模式直接使用宿主机网络栈，none 模式不配置网络。"},
    {"question": "SSH 的默认端口号是什么？", "type": "选择题", "difficulty": "easy", "topic": "Linux", "options": {"A": "22", "B": "80", "C": "443", "D": "3306"}, "correct_answer": "A", "explanation": "SSH 默认端口是 22。80 是 HTTP，443 是 HTTPS，3306 是 MySQL。"},
    {"question": "Linux 中 /etc/fstab 文件的作用是什么？", "type": "选择题", "difficulty": "medium", "topic": "Linux", "options": {"A": "定义系统启动时要挂载的文件系统", "B": "防火墙规则配置", "C": "用户密码存储", "D": "日志配置文件"}, "correct_answer": "A", "explanation": "/etc/fstab 文件在系统启动时被读取，自动挂载其中定义的分区/设备（包括文件系统类型、挂载点、挂载选项等）。"},
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
        # 收集已出过的题目文本，用于 AI 出题去重和 fallback 过滤
        used_questions = {h["q"] for h in history}
        if round_name == "written":
            prompt = self._build_next_prompt_written(history, resume, profile, used_questions)
            result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        else:
            prompt = self._build_next_prompt(history, resume, profile, round_name)
            result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        question_num = len(history) + 1
        return self._parse_question(result, question_num, round_name, profile, used_questions)

    async def pre_generate_written(self, total: int, resume: str, profile: dict,
                                    used_questions: set = None) -> list[dict]:
        """预生成笔试题：分批并发出题，失败从备选题库补位"""
        used_questions = set(used_questions or set())
        all_questions = []
        batch_size = 5

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch_count = batch_end - batch_start

            # 并发调 AI 生成本批题目
            tasks = []
            for offset in range(batch_count):
                q_num = batch_start + offset + 1
                prompt = self._build_pregen_prompt_written(q_num, total, resume, profile, used_questions)
                tasks.append(self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024))

            results = await asyncio.gather(*tasks)

            # 解析并去重
            for raw in results:
                q = self._parse_question(raw, len(all_questions) + 1, "written", profile, used_questions)
                all_questions.append(q)
                used_questions.add(q["question"])

        # 用 fallback pool 补足不足部分
        while len(all_questions) < total:
            q = self._make_written_fallback(len(all_questions) + 1, profile, used_questions)
            all_questions.append(q)
            used_questions.add(q["question"])

        return all_questions[:total]

    def _build_pregen_prompt_written(self, q_num: int, total: int, resume: str, profile: dict, used_questions: set = None) -> str:
        """预生成笔试的简化 prompt（不含答题历史）"""
        rc = self._get_round_config("written")
        profile_str = json.dumps(profile, ensure_ascii=False, indent=2)

        # 根据位置分配难度
        ratio = q_num / total
        if ratio <= 0.3:
            expected_difficulty = "easy"
            difficulty_hint = "基础概念题"
        elif ratio <= 0.7:
            expected_difficulty = "easy 或 medium"
            difficulty_hint = "过渡到中等难度"
        else:
            expected_difficulty = "medium"
            difficulty_hint = "中等偏难题"

        used_list = [q for q in (used_questions or set())]
        dedup_note = ""
        if used_list:
            dedup_note = "\n【去重】以下题目已经出过，严禁重复：\n" + "\n".join(f"- {q[:80]}..." for q in used_list)

        return f"""你是一个专业的笔试考官。这是第 {q_num}/{total} 题。

== 岗位画像 ==
{profile_str[:1000]}

== 简历 ==
{resume[:1500]}

{rc['prompt_extra']}

难度：{expected_difficulty}（{difficulty_hint}）
{dedup_note}

注意：以岗位画像中的 required_skills 和 tech_stack 为核心考察范围
绝对不要出简答题、论述题！
必须包含 options 字段，选择题 4 个选项（A/B/C/D），判断题 2 个选项（A. 正确 / B. 错误）。
correct_answer 必须正确无误，explanation 2-3 句解析。

只输出 JSON:
{{"question": "题目", "type": "选择题/判断题", "difficulty": "easy/medium/hard", "topic": "考察主题", "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}}, "correct_answer": "正确选项字母", "explanation": "解析（2-3句话）"}}"""

    async def evaluate_answer(self, question: str, answer: str, context: dict, round_name: str = "", question_data: dict = None) -> dict:
        """评估用户的回答，根据轮次使用差异化的评估标准"""
        latency_ms = None
        token_count = None
        if round_name == "written":
            result = self._evaluate_written_direct(answer, question_data or {})
        else:
            # 根据轮次选择对应的评估提示词
            if round_name == "tech_1":
                prompt = self._build_evaluation_prompt_tech_1(question, answer, context)
            elif round_name == "tech_2":
                prompt = self._build_evaluation_prompt_tech_2(question, answer, context)
            elif round_name == "comprehensive":
                prompt = self._build_evaluation_prompt_comprehensive(question, answer, context)
            else:
                prompt = self._build_evaluation_prompt(question, answer, context)

            t0 = time.monotonic()
            raw = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=2048)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            token_count = self.ai.last_usage.get("total_tokens") if self.ai.last_usage else None
            result = self._parse_evaluation(raw)

        # 自动采集训练数据
        try:
            from .finetune import get_collector
            collector = get_collector()
            record_id = collector.save_evaluation(
                question, answer, result, round_name, context,
                latency_ms=latency_ms, token_count=token_count,
            )
            result["_record_id"] = record_id
        except Exception as e:
            logger.warning(f"采集训练数据失败: {e}")

        return result

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
        report = self._parse_report(result, history)

        # 笔试分数由实际答题数据计算，避免 AI 输出未归一化的 200 分制
        if round_name == "written":
            computed = self._compute_written_report_scores(history)
            report["overall_score"] = computed["overall_score"]
            report["score_breakdown"] = computed["score_breakdown"]

        return report

    # ---- 笔试分数计算（基于实际答题数据，不依赖 AI） ----

    _TOPIC_TO_DIM = {
        # 技术基础
        "编程基础": "technical", "计算机基础": "technical",
        # 编程语言
        "python基础": "technical", "python进阶": "technical", "python": "technical",
        "javascript": "technical", "typescript": "technical",
        # Web/前端
        "html": "technical", "css": "technical", "react": "technical", "vue": "technical",
        "web框架": "technical", "浏览器api": "technical", "构建工具": "technical",
        # 后端/数据库/网络
        "数据库": "technical", "网络基础": "technical",
        "api设计": "technical", "web服务器": "technical",
        # 操作系统/DevOps
        "操作系统": "technical", "linux": "technical", "docker": "technical",
        "k8s": "technical", "容器化": "technical", "容器编排": "technical",
        "版本控制": "technical", "监控": "technical", "自动化运维": "technical",
        # 安全
        "安全": "technical", "网络安全": "technical",
        # 缓存/队列/异步
        "缓存与队列": "technical", "异步任务": "technical",
        # 测试 → communication
        "测试基础": "communication", "测试方法论": "communication",
        "自动化测试": "communication", "测试工具": "communication",
        "测试用例设计": "communication", "测试策略": "communication",
        "api测试": "communication", "测试": "communication",
        # 数据结构/算法 → logic
        "数据结构": "logic", "算法": "logic",
        # 设计/架构 → depth
        "设计模式": "depth", "系统设计": "depth", "架构": "depth",
        # AI/ML → depth
        "机器学习": "depth", "深度学习": "depth", "nlp": "depth", "大模型": "depth",
        "大模型微调": "depth", "ai基础概念": "depth", "prompt工程": "depth",
        "数据处理": "depth", "计算机视觉": "depth",
    }

    def _compute_written_report_scores(self, history: list[dict]) -> dict:
        """根据笔试答题记录计算 0-10 分制的分数和维度 breakdown"""
        total = len(history)
        default = {
            "overall_score": 0,
            "score_breakdown": {"technical": 0, "logic": 0, "depth": 0, "communication": 0},
        }
        if total == 0:
            return default

        correct_count = sum(1 for h in history if h.get("score", {}).get("correct", False))
        overall_score = round((correct_count / total) * 10, 1)

        # 按知识点维度统计正确率
        dim_correct = {"technical": 0, "logic": 0, "depth": 0, "communication": 0}
        dim_total = {"technical": 0, "logic": 0, "depth": 0, "communication": 0}

        for h in history:
            topic = (h.get("topic") or "").strip().lower()
            dim = self._TOPIC_TO_DIM.get(topic, "technical")
            dim_total[dim] += 1
            if h.get("score", {}).get("correct", False):
                dim_correct[dim] += 1

        score_breakdown = {}
        for dim in dim_total:
            if dim_total[dim] > 0:
                score_breakdown[dim] = round((dim_correct[dim] / dim_total[dim]) * 10, 1)
            else:
                score_breakdown[dim] = 0

        # 无题目的维度用 overall_score 兜底
        for dim in score_breakdown:
            if dim_total[dim] == 0:
                score_breakdown[dim] = overall_score

        return {"overall_score": overall_score, "score_breakdown": score_breakdown}

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

    def _build_next_prompt_written(self, history: list[dict], resume: str, profile: dict, used_questions: set = None) -> str:
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

        # 已出过的题目列表（去重用）
        used_list = [q for q in (used_questions or set())]
        dedup_note = ""
        if used_list:
            dedup_note = f"\n\n【重要去重要求】以下题目已经出过，严禁再次出现（包括变体）：\n" + "\n".join(f"- {q[:80]}..." for q in used_list)

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
{dedup_note}
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
        score = 10 if is_correct else 0

        return {
            "correct": is_correct,
            "correct_answer": correct,
            "explanation": question_data.get("explanation", ""),
            "score": score,
            "overall_score": score,  # 前端统一用 overall_score 展示
        }

    # ---- 统一的评估 JSON 模板 ----
    _EVAL_JSON_TEMPLATE = '{"technical_score": 0, "technical_comment": "评语", "logic_score": 0, "logic_comment": "评语", "depth_score": 0, "depth_comment": "评语", "communication_score": 0, "communication_comment": "评语", "overall_score": 0, "summary": "综合评价", "strengths": ["优点1"], "improvements": ["建议1"], "reference_answer": "参考回答要点"}'

    def _build_evaluation_prompt(self, question: str, answer: str, context: dict) -> str:
        hint_note = ""
        if context.get("hint_used"):
            hint_note = "\n注意：候选人在回答此题前使用了提示，说明独立思考能力不足，各项评分应适当降低。"
        return f"""你是一名资深面试官，请评估候选人的回答。

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

> 注意：总输出不要超过 800 token。参考回答仅写要点，不要包含代码。

输出格式（只输出 JSON，不要有任何额外文字或 markdown 标记）：
{self._EVAL_JSON_TEMPLATE}"""

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

> 注意：总输出不要超过 800 token。参考回答仅写要点，不要包含代码。

输出格式（只输出 JSON，不要有任何额外文字或 markdown 标记）：
{self._EVAL_JSON_TEMPLATE}"""

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

> 注意：总输出不要超过 800 token。参考回答仅写要点，不要包含代码。

输出格式（只输出 JSON，不要有任何额外文字或 markdown 标记）：
{self._EVAL_JSON_TEMPLATE}"""

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

> 注意：总输出不要超过 800 token。参考回答仅写要点，不要包含代码。

输出格式（只输出 JSON，不要有任何额外文字或 markdown 标记）：
{self._EVAL_JSON_TEMPLATE}"""

    def _build_report_prompt(self, history: list[dict], profile: dict, round_name: str = "") -> str:
        history_str = ""
        for i, h in enumerate(history, 1):
            score = h.get("score", {})
            history_str += f"\nQ{i}: {h['q']}\nA{i}: {h['a'][:300]}\n评分: {json.dumps(score, ensure_ascii=False)}\n"

        # 根据轮次生成差异化的报告框架
        rc = self._get_round_config(round_name)
        round_focus_map = {
            "written": "本次面试是**笔试**，全部为客观题（选择题/判断题），每道题有明确的正误判定。"
                "请严格按照 0-10 分制评分：overall_score = 答对率 × 10（如答对 16/20 题则 overall_score = 8.0）。"
                "score_breakdown 中各维度（technical/logic/depth/communication）也使用 0-10 分制。",
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

    def _parse_question(self, raw: Optional[str], num: int, round_name: str = "", profile: dict = None, used_questions: set = None) -> dict:
        if not raw:
            return self._make_fallback(num, round_name, profile, used_questions)

        raw = self._repair_json_newlines(raw)

        try:
            data = json.loads(raw)
            if "question" in data:
                if round_name == "written":
                    return self._validate_written_question(data, num, profile, used_questions)
                return data
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    if "question" in data:
                        if round_name == "written":
                            return self._validate_written_question(data, num, profile, used_questions)
                        return data
                except json.JSONDecodeError:
                    pass
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.startswith("{") and not l.startswith("}")]
        if round_name == "written":
            return self._make_written_fallback(num, profile, used_questions)
        question_text = lines[0] if lines else f"请结合你的项目经验，谈谈你在 {num} 个项目中的技术挑战和解决方案。"
        return {"question": question_text, "type": "技术", "difficulty": "medium", "topic": "综合", "expected_points": []}

    @staticmethod
    def _repair_json_newlines(text: str) -> str:
        """修复 AI 输出中 JSON 字符串内的真实换行符 → \\n 转义序列"""
        result = []
        in_str = False
        for ch in text:
            if ch == '"':
                in_str = not in_str
            if in_str and ch == '\n':
                result.append('\\n')
            else:
                result.append(ch)
        return ''.join(result)

    def _validate_written_question(self, data: dict, num: int, profile: dict = None, used_questions: set = None) -> dict:
        """校验笔试题目必须包含 options 字段，不符合则返回备选题"""
        options = data.get("options")
        if options and isinstance(options, dict) and len(options) >= 2:
            return data
        logger.warning(f"笔试第{num}题缺少 options 字段，使用备选题。原始数据: {json.dumps(data, ensure_ascii=False)[:200]}")
        return self._make_written_fallback(num, profile, used_questions)

    def _make_written_fallback(self, num: int, profile: dict = None, used_questions: set = None) -> dict:
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

        # 过滤已使用的题目，避免重复
        if used_questions:
            available = [q for q in pool if q["question"] not in used_questions]
            if available:
                pool = available

        return pool[(num - 1) % len(pool)]

    def _make_fallback(self, num: int, round_name: str = "", profile: dict = None, used_questions: set = None) -> dict:
        if round_name == "written":
            return self._make_written_fallback(num, profile, used_questions)
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

        # 0. 清理：去除 markdown 代码围栏 ```json ``` 及 BOM
        cleaned = raw.strip()
        cleaned = re.sub(r'^```(?:json|JSON)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip().lstrip('\ufeff')
        cleaned = self._repair_json_newlines(cleaned)

        # 1. 尝试完整 JSON 解析
        try:
            data = json.loads(cleaned)
            return {**default, **data}
        except json.JSONDecodeError:
            pass

        # 2. 尝试提取 JSON 块（兼容围栏去除后仍有杂音的情况）
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            candidate = match.group()
            # 修复常见 JSON 问题：尾随逗号
            candidate = re.sub(r',\s*}', '}', candidate)
            candidate = re.sub(r',\s*]', ']', candidate)
            logger.info("JSON块提取(前300字): %s", candidate[:300])
            try:
                data = json.loads(candidate)
                return {**default, **data}
            except json.JSONDecodeError as e:
                logger.info("JSON块解析失败: %s", str(e)[:100])

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

        # 4. 文本提取评分 + 自然语言抽取评语
        result = {**default, **scores}

        def _extract_text_block(text, keywords, block_pattern):
            """按关键词列表依次匹配，返回第一个匹配的文本块"""
            for kw in keywords:
                m = re.search(block_pattern(kw), text)
                if m:
                    return m.group(1).strip()
            return None

        def _extract_list_items(text, keywords):
            """按关键词列表查找列表项（- / * 开头的行）"""
            for kw in keywords:
                block = re.search(
                    rf'{kw}[：:]\s*([\s\S]+?)(?=(?:\n\s*(?:不足|改进|建议|Improvements|improvements|建议|参考回答|Reference|优势|优点|Strengths|总结|综合评价))|$)',
                    text
                )
                if block:
                    items = re.findall(r'[-\u2022*]\s*(.+?)(?=[\n]|$)', block.group(1))
                    if items:
                        return [i.strip().rstrip('。') for i in items if i.strip()]
                    parts = re.split(r'[；;、，]', block.group(1).strip())
                    return [p.strip() for p in parts if p.strip()]
            return []

        # 提取 summary
        summary_kw = ['综合评价', '总结', '总体评价', 'Summary', 'summary']
        summary_val = _extract_text_block(cleaned, summary_kw,
            lambda kw: rf'{kw}[：:]\s*([^。\n]+(?:[^。\n]*[。]?))')
        if summary_val:
            result["summary"] = summary_val

        # 提取 strengths
        result["strengths"] = _extract_list_items(cleaned,
            ['优点', '优势', 'Strengths', 'strengths'])

        # 提取 improvements
        result["improvements"] = _extract_list_items(cleaned,
            ['改进', '建议', 'Improvements', 'improvements'])

        # 提取 reference_answer
        ref_kw = ['参考回答', '参考答案', 'Reference', 'reference', '参考']
        ref_val = _extract_text_block(cleaned, ref_kw,
            lambda kw: rf'{kw}[：:]\s*([\s\S]+?)(?=(?:\n\s*(?:$|\n\s*(?:优点|优势|不足|改进|建议|总结|综合评价|\d+\s*分)))|$)')
        if ref_val:
            result["reference_answer"] = ref_val

        if scores:
            # 把空字符串的 comment 也填一份 summary 的摘要
            for key in ("technical_comment", "logic_comment", "depth_comment", "communication_comment"):
                if not result.get(key) and result.get("summary"):
                    result[key] = result["summary"][:50]

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
