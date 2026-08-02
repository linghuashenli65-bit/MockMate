# -*- coding: utf-8 -*-
"""真实岗位搜索验证脚本（UTF-8 源文件，避免 heredoc 编码问题）"""
import asyncio
import json
import sys

sys.path.insert(0, "C:/Users/27644/Desktop/MockMate")
from backend.ai_client import AIClient
from backend.web_research import WebResearch


async def main():
    ai = AIClient()
    r = WebResearch(ai)
    try:
        profile = await r.search_position("ai应用开发工程师", "上海喆塔")
        print("=== 画像输出 ===")
        for k in ("position", "company", "hiring_status", "salary_range", "company_insights", "sources", "industry_insights"):
            print(f"{k}: {json.dumps(profile.get(k), ensure_ascii=False)[:300]}")
        print("required_skills:", json.dumps(profile.get("required_skills"), ensure_ascii=False)[:200])
        print("summary:", json.dumps(profile.get("summary"), ensure_ascii=False)[:200])
        print("is_fallback:", bool(profile.get("_raw")) or not profile.get("required_skills"))
    finally:
        await r.close()
        await ai.close()


asyncio.run(main())
