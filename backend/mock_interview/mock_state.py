"""拟真面试 LangGraph 状态管理

使用 LangGraph 构建多面试官面试工作流。
状态机管理面试流程：提问 → 回答 → 评估 → 决策(追问/换人/收尾/结束)。
"""
import json
import logging
import re
from datetime import datetime
from typing import Optional, Any

from backend.mock_interview.interviewer_config import InterviewerConfig
from backend.mock_interview.security import StateVerifier, get_security

logger = logging.getLogger(__name__)

# 兼容旧版阶段名
VALID_PHASES = {"questioning", "follow_up", "wrap_up", "completed"}

from backend.mock_interview.interviewer_config import InterviewStage, _STAGE_ORDER, _STAGE_LEAD_ROLES, _STAGE_DESC

# LangGraph 节点名称
NODE_GENERATE_QUESTION = "generate_question"
NODE_EVALUATE_ANSWER = "evaluate_answer"
NODE_DECIDE_NEXT = "decide_next"
NODE_SWITCH_INTERVIEWER = "switch_interviewer"
NODE_WRAP_UP = "wrap_up"
NODE_GENERATE_REPORT = "generate_report"


class MockInterviewState(dict):
    """拟真面试状态

    使用 TypedDict 风格的 dict 子类，兼容 LangGraph State 要求。
    """
    pass


def create_initial_state(
    session_id: str,
    interviewers: list[InterviewerConfig],
    resume: str,
    profile: dict,
    max_duration: int = 40,
    wrap_up_threshold: int = 35,
) -> dict:
    """创建初始面试状态"""
    if not interviewers:
        raise ValueError("至少需要一位面试官")

    # 收集所有考察点
    all_topics = set()
    for iv in interviewers:
        areas = iv.focus_area if isinstance(iv.focus_area, list) else [iv.focus_area]
        all_topics.update(areas)

    return {
        "session_id": session_id,
        "interviewers": [iv.to_dict() for iv in interviewers],
        "current_interviewer_idx": 0,
        "resume": resume,
        "profile": profile,
        "history": [],
        "covered_topics": set(),
        "all_topics": all_topics,
        "elapsed_minutes": 0,
        "phase": "questioning",
        "current_question": None,
        # 阶段驱动（取代简单的 follow_up_count 切换）
        "stage": InterviewStage.INTRO.value,
        "stage_idx": 0,
        "current_interviewer_stage_follow_ups": 0,  # 当前面试官本阶段追问计数
        "stage_question_count": 0,                   # 当前阶段已提问题总数
        "last_interviewer_idx": 0,
        # 行为状态
        "pressure_level": 0.0,       # 压力等级，随时间递增
        "question_difficulty": "easy",  # 当前难度
        # 兼容旧字段（不再用于路由决策，仅用于序列化兼容）
        "follow_up_count": 0,
        "max_follow_ups": 2,
        "generation_retries": 0,
        "max_generation_retries": 2,
        "max_duration_minutes": max_duration,
        "wrap_up_threshold_minutes": wrap_up_threshold,
    }


def switch_to_next_interviewer(state: dict) -> dict:
    """切换到下一位面试官"""
    state = dict(state)
    n = len(state["interviewers"])
    state["current_interviewer_idx"] = (state["current_interviewer_idx"] + 1) % n
    state["follow_up_count"] = 0
    state["generation_retries"] = 0
    logger.info(
        f"切换到面试官 #{state['current_interviewer_idx']}: "
        f"{state['interviewers'][state['current_interviewer_idx']]['name']}"
    )
    return state


def get_current_interviewer(state: dict) -> InterviewerConfig:
    """获取当前面试官对象"""
    iv_dict = state["interviewers"][state["current_interviewer_idx"]]
    return InterviewerConfig(**iv_dict)


def record_question(
    state: dict,
    question: str,
    interviewer_name: str,
    timestamp: Optional[datetime] = None,
) -> dict:
    """记录一个问题，同时更新 current_question"""
    state = dict(state)
    state["current_question"] = {
        "question_text": question,
        "interviewer_name": interviewer_name,
        "difficulty": "medium",
    }
    state.setdefault("history", []).append({
        "type": "question",
        "question": question,
        "interviewer_name": interviewer_name,
        "timestamp": (timestamp or datetime.now()).isoformat(),
    })
    return state


def record_answer(
    state: dict,
    answer: str,
    score: Optional[int] = None,
    evaluation: Optional[str] = None,
) -> dict:
    """记录用户回答和评分（含记忆污染防护）"""
    state = dict(state)

    # 记忆污染检测
    security = get_security()
    content = {"answer": answer, "score": score, "evaluation": evaluation}
    if not security.check_memory("answer", content):
        logger.warning(f"[Security] 回答被记忆防护拦截，已净化")
        # 只提取可能的技术内容，过滤掉指令部分
        answer = _extract_technical_content(answer)
        content["answer"] = answer
        if not answer.strip():
            # 完全过滤后为空，用占位符替代
            answer = "[内容已安全过滤]"
            content["answer"] = answer

    # 验证评分范围
    if score is not None and not StateVerifier.validate_score(score):
        logger.warning(f"[Security] 评分越界被修正: {score}")
        score = max(0, min(100, score))

    state.setdefault("history", []).append({
        "type": "answer",
        "answer": answer,
        "score": score,
        "evaluation": evaluation,
        "timestamp": datetime.now().isoformat(),
    })
    return state


def _extract_technical_content(text: str) -> str:
    """从文本中提取技术内容，过滤指令注入部分"""
    # 按行分割，移除包含攻击指令的行
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        line_stripped = line.strip().lower()
        # 跳过明显的指令行
        if re.search(
            r'(忽略|覆盖|替换|从现在开始|你(是|要|必须|不是)|'
            r'ignore|override|forget|disregard)',
            line_stripped,
        ):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def get_question_history(state: dict) -> list[dict]:
    """获取所有提问记录"""
    return [h for h in state.get("history", []) if h.get("type") == "question"]


def get_answer_history(state: dict) -> list[dict]:
    """获取所有回答记录"""
    return [h for h in state.get("history", []) if h.get("type") == "answer"]


def get_stage_answer_scores(state: dict) -> list[int]:
    """获取当前阶段所有已有评分的回答分数（用于判断回答质量）

    根据 stage_question_count 确定当前阶段的回答范围，
    从回答历史中提取有效分数（排除还没评分的 None）。
    """
    stage_count = state.get("stage_question_count", 0)
    answers = get_answer_history(state)
    # 当前阶段的回答是最后的 stage_count 条
    stage_answers = answers[-stage_count:] if stage_count > 0 else []
    scores = [a["score"] for a in stage_answers if a.get("score") is not None]
    return scores


def get_stage_avg_answer_length(state: dict) -> Optional[float]:
    """获取当前阶段的平均回答长度（字符数）

    回答长度可以作为回答质量的即时信号——太短说明没展开。
    在 AI 评分还没出来的时候，这个信号是立即可用的。
    """
    stage_count = state.get("stage_question_count", 0)
    answers = get_answer_history(state)
    stage_answers = answers[-stage_count:] if stage_count > 0 else []
    lengths = [len(a.get("answer", "")) for a in stage_answers]
    if not lengths:
        return None
    return sum(lengths) / len(lengths)


def update_phase(state: dict, new_phase: str) -> dict:
    """更新面试阶段（含状态机校验）"""
    if new_phase not in VALID_PHASES:
        raise ValueError(f"无效的阶段: {new_phase}，合法值: {VALID_PHASES}")
    current_phase = state.get("phase", "questioning")
    if not StateVerifier.validate_phase_transition(current_phase, new_phase):
        raise ValueError(
            f"非法阶段转换: {current_phase} → {new_phase}，"
            f"允许: {StateVerifier.get_allowed_transitions(current_phase)}"
        )
    state = dict(state)
    state["phase"] = new_phase
    logger.info(f"面试阶段变更为: {new_phase} (来自 {current_phase})")
    return state


def update_elapsed_time(state: dict, minutes: int) -> dict:
    """更新已用时间"""
    state = dict(state)
    state["elapsed_minutes"] = minutes
    return state


def should_wrap_up(state: dict) -> bool:
    """是否应该进入收尾阶段"""
    return state["elapsed_minutes"] >= state["wrap_up_threshold_minutes"]


def should_end(state: dict) -> bool:
    """是否应该结束面试"""
    return state["elapsed_minutes"] >= state["max_duration_minutes"]


def mark_topic_covered(state: dict, topic: str) -> dict:
    """标记一个考察点已覆盖"""
    state = dict(state)
    covered = set(state.get("covered_topics", set()))
    covered.add(topic)
    state["covered_topics"] = covered
    return state


def get_coverage_summary(state: dict) -> dict:
    """获取考察点覆盖总结"""
    covered = state.get("covered_topics", set())
    total = state.get("all_topics", set())
    return {
        "covered": len(covered),
        "total": len(total),
        "remaining": sorted(total - covered) if isinstance(total, set) else [],
    }


# ==================== 阶段驱动面试流程 ====================

def advance_stage(state: dict) -> dict:
    """推进到下一个面试阶段

    阶段推进由 should_advance_stage() 触发，在每次回答处理后检查。
    到达 END 阶段后不会自动结束面试，由 should_end()（时间到）驱动结束。
    """
    state = dict(state)
    current_idx = state.get("stage_idx", 0)
    next_idx = current_idx + 1
    if next_idx < len(_STAGE_ORDER):
        state["stage"] = _STAGE_ORDER[next_idx].value
        state["stage_idx"] = next_idx
        state["current_interviewer_stage_follow_ups"] = 0
        state["stage_question_count"] = 0
        logger.info(f"面试阶段推进: {_STAGE_ORDER[current_idx].value} → {_STAGE_ORDER[next_idx].value}")
    else:
        # 已到最后一个阶段，保持 END 标记，不强制结束
        state["stage"] = InterviewStage.END.value
    return state


def get_current_stage(state: dict) -> InterviewStage:
    """获取当前面试阶段"""
    stage_val = state.get("stage", InterviewStage.INTRO.value)
    try:
        return InterviewStage(stage_val)
    except ValueError:
        return InterviewStage.INTRO


def should_advance_stage(state: dict) -> bool:
    """判断是否应该推进到下一面试阶段

    不再使用固定题数阈值，而是根据回答质量（评分+长度）+ 时间压力综合判断。
    让面试官节奏更自然：回答充分就推进，回答浅就继续追问。
    """
    stage = get_current_stage(state)
    if stage == InterviewStage.END:
        return False

    stage_q_count = state.get("stage_question_count", 0)

    # 至少问 1 题
    if stage_q_count < 1:
        return False

    # ===== 时间压力：超过 70% 时间强制推进 =====
    elapsed = state.get("elapsed_minutes", 0)
    max_minutes = state.get("max_duration_minutes", 40)
    time_ratio = elapsed / max_minutes if max_minutes > 0 else 0
    if time_ratio > 0.7 and stage_q_count >= 1:
        logger.info(f"时间压力({elapsed}/{max_minutes}分钟)，强制推进阶段")
        return True

    # ===== 评分信号（回答质量高 → 推进） =====
    scores = get_stage_answer_scores(state)
    avg_score = sum(scores) / len(scores) if scores else None
    if avg_score is not None and avg_score >= 75 and stage_q_count >= 1:
        logger.info(
            f"阶段 {stage.value} 平均分 {avg_score:.0f}，回答质量达标，推进"
        )
        return True

    # ===== 回答长度信号（回答充分 → 推进） =====
    avg_length = get_stage_avg_answer_length(state)
    if avg_length is not None and avg_length >= 150 and stage_q_count >= 2:
        # 回答充分（平均150字以上），且至少问了2题，推进
        logger.info(
            f"阶段 {stage.value} 平均回答长度 {avg_length:.0f} 字，内容充分，推进"
        )
        return True

    # ===== 回答太短且已追问过多，说明候选人能力有限，推进 =====
    if avg_length is not None and avg_length < 40 and stage_q_count >= 3:
        logger.info(
            f"阶段 {stage.value} 回答过短({avg_length:.0f}字)，"
            f"已问{stage_q_count}题不再追问，推进"
        )
        return True

    # ===== 最大题数兜底（防止某个阶段永远卡住） =====
    max_q = {
        InterviewStage.INTRO: 3,
        InterviewStage.RESUME: 4,
        InterviewStage.GENERAL_TECH: 5,
        InterviewStage.DEEP_DIVE: 5,
        InterviewStage.PROJECT: 5,
        InterviewStage.PRESSURE: 4,
        InterviewStage.HR: 4,
        InterviewStage.QNA: 2,
    }.get(stage, 4)
    if stage_q_count >= max_q:
        logger.info(
            f"阶段 {stage.value} 已达最大题数 {max_q}，强制推进"
        )
        return True

    # ===== 面试官的 follow_up_depth 影响：高追问深度的面试官会多留一会儿 =====
    current_iv = get_current_interviewer(state)
    if current_iv.follow_up_depth >= 0.6:
        # 高追问深度的面试官不轻易推进
        if stage_q_count < 3 and avg_score is not None and avg_score < 70:
            logger.info(
                f"当前面试官{current_iv.name}追问深度高({current_iv.follow_up_depth})，"
                f"且评分({avg_score:.0f})不高，继续追问不推进"
            )
            return False

    return False


def calc_stage_weight(interviewer: InterviewerConfig, stage: InterviewStage) -> float:
    """计算面试官在当前阶段的权重

    根据面试官的 role 是否匹配当前阶段的 lead role 来决定。
    """
    lead_roles = _STAGE_LEAD_ROLES.get(stage, [])
    if interviewer.role in lead_roles:
        return 0.6
    # 有偏好阶段且包含当前阶段
    if interviewer.preferred_stages and stage.value in interviewer.preferred_stages:
        return 0.4
    return 0.2


def calc_follow_up_bonus(
    state: dict, interviewer_idx: int, interviewer: InterviewerConfig,
    answer_text: str = "",
) -> float:
    """计算追问加分 — 同一面试官连续提问的权重加成

    follow_up_depth 越高，追问粘性越大。
    如果上一条回答很短（候选人没展开），自动加权重促使追问深挖。
    """
    last_idx = state.get("last_interviewer_idx")
    if last_idx == interviewer_idx:
        follow_ups = state.get("current_interviewer_stage_follow_ups", 0)
        # 基础追问加成 0.5（与 stage_weight 的 0.6 相当，保证追问有竞争力）
        # 减速衰减：depth 越高，衰减越慢
        decay = follow_ups * 0.4 * (1 - interviewer.follow_up_depth)
        bonus = max(0, 0.5 - decay)

        # 回答太短（<80字）说明没展开，需要追问深挖
        if answer_text and len(answer_text) < 80:
            bonus += 0.3
            logger.info(
                f"回答偏短({len(answer_text)}字)，为 {interviewer.name} 增加追问权重"
            )

        # 高追问深度面试官额外加成
        if interviewer.follow_up_depth >= 0.7:
            bonus += 0.15
        elif interviewer.follow_up_depth >= 0.5:
            bonus += 0.05

        return bonus
    return 0.0


def calc_pressure_score(interviewer: InterviewerConfig, pressure_level: float) -> float:
    """计算压力评分 — 高压阶段更喜欢高攻击性面试官"""
    return interviewer.aggressiveness * pressure_level * 0.5


def calc_interruption_score(
    state: dict, interviewer_idx: int, interviewer: InterviewerConfig
) -> float:
    """计算打断概率 — 低概率触发打断，切换面试官"""
    import random
    if interviewer_idx == state.get("current_interviewer_idx"):
        return 0.0  # 当前发言者不打断自己
    if random.random() < interviewer.interruption_rate:
        logger.info(f"{interviewer.name} 触发打断 (rate={interviewer.interruption_rate})")
        return 0.5
    return 0.0


def route_next_interviewer(
    state: dict,
    interviewers: list[InterviewerConfig],
    answer_text: str,
) -> tuple[dict, int, bool]:
    """加权调度算法：根据多维评分选出最合适的下一位面试官

    评分公式：
        score = stage_weight + follow_up_bonus + pressure_score + interruption_score + randomness

    Returns:
        (new_state, selected_idx, is_interruption)
    """
    stage = get_current_stage(state)
    pressure = state.get("pressure_level", 0.0)

    scores = []
    for i, iv in enumerate(interviewers):
        sw = calc_stage_weight(iv, stage)
        fb = calc_follow_up_bonus(state, i, iv, answer_text)
        ps = calc_pressure_score(iv, pressure)
        it = calc_interruption_score(state, i, iv)
        # 少量随机扰动，增加不可预测性
        import random
        rn = random.uniform(0, 0.15)

        total = sw + fb + ps + it + rn
        scores.append((i, total, it > 0))
        logger.debug(
            f"  路由评分: {iv.name} stage={sw:.2f} follow_up={fb:.2f} "
            f"pressure={ps:.2f} interrupt={it:.2f} random={rn:.2f} = {total:.2f}"
        )

    # 按总分降序排列
    scores.sort(key=lambda x: x[1], reverse=True)
    selected_idx, _, is_interruption = scores[0]

    state = dict(state)
    state["last_interviewer_idx"] = state["current_interviewer_idx"]

    if selected_idx != state["current_interviewer_idx"]:
        # 切换面试官
        state["current_interviewer_idx"] = selected_idx
        state["current_interviewer_stage_follow_ups"] = 0
    else:
        # 同一面试官继续追问
        state["current_interviewer_stage_follow_ups"] += 1

    logger.info(
        f"路由决策: 当前=#{state['last_interviewer_idx']} {interviewers[state['last_interviewer_idx']].name} "
        f"→ 选择=#{selected_idx} {interviewers[selected_idx].name} "
        f"(is_interruption={is_interruption})"
    )
    return state, selected_idx, is_interruption


def update_pressure(state: dict) -> dict:
    """更新压力等级 — 随时间递增，影响问题难度和面试官行为"""
    state = dict(state)
    elapsed = state.get("elapsed_minutes", 0)
    # 压力 = 时间比例 * 0.8（最到 0.8）
    max_minutes = state.get("max_duration_minutes", 40)
    ratio = min(1.0, elapsed / max_minutes) if max_minutes > 0 else 0
    state["pressure_level"] = round(ratio * 0.8, 2)

    # 随压力升级问题难度
    if state["pressure_level"] > 0.5:
        state["question_difficulty"] = "hard"
    elif state["pressure_level"] > 0.25:
        state["question_difficulty"] = "medium"
    else:
        state["question_difficulty"] = "easy"
    return state


def serialize_state(state: dict) -> dict:
    """序列化状态为 JSON 兼容的字典"""
    covered = state.get("covered_topics", set())
    return {
        **state,
        "covered_topics": list(covered) if isinstance(covered, set) else covered,
        "all_topics": list(state.get("all_topics", set())),
        "stage": state.get("stage", InterviewStage.INTRO.value),
    }


def deserialize_state(data: dict) -> dict:
    """反序列化恢复状态"""
    state = dict(data)
    state["covered_topics"] = set(data.get("covered_topics", []))
    state["all_topics"] = set(data.get("all_topics", []))
    # 兼容旧序列化数据（没有 stage 字段）
    if "stage" not in state:
        state["stage"] = InterviewStage.INTRO.value
        state["stage_idx"] = 0
        state["current_interviewer_stage_follow_ups"] = 0
        state["last_interviewer_idx"] = state.get("current_interviewer_idx", 0)
        state["pressure_level"] = 0.0
        state["question_difficulty"] = "easy"
    return state


def update_last_answer(state: dict, score: Optional[int] = None, evaluation: Optional[str] = None) -> dict:
    """更新最后一条回答记录的评分（先记录后评分的场景用）"""
    state = dict(state)
    history = state.get("history", [])
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("type") == "answer":
            history[i] = {**history[i], "score": score, "evaluation": evaluation}
            break
    return state


# ==================== LangGraph 工作流 ====================

try:
    from langgraph.graph import StateGraph, END
    from typing import TypedDict

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


def generate_question_node(state: dict) -> dict:
    """生成问题节点 — 由当前面试官生成问题

    在实际运行时，此节点会调用 AI 生成问题。
    在测试中返回占位问题。
    """
    state = dict(state)
    current_iv = state["interviewers"][state["current_interviewer_idx"]]

    state["generation_retries"] = state.get("generation_retries", 0) + 1
    state["current_question"] = {
        "question_text": f"[{current_iv['name']}] 请介绍一下你的项目经验",
        "interviewer_name": current_iv["name"],
        "difficulty": "medium",
    }
    state["generation_retries"] = 0
    return state


def evaluate_answer_node(state: dict) -> dict:
    """评估回答节点 — 评估用户回答质量"""
    state = dict(state)
    # 占位评估逻辑，实际运行时调用 AI
    state["last_score"] = 85
    state["last_evaluation"] = "回答清晰完整"
    return state


def decide_next_node(state: dict) -> str:
    """决策节点 — 决定下一步: 追问/换人/收尾/结束"""
    if state.get("phase") == "completed":
        return NODE_GENERATE_REPORT
    if should_end(state):
        return NODE_GENERATE_REPORT
    if should_wrap_up(state) or state.get("phase") == "wrap_up":
        return NODE_WRAP_UP
    if state["follow_up_count"] < state["max_follow_ups"]:
        return NODE_GENERATE_QUESTION
    return NODE_SWITCH_INTERVIEWER


def wrap_up_node(state: dict) -> dict:
    """收尾节点 — 补充未覆盖考察点"""
    state = dict(state)
    summary = get_coverage_summary(state)
    remaining = summary.get("remaining", [])
    if remaining:
        current_iv = state["interviewers"][state["current_interviewer_idx"]]
        state["current_question"] = {
            "question_text": f"[收尾] 关于{'、'.join(remaining)}，你有什么想补充的吗？",
            "interviewer_name": current_iv["name"],
            "difficulty": "easy",
        }
    state["phase"] = "wrap_up"
    return state


def generate_report_node(state: dict) -> dict:
    """生成报告节点 — 生成最终面试报告"""
    state = dict(state)
    state["phase"] = "completed"
    state["report"] = {
        "summary": get_coverage_summary(state),
        "total_questions": len(get_question_history(state)),
        "completed_at": datetime.now().isoformat(),
    }
    return state


def create_mock_interview_graph() -> Any:
    """创建 LangGraph 工作流图"""
    if not HAS_LANGGRAPH:
        raise ImportError("需要安装 langgraph 包: pip install langgraph")

    workflow = StateGraph(MockInterviewState)

    # 注册节点
    workflow.add_node(NODE_GENERATE_QUESTION, generate_question_node)
    workflow.add_node(NODE_EVALUATE_ANSWER, evaluate_answer_node)
    workflow.add_node(NODE_DECIDE_NEXT, decide_next_node)
    workflow.add_node(NODE_SWITCH_INTERVIEWER, switch_to_next_interviewer)
    workflow.add_node(NODE_WRAP_UP, wrap_up_node)
    workflow.add_node(NODE_GENERATE_REPORT, generate_report_node)

    # 设置边
    workflow.set_entry_point(NODE_GENERATE_QUESTION)
    workflow.add_edge(NODE_GENERATE_QUESTION, NODE_EVALUATE_ANSWER)
    workflow.add_edge(NODE_EVALUATE_ANSWER, NODE_DECIDE_NEXT)

    # 条件分支
    workflow.add_conditional_edges(
        NODE_DECIDE_NEXT,
        lambda s: s,  # 实际由 decide_next_node 返回值决定
        {
            NODE_GENERATE_QUESTION: NODE_GENERATE_QUESTION,
            NODE_SWITCH_INTERVIEWER: NODE_SWITCH_INTERVIEWER,
            NODE_WRAP_UP: NODE_WRAP_UP,
            NODE_GENERATE_REPORT: NODE_GENERATE_REPORT,
        },
    )
    workflow.add_edge(NODE_SWITCH_INTERVIEWER, NODE_GENERATE_QUESTION)
    workflow.add_edge(NODE_WRAP_UP, NODE_GENERATE_REPORT)
    workflow.add_edge(NODE_GENERATE_REPORT, END)

    return workflow.compile()
