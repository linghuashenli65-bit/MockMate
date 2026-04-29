"""面试报告与历史记录管理"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DATA_DIR

logger = logging.getLogger(__name__)


class ReportManager:
    """面试报告管理（JSON 持久化）"""

    def __init__(self):
        self._sessions_dir = DATA_DIR / "sessions"
        self._sessions_dir.mkdir(exist_ok=True)

    def save_session(self, session_id: str, data: dict):
        """保存面试会话"""
        filepath = self._sessions_dir / f"{session_id}.json"
        data["_updated_at"] = datetime.now().isoformat()
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_session(self, session_id: str) -> Optional[dict]:
        """加载面试会话"""
        filepath = self._sessions_dir / f"{session_id}.json"
        if filepath.exists():
            return json.loads(filepath.read_text(encoding="utf-8"))
        return None

    def list_sessions(self) -> list[dict]:
        """列出所有面试记录（摘要）"""
        sessions = []
        for fp in sorted(self._sessions_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                sessions.append({
                    "id": fp.stem,
                    "position": data.get("position", "未知"),
                    "date": data.get("_updated_at", "")[:19],
                    "total_questions": len(data.get("history", [])),
                    "overall_score": data.get("report", {}).get("overall_score", 0),
                    "company": data.get("company", ""),
                })
            except Exception:
                continue
            if len(sessions) >= 50:
                break
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除面试记录"""
        fp = self._sessions_dir / f"{session_id}.json"
        if fp.exists():
            fp.unlink()
            return True
        return False
