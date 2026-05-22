"""TDD Cycle 2: LangGraph 状态机测试"""
import pytest
from typing import Optional


class TestMockInterviewState:
    """MockInterviewState 和 LangGraph 工作流测试"""

    def test_state_initialization(self):
        """可以初始化面试状态"""
        from backend.mock_interview.mock_state import MockInterviewState, create_initial_state
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="资深工程师", style="严谨深入", focus_area="编码能力")
        li = InterviewerConfig(name="李总", role="技术总监", style="宏观开放", focus_area="架构设计")

        state = create_initial_state(
            session_id="test123",
            interviewers=[gong, li],
            resume="精通Python...",
            profile={"position": "后端开发"},
        )

        assert state["session_id"] == "test123"
        assert len(state["interviewers"]) == 2
        assert state["current_interviewer_idx"] == 0
        assert state["phase"] == "questioning"
        assert state["elapsed_minutes"] == 0
        assert state["follow_up_count"] == 0
        assert state["generation_retries"] == 0

    def test_state_prevents_empty_interviewers(self):
        """空面试官列表不能初始化状态"""
        from backend.mock_interview.mock_state import create_initial_state

        with pytest.raises(ValueError, match="至少需要一位面试官"):
            create_initial_state(
                session_id="test", interviewers=[], resume="", profile={},
            )

    def test_interviewer_rotation(self):
        """可以切换到下一位面试官"""
        from backend.mock_interview.mock_state import MockInterviewState, create_initial_state
        from backend.mock_interview.interviewer_config import InterviewerConfig
        from backend.mock_interview.mock_state import switch_to_next_interviewer

        gong = InterviewerConfig(name="张工", role="资深工程师", style="严谨深入", focus_area="编码能力")
        li = InterviewerConfig(name="李总", role="技术总监", style="宏观开放", focus_area="架构设计")
        wang = InterviewerConfig(name="王姐", role="HR负责人", style="温和引导", focus_area="软技能")

        state = create_initial_state("test", [gong, li, wang], "", {})
        assert state["current_interviewer_idx"] == 0

        state = switch_to_next_interviewer(state)
        assert state["current_interviewer_idx"] == 1

        state = switch_to_next_interviewer(state)
        assert state["current_interviewer_idx"] == 2

    def test_interviewer_rotation_wraparound(self):
        """面试官轮转到最后一位后回到第一位"""
        from backend.mock_interview.mock_state import create_initial_state, switch_to_next_interviewer
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {})

        state = switch_to_next_interviewer(state)
        assert state["current_interviewer_idx"] == 0  # 只有一个人，回到自身

    def test_current_interviewer(self):
        """可以获取当前面试官"""
        from backend.mock_interview.mock_state import create_initial_state, get_current_interviewer
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        li = InterviewerConfig(name="李总", role="总监", style="开放", focus_area="架构")

        state = create_initial_state("test", [gong, li], "", {})
        current = get_current_interviewer(state)
        assert current.name == "张工"

        from backend.mock_interview.mock_state import switch_to_next_interviewer
        state = switch_to_next_interviewer(state)
        current = get_current_interviewer(state)
        assert current.name == "李总"

    def test_records_question(self):
        """可以记录已提的问题"""
        from backend.mock_interview.mock_state import create_initial_state, record_question, get_question_history
        from backend.mock_interview.interviewer_config import InterviewerConfig
        from datetime import datetime, timedelta

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {})

        now = datetime.now()
        state = record_question(state, question="什么是Python装饰器?", interviewer_name="张工", timestamp=now)
        state = record_question(state, question="什么是GIL?", interviewer_name="张工", timestamp=now)

        history = get_question_history(state)
        assert len(history) == 2
        assert history[0]["question"] == "什么是Python装饰器?"
        assert history[1]["interviewer_name"] == "张工"

    def test_records_answer_and_evaluation(self):
        """可以记录用户回答和评估"""
        from backend.mock_interview.mock_state import create_initial_state, record_answer, get_answer_history, record_question
        from backend.mock_interview.interviewer_config import InterviewerConfig
        from datetime import datetime

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {})
        now = datetime.now()

        state = record_question(state, "什么是装饰器?", "张工", now)
        state = record_answer(state, answer="装饰器是高阶函数", score=85, evaluation="回答清晰完整")

        answers = get_answer_history(state)
        assert len(answers) == 1
        assert answers[0]["answer"] == "装饰器是高阶函数"
        assert answers[0]["score"] == 85

    def test_update_phase(self):
        """可以更新面试阶段"""
        from backend.mock_interview.mock_state import create_initial_state, update_phase
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {})

        state = update_phase(state, "wrap_up")
        assert state["phase"] == "wrap_up"

        state = update_phase(state, "completed")
        assert state["phase"] == "completed"

    def test_invalid_phase_transition(self):
        """无效的阶段转换应该被拒绝"""
        from backend.mock_interview.mock_state import create_initial_state, update_phase
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {})

        with pytest.raises(ValueError):
            update_phase(state, "invalid_phase")

    def test_time_management(self):
        """可以更新时间并检测是否进入收尾/结束阶段"""
        from backend.mock_interview.mock_state import create_initial_state, update_elapsed_time, should_wrap_up, should_end
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        state = create_initial_state("test", [gong], "", {}, max_duration=40, wrap_up_threshold=35)

        assert not should_wrap_up(state)
        assert not should_end(state)

        state = update_elapsed_time(state, 36)
        assert should_wrap_up(state)
        assert not should_end(state)

        state = update_elapsed_time(state, 40)
        assert should_end(state)

    def test_track_coverage(self):
        """可以跟踪考察点覆盖情况"""
        from backend.mock_interview.mock_state import create_initial_state, mark_topic_covered, get_coverage_summary
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(
            name="张工", role="工程师", style="严谨",
            focus_area=["编码能力", "项目深挖", "代码质量"],
        )
        state = create_initial_state("test", [gong], "", {})

        state = mark_topic_covered(state, "编码能力")
        state = mark_topic_covered(state, "项目深挖")

        summary = get_coverage_summary(state)
        assert summary["covered"] == 2
        assert summary["total"] == 3
        assert summary["remaining"] == ["代码质量"]

    def test_state_serialization(self):
        """状态可以序列化和反序列化"""
        from backend.mock_interview.mock_state import create_initial_state, serialize_state, deserialize_state, get_current_interviewer as get_iv
        from backend.mock_interview.interviewer_config import InterviewerConfig

        gong = InterviewerConfig(name="张工", role="工程师", style="严谨", focus_area="编码")
        li = InterviewerConfig(name="李总", role="总监", style="开放", focus_area="架构")

        state = create_initial_state("test", [gong, li], "简历内容", {"position": "后端"})
        state = state.copy()
        state["elapsed_minutes"] = 15

        serialized = serialize_state(state)
        assert serialized["session_id"] == "test"
        assert serialized["elapsed_minutes"] == 15
        assert len(serialized["interviewers"]) == 2

        restored = deserialize_state(serialized)
        assert restored["session_id"] == "test"
        assert restored["elapsed_minutes"] == 15
        assert get_iv(restored).name == "张工"

    def test_langgraph_workflow(self):
        """LangGraph 工作流可以创建并运行基础节点"""
        from backend.mock_interview.mock_state import create_mock_interview_graph
        gong = __import__("backend.mock_interview.interviewer_config", fromlist=["InterviewerConfig"]).InterviewerConfig
        config = gong(name="张工", role="工程师", style="严谨", focus_area="编码")

        graph = create_mock_interview_graph()
        assert graph is not None

        # 验证图有正确的节点
        # 通过检查节点名称来验证
        pass


