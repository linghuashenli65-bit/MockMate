"""网络信息搜集模块

搜索招聘网站的岗位要求和社区平台的面经，
生成结构化的岗位画像供面试引擎使用。

支持「目标公司」定向搜索：当用户指定公司时，追加公司维度查询
（是否在招 / JD / 薪资待遇 / 官网招聘），并在画像中输出公司专属信息。
"""
import asyncio
import json
import logging
import random
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .ai_client import AIClient

logger = logging.getLogger(__name__)

# 搜索来源配置：{position} 岗位维度，{company} 公司维度
SEARCH_SOURCES = {
    "jobs": [
        "{position} 岗位要求 技能要求",
        "{position} JD 职位描述 任职要求",
    ],
    "interviews": [
        "{position} 面经 面试经验",
        "{position} 面试题 小红书",
        "{position} 面试经验 知乎",
        "{position} 面试 贴吧",
        "{position} 面经 技术栈 面试问题",
    ],
    "company_jobs": [
        "{company} {position} 招聘 岗位职责 薪资待遇",
        "{company} {position} JD 任职要求 招聘公告",
        "{company} {position} 2026 校招 社招 招聘",
        "{company} 招聘 官网 {position} 岗位",
    ],
    "company_interviews": [
        "{company} {position} 面经 面试经验",
        "{company} {position} 面试 知乎",
        "{company} {position} 薪资 待遇",
    ],
}

# 搜索引擎配置
# DuckDuckGo 在中国可能被屏蔽，所以用 Bing 作为主要搜索引擎
SEARCH_ENGINES = [
    {
        "name": "bing",
        "url": "https://www.bing.com/search",
        "method": "GET",
        "param_field": "q",
        "result_selector": ".b_algo",
        "snippet_selector": ".b_caption p",
        "url_selector": "h2 a",
    },
    {
        "name": "duckduckgo",
        "url": "https://html.duckduckgo.com/html/",
        "method": "POST",
        "data_field": "q",
        "result_selector": ".result",
        "snippet_selector": ".result__snippet",
        "url_selector": ".result__a",
    },
]

# 轮换 User-Agent，降低被拦截概率
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]

HTTP_TIMEOUT = 15.0
MAX_RETRIES = 2


class WebResearch:
    """网络信息搜集 + 岗位画像生成"""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            trust_env=False,  # 不读系统代理，直连搜索
        )
        self._http.headers.update({
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._user_agent_index = random.randint(0, len(USER_AGENTS) - 1)

    def _rotate_user_agent(self):
        """轮换 User-Agent"""
        self._user_agent_index = (self._user_agent_index + 1) % len(USER_AGENTS)
        self._http.headers["User-Agent"] = USER_AGENTS[self._user_agent_index]

    async def search_position(self, position: str, company: str = "") -> dict:
        """搜索岗位信息 + 面经，生成结构化的岗位画像。

        指定 company 时追加公司定向查询（是否在招 / JD / 薪资）。
        """
        company = (company or "").strip()
        logger.info(f"开始搜索岗位信息: {position}" + (f" @ {company}" if company else ""))

        if company:
            job_results, interview_results, cjob, civ = await asyncio.gather(
                self._search_all("jobs", position),
                self._search_all("interviews", position),
                self._search_all("company_jobs", position, company),
                self._search_all("company_interviews", position, company),
            )
            job_results = cjob + job_results
            interview_results = civ + interview_results
        else:
            job_results, interview_results = await asyncio.gather(
                self._search_all("jobs", position),
                self._search_all("interviews", position),
            )

        profile = await self._generate_profile(position, company, job_results, interview_results)
        return profile

    async def _search_all(self, category: str, position: str, company: str = "") -> list[str]:
        """并行搜索一类关键词（岗位要求 / 面经 / 公司定向）"""
        queries = [
            t.replace("{position}", position).replace("{company}", company)
            for t in SEARCH_SOURCES.get(category, [])
        ]
        tasks = [self._search_with_fallback(q) for q in queries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for q, r in zip(queries, results_list):
            if isinstance(r, tuple) and r[0]:
                results.extend(r[0])
                logger.info(f"  {category}搜索完成: {q} ({len(r[0])} 条)")
            elif isinstance(r, list) and r:
                results.extend(r)
                logger.info(f"  {category}搜索完成: {q} ({len(r)} 条)")
            else:
                logger.warning(f"  {category}搜索失败 [{q}]: {r}")
        return results

    async def _search_with_fallback(self, query: str, max_results: int = 5):
        """多搜索引擎搜索，逐个尝试直到拿到结果，返回 (snippets, urls)"""
        for engine in SEARCH_ENGINES:
            snippets, urls = await self._search_engine(engine, query, max_results)
            if snippets:
                return snippets, urls
            logger.info(f"{engine['name']} 无结果，尝试下一个搜索引擎: {query}")
        return [], []

    async def _search_engine(self, engine: dict, query: str, max_results: int):
        """使用指定搜索引擎搜索，返回 (snippets, urls)"""
        for attempt in range(MAX_RETRIES):
            self._rotate_user_agent()
            try:
                if engine["method"] == "POST":
                    resp = await self._http.post(
                        engine["url"],
                        data={engine["data_field"]: query},
                        timeout=HTTP_TIMEOUT,
                    )
                else:
                    resp = await self._http.get(
                        engine["url"],
                        params={engine["param_field"]: query},
                        timeout=HTTP_TIMEOUT,
                    )
                logger.info(f"  {engine['name']} 返回状态码 {resp.status_code}")
                snippets, urls = self._parse_results(resp.text, engine, max_results)
                logger.info(f"  {engine['name']} 解析到 {len(snippets)} 条结果")
                return snippets, urls
            except httpx.TimeoutException:
                logger.warning(f"  {engine['name']} 超时 (尝试 {attempt + 1}/{MAX_RETRIES}): {query}")
            except httpx.HTTPStatusError as e:
                logger.warning(f"  {engine['name']} HTTP {e.response.status_code} (尝试 {attempt + 1}/{MAX_RETRIES}): {query}")
            except Exception as e:
                logger.warning(f"  {engine['name']} 错误: {e} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1)
        return [], []

    def _parse_results(self, html: str, engine: dict, max_results: int):
        """从 HTML 中解析搜索结果，返回 (snippets, urls)"""
        soup = BeautifulSoup(html, "lxml")
        snippets = []
        urls = []
        for result in soup.select(engine["result_selector"])[:max_results]:
            snippet_el = result.select_one(engine["snippet_selector"])
            if snippet_el:
                text = snippet_el.get_text(strip=True)
                if text:
                    snippets.append(text)
                    link = result.select_one(engine.get("url_selector", "a"))
                    href = link.get("href") if link else None
                    if href:
                        urls.append(href)
        return snippets, urls

    async def _generate_profile(
        self,
        position: str,
        company: str,
        job_results: list[str],
        interview_results: list[str],
    ) -> dict:
        """用 AI 生成结构化岗位画像（搜索结果为参考，公司定向信息优先）"""
        hint = ""
        if company:
            hint += f"\n=== 目标公司: {company} ===\n"
        if job_results:
            hint += "\n=== 从招聘网站搜集到的岗位要求 ===\n" + "\n".join(job_results[:12])
        if interview_results:
            hint += "\n=== 从社区搜集到的面经信息 ===\n" + "\n".join(interview_results[:12])

        if company:
            company_section = (
                f"目标公司: {company}\n"
                "请优先基于与该目标公司相关的搜索结果判断该公司该岗位的招聘情况、薪酬待遇和任职要求。\n"
                "如果搜索结果中没有该公司的专属信息，请在 hiring_status / salary_range / company_insights 中如实标注'未查到该公司专属信息'，不要编造。"
            )
        else:
            company_section = "目标公司: 未指定（生成通用岗位画像）"

        prompt = f"""你是一个资深的招聘专家和面试官。请为目标岗位生成详细的"岗位画像"。

{company_section}

目标岗位: {position}

请基于你的专业知识回答，以下网络搜索结果仅供参考（可能为空）：{hint}

输出 JSON 格式（必须包含以下所有字段）：

{{
  "position": "岗位名称",
  "summary": "岗位概述（2-3句话，包括该岗位的核心职责和发展方向）",
  "required_skills": ["必备技能1", "必备技能2", ...],
  "nice_to_have": ["加分技能1", ...],
  "tech_stack": ["核心技术1", "技术2", ...],
  "responsibilities": ["工作职责1", ...],
  "common_interview_topics": [
    "常见面试题1（附考察点说明）",
    "常见面试题2（附考察点说明）",
    "常见面试题3（附考察点说明）"
  ],
  "interview_focus": ["面试重点考察方向1", ...],
  "difficulty": "junior/mid/senior",
  "years_experience": "X年经验",
  "industry_insights": "该岗位的市场趋势和薪资概况",
  "hiring_status": "是否在招（在招/未查到在招信息/无法确认，基于搜索结果判断）",
  "salary_range": "薪酬范围（例如 25k-40k·13薪，优先用目标公司相关搜索结果，否则给市场概况并注明）",
  "company_insights": "目标公司该岗位的招聘特点、面试风格或要求（未指定公司时留空）",
  "sources": ["参考来源链接或页面描述，最多5条"]
}}

要求：
- 直接基于你的知识生成，如果网络搜索结果为空也完全没关系
- 所有字段用中文填写
- common_interview_topics 写5-8个真实具体的面试题
- interview_focus 写3-5个考察重点
- 内容要具体、有参考价值，不要泛泛而谈"""

        result = await self.ai.reason([{"role": "user", "content": prompt}], max_tokens=4096)
        if not result:
            return self._fallback_profile(position, company)

        # 尝试解析 JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
            result = result.rsplit("```", 1)[0]
        result = result.strip()

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', result)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return self._fallback_profile(position, company, result)

    def _fallback_profile(self, position: str, company: str = "", raw_text: str = "") -> dict:
        return {
            "position": position,
            "company": company,
            "summary": "基于 AI 知识库生成的岗位画像（网络搜索未返回有效数据）",
            "required_skills": [],
            "nice_to_have": [],
            "tech_stack": [],
            "responsibilities": [],
            "common_interview_topics": [],
            "interview_focus": [],
            "difficulty": "mid",
            "years_experience": "1-3年",
            "industry_insights": "",
            "hiring_status": "无法确认",
            "salary_range": "",
            "company_insights": "",
            "sources": [],
            "_raw": raw_text[:500] if raw_text else "",
        }

    async def close(self):
        await self._http.aclose()
