"""TDD Cycle 3: MockInterviewEngine 核心流程测试"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestMockInterviewEngine:
    """MockInterviewEngine 核心流程测试"""

    def test_engine_initialization(self):
        """引擎可以初始化"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        ai_mock = MagicMock()
        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="精通Python",
            profile={"position": "后端开发"},
        )
        assert engine is not None
        assert len(engine.interviewers) == 1
        assert engine.state["phase"] == "questioning"

    def test_engine_requires_at_least_one_interviewer(self):
        """至少需要一位面试官"""
        from backend.mock_interview.mock_engine import MockInterviewEngine

        with pytest.raises(ValueError, match="至少需要一位面试官"):
            MockInterviewEngine(
                interviewers=[], ai_client=MagicMock(),
                resume="", profile={},
            )

    @pytest.mark.asyncio
    async def test_start_interview(self):
        """启动面试生成第一个问题"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="资深工程师", style="严谨深入", focus_area="编码能力")
        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "什么是装饰器?", "difficulty": "medium"}')

        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="精通Python",
            profile={"position": "后端开发"},
        )

        result = await engine.start()
        assert result["session_id"] is not None
        assert result["question"] is not None
        assert result["question_text"] is not None
        assert result["interviewer_name"] == "张工"
        assert result["phase"] == "questioning"

    @pytest.mark.asyncio
    async def test_submit_answer_and_get_next(self):
        """提交回答后获取下一题"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="资深工程师", style="严谨深入", focus_area="编码能力")
        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "什么是装饰器?", "difficulty": "medium"}')
        ai_mock.chat = AsyncMock(return_value='{"score": 85, "evaluation": "回答清晰", "suggestions": ["深入点"]}')

        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="精通Python",
            profile={"position": "后端开发"},
        )
        await engine.start()

        result = await engine.submit_answer("装饰器是高阶函数")
        assert result["answer_recorded"] is True
        assert "next_question" in result or "completed" in result

    @pytest.mark.asyncio
    async def test_multiple_interviewers_rotate(self):
        """多个面试官轮转"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        li = InterviewerConfig(name="李总", role="总监", style="开放", focus_area="架构")
        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "测试问题", "difficulty": "medium"}')

        engine = MockInterviewEngine(
            interviewers=[gong, li],
            ai_client=ai_mock,
            resume="", profile={},
        )
        await engine.start()
        current_name = engine.get_current_interviewer_name()
        assert current_name in ("张工", "李总")

    @pytest.mark.asyncio
    async def test_engine_respects_time_limit(self):
        """引擎在达到时间限制时结束"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        ai_mock = MagicMock()
        ai_mock.reason = AsyncMock(return_value='{"question": "测试", "difficulty": "medium"}')

        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="", profile={},
            max_duration=40,
        )
        # 模拟时间到达
        engine.state["elapsed_minutes"] = 40
        result = await engine.submit_answer("回答内容")
        assert result.get("completed") is True

    def test_get_coverage_report(self):
        """可以获取覆盖情况报告"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码能力")
        ai_mock = MagicMock()

        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="", profile={},
        )
        engine.state = engine._mark_topic_covered(engine.state, "编码能力")

        report = engine.get_coverage_report()
        assert report["covered"] == 1
        assert report["total"] == 1

    def test_engine_serialization(self):
        """引擎状态可以序列化保存和恢复"""
        from backend.mock_interview.mock_engine import MockInterviewEngine
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        ai_mock = MagicMock()

        engine = MockInterviewEngine(
            interviewers=[gong],
            ai_client=ai_mock,
            resume="简历内容",
            profile={"position": "后端"},
        )

        serialized = engine.serialize()
        assert serialized["session_id"] is not None
        assert len(serialized["interviewers"]) == 1

        restored = MockInterviewEngine.deserialize(serialized, ai_client=ai_mock)
        assert restored.state["session_id"] == engine.state["session_id"]
        assert restored.get_current_interviewer_name() == "张工"
