"""数据清洗与转换：原始 JSON → ChatML 训练格式

用法:
    python -m backend.finetune.prepare_data

输出:
    backend/data/training/train.jsonl   (训练集)
    backend/data/training/val.jsonl     (验证集)
"""
import json
import re
import random
from pathlib import Path

# ---- 路径 ----
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "training" / "raw"
OUT_DIR = DATA_DIR / "training"

# ---- 1. Question 清洗 ----
def clean_question(raw_q: str) -> str:
    """把被 JSON 包裹的 question 还原为纯文本"""
    q = raw_q.strip()

    # 情况1: 整条 question 是 '"question": "xxx"' 格式
    # 从里面把真正的题目文本提取出来
    if q.startswith('"question"'):
        m = re.search(r'"question":\s*"(.+)"\s*$', q, re.DOTALL)
        if m:
            q = m.group(1)
            # 反转义
            q = q.replace('\\n', '\n').replace('\\"', '"').replace('\\\'', "'")

    # 情况2: 以 "question": 开头但没被完整 JSON 包裹（残余前缀）
    if q.startswith('"question":'):
        q = re.sub(r'^"question":\s*', '', q).strip()
        if (q.startswith('"') and q.endswith('"')) or (q.startswith("'") and q.endswith("'")):
            q = q[1:-1]

    return q.strip()


# ---- 2. Answer 清洗 ----
def is_answer_valid(answer: str, min_len: int = 10) -> bool:
    """判断回答是否有效（足够长、不是空）"""
    a = answer.strip() if answer else ""
    return len(a) >= min_len


# ---- 3. Score 归一化 ----
def normalize_score(score: float, min_val: int = 1, max_val: int = 10) -> int:
    """确保分数在有效范围内"""
    s = max(min_val, min(score, max_val))
    return int(round(s))


def clean_result(result: dict) -> dict:
    """清洗评分结果"""
    cleaned = {}
    for key in ["technical_score", "logic_score", "depth_score", "communication_score", "overall_score"]:
        if key in result:
            cleaned[key] = normalize_score(result[key])
    for key in ["summary", "reference_answer"]:
        if key in result:
            cleaned[key] = result[key].strip() if result[key] else ""
    for key in ["strengths", "improvements"]:
        if key in result:
            cleaned[key] = [s.strip() for s in result[key]] if result[key] else []
    return cleaned


# ---- 4. 构建 ChatML 格式 ----
ROUND_NAMES = {
    "tech_1": "技术一面（资深工程师面试官）",
    "tech_2": "技术二面（架构师面试官）",
    "written": "笔试",
    "comprehensive": "综合面",
    "custom": "自定义练习",
}

def build_chatml(record: dict) -> dict | None:
    """将一条原始记录转换成 ChatML 格式的 training example"""
    # --- 清洗 question ---
    question = clean_question(record.get("question", ""))
    if not question:
        return None

    # --- 检查 answer ---
    answer = record.get("answer", "")
    if not is_answer_valid(answer):
        return None

    # --- 清洗 result ---
    result = clean_result(record.get("result", {}))
    if result.get("overall_score", 0) < 1:
        return None  # 无效评分

    # --- 提取上下文 ---
    context = record.get("context", {})
    profile = context.get("profile", {})
    position = profile.get("position", "未知岗位")
    round_name = ROUND_NAMES.get(record.get("round", ""), record.get("round", "面试"))
    years = profile.get("years_experience", "")
    tech_stack = ", ".join(profile.get("tech_stack", [])[:5])  # 取前5个技能

    # --- 构造 System Prompt ---
    system = (
        f"你是一个专业的{round_name}。"
        f"你正在面试一位{position}岗位的候选人。"
        f"请根据候选人的回答，从技术深度、逻辑思维、表达沟通等维度进行评分（1-10分），并给出评语和改进建议。"
    )

    # --- 构造 User Prompt ---
    user_parts = [f"【面试题】\n{question}\n", f"【回答】\n{answer}"]
    user = "\n".join(user_parts)

    # --- 构造 Assistant 输出 ---
    r = result
    strengths_str = "；".join(r.get("strengths", []))
    improvements_str = "；".join(r.get("improvements", []))
    ref_answer = r.get("reference_answer", "")

    assistant = (
        f"【评分结果】\n"
        f"技术掌握：{r.get('technical_score', 0)}/10\n"
        f"逻辑思维：{r.get('logic_score', 0)}/10\n"
        f"思维深度：{r.get('depth_score', 0)}/10\n"
        f"表达沟通：{r.get('communication_score', 0)}/10\n"
        f"综合评分：{r.get('overall_score', 0)}/10\n\n"
        f"【评语】\n{r.get('summary', '')}\n"
    )
    if strengths_str:
        assistant += f"\n【优点】\n{strengths_str}\n"
    if improvements_str:
        assistant += f"\n【改进建议】\n{improvements_str}\n"
    if ref_answer:
        assistant += f"\n【参考回答】\n{ref_answer}"

    # ChatML 格式
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]
    return {"messages": messages, "source_id": record.get("id", "")}


# ---- 5. 主流程 ----
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 读取所有原始评估数据
    raw_files = sorted(RAW_DIR.glob("eval_*.json"))
    print(f"找到 {len(raw_files)} 条原始评估记录\n")

    records = []
    for f in raw_files:
        try:
            records.append(json.loads(f.read_text("utf-8")))
        except json.JSONDecodeError as e:
            print(f"  [跳过] 解析失败 {f.name}: {e}")

    # 清洗 & 转换
    valid = []
    skipped_stats = {"question_empty": 0, "answer_invalid": 0, "score_invalid": 0}

    for rec in records:
        example = build_chatml(rec)
        if example is None:
            # 判断具体原因
            q = clean_question(rec.get("question", ""))
            if not q:
                skipped_stats["question_empty"] += 1
            elif not is_answer_valid(rec.get("answer", "")):
                skipped_stats["answer_invalid"] += 1
            else:
                skipped_stats["score_invalid"] += 1
            continue
        valid.append(example)

    print(f"清洗后有效: {len(valid)} 条")
    for reason, count in skipped_stats.items():
        if count > 0:
            print(f"  跳过: {reason} = {count} 条")

    # 按面试轮次统计
    rounds = {}
    for ex in valid:
        sys_msg = ex["messages"][0]["content"]
        for r, name in ROUND_NAMES.items():
            if name in sys_msg:
                rounds[r] = rounds.get(r, 0) + 1
                break
    print("\n轮次分布:")
    for r, c in sorted(rounds.items()):
        print(f"  {r}: {c}条")

    # 随机打乱并分割 (80% train, 20% val)
    random.shuffle(valid)
    split_idx = max(1, int(len(valid) * 0.8))
    train = valid[:split_idx]
    val = valid[split_idx:]

    print(f"\n分割: 训练集 {len(train)} 条, 验证集 {len(val)} 条")

    # 保存
    train_path = OUT_DIR / "train.jsonl"
    val_path = OUT_DIR / "val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(val_path, "w", encoding="utf-8") as f:
        for ex in val:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n已保存:")
    print(f"  {train_path}")
    print(f"  {val_path}")

    # 打印一条样例
    print("\n======== 样例数据 ========")
    sample = valid[0]
    for msg in sample["messages"]:
        role = msg["role"]
        content = msg["content"][:150]
        print(f"\n--- {role} ---")
        print(content + ("..." if len(msg["content"]) > 150 else ""))


if __name__ == "__main__":
    main()
