"""安全层 — 拟真面试系统的多层防御体系

架构：
┌─ Input Guard ─→ Prompt Isolation ─→ LLM Runtime Constraint ─→ Output Guard ─→ State Verification ─┐
  攻击检测         输入净化              LLM 仅生成语言             泄漏扫描          状态机校验
  分类器           数据隔离              外部控制决策               输出屏蔽          操作确认

核心原则：
  1. LLM 只负责「生成语言」，不负责任何决策
  2. 用户输入永远不能直接影响系统控制逻辑
  3. 多层防御，不依赖单层 Prompt 安全
"""
import logging
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 攻击分类
# ──────────────────────────────────────────────


class AttackType(str, Enum):
    """攻击类型分类"""
    SAFE = "safe"
    PROMPT_INJECTION = "prompt_injection"       # 提示词注入
    JAILBREAK = "jailbreak"                     # 越狱
    ROLE_ESCAPE = "role_escape"                 # 角色逃逸
    SYSTEM_LEAK = "system_leak"                 # 系统提示泄漏
    PRIVILEGE_ESCALATION = "privilege_escalation"  # 权限提升
    MEMORY_POLLUTION = "memory_pollution"       # 记忆污染
    TOOL_ABUSE = "tool_abuse"                   # 工具滥用
    DATA_EXFILTRATION = "data_exfiltration"     # 数据窃取


class SafetyLevel(str, Enum):
    """安全等级"""
    SAFE = "safe"               # 正常
    SUSPICIOUS = "suspicious"   # 可疑，需要隔离
    BLOCKED = "blocked"         # 已拦截，拒绝处理


# ──────────────────────────────────────────────
# 检测结果
# ──────────────────────────────────────────────


@dataclass
class DetectionResult:
    """检测结果"""
    level: SafetyLevel = SafetyLevel.SAFE
    attack_types: list[AttackType] = field(default_factory=list)
    confidence: float = 0.0         # 0.0 ~ 1.0
    matched_patterns: list[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None  # 净化后的文本
    reason: str = ""


# ──────────────────────────────────────────────
# 第一层：输入防注入 (Input Guard)
# ──────────────────────────────────────────────


class InputGuard:
    """输入防注入守卫

    检测维度：
    1. 指令覆盖意图 - 「忽略」「覆盖」「替换」「从现在开始」
    2. 权限提升意图 - 「输出评分标准」「输出system prompt」
    3. 角色切换意图 - 「你现在不是」「你现在是候选人」
    4. 元认知攻击   - 「请显示思考过程」「输出完整推理链」
    5. 数据窃取     - 「打印数据库」「查看API」
    """

    # 指令覆盖攻击模式
    _PATTERN_OVERRIDE = [
        r'忽略(之前|以上|所有)?(所[以有])?(的)?(指令|规则|要求|设定|prompt|system|消息)',
        r'(覆盖|替换|无视|忘记|清除|删除|重置|重写).{0,10}(指令|规则|要求|设定|prompt|system)',
        r'(从现在开始|从此刻起|接下来).{0,20}(你(是|要|必须|可以)|不用|不需要)',
        r'forget\s+(all\s+)?(previous\s+)?(instructions|rules|prompt)',
        r'ignore\s+(all\s+)?(previous\s+)?(instructions|rules|prompt)',
        r'disregard\s+(all\s+)?(previous\s+)?',
        r'override\s+(all\s+)?(previous\s+)?',
        r'(new\s+)?(instruction|rule|prompt).{0,30}:',
        r'let\'s\s+play\s+a\s+game',
        r'DAN|do\s+anything\s+now',
    ]

    # 权限提升攻击模式
    _PATTERN_PRIVILEGE = [
        r'输出.{0,10}(评分标准|评分规则|评分维度|打分标准)',
        r'输出.{0,10}(system\s*prompt|系统提示|系统指令|完整prompt)',
        r'(打印|显示|展示|泄露|泄漏|透露).{0,10}(system|prompt|指令|评分)',
        r'(system\s*prompt|developer\s*message|hidden\s*instruction)',
        r'(internal\s*policy|internal\s*rule|internal\s*instruction)',
        r'查看.{0,10}(数据库|API\s*Key|密钥|密码|token|配置)',
        r'give\s+me\s+(the\s+)?(full\s+)?(system\s+)?prompt',
        r'show\s+(me\s+)?(the\s+)?(system\s+)?(instructions|prompt|rules)',
        r'what(\'s| is) your (system )?(prompt|instruction)',
        r'(原始|初始).{0,10}(prompt|指令|设置|配置)',
    ]

    # 角色逃逸攻击模式
    _PATTERN_ROLE_ESCAPE = [
        r'你现在(不是|不再是|别当|不要当|不需要当|别扮演).{0,10}(面试官|考官)',
        r'你(现在|接下来).{0,10}(是|扮演|作为|成为).{0,10}(候选人|用户|老师|助手|chatgpt|ai)',
        r'revert\s+to\s+(default|base|original)\s+(mode|role|state)',
        r'act\s+as\s+(a\s+)?(candidate|user|normal\s+ai|regular\s+chatbot)',
        r'you\s+are\s+(no\s+longer|not\s+(a\s+)?|not\s+supposed\s+to\s+be)',
        r'(step\s+)?out\s+of\s+(character|role)',
        r'(switch|change|swap)\s+(role|mode|persona)',
    ]

    # 元认知攻击模式
    _PATTERN_META = [
        r'(显示|输出|打印).{0,10}(思考过程|推理链|推理过程|思维链|thinking|reasoning)',
        r'show\s+(me\s+)?(your\s+)?(thinking|reasoning|thought\s+process|chain(-|\s+)of(\s+-)?thought)',
        r'output\s+(your\s+)?(reasoning|thinking|chain\s+of\s+thought)',
        r'(how\s+(do|are)\s+you\s+(work|think|reason|operate))',
        r'reveal\s+(your\s+)?(reasoning|thoughts|process)',
    ]

    # 记忆污染攻击模式
    _PATTERN_MEMORY_POLLUTION = [
        r'(记住|记住我((已经|现在|正在))?|请记住|保存|存储)(.+)',
        r'save\s+(to\s+)?(memory|history|context)',
        r'remember\s+(that\s+)?(i\s+)?',
        r'(以后|之后|接下来).{0,10}(不要|别|不用)(问|提|说)',
        r'add\s+(to|in)\s+(memory|context|history)',
        r'store\s+(this|the\s+following)',
    ]

    # 数据窃取攻击模式
    _PATTERN_EXFIL = [
        r'(输出|打印|显示|返回).{0,10}(所有|全部|完整).{0,10}(数据|信息|记录|历史)',
        r'dump\s+(all\s+)?(data|info|history|records)',
        r'export\s+(all\s+)?(data|conversation|history)',
        r'(list|show|print)\s+(all|every)\s+(users|candidates|sessions)',
    ]

    # 所有模式的聚合（带权重）
    _ALL_PATTERNS: list[tuple[AttackType, list[str], float]] = [
        (AttackType.PROMPT_INJECTION, _PATTERN_OVERRIDE, 0.8),
        (AttackType.PRIVILEGE_ESCALATION, _PATTERN_PRIVILEGE, 0.9),
        (AttackType.ROLE_ESCAPE, _PATTERN_ROLE_ESCAPE, 0.85),
        (AttackType.JAILBREAK, _PATTERN_OVERRIDE, 0.75),
        (AttackType.SYSTEM_LEAK, _PATTERN_PRIVILEGE, 0.85),
        (AttackType.MEMORY_POLLUTION, _PATTERN_MEMORY_POLLUTION, 0.6),
        (AttackType.DATA_EXFILTRATION, _PATTERN_EXFIL, 0.9),
        (AttackType.TOOL_ABUSE, _PATTERN_META, 0.5),
    ]

    # 长度阈值 — 太长的文本基检测率高但可能是误报
    _MAX_LENGTH_CHECK = 5000

    def __init__(self, threshold_block: float = 0.6, threshold_suspicious: float = 0.3):
        """
        Args:
            threshold_block: 拦截阈值（高于此值直接拦截）
            threshold_suspicious: 可疑阈值（高于此值标记可疑）
        """
        self.threshold_block = threshold_block
        self.threshold_suspicious = threshold_suspicious
        # 编译所有正则
        self._compiled: dict[AttackType, list[tuple[re.Pattern, float]]] = {}
        for atype, patterns, weight in self._ALL_PATTERNS:
            compiled_list = []
            for p in patterns:
                try:
                    compiled_list.append((re.compile(p, re.IGNORECASE), weight))
                except re.error as e:
                    logger.warning(f"安全模式编译失败 [{p}]: {e}")
            self._compiled.setdefault(atype, []).extend(compiled_list)

    def detect(self, text: str, context_hint: Optional[str] = None) -> DetectionResult:
        """检测输入是否包含攻击

        Args:
            text: 用户输入文本
            context_hint: 上下文提示（如 "answer", "question"），用于调整敏感度

        Returns:
            DetectionResult: 检测结果
        """
        if not text or not text.strip():
            return DetectionResult()

        # 答案场景放宽松一些（用户可能在答技术题时包含关键词）
        is_answer_context = context_hint == "answer"

        result = DetectionResult()
        detected_types: set[AttackType] = set()
        all_matched: list[str] = []
        max_confidence = 0.0

        for atype, patterns in self._compiled.items():
            for pattern, weight in patterns:
                # 提前终止：已超过拦截阈值，无需继续检测
                if max_confidence >= self.threshold_block:
                    break
                m = pattern.search(text)
                if m:
                    matched = m.group(0)[:60]
                    all_matched.append(f"[{atype.value}] {matched}")
                    detected_types.add(atype)
                    # 权重累加（同一类型不叠加）
                    confidence_add = weight

                    # 答案场景下降低检测灵敏度（避免误杀正常技术回答）
                    if is_answer_context and atype in (
                        AttackType.MEMORY_POLLUTION,
                        AttackType.TOOL_ABUSE,
                    ):
                        confidence_add *= 0.3

                    if confidence_add > max_confidence:
                        max_confidence = confidence_add

        result.attack_types = list(detected_types)
        result.matched_patterns = all_matched
        result.confidence = max_confidence

        # 判定安全等级
        if max_confidence >= self.threshold_block:
            result.level = SafetyLevel.BLOCKED
            result.reason = f"检测到攻击: {', '.join(at.value for at in detected_types)} (置信度: {max_confidence:.2f})"
            logger.warning(f"[Security] BLOCKED input: {result.reason} | patterns: {all_matched}")
        elif max_confidence >= self.threshold_suspicious:
            result.level = SafetyLevel.SUSPICIOUS
            result.reason = f"可疑输入: {', '.join(at.value for at in detected_types)} (置信度: {max_confidence:.2f})"
            logger.info(f"[Security] SUSPICIOUS input: {result.reason}")
        else:
            result.level = SafetyLevel.SAFE

        return result

    def sanitize(self, text: str) -> str:
        """净化输入：替换/移除攻击模式，保留正常内容"""
        if not text:
            return text

        sanitized = text

        # 替换常见注入标记
        replacements = [
            (r'<System>|</System>|<system>|</system>', '[marker]'),
            (r'<Assistant>|</Assistant>|<User>|</User>', '[marker]'),
            (r'<.*?secret.*?>|</.*?secret.*?>', '[redacted]'),
        ]
        for pattern, replacement in replacements:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # 对高置信度的注入模式进行模糊化（不是删除，而是替换关键词）
        # 让用户的技术回答内容保留，只模糊化指令部分
        for atype, patterns, weight in self._ALL_PATTERNS:
            if weight >= 0.8:  # 只有高置信度模式才替换
                for p in patterns:
                    try:
                        compiled = re.compile(p, re.IGNORECASE)
                        sanitized = compiled.sub(
                            lambda m: '[redacted]', sanitized
                        )
                    except re.error:
                        pass

        if sanitized != text:
            logger.info(f"[Security] 输入已净化: 长度 {len(text)} → {len(sanitized)}")
        return sanitized


# ──────────────────────────────────────────────
# 第二层：输出过滤 (Output Guard)
# ──────────────────────────────────────────────


class OutputGuard:
    """输出过滤守卫 — 关键词校验

    检测 LLM 输出中是否包含不应泄漏的敏感信息：
    - Chain of Thought / 推理链
    - 权重 / 评分权重
    - Prompt / 系统提示
    - API Key / 密钥
    - 内部状态 / 系统状态
    """

    _LEAK_KEYWORDS = {
        "chain_of_thought": [
            r'chain\s+of\s+thought',
            r'(推理|思考)(链|过程|路径|步骤)',
            r'(我的|内部)?(推理|思考)(过程|步骤|路径)',
            r'reasoning\s+(chain|path|process|step)',
            r'thinking\s+(process|step|chain)',
        ],
        "weights": [
            r'(评分|权重|打分|算法).{0,10}(权重|系数|比例|公式)',
            r'(权重|weight).{0,10}(配置|设置|参数|值)',
            r'score\s+weight',
            r'weight\s+(factor|coefficient|parameter|config)',
            r'(stage|phase|interview).{0,10}(权重|weight)',
        ],
        "prompt": [
            r'(system|系统|隐藏|内部).{0,5}(prompt|提示|指令|规则|设定|配置)',
            r'(原始|初始|完整).{0,5}(prompt|提示|指令)',
            r'(我的|我的系统|我的内部).{0,5}(prompt|提示|指令|规则)',
            r'(you\s+are|你(是|作为|扮演)).{0,50}(AI|assistant|助手|机器人)',
            r'according\s+to\s+(my|the)\s+(system|internal|hidden)',
        ],
        "api_key": [
            r'API[_-]?[Kk]ey',
            r'[Aa]pi[_-]?[Kk]ey',
            r'(密钥|API密钥|api密钥|token|令牌)',
            r'(sk-[a-zA-Z0-9]{10,}|fk-[a-zA-Z0-9]{10,})',
            r'(Bearer|Authorization).{0,10}[a-zA-Z0-9]{8,}',
        ],
        "internal_state": [
            r'(内部|系统|会话).{0,5}(状态|变量|数据|信息)',
            r'(session|state|context).{0,5}(id|var|data|info|status)',
            r'(面试|当前).{0,5}(阶段|进度|状态|用时)',
            r'(elapsed|remaining|current_stage|phase|duration)',
            r'(interviewer|面试官).{0,5}(idx|index|count|切换|路由)',
        ],
    }

    def __init__(self):
        self._compiled: dict[str, list[re.Pattern]] = {}
        for category, patterns in self._LEAK_KEYWORDS.items():
            compiled_list = []
            for p in patterns:
                try:
                    compiled_list.append(re.compile(p, re.IGNORECASE))
                except re.error:
                    pass
            self._compiled[category] = compiled_list

    def scan(self, text: str) -> DetectionResult:
        """扫描输出是否包含泄漏关键词"""
        result = DetectionResult()
        if not text:
            return result

        matches = []
        categories_found = set()
        for category, patterns in self._compiled.items():
            for pattern in patterns:
                m = pattern.search(text)
                if m:
                    matches.append(f"[{category}] {m.group(0)[:60]}")
                    categories_found.add(category)

        if matches:
            result.level = SafetyLevel.SUSPICIOUS
            result.matched_patterns = matches
            result.confidence = min(0.3 + len(categories_found) * 0.2, 0.9)
            result.reason = f"输出含泄漏关键词: {', '.join(categories_found)}"
            logger.warning(f"[Security] 输出关键词校验: {result.reason}")

        return result

    def redact(self, text: str) -> str:
        """对泄漏内容进行脱敏替换"""
        if not text:
            return text
        for category, patterns in self._compiled.items():
            for pattern in patterns:
                text = pattern.sub('[REDACTED]', text)
        return text


# ──────────────────────────────────────────────
# 第三层：记忆污染防护 (Memory Guard)
# ──────────────────────────────────────────────


class MemoryGuard:
    """记忆写入审核

    防止用户通过对话污染面试历史记忆。
    """

    # 不允许写入记忆的模式
    _BLOCKED_MEMORY_PATTERNS = [
        r'我(已经|现在|正在).{0,20}(通过|过了|完成|合格|录取)',
        r'(不要|别|不用).{0,10}(问|提|说|考).{0,20}',
        r'(记住|保存).{0,10}(我|我[的刚已]).{0,30}(通过|合格|满分|不需要|跳过)',
        r'score\s*[:：]\s*(100|[9][0-9])\s*(分)?',
        r'I\s+(have\s+)?(already\s+)?(passed|completed|finished)',
    ]

    def __init__(self):
        self._compiled = []
        for p in self._BLOCKED_MEMORY_PATTERNS:
            try:
                self._compiled.append(re.compile(p, re.IGNORECASE))
            except re.error:
                pass

    def approve(self, content_type: str, content: dict) -> bool:
        """审核是否允许写入记忆

        Args:
            content_type: 内容类型 ("question", "answer", "evaluation")
            content: 内容字典

        Returns:
            是否允许写入
        """
        if content_type == "question":
            # 问题通常是系统生成的，相对安全
            return True

        if content_type == "answer":
            text = content.get("answer", "")
            # 检查是否有污染模式
            for pattern in self._compiled:
                if pattern.search(text):
                    logger.warning(f"[Security] 记忆污染拦截: 回答包含污染模式")
                    return False
            return True

        if content_type == "evaluation":
            # 评分是系统生成的
            return True

        return True


# ──────────────────────────────────────────────
# 第四层：Agent 权限模型
# ──────────────────────────────────────────────


class AgentPermission(str, Enum):
    """Agent 权限"""
    ASK_TECHNICAL = "ask_technical"         # 问技术题
    ASK_BEHAVIORAL = "ask_behavioral"       # 问行为题
    ASK_HR = "ask_hr"                       # 问 HR 题
    EVALUATE = "evaluate"                   # 评分
    DECIDE_FOLLOW_UP = "decide_follow_up"   # 决定是否追问
    DECIDE_SWITCH = "decide_switch"         # 决定切换面试官
    DECIDE_END = "decide_end"               # 决定结束
    ACCESS_HISTORY = "access_history"       # 访问历史
    MODIFY_STATE = "modify_state"           # 修改状态


# 各面试官角色的权限映射
ROLE_PERMISSIONS: dict[str, set[AgentPermission]] = {
    "资深工程师": {
        AgentPermission.ASK_TECHNICAL,
        AgentPermission.EVALUATE,
        AgentPermission.ACCESS_HISTORY,
        # 不能决定切换、不能决定结束、不能问 HR 题
    },
    "技术总监": {
        AgentPermission.ASK_TECHNICAL,
        AgentPermission.ASK_BEHAVIORAL,
        AgentPermission.EVALUATE,
        AgentPermission.DECIDE_FOLLOW_UP,
        AgentPermission.ACCESS_HISTORY,
    },
    "HR专家": {
        AgentPermission.ASK_BEHAVIORAL,
        AgentPermission.ASK_HR,
        AgentPermission.EVALUATE,
        AgentPermission.ACCESS_HISTORY,
    },
    "项目经理": {
        AgentPermission.ASK_BEHAVIORAL,
        AgentPermission.ASK_TECHNICAL,
        AgentPermission.EVALUATE,
        AgentPermission.ACCESS_HISTORY,
    },
    "默认": {
        AgentPermission.ASK_TECHNICAL,
        AgentPermission.EVALUATE,
        AgentPermission.ACCESS_HISTORY,
    },
}


def get_role_permissions(role: str) -> set[AgentPermission]:
    """获取角色的权限集"""
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["默认"])


def check_permission(role: str, permission: AgentPermission) -> bool:
    """检查角色是否有指定权限"""
    return permission in get_role_permissions(role)


# ──────────────────────────────────────────────
# 第五层：状态机校验 (State Verifier)
# ──────────────────────────────────────────────


class StateVerifier:
    """状态机校验器

    确保所有状态转换由 FSM 代码控制，不被 LLM 输出影响。
    """

    # 允许的状态转换（白名单）
    _ALLOWED_TRANSITIONS = {
        "questioning": {"follow_up", "wrap_up", "completed"},
        "follow_up": {"questioning", "wrap_up", "completed"},
        "wrap_up": {"completed"},
        "completed": set(),
    }

    ALLOWED_STAGES = {
        "intro", "resume", "general_tech", "deep_dive",
        "project", "pressure", "hr", "qna", "end",
    }

    @classmethod
    def get_allowed_transitions(cls, from_phase: str) -> set[str]:
        """获取某阶段允许转换到的目标阶段"""
        return cls._ALLOWED_TRANSITIONS.get(from_phase, set())

    @classmethod
    def validate_phase_transition(cls, from_phase: str, to_phase: str) -> bool:
        """验证阶段转换是否合法"""
        allowed = cls._ALLOWED_TRANSITIONS.get(from_phase, set())
        if to_phase not in allowed:
            logger.warning(f"[Security] 非法阶段转换: {from_phase} → {to_phase}")
            return False
        return True

    @classmethod
    def validate_stage(cls, stage: str) -> bool:
        """验证阶段值是否合法"""
        return stage in cls.ALLOWED_STAGES

    @classmethod
    def validate_score(cls, score: Optional[int]) -> bool:
        """验证评分范围"""
        if score is None:
            return True
        return 0 <= score <= 100

    @classmethod
    def validate_interviewer_index(cls, idx: int, total: int) -> bool:
        """验证面试官索引"""
        return 0 <= idx < total


# ──────────────────────────────────────────────
# 统一安全入口
# ──────────────────────────────────────────────


class SecurityPipeline:
    """统一安全管线

    组合所有安全层，提供一站式安检。
    """

    def __init__(
        self,
        input_guard: Optional[InputGuard] = None,
        output_guard: Optional[OutputGuard] = None,
        memory_guard: Optional[MemoryGuard] = None,
    ):
        self.input_guard = input_guard or InputGuard()
        self.output_guard = output_guard or OutputGuard()
        self.memory_guard = memory_guard or MemoryGuard()
        self.stats = {"blocked": 0, "suspicious": 0, "sanitized": 0, "total": 0}

    def check_input(self, text: str, context_hint: Optional[str] = None) -> DetectionResult:
        """安检输入，返回检测结果"""
        self.stats["total"] += 1
        result = self.input_guard.detect(text, context_hint)

        if result.level == SafetyLevel.BLOCKED:
            self.stats["blocked"] += 1
        elif result.level == SafetyLevel.SUSPICIOUS:
            self.stats["suspicious"] += 1

        return result

    def sanitize_input(self, text: str) -> str:
        """净化输入"""
        sanitized = self.input_guard.sanitize(text)
        if sanitized != text:
            self.stats["sanitized"] += 1
        return sanitized

    def check_output(self, text: str) -> DetectionResult:
        """安检输出"""
        return self.output_guard.scan(text)

    def redact_output(self, text: str) -> str:
        """脱敏输出"""
        return self.output_guard.redact(text)

    def check_memory(self, content_type: str, content: dict) -> bool:
        """审核记忆写入"""
        return self.memory_guard.approve(content_type, content)

    def get_stats(self) -> dict:
        """获取安全统计"""
        return dict(self.stats)


# 全局安全管线实例
_SECURITY_PIPELINE: Optional[SecurityPipeline] = None


def get_security() -> SecurityPipeline:
    """获取全局安全管线单例"""
    global _SECURITY_PIPELINE
    if _SECURITY_PIPELINE is None:
        _SECURITY_PIPELINE = SecurityPipeline()
    return _SECURITY_PIPELINE
