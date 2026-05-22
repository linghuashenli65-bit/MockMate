"""TDD Cycle 4: API 端点和 WebSocket 通信测试"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestMockInterviewAPI:
    """Mock Interview API 端点测试"""

    def test_mock_interview_models(self):
        """请求/响应模型正确定义"""
        from backend.mock_interview.api_models import (
            MockInterviewStartRequest,
            MockInterviewStartResponse,
            MockInterviewAnswerRequest,
            MockInterviewAnswerResponse,
        )

        req = MockInterviewStartRequest(interviewer_ids=["id1", "id2"])
        assert len(req.interviewer_ids) == 2
        assert req.max_duration == 40

        req2 = MockInterviewStartRequest(interviewer_ids=["id1"], max_duration=30)
        assert req2.max_duration == 30

    def test_mock_interview_models_require_interviewers(self):
        """至少需要一位面试官ID"""
        from backend.mock_interview.api_models import MockInterviewStartRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MockInterviewStartRequest(interviewer_ids=[])

    def test_mock_interview_answer_model(self):
        """回答提交模型"""
        from backend.mock_interview.api_models import MockInterviewAnswerRequest

        req = MockInterviewAnswerRequest(
            session_id="test123",
            answer="我的回答内容",
            elapsed_minutes=10,
        )
        assert req.session_id == "test123"
        assert req.answer == "我的回答内容"

    def test_websocket_message_protocol(self):
        """WebSocket 消息协议定义"""
        from backend.mock_interview.api_models import (
            WSMessage,
            WSQuestionMessage,
            WSEvaluationMessage,
            WSEndMessage,
        )

        q_msg = WSQuestionMessage(
            type="question",
            question_text="请介绍一下你的项目经历",
            interviewer_name="张工",
        )
        assert q_msg.type == "question"
        assert q_msg.interviewer_name == "张工"

        eval_msg = WSEvaluationMessage(
            type="evaluation",
            score=85,
            evaluation="回答清晰",
        )
        assert eval_msg.score == 85

        end_msg = WSEndMessage(
            type="end",
            reason="time_limit",
            total_questions=5,
        )
        assert end_msg.reason == "time_limit"

    def test_websocket_message_serialization(self):
        """WebSocket 消息可以序列化为 JSON"""
        from backend.mock_interview.api_models import WSQuestionMessage

        msg = WSQuestionMessage(
            type="question",
            question_text="测试问题",
            interviewer_name="张工",
        )
        data = msg.model_dump()
        assert data["type"] == "question"
        assert data["question_text"] == "测试问题"

    @pytest.mark.asyncio
    async def test_mock_interview_router_initialization(self):
        """路由处理器可以初始化"""
        from backend.mock_interview.api_router import MockInterviewRouter

        ai_mock = MagicMock()
        router = MockInterviewRouter(ai_client=ai_mock)
        assert router is not None
        assert router.sessions == {}

    @pytest.mark.asyncio
    async def test_create_session(self):
        """可以创建 Mock 面试会话"""
        from backend.mock_interview.api_router import MockInterviewRouter
        from backend.mock_interview.interviewer_config import InterviewerConfig

        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "测试问题", "difficulty": "medium"}')

        router = MockInterviewRouter(ai_client=ai_mock)

        gong = InterviewerConfig(id="iv1", name="张工", role="工程师", style="严谨", focus_area="编码")

        result = await router.create_session(
            interviewer_configs=[gong],
            resume="简历内容",
            profile={"position": "后端"},
        )
        assert result["session_id"] is not None
        assert result["question_text"] is not None
        assert result["interviewer_name"] == "张工"

    @pytest.mark.asyncio
    async def test_handle_answer(self):
        """可以处理回答并返回下一题"""
        from backend.mock_interview.api_router import MockInterviewRouter
        from backend.mock_interview.interviewer_config import InterviewerConfig

        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "下一题", "difficulty": "medium"}')
        ai_mock.chat = AsyncMock(return_value='{"score": 85, "evaluation": "好"}')

        router = MockInterviewRouter(ai_client=ai_mock)

        gong = InterviewerConfig(id="iv1", name="张工", role="工程师", style="严谨", focus_area="编码")
        result = await router.create_session([gong], "", {})

        answer_result = await router.handle_answer(
            session_id=result["session_id"],
            answer="我的回答",
        )
        assert answer_result["answer_recorded"] is True
        assert "next_question" in answer_result or "completed" in answer_result

    @pytest.mark.asyncio
    async def test_end_session(self):
        """可以结束面试会话"""
        from backend.mock_interview.api_router import MockInterviewRouter
        from backend.mock_interview.interviewer_config import InterviewerConfig

        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "测试", "difficulty": "medium"}')

        router = MockInterviewRouter(ai_client=ai_mock)
        gong = InterviewerConfig(id="iv1", name="张工", role="工程师", style="严谨", focus_area="编码")
        result = await router.create_session([gong], "", {})

        end_result = await router.end_session(result["session_id"])
        assert end_result["completed"] is True
        assert end_result["total_questions"] >= 1

    @pytest.mark.asyncio
    async def test_get_session_state(self):
        """可以获取会话状态"""
        from backend.mock_interview.api_router import MockInterviewRouter
        from backend.mock_interview.interviewer_config import InterviewerConfig

        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "测试", "difficulty": "medium"}')

        router = MockInterviewRouter(ai_client=ai_mock)
        gong = InterviewerConfig(id="iv1", name="张工", role="工程师", style="严谨", focus_area="编码")
        result = await router.create_session([gong], "", {})

        state = await router.get_session_state(result["session_id"])
        assert state is not None
        assert state["phase"] is not None

    def test_invalid_session_raises_error(self):
        """无效的 session_id 返回错误"""
        from backend.mock_interview.api_router import MockInterviewRouter

        ai_mock = MagicMock()
        router = MockInterviewRouter(ai_client=ai_mock)

        with pytest.raises(ValueError, match="会话不存在"):
            router.get_session("invalid_id")
