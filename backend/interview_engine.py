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
        "desc": "选择题 + 判断题，考察知识广度",
        "prompt_extra": """这是笔试环节，只出选择题（四选一）和判断题。
- 选择题提供四个选项（A/B/C/D）
- 判断题提供"A. 正确"/"B. 错误"两个选项
- 必须标注正确答案 correct_answer
- 题目要有明确的标准答案
- 用户只需选择答案，不需要文字解释
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
        if round_name == "written":
            prompt = self._build_opening_prompt_written(resume, profile)
            result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        else:
            prompt = self._build_opening_prompt(resume, profile, round_name, question_type)
            result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        return self._parse_question(result, 1, round_name)

    async def generate_next_question(
        self, history: list[dict], resume: str, profile: dict,
        round_name: str = DEFAULT_ROUND,
    ) -> dict:
        """根据对话历史生成下一题"""
        if round_name == "written":
            prompt = self._build_next_prompt_written(history, resume, profile)
            result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
        else:
            prompt = self._build_next_prompt(history, resume, profile, round_name)
            result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=1024)
        question_num = len(history) + 1
        return self._parse_question(result, question_num, round_name)

    async def evaluate_answer(self, question: str, answer: str, context: dict, round_name: str = "", question_data: dict = None) -> dict:
        """评估用户的回答"""
        if round_name == "written":
            return self._evaluate_written_direct(answer, question_data or {})
        prompt = self._build_evaluation_prompt(question, answer, context)
        result = await self.ai.chat([{"role": "user", "content": prompt}], max_tokens=1024)
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

    def _build_opening_prompt_written(self, resume: str, profile: dict) -> str:
        rc = self._get_round_config("written")
        profile_str = json.dumps(profile, ensure_ascii=False, indent=2)
        return f"""你是一个专业的笔试考官，正在出{rc['name']}。这是第 1 题。

== 候选人简历 ==
{resume[:3000]}

== 目标岗位画像 ==
{profile_str}

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

    def _build_next_prompt_written(self, history: list[dict], resume: str, profile: dict) -> str:
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

        return f"""你是一个专业的笔试考官，正在出{rc['name']}。这是第 {current_q} 题。

== 候选人简历 ==
{resume[:2000]}

== 岗位画像 ==
{json.dumps(profile, ensure_ascii=False, indent=2)[:1000]}

== 笔试历史 ==
{history_str}

{rc['prompt_extra']}

难度要求：{expected_difficulty}（{difficulty_hint}）

动态调整：
- 上一题正确 → 加深难度
- 上一题错误 → 换知识点，保持或降低难度
- 不要连续考同一个 topic

注意：题目要结合候选人简历中的技能栈

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

        return {
            "correct": is_correct,
            "correct_answer": correct,
            "explanation": question_data.get("explanation", ""),
            "score": 10 if is_correct else 0,
        }

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

    def _parse_question(self, raw: Optional[str], num: int, round_name: str = "") -> dict:
        if not raw:
            return self._make_fallback(num, round_name)
        try:
            data = json.loads(raw)
            if "question" in data:
                if round_name == "written":
                    return self._validate_written_question(data, num)
                return data
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    if "question" in data:
                        if round_name == "written":
                            return self._validate_written_question(data, num)
                        return data
                except json.JSONDecodeError:
                    pass
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.startswith("{") and not l.startswith("}")]
        if round_name == "written":
            return self._make_written_fallback(num)
        question_text = lines[0] if lines else f"请结合你的项目经验，谈谈你在 {num} 个项目中的技术挑战和解决方案。"
        return {"question": question_text, "type": "技术", "difficulty": "medium", "topic": "综合", "expected_points": []}

    def _validate_written_question(self, data: dict, num: int) -> dict:
        """校验笔试题目必须包含 options 字段，不符合则返回备选题"""
        options = data.get("options")
        if options and isinstance(options, dict) and len(options) >= 2:
            return data
        logger.warning(f"笔试第{num}题缺少 options 字段，使用备选题。原始数据: {json.dumps(data, ensure_ascii=False)[:200]}")
        return self._make_written_fallback(num)

    def _make_written_fallback(self, num: int) -> dict:
        """生成笔试备选选择题"""
        fallbacks = [
            {
                "question": "在软件开发中，下列哪种设计模式属于创建型模式？",
                "type": "选择题", "difficulty": "easy", "topic": "设计模式",
                "options": {"A": "工厂模式", "B": "观察者模式", "C": "装饰器模式", "D": "策略模式"},
                "correct_answer": "A",
                "explanation": "工厂模式属于创建型模式，用于封装对象的创建过程。观察者、装饰器、策略都属于行为型或结构型模式。",
            },
            {
                "question": "HTTP 状态码 404 表示什么？",
                "type": "选择题", "difficulty": "easy", "topic": "网络基础",
                "options": {"A": "服务器内部错误", "B": "资源未找到", "C": "重定向", "D": "请求超时"},
                "correct_answer": "B",
                "explanation": "404 Not Found 表示服务器无法找到请求的资源，是最常见的客户端错误状态码之一。500 为服务器错误，301/302 为重定向，408 为请求超时。",
            },
            {
                "question": "以下哪种数据结构是先进后出（LIFO）的？",
                "type": "选择题", "difficulty": "easy", "topic": "数据结构",
                "options": {"A": "队列", "B": "栈", "C": "链表", "D": "数组"},
                "correct_answer": "B",
                "explanation": "栈（Stack）是典型的 LIFO 结构，只允许在一端进行插入和删除。队列是 FIFO，链表和数组不限定访问顺序。",
            },
            {
                "question": "关系型数据库中的主键（Primary Key）的主要作用是什么？",
                "type": "选择题", "difficulty": "easy", "topic": "数据库",
                "options": {"A": "加快查询速度", "B": "唯一标识一条记录", "C": "建立索引", "D": "保证数据安全性"},
                "correct_answer": "B",
                "explanation": "主键的核心作用是唯一标识表中的每一行记录。虽然主键会自动创建索引从而加快查询，但这是副作用而非主要作用。",
            },
            {
                "question": "在 Python 中，列表（list）和元组（tuple）的主要区别是什么？",
                "type": "选择题", "difficulty": "easy", "topic": "Python基础",
                "options": {"A": "列表可变，元组不可变", "B": "列表不可变，元组可变", "C": "两者没有区别", "D": "列表只能存储数字"},
                "correct_answer": "A",
                "explanation": "列表（list）创建后可以增删改元素，是可变的；元组（tuple）创建后不可修改，是不可变的。这是两者最核心的区别。",
            },
        ]
        return fallbacks[(num - 1) % len(fallbacks)]

    def _make_fallback(self, num: int, round_name: str = "") -> dict:
        if round_name == "written":
            return self._make_written_fallback(num)
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
