"""API 路由处理器

管理 Mock Interview 会话生命周期：
- 创建会话并生成第一题
- 处理回答，评估并生成下一题
- 结束会话
- 查询会话状态
"""
import asyncio
import json
import logging
from typing import Optional

from backend.mock_interview.interviewer_config import InterviewerConfig
from backend.mock_interview.mock_engine import MockInterviewEngine
from backend.mock_interview.mock_state import (
    advance_stage,
    get_current_interviewer,
    get_current_stage,
    get_question_history,
    InterviewStage,
    mark_topic_covered,
    record_answer,
    record_question,
    route_next_interviewer,
    should_advance_stage,
    should_end,
    should_wrap_up,
    update_elapsed_time,
    update_last_answer,
    update_pressure,
    update_phase,
)

from backend.mock_interview.security import get_security, SafetyLevel

logger = logging.getLogger(__name__)


class MockInterviewRouter:
    """Mock Interview 路由处理器"""

    def __init__(self, ai_client, tts_engine=None):
        self.ai = ai_client
        self.tts = tts_engine
        self.sessions: dict[str, MockInterviewEngine] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话级别的锁，防止并发处理同一会话的回答"""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    async def create_session(
        self,
        interviewer_configs: list[InterviewerConfig],
        resume: str,
        profile: dict,
        max_duration: int = 40,
        wrap_up_threshold: int = 35,
    ) -> dict:
        """创建新的 Mock 面试会话"""
        engine = MockInterviewEngine(
            interviewers=interviewer_configs,
            ai_client=self.ai,
            resume=resume,
            profile=profile,
            max_duration=max_duration,
            wrap_up_threshold=wrap_up_threshold,
            tts_engine=self.tts,
        )
        # generate_audio=False：让 WebSocket 连接后流式推送音频
        result = await engine.start(generate_audio=False)
        self.sessions[engine.session_id] = engine
        logger.info(f"创建拟真面试会话: {engine.session_id}")
        return result

    async def handle_answer_stream(self, session_id: str, answer: str, elapsed_minutes: Optional[int] = None):
        """流式处理回答：并行运行评估（流式）和下一题生成

        Yields:
            ("eval_token", token) — 评估 token
            ("eval_result", dict) — 评估完成结果
            ("result", dict) — 完整结果（含下一题）
        """
        async with self._get_lock(session_id):
            engine = self.get_session(session_id)

            # 输入防注入检测（用户回答）
            _security = get_security()
            _check = _security.check_input(answer, context_hint="answer")
            if _check.level == SafetyLevel.BLOCKED:
                logger.warning(f"[Security] 拦截注入回答: {_check.reason}")
                yield ("result", {
                    "answer_recorded": True,
                    "next_question_text": "请正常回答面试问题，不要输入无关指令。",
                    "interviewer_name": engine.get_current_interviewer_name(),
                    "phase": engine.state["phase"],
                    "evaluation": {"score": 0, "evaluation": "回答包含无效内容"},
                })
                return
            # 可疑回答用净化版本替代
            if _check.level == SafetyLevel.SUSPICIOUS:
                answer = _security.sanitize_input(answer)
                logger.info(f"[Security] 使用净化后的回答 (长度 {len(answer)})")

            # 去重检测
            history = engine.state.get("history", [])
            if len(history) >= 2 and history[-1].get("type") == "answer":
                logger.info(f"检测到重复提交，跳过: session={session_id}")
                prev_q = history[-2].get("question", "")
                yield ("result", {
                    "answer_recorded": True,
                    "next_question_text": prev_q,
                    "interviewer_name": engine.get_current_interviewer_name(),
                    "phase": engine.state["phase"],
                    "evaluation": {"score": 0, "evaluation": ""},
                })
                return

            # 更新时间
            if elapsed_minutes is not None:
                engine.state = update_elapsed_time(engine.state, elapsed_minutes)

            # 先记录回答（没有评分，稍后更新）
            engine.state = record_answer(engine.state, answer, None, None)

            # 更新覆盖的考察点（不需要等评估结果）
            focus = get_current_interviewer(engine.state).focus_area
            areas = focus if isinstance(focus, list) else [focus]
            for area in areas:
                engine.state = mark_topic_covered(engine.state, area)

            # 检查是否需要推进阶段
            if should_advance_stage(engine.state):
                engine.state = advance_stage(engine.state)

            # 决策是否该结束
            if should_end(engine.state):
                result = await engine._finish()
                yield ("result", result)
                return

            if should_wrap_up(engine.state) and engine.state["phase"] != "wrap_up":
                engine.state = update_phase(engine.state, "wrap_up")
                # 进入收尾阶段后，强制推进到 HR 阶段（除非已在更后的阶段）
                stage = get_current_stage(engine.state)
                if stage not in (InterviewStage.HR, InterviewStage.QNA, InterviewStage.END):
                    # 直接设置 stage，跳过 advance_stage 的阈值检查
                    engine.state["stage"] = InterviewStage.HR.value
                    engine.state["stage_question_count"] = 0

            # 更新压力等级
            engine.state = update_pressure(engine.state)

            # 加权路由：根据阶段权重+追问加成+压力+打断概率选出最佳面试官
            prev_name = engine.get_current_interviewer_name()
            engine.state, next_idx, is_interruption = route_next_interviewer(
                engine.state, engine.interviewers, answer,
            )
            engine._pending_switch_from = prev_name
            engine._pending_switch_to = engine.get_current_interviewer_name()
            if next_idx == engine.state["last_interviewer_idx"]:
                engine._pending_switch_from = None
                engine._pending_switch_to = None

            # ===== 并行运行：流式评估 + 流式生成下一题 =====
            eval_iter = engine._evaluate_answer_stream(answer)
            q_index = len(get_question_history(engine.state))
            question_stream = engine._generate_question_stream(q_index)

            queue: asyncio.Queue[tuple[str, str | None, object]] = asyncio.Queue()

            # 先发送 start 信号，告诉前端停止旧题音频、清空播放缓冲
            await queue.put(("question", "start", None))

            async def pump_eval():
                async for stage, data in eval_iter:
                    await queue.put(("eval", stage, data))
                await queue.put(("eval", None, None))

            async def pump_question():
                async for stage, data in question_stream:
                    await queue.put(("question", stage, data))
                await queue.put(("question", None, None))

            asyncio.create_task(pump_eval())
            asyncio.create_task(pump_question())

            evaluation = None
            next_q = None
            eval_done = False
            question_done = False
            audio_streamed = False  # 标记是否已通过 WebSocket 流式推送音频

            while not (eval_done and question_done):
                source, stage, data = await queue.get()
                if source == "eval":
                    if stage is None:
                        eval_done = True
                        continue
                    if stage == "token":
                        yield ("eval_token", data)
                    elif stage == "result":
                        evaluation = data
                        engine.state = update_last_answer(engine.state, evaluation.get("score"), evaluation.get("evaluation"))
                        yield ("eval_result", evaluation)
                elif source == "question":
                    if stage is None:
                        question_done = True
                        continue
                    if stage == "start":
                        yield ("question_start", None)
                        # 在音频流式推送之前发送面试官切换信号，
                        # 让前端先显示切换动画再播音频
                        if engine._pending_switch_from:
                            yield ("switch_interviewer", {
                                "from": engine._pending_switch_from,
                                "to": engine._pending_switch_to,
                            })
                        continue
                    if stage == "token":
                        yield ("question_token", data)
                    elif stage == "audio_chunk":
                        audio_streamed = True
                        yield ("audio_chunk", data)
                    elif stage == "audio_done":
                        yield ("audio_done", data)
                    elif stage == "done":
                        next_q = data

            # TTS 已在 _generate_question_stream 中通过 audio_chunk 推送
            # 如果音频已流式推送，不再返回 audio_url，避免前端重复播放
            if next_q:
                engine.state = record_question(engine.state, next_q["question_text"], engine.get_current_interviewer_name())
                engine.state["stage_question_count"] = engine.state.get("stage_question_count", 0) + 1

            result = {
                "answer_recorded": True,
                "next_question": next_q or {},
                "next_question_text": (next_q or {}).get("question_text", ""),
                "interviewer_name": engine.get_current_interviewer_name(),
                "interviewer_index": engine.state["current_interviewer_idx"],
                "phase": engine.state["phase"],
                "elapsed_minutes": engine.state["elapsed_minutes"],
                "evaluation": evaluation or {"score": 0, "evaluation": ""},
            }
            if engine._pending_switch_from:
                result["switch_from"] = engine._pending_switch_from
                result["switch_to"] = engine._pending_switch_to
                engine._pending_switch_from = None
                engine._pending_switch_to = None
            # 音频未流式推送时才返回 audio_url（降级路径）
            if not audio_streamed:
                result["audio_url"] = (next_q or {}).get("audio_url")
            yield ("result", result)

    async def end_session(self, session_id: str) -> dict:
        """结束面试会话"""
        engine = self.get_session(session_id)
        result = await engine._finish()
        return result

    async def get_session_state(self, session_id: str) -> Optional[dict]:
        """获取会话状态"""
        engine = self.get_session(session_id)
        return {
            "session_id": engine.session_id,
            "phase": engine.state["phase"],
            "current_interviewer": engine.get_current_interviewer_name(),
            "elapsed_minutes": engine.state["elapsed_minutes"],
            "total_questions": len(engine.state["history"]) // 2 if engine.state["history"] else 0,
            "coverage": engine.get_coverage_report(),
        }

    def get_session(self, session_id: str) -> MockInterviewEngine:
        """获取会话引擎实例"""
        engine = self.sessions.get(session_id)
        if not engine:
            raise ValueError(f"会话不存在: {session_id}")
        return engine

    def remove_session(self, session_id: str):
        """移除会话"""
        self.sessions.pop(session_id, None)
