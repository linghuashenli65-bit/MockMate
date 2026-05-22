"""面试官角色配置模块

管理面试官角色的创建、编辑、删除和查询。
每个面试官有独立的角色定位、风格和考察重点。
支持行为建模：侵略性、追问深度、打断概率等。
"""
import uuid
import logging
from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class InterviewStage(str, Enum):
    """面试阶段

    真实面试的典型流程：
    破冰 → 简历确认 → 技术广度 → 技术深挖 → 项目拷打 → 场景压力 → HR → 反问 → 收尾
    """
    INTRO = "intro"               # 破冰/自我介绍
    RESUME = "resume"             # 简历确认
    GENERAL_TECH = "general_tech"  # 技术广度
    DEEP_DIVE = "deep_dive"       # 技术深挖
    PROJECT = "project"           # 项目拷打
    PRESSURE = "pressure"         # 场景压力
    HR = "hr"                     # HR 面
    QNA = "qna"                   # 反问环节
    END = "end"                   # 收尾


# 阶段顺序（用于自动推进）
_STAGE_ORDER = [
    InterviewStage.INTRO,
    InterviewStage.RESUME,
    InterviewStage.GENERAL_TECH,
    InterviewStage.DEEP_DIVE,
    InterviewStage.PROJECT,
    InterviewStage.PRESSURE,
    InterviewStage.HR,
    InterviewStage.QNA,
    InterviewStage.END,
]

# 各阶段中文描述
_STAGE_DESC = {
    InterviewStage.INTRO: "破冰与自我介绍",
    InterviewStage.RESUME: "简历细节确认",
    InterviewStage.GENERAL_TECH: "技术广度考察",
    InterviewStage.DEEP_DIVE: "技术深度挖掘",
    InterviewStage.PROJECT: "项目经验拷问",
    InterviewStage.PRESSURE: "场景压力测试",
    InterviewStage.HR: "HR 综合素质面",
    InterviewStage.QNA: "候选人反问环节",
    InterviewStage.END: "面试收尾",
}

# 各阶段的主导面试官角色类型
_STAGE_LEAD_ROLES = {
    InterviewStage.INTRO: ["HR 负责人", "资深工程师"],
    InterviewStage.RESUME: ["资深工程师", "技术总监"],
    InterviewStage.GENERAL_TECH: ["资深工程师", "算法专家"],
    InterviewStage.DEEP_DIVE: ["算法专家", "资深工程师"],
    InterviewStage.PROJECT: ["业务负责人", "技术总监"],
    InterviewStage.PRESSURE: ["算法专家", "业务负责人"],
    InterviewStage.HR: ["HR 负责人"],
    InterviewStage.QNA: ["技术总监", "HR 负责人"],
    InterviewStage.END: ["HR 负责人"],
}

# 默认 prompt 模板
# 注意：{behavior_desc} 由 render_prompt 根据行为属性自动生成
DEFAULT_PROMPT_TEMPLATE = """你是一位{role}，面试风格{style}。
你的核心考察方向是：{focus_area}。

{behavior_desc}

你的任务是作为面试官，根据候选人的简历、岗位要求以及之前的对话历史，提出有针对性的面试问题。你的每个问题都要体现你的角色特征和考察重点。

注意事项：
- 保持{style}的风格
- 聚焦考察{focus_area}
- {follow_up_rule}
- 不要重复其他面试官已经问过的内容
- 问题要简短自然（不超过40字），用口语化的方式提问，就像真实的面对面面试
- 不要一次性问多个问题"""


class InterviewerConfig(BaseModel):
    """面试官角色配置

    行为属性说明：
    - aggressiveness (0~1): 攻击性。越高越倾向 challenge、质疑、施压
    - follow_up_depth (0~1): 追问深度。越高越倾向连续深挖不换人
    - interruption_rate (0~1): 打断概率。越高越倾向插话抢问
    - preferred_stages: 偏好的面试阶段列表
    """
    id: str = ""
    name: str
    role: str
    style: str
    focus_area: Union[str, list[str]]
    prompt_template: Optional[str] = None
    voice_style: Optional[str] = None

    # 行为建模属性
    aggressiveness: float = 0.5
    follow_up_depth: float = 0.5
    interruption_rate: float = 0.1
    preferred_stages: Optional[list[str]] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("角色名称不能为空")
        return v.strip()

    @field_validator("aggressiveness")
    @classmethod
    def aggressiveness_range(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("aggressiveness 必须在 0~1 之间")
        return v

    @field_validator("follow_up_depth")
    @classmethod
    def follow_up_range(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("follow_up_depth 必须在 0~1 之间")
        return v

    @field_validator("interruption_rate")
    @classmethod
    def interruption_range(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("interruption_rate 必须在 0~1 之间")
        return v

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.prompt_template:
            self.prompt_template = DEFAULT_PROMPT_TEMPLATE

    def render_prompt(self, resume: str = "", profile: dict = None) -> str:
        """将 prompt 模板与运行时上下文结合，生成完整 prompt"""
        focus_str = (
            "、".join(self.focus_area)
            if isinstance(self.focus_area, list)
            else self.focus_area
        )

        # 根据行为属性生成个性化行为描述
        behavior_parts = []
        if self.aggressiveness >= 0.7:
            behavior_parts.append("你会挑战候选人的回答，指出漏洞和不足，施加专业压力")
        elif self.aggressiveness >= 0.4:
            behavior_parts.append("你会适当追问，对模糊回答保持怀疑态度")
        else:
            behavior_parts.append("你态度温和，以引导和鼓励为主")

        if self.follow_up_depth >= 0.7:
            behavior_parts.append("你喜欢在一个话题上深挖到底，连续追问直到满意为止")
        elif self.follow_up_depth >= 0.4:
            behavior_parts.append("你会根据回答质量决定是否追问，不轻易放过关键点")
        else:
            behavior_parts.append("你倾向于快速切换话题，保持面试节奏")

        if self.interruption_rate >= 0.5:
            behavior_parts.append("你会打断啰嗦或偏离方向的回答，把话题拉回正轨")
        else:
            behavior_parts.append("你会耐心听完候选人的完整回答再提问")

        behavior_desc = "你的面试风格：\n- " + "\n- ".join(behavior_parts)

        # 追问深度规则
        if self.follow_up_depth >= 0.6:
            follow_up_rule = "如果候选人的回答不够深入或关键点没讲透，必须连续追问深挖，最多可在同一话题追问2-3轮再考虑换方向"
        elif self.follow_up_depth >= 0.3:
            follow_up_rule = "根据候选人的回答质量自然追问，浅了追问深挖，到位了换话题继续"
        else:
            follow_up_rule = "每个话题最多追问一次，快速覆盖更多考察点"

        return self.prompt_template.format(
            role=self.role,
            style=self.style,
            focus_area=focus_str,
            behavior_desc=behavior_desc,
            follow_up_rule=follow_up_rule,
        )

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "style": self.style,
            "focus_area": self.focus_area,
            "prompt_template": self.prompt_template,
            "voice_style": self.voice_style,
            "aggressiveness": self.aggressiveness,
            "follow_up_depth": self.follow_up_depth,
            "interruption_rate": self.interruption_rate,
            "preferred_stages": self.preferred_stages,
        }


class InterviewerManager:
    """面试官管理器，管理多个面试官角色"""

    def __init__(self):
        self._interviewers: dict[str, InterviewerConfig] = {}

    def add_interviewer(
        self,
        name: str,
        role: str,
        style: str,
        focus_area: Union[str, list[str]],
        prompt_template: Optional[str] = None,
        voice_style: Optional[str] = None,
        aggressiveness: float = 0.5,
        follow_up_depth: float = 0.5,
        interruption_rate: float = 0.1,
        preferred_stages: Optional[list[str]] = None,
    ) -> InterviewerConfig:
        """添加面试官"""
        config = InterviewerConfig(
            name=name,
            role=role,
            style=style,
            focus_area=focus_area,
            prompt_template=prompt_template,
            voice_style=voice_style,
            aggressiveness=aggressiveness,
            follow_up_depth=follow_up_depth,
            interruption_rate=interruption_rate,
            preferred_stages=preferred_stages,
        )
        self._interviewers[config.id] = config
        logger.info(f"添加面试官: {config.name}({config.role}) id={config.id}")
        return config

    def remove_interviewer(self, interviewer_id: str) -> bool:
        """删除面试官"""
        if interviewer_id in self._interviewers:
            removed = self._interviewers.pop(interviewer_id)
            logger.info(f"删除面试官: {removed.name}")
            return True
        return False

    def update_interviewer(self, interviewer_id: str, **kwargs) -> Optional[InterviewerConfig]:
        """更新面试官配置"""
        config = self._interviewers.get(interviewer_id)
        if not config:
            logger.warning(f"面试官不存在: {interviewer_id}")
            return None
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        logger.info(f"更新面试官: {config.name}")
        return config

    def list_interviewers(self) -> list[InterviewerConfig]:
        """列出所有面试官"""
        return list(self._interviewers.values())

    def get_interviewer(self, interviewer_id: str) -> Optional[InterviewerConfig]:
        """获取单个面试官"""
        return self._interviewers.get(interviewer_id)

    def has_interviewers(self) -> bool:
        """是否有至少一位面试官"""
        return len(self._interviewers) > 0

    def clear(self):
        """清空所有面试官"""
        self._interviewers.clear()
