"""训练数据采集与反馈管理

自动记录 AI 评分结果，管理用户点赞/点踩反馈。
点赞 → 标记 quality=good，可作训练数据
点踩 → 用户提交修正后存入 reviewed 目录
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

_TRAINING_DIR = DATA_DIR / "training"
_RAW_DIR = _TRAINING_DIR / "raw"
_REVIEWED_DIR = _TRAINING_DIR / "reviewed"


class TrainingDataCollector:
    """训练数据采集器"""

    def __init__(self):
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        _REVIEWED_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 写入 ----

    def save_evaluation(
        self,
        question: str,
        answer: str,
        result: dict,
        round_name: str = "",
        context: Optional[dict] = None,
        latency_ms: Optional[float] = None,
        token_count: Optional[int] = None,
    ) -> str:
        """保存一次 AI 评分结果到 raw 目录"""
        record_id = uuid.uuid4().hex[:12]
        record = {
            "id": record_id,
            "type": "evaluation",
            "round": round_name,
            "question": question,
            "answer": answer,
            "result": result,
            "context": context or {},
            "latency_ms": latency_ms,
            "token_count": token_count,
            "quality": None,  # "good" | "bad" | None
            "corrections": None,
            "timestamp": datetime.now().isoformat(),
            "reviewed": False,
        }
        filepath = _RAW_DIR / f"eval_{record_id}.json"
        filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record_id

    def save_score(self, resume: str, profile: dict, result: dict,
                   latency_ms: Optional[float] = None,
                   token_count: Optional[int] = None) -> str:
        """保存一次简历评分结果"""
        record_id = uuid.uuid4().hex[:12]
        record = {
            "id": record_id,
            "type": "score",
            "resume_snippet": resume[:300],
            "profile": {k: v for k, v in profile.items() if k != "_raw"},
            "result": result,
            "latency_ms": latency_ms,
            "token_count": token_count,
            "quality": None,
            "corrections": None,
            "timestamp": datetime.now().isoformat(),
            "reviewed": False,
        }
        filepath = _RAW_DIR / f"score_{record_id}.json"
        filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record_id

    def submit_feedback(self, record_type: str, record_id: str, rating: str,
                        corrections: Optional[dict] = None) -> bool:
        """提交用户反馈

        Args:
            record_type: "eval" 或 "score"
            record_id: 记录 ID
            rating: "up" 或 "down"
            corrections: 点踩时用户提交的修正内容
        Returns:
            是否成功
        """
        prefix = "eval" if record_type == "eval" else "score"
        filepath = _RAW_DIR / f"{prefix}_{record_id}.json"

        if not filepath.exists():
            logger.warning(f"反馈目标不存在: {filepath}")
            return False

        try:
            record = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"读取记录失败 {filepath}: {e}")
            return False

        record["quality"] = "good" if rating == "up" else "bad"
        record["reviewed"] = rating == "down"  # 点踩视为已人工审查

        if corrections:
            record["corrections"] = corrections
            # 同时存到 reviewed 目录（人工修正数据）
            reviewed_path = _REVIEWED_DIR / f"{prefix}_{record_id}.json"
            reviewed_record = dict(record)
            reviewed_record["result"] = corrections  # 用修正值替代原始结果
            reviewed_path.write_text(
                json.dumps(reviewed_record, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        filepath.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"反馈已记录: {record_type}/{record_id} → {rating}")
        return True

    # ---- 读取 ----

    def list_records(self, record_type: Optional[str] = None,
                     quality: Optional[str] = None,
                     source: str = "raw") -> list[dict]:
        """列出训练数据

        Args:
            record_type: "eval" | "score" | None（全部）
            quality: "good" | "bad" | None（全部）
            source: "raw" | "reviewed"
        """
        directory = _RAW_DIR if source == "raw" else _REVIEWED_DIR
        if not directory.exists():
            return []

        records = []
        for f in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix != ".json":
                continue
            try:
                record = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if record_type and record.get("type") != record_type:
                continue
            if quality is not None and record.get("quality") != quality:
                continue
            records.append(record)
        return records

    def get_stats(self) -> dict:
        """获取训练数据统计"""
        raw_evals = list(_RAW_DIR.glob("eval_*.json"))
        raw_scores = list(_RAW_DIR.glob("score_*.json"))
        reviewed = list(_REVIEWED_DIR.glob("*.json"))

        good = sum(1 for f in raw_evals + raw_scores if self._check_quality(f, "good"))
        bad = sum(1 for f in raw_evals + raw_scores if self._check_quality(f, "bad"))
        pending = sum(1 for f in raw_evals + raw_scores if self._check_quality(f, None))

        return {
            "total_raw": len(raw_evals) + len(raw_scores),
            "evaluations": len(raw_evals),
            "scores": len(raw_scores),
            "reviewed": len(reviewed),
            "quality_good": good,
            "quality_bad": bad,
            "quality_pending": pending,
        }

    @staticmethod
    def _check_quality(filepath: Path, expected: Optional[str]) -> bool:
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return data.get("quality") is expected
        except (json.JSONDecodeError, OSError):
            return False


# 全局单例
_collector: Optional[TrainingDataCollector] = None


def get_collector() -> TrainingDataCollector:
    global _collector
    if _collector is None:
        _collector = TrainingDataCollector()
    return _collector
