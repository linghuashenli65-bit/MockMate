"""API 请求/响应模型定义"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


# ==================== REST API 模型 ====================

class MockInterviewStartRequest(BaseModel):
    """启动拟真面试请求"""
    interviewer_ids: list[str]
    max_duration: int = 40
    wrap_up_threshold: int = 35
    enable_tts: bool = True
    resume: Optional[str] = None
    profile: Optional[dict] = None

    @field_validator("interviewer_ids")
    @classmethod
    def must_have_interviewers(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("interviewer_ids 不能为空")
        return v

    @field_validator("max_duration")
    @classmethod
    def valid_duration(cls, v: int) -> int:
        if v < 10 or v > 120:
            raise ValueError("面试时长应在 10-120 分钟之间")
        return v


class MockInterviewStartResponse(BaseModel):
    """启动拟真面试响应"""
    session_id: str
    question_text: str
    interviewer_name: str
    interviewer_index: int
    phase: str
    elapsed_minutes: int


class MockInterviewAnswerRequest(BaseModel):
    """提交回答请求"""
    session_id: str
    answer: str
    elapsed_minutes: Optional[int] = None
    enable_tts: Optional[bool] = None


class MockInterviewAnswerResponse(BaseModel):
    """提交回答响应"""
    answer_recorded: bool
    next_question_text: Optional[str] = None
    interviewer_name: Optional[str] = None
    interviewer_index: Optional[int] = None
    phase: Optional[str] = None
    elapsed_minutes: Optional[int] = None
    evaluation: Optional[dict] = None
    completed: Optional[bool] = None
    coverage: Optional[dict] = None
    total_questions: Optional[int] = None


class InterviewerCreateRequest(BaseModel):
    """创建面试官请求"""
    name: str
    role: str
    style: str
    focus_area: str | list[str]
    prompt_template: Optional[str] = None
    voice_style: Optional[str] = None
    # 行为建模属性
    aggressiveness: float = 0.5
    follow_up_depth: float = 0.5
    interruption_rate: float = 0.1
    preferred_stages: Optional[list[str]] = None


class InterviewerUpdateRequest(BaseModel):
    """更新面试官请求"""
    name: Optional[str] = None
    role: Optional[str] = None
    style: Optional[str] = None
    focus_area: Optional[str | list[str]] = None
    prompt_template: Optional[str] = None
    voice_style: Optional[str] = None
    # 行为建模属性
    aggressiveness: Optional[float] = None
    follow_up_depth: Optional[float] = None
    interruption_rate: Optional[float] = None
    preferred_stages: Optional[list[str]] = None


# ==================== WebSocket 消息模型 ====================

class WSMessage(BaseModel):
    """WebSocket 消息基类"""
    type: str


class WSQuestionMessage(WSMessage):
    """问题消息 — 服务端→客户端"""
    type: str = "question"
    question_text: str
    interviewer_name: str
    question_index: Optional[int] = None
    phase: Optional[str] = None
    elapsed_minutes: Optional[int] = None


class WSAudioMessage(WSMessage):
    """音频消息 — 服务端→客户端"""
    type: str = "audio"
    audio_data: str  # base64 编码的音频数据
    is_final: bool = False


class WSEvaluationMessage(WSMessage):
    """评估消息 — 服务端→客户端"""
    type: str = "evaluation"
    score: int
    evaluation: str
    suggestions: list[str] = []


class WSEndMessage(WSMessage):
    """结束消息 — 服务端→客户端"""
    type: str = "end"
    reason: str
    total_questions: int
    coverage: Optional[dict] = None


class WSErrorMessage(WSMessage):
    """错误消息 — 服务端→客户端"""
    type: str = "error"
    message: str
    code: str = "unknown"


class WSAnswerMessage(WSMessage):
    """回答消息 — 客户端→服务端"""
    type: str = "answer"
    text: str
    audio_data: Optional[str] = None


class WSTimeMessage(WSMessage):
    """时间消息 — 客户端→服务端"""
    type: str = "time_update"
    elapsed_minutes: int


class WSEndRequestMessage(WSMessage):
    """结束请求 — 客户端→服务端"""
    type: str = "end_request"
    reason: str = "user_request"


class WSHeartbeatMessage(WSMessage):
    """心跳消息"""
    type: str = "pong"
