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
ROUND_CONFIG = {
    "written": {
        "name": "笔试",
        "desc": "基础题 + 选择题/填空题/简答题，考察知识广度",
        "prompt_extra": """这是笔试环节，请出选择题、填空题或简答题。
- 题目要有明确的标准答案
- 可包含代码补全、概念选择、SQL 编写等
- 难度：前几题 easy，后面逐渐 medium""",
    },
    "tech_1": {
        "name": "技术一面",
        "desc": "基础技术 + 项目经验深入",
        "prompt_extra": """这是第一轮技术面试。
- 重点考察候选人的项目经验和技术基础
- 从简历项目入手，追问技术选型、难点和解决方案
- 可出场景题但不要求完整系统设计""",
    },
    "tech_2": {
        "name": "技术二面",
        "desc": "系统设计 + 架构能力 + 深度原理",
        "prompt_extra": """这是第二轮技术深度面试。
- 重点考察系统设计能力、架构思维
- 出设计题（如"设计一个短链接系统""秒杀架构"）
- 深挖技术原理（底层实现、性能优化、源码理解）""",
    },
    "comprehensive": {
        "name": "综合面",
        "desc": "综合素质 + 团队协作 + 职业规划",
        "prompt_extra": """这是综合面试。
- 考察沟通表达、团队协作、解决问题的思路
- 可问行为面试题（STAR 法则）
- 了解职业规划、技术视野、学习能力""",
    },
}

DEFAULT_ROUND = "tech_1"


class InterviewEngine:
    """面试引擎，管理面试流程和 AI 交互"""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client

    async def generate_first_question(
        self, resume: str, profile: dict,
        round_name: str = DEFAULT_ROUND, question_type: str = "mixed",
    ) -> dict:
        """生成第一道面试题"""
        prompt = self._build_opening_prompt(resume, profile, round_name, question_type)
        result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        return self._parse_question(result, 1)

    async def generate_next_question(
        self, history: list[dict], resume: str, profile: dict,
        round_name: str = DEFAULT_ROUND,
    ) -> dict:
        """根据对话历史生成下一题"""
        prompt = self._build_next_prompt(history, resume, profile, round_name)
        result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        question_num = len(history) + 1
        return self._parse_question(result, question_num)

    async def evaluate_answer(self, question: str, answer: str, context: dict) -> dict:
        """评估用户的回答"""
        prompt = self._build_evaluation_prompt(question, answer, context)
        result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        return self._parse_evaluation(result)

    async def end_interview(self, history: list[dict], profile: dict) -> dict:
        """结束面试，生成总结报告"""
        prompt = self._build_report_prompt(history, profile)
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

== 候选人简历 ==
{resume[:3000]}

== 目标岗位画像 ==
{profile_str}

{rc['prompt_extra']}

难度要求（第1题必须简单热身）：
- 第1题：easy
- 如果候选人简历上有项目，从项目中最熟悉的部分问起

只输出 JSON:
{{"question": "题目", "type": "技术/行为/设计", "difficulty": "easy", "topic": "考察主题", "expected_points": ["要点1", "要点2"]}}"""

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

== 候选人简历 ==
{resume[:2000]}

== 岗位画像 ==
{json.dumps(profile, ensure_ascii=False, indent=2)[:1000]}

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

注意：题目要结合候选人简历项目，不要脱离简历

只输出 JSON:
{{"question": "题目", "type": "技术/行为/设计", "difficulty": "easy/medium/hard", "topic": "考察主题", "expected_points": ["要点1", "要点2"], "reason": "为什么出这题"}}"""

    def _build_evaluation_prompt(self, question: str, answer: str, context: dict) -> str:
        return f"""你是一个专业的面试官，请严格按以下 JSON 格式评估候选人的回答，不要输出其他内容。

面试题: {question}

回答: {answer[:2000]}

岗位信息: {json.dumps(context.get("profile", {}), ensure_ascii=False)[:500]}

评分标准：每个维度 1-10 分（10 分制），只输出 JSON：

{{"technical_score": 7, "technical_comment": "评价", "logic_score": 7, "logic_comment": "评价", "depth_score": 7, "depth_comment": "评价", "communication_score": 7, "communication_comment": "评价", "overall_score": 7, "summary": "综合评价", "strengths": ["优点"], "improvements": ["建议"], "reference_answer": "参考回答"}}"""

    def _build_report_prompt(self, history: list[dict], profile: dict) -> str:
        history_str = ""
        for i, h in enumerate(history, 1):
            score = h.get("score", {})
            history_str += f"\nQ{i}: {h['q']}\nA{i}: {h['a'][:300]}\n评分: {json.dumps(score, ensure_ascii=False)}\n"

        return f"""请根据以下完整的面试记录，生成一份面试总结报告。

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
  "skill_summary": "技能掌握情况总结",
  "preparation_advice": ["复习建议1", "建议2", "建议3"],
  "recommended_positions": ["适合的岗位1", "岗位2"],
  "final_verdict": "最终评价（2-3句话）"
}}"""

    # ==================== 解析器 ====================

    def _parse_question(self, raw: Optional[str], num: int) -> dict:
        if not raw:
            return {"question": f"请介绍一下你在最近项目中的技术选型和架构设计。", "type": "技术", "difficulty": "medium", "topic": "项目经验", "expected_points": []}
        try:
            data = json.loads(raw)
            if "question" in data:
                return data
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.startswith("{") and not l.startswith("}")]
        question_text = lines[0] if lines else f"请结合你的项目经验，谈谈你在 {num} 个项目中的技术挑战和解决方案。"
        return {"question": question_text, "type": "技术", "difficulty": "medium", "topic": "综合", "expected_points": []}

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
