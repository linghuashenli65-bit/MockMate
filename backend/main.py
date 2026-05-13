"""MockMate 主服务"""
import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import socket

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import io

from pypdf import PdfReader
from docx import Document

from .config import HOST, PORT, DATA_DIR, ALLOW_SHARED_API_KEY
from .ai_client import AIClient
from .web_research import WebResearch
from .interview_engine import InterviewEngine, QuestionPool, load_pool_cache, save_pool_cache
from .tts import TTSEngine
from .finetune import get_collector
from .database import db
from .mail import create_mailer, send_verification_email
from .auth import (
    create_access_token, generate_code, save_code, verify_code,
    create_user, authenticate_user, get_user_by_id, email_exists,
    get_current_user, init_user_tables,
)

# -------- 日志配置（控制台 + 文件）--------
DATA_DIR.mkdir(exist_ok=True)
log_file = DATA_DIR / "mockmate.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_file), encoding="utf-8", mode="a"),
    ],
)
logger = logging.getLogger("mockmate")

# 全局实例
ai = AIClient()
mailer = None  # 在 lifespan 中初始化

# 各类面试默认总题数
ROUND_TOTALS = {
    "written": 20,
    "tech_1": 8,
    "tech_2": 6,
    "comprehensive": 6,
}

# 面试题库池（内存）
_question_pools: dict[str, 'QuestionPool'] = {}

# 笔试后台预生成
_written_bg_tasks: dict[str, asyncio.Task] = {}   # 运行中的 task
_written_bg_results: dict[str, list[dict]] = {}   # 已完成的结果


async def _background_written_batch(
    session_id: str, total: int, resume: str, profile: dict,
    used_questions: set,
):
    """后台并发生成下一批笔试题，完成后存入结果池"""
    try:
        engine = InterviewEngine(ai)
        qs = await engine.pre_generate_written(total, resume, profile, used_questions)
        _written_bg_results[session_id] = qs
    except Exception as e:
        logger.error(f"后台生成笔试题失败 [{session_id}]: {e}")
        _written_bg_results[session_id] = []
    finally:
        _written_bg_tasks.pop(session_id, None)


async def background_refill(session_id: str, pool: QuestionPool, resume: str, profile: dict, round_name: str):
    """后台补题任务"""
    try:
        engine = InterviewEngine(ai)
        await engine.refill_pool(pool, resume, profile, round_name, used_questions=set())
        logger.info(f"后台补题完成 [{session_id}]: 池中 easy={len(pool.easy)} medium={len(pool.medium)} hard={len(pool.hard)}")
    except Exception as e:
        logger.error(f"后台补题失败 [{session_id}]: {e}")


# -------- API Key 请求头提取 --------

def get_user_ai(
    x_mimo_api_key: Optional[str] = Header(None, alias="X-Mimo-Api-Key"),
    x_deepseek_api_key: Optional[str] = Header(None, alias="X-Deepseek-Api-Key"),
    x_qwen_api_key: Optional[str] = Header(None, alias="X-Qwen-Api-Key"),
    x_qwen_model_reasoner: Optional[str] = Header(None, alias="X-Qwen-Model-Reasoner"),
    x_qwen_model_chat: Optional[str] = Header(None, alias="X-Qwen-Model-Chat"),
    x_qwen_model_written_eval: Optional[str] = Header(None, alias="X-Qwen-Model-Written-Eval"),
    x_qwen_tts_model: Optional[str] = Header(None, alias="X-Qwen-Tts-Model"),
    x_zhipu_api_key: Optional[str] = Header(None, alias="X-Zhipu-Api-Key"),
    x_zhipu_model_reasoner: Optional[str] = Header(None, alias="X-Zhipu-Model-Reasoner"),
    x_zhipu_model_chat: Optional[str] = Header(None, alias="X-Zhipu-Model-Chat"),
    x_zhipu_model_written_eval: Optional[str] = Header(None, alias="X-Zhipu-Model-Written-Eval"),
    x_zhipu_tts_model: Optional[str] = Header(None, alias="X-Zhipu-Tts-Model"),
    x_ai_provider: Optional[str] = Header(None, alias="X-Ai-Provider"),
) -> AIClient:
    """从请求头提取 API Key，创建 per-request 的 AIClient。"""
    has_any_key = x_mimo_api_key or x_deepseek_api_key or x_qwen_api_key or x_zhipu_api_key
    if has_any_key:
        return ai.with_keys(
            mimo_key=x_mimo_api_key,
            deepseek_key=x_deepseek_api_key,
            qwen_key=x_qwen_api_key,
            qwen_reasoner_model=x_qwen_model_reasoner,
            qwen_chat_model=x_qwen_model_chat,
            qwen_written_eval_model=x_qwen_model_written_eval,
            qwen_tts_model=x_qwen_tts_model,
            zhipu_key=x_zhipu_api_key,
            zhipu_reasoner_model=x_zhipu_model_reasoner,
            zhipu_chat_model=x_zhipu_model_chat,
            zhipu_written_eval_model=x_zhipu_model_written_eval,
            zhipu_tts_model=x_zhipu_tts_model,
            provider=x_ai_provider,
        )
    if x_ai_provider:
        return ai.with_keys(provider=x_ai_provider)
    if not ALLOW_SHARED_API_KEY:
        raise HTTPException(401, "请提供 API Key（通过 X-Mimo-Api-Key / X-Deepseek-Api-Key / X-Qwen-Api-Key / X-Zhipu-Api-Key 请求头）")
    logger.warning("未提供 API Key 的请求正在使用全局配置的 Key（如需关闭请设置 ALLOW_SHARED_API_KEY=false）")
    return ai


# ---------- Request Models ----------

class ConfigUpdate(BaseModel):
    provider: str = ""

# ---------- Auth Request Models ----------

class SendCodeRequest(BaseModel):
    email: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    code: str
    nickname: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class ResearchRequest(BaseModel):
    position: str
    refresh: bool = False

class ResumeText(BaseModel):
    text: str

class ResumeScoreRequest(BaseModel):
    resume: str
    profile: dict

class FeedbackRequest(BaseModel):
    """点赞/点踩反馈"""
    record_type: str = "eval"    # "eval" | "score"
    record_id: str               # collector 返回的 ID
    rating: str                  # "up" | "down"
    corrections: Optional[dict] = None  # 点踩后的修正值

class FeedbackDataRequest(BaseModel):
    """获取训练数据列表"""
    record_type: Optional[str] = None
    quality: Optional[str] = None
    source: str = "raw"

class StartInterview(BaseModel):
    resume: str
    position: str
    company: str = ""
    profile: dict = {}
    round: str = "tech_1"
    custom_question_ids: list[int] = []
    enable_tts: bool = True

class AnswerSubmission(BaseModel):
    session_id: str
    question_index: int
    answer: str
    hint_used: bool = False
    enable_tts: Optional[bool] = None

class EndInterview(BaseModel):
    session_id: str

class HintRequest(BaseModel):
    session_id: str
    question_index: int

class FavoriteCreate(BaseModel):
    session_id: str = ""
    question: str
    type: str = ""
    difficulty: str = ""
    topic: str = ""
    user_answer: str = ""
    overall_score: int = 0

class CustomQuestionCreate(BaseModel):
    question: str
    type: str = "技术"
    difficulty: str = "medium"
    topic: str = ""
    expected_points: list = []
    tags: str = ""

class CustomQuestionUpdate(BaseModel):
    question: str
    type: str = "技术"
    difficulty: str = "medium"
    topic: str = ""
    expected_points: list = []
    tags: str = ""


# ---------- FastAPI ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    # 初始化用户表（在 MySQL 可用时）
    if db.available and db.pool:
        await init_user_tables(db.pool)
    # 初始化邮件发送器
    global mailer
    mailer = create_mailer()
    logger.info("MockMate 服务启动")
    logger.info(f"  日志文件: {log_file}")
    logger.info(f"  数据库:   {'MySQL' if db.available else 'JSON 文件'}")
    for name, client in [("MiMo API", ai.mimo), ("DeepSeek", ai.deepseek), ("Qwen", ai.qwen), ("Zhipu", ai.zhipu)]:
        logger.info(f"  {name}:    {'已配置' if client.ready else '未配置'}")
    logger.info(f"  当前提供商:   {ai.provider}")
    stats = await db.cache_stats()
    logger.info(f"  缓存:         {stats['valid']} 条有效")
    yield
    await ai.close()
    await db.close()

app = FastAPI(title="MockMate", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ==================== 基础 ====================

@app.get("/api/status")
async def get_status(user_ai: AIClient = Depends(get_user_ai)):
    stats = await db.cache_stats()
    return {
        "status": "ok",
        "provider": user_ai.provider,
        "mimo_ready": user_ai.mimo.ready,
        "deepseek_ready": user_ai.deepseek.ready,
        "qwen_ready": user_ai.qwen.ready,
        "zhipu_ready": user_ai.zhipu.ready,
        "db": "mysql" if db.available else "json",
        "cache": stats,
    }

@app.post("/api/config")
def update_config(cfg: ConfigUpdate, user_ai: AIClient = Depends(get_user_ai)):
    """切换 AI 提供商（API Key 由浏览器管理，不经过后端存储）"""
    if cfg.provider in ("mimo", "deepseek", "qwen", "zhipu"):
        user_ai.provider = cfg.provider
    return {"message": "配置已更新"}


# ==================== 用户认证 ====================

@app.post("/api/auth/send-code")
async def send_verification_code(req: SendCodeRequest):
    """发送邮箱验证码（基于 fastapi-mail 异步发送）"""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "请输入有效邮箱地址")
    # 生成验证码
    code = generate_code()
    save_code(email, code)
    # 异步发送邮件
    sent = await send_verification_email(mailer, email, code)
    logger.info(f"验证码已发送到 {email}: {code}")
    return {
        "message": "验证码已发送",
        "dev_code": code if not sent else None,  # 开发模式返回验证码
    }


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """用户注册（邮箱 + 验证码）"""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "请输入有效邮箱")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    # 校验验证码
    if not verify_code(email, req.code):
        raise HTTPException(400, "验证码错误或已过期")
    # 检查邮箱是否已注册
    if db.available and db.pool:
        if await email_exists(db.pool, email):
            raise HTTPException(409, "该邮箱已被注册")
        user_id = await create_user(db.pool, email, req.password, req.nickname)
        if user_id is None:
            raise HTTPException(409, "该邮箱已被注册")
    else:
        # MySQL 不可用时模拟注册（仅开发）
        logger.warning(f"[DEV] 模拟注册: {email}")
        user_id = 1
    # 生成 Token
    token = create_access_token(user_id, email)
    return {
        "token": token,
        "user": {"id": user_id, "email": email, "nickname": req.nickname or email.split("@")[0]},
    }


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """用户登录"""
    email = req.email.strip().lower()
    if not email or not req.password:
        raise HTTPException(400, "请输入邮箱和密码")
    if not db.available or not db.pool:
        raise HTTPException(503, "数据库不可用，无法登录")
    user = await authenticate_user(db.pool, email, req.password)
    if not user:
        raise HTTPException(401, "邮箱或密码错误")
    token = create_access_token(user["id"], user["email"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "nickname": user.get("nickname", "")},
    }


@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    if db.available and db.pool:
        user = await get_user_by_id(db.pool, current_user["id"])
        if user:
            return {"id": user["id"], "email": user["email"], "nickname": user.get("nickname", "")}
    return current_user


# ==================== 简历 ====================

@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...), user_ai: AIClient = Depends(get_user_ai)):
    contents = await file.read()
    ext = Path(file.filename).suffix.lower()

    if ext in (".jpg", ".jpeg", ".png"):
        text = await user_ai.extract_text_from_image(contents)
        if text:
            return {"text": text, "source": "ocr"}
        raise HTTPException(503, "图片识别需要配置 MiMo API Key")

    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return {"text": text.strip(), "source": "pdf"}
        except Exception:
            pass  # pypdf 失败，尝试 OCR
        try:
            import fitz
            doc = fitz.open(stream=contents, filetype="pdf")
            pages_text = []
            for page_num in range(min(len(doc), 10)):
                pix = doc[page_num].get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                page_text = await user_ai.extract_text_from_image(img_bytes)
                if page_text and page_text.strip():
                    pages_text.append(page_text.strip())
            doc.close()
            if pages_text:
                return {"text": "\n\n".join(pages_text), "source": "ocr"}
        except ImportError:
            logger.warning("PyMuPDF 未安装，无法对扫描件 PDF 执行 OCR")
        except Exception as e:
            logger.error(f"PDF OCR 失败: {e}")
        raise HTTPException(400, "无法从 PDF 中提取文字（可能为扫描件），请先转换为图片格式上传")

    if ext == ".docx":
        try:
            doc = Document(io.BytesIO(contents))
            parts = [p.text for p in doc.paragraphs]
            # 表格中的文字（中文简历常用表格排版，需处理合并单元格重复）
            for table in doc.tables:
                for row in table.rows:
                    seen = set()
                    for cell in row.cells:
                        t = cell.text.strip()
                        if t and t not in seen:
                            parts.append(t)
                            seen.add(t)
            text = "\n".join(parts)
            if text.strip():
                return {"text": text.strip(), "source": "docx"}
        except Exception as e:
            logger.error(f"DOCX 解析失败: {e}")
            raise HTTPException(400, f"Word 文档解析失败: {str(e)}")
        # 段落和表格都为空，可能是扫描件或纯图片型 DOCX
        raise HTTPException(400, "无法从 Word 文档中提取文字，请转换为 PDF 或图片上传")

    if ext == ".md":
        try:
            text = contents.decode("utf-8")
            if text.strip():
                return {"text": text.strip(), "source": "markdown"}
            raise HTTPException(400, "Markdown 文件内容为空")
        except UnicodeDecodeError:
            raise HTTPException(400, "Markdown 文件编码错误，请使用 UTF-8 编码")
        except Exception as e:
            logger.error(f"MD 解析失败: {e}")
            raise HTTPException(400, f"Markdown 解析失败: {str(e)}")

    raise HTTPException(400, f"不支持的文件格式: {ext}，支持 JPG/PNG/PDF/DOCX/MD")

@app.post("/api/resume/analyze")
async def analyze_resume(req: ResumeText, user_ai: AIClient = Depends(get_user_ai)):
    if not req.text.strip():
        raise HTTPException(400, "简历内容不能为空")
    prompt = f"""分析以下简历，输出 JSON：
{req.text[:4000]}
{{"skills":[],"experience_years":"","projects":[],"strengths":[],"weaknesses":[]}}"""
    result = await user_ai.reason([{"role": "user", "content": prompt}], max_tokens=2048)
    if not result:
        raise HTTPException(503, "AI 不可用")
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"raw": result, "skills": []}


@app.post("/api/resume/score")
async def score_resume(req: ResumeScoreRequest, user_ai: AIClient = Depends(get_user_ai)):
    """依据岗位画像对简历评分（0-100），并给出优缺点和优化建议"""
    if not req.resume.strip():
        raise HTTPException(400, "简历内容不能为空")
    if not req.profile:
        raise HTTPException(400, "请先生成岗位画像")

    provider = user_ai.provider
    logger.info(f"开始简历评分，provider={provider}, mimo_ready={user_ai.mimo.ready}, deepseek_ready={user_ai.deepseek.ready}")

    profile_str = json.dumps(req.profile, ensure_ascii=False, indent=2)
    prompt = f"""你是一个资深的招聘专家（HR + 技术面试官）。请根据目标岗位画像，对候选人简历进行评分和评估。

== 目标岗位画像 ==
{profile_str}

== 候选人简历 ==
{req.resume[:3000]}

请从以下维度评估简历与目标岗位的匹配度：
1. 教育背景（学校层次、学历、专业是否匹配或相关）
2. 技能匹配度（必备技能覆盖了多少）
3. 项目经验相关性（项目经验是否与岗位方向一致）
4. 技术栈覆盖（核心技术的掌握程度）
5. 工作年限匹配度
6. 整体竞争力

输出 JSON（严格按照以下格式，不要输出其他内容）：
{{"score": 0-100, "strengths": ["优点1", "优点2", "优点3"], "weaknesses": ["不足1", "不足2"], "suggestions": ["优化建议1", "优化建议2", "优化建议3"]}}

评分标准：
- 90-100：完美匹配，几乎可以直接面试
- 70-89：良好匹配，可以参加面试
- 50-69：部分匹配，简历需要优化
- 0-49：匹配度低，建议大幅修改简历后再投递

请确保分数客观公正，严格根据简历内容与岗位画像的匹配程度打分。"""
    # 调用 AI，失败时重试一次（记录耗时和 token）
    t0 = time.monotonic()
    result = await user_ai.reason([{"role": "user", "content": prompt}], max_tokens=2048)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    if not result:
        logger.warning(f"简历评分 AI 首次调用返回空，2 秒后重试...")
        await asyncio.sleep(2)
        t0 = time.monotonic()
        result = await user_ai.reason([{"role": "user", "content": prompt}], max_tokens=2048)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
    if not result:
        logger.error(f"简历评分 AI 返回空（provider={provider}，mimo={user_ai.mimo.ready} deepseek={user_ai.deepseek.ready}）")
        raise HTTPException(503, "AI 不可用，请稍后重试")

    usage = user_ai.last_usage
    token_count = usage.get("total_tokens") if usage else None
    # 修复 AI 输出中 JSON 字符串内的真实换行符 → \\n 转义序列
    result = InterviewEngine._repair_json_newlines(result)

    collector = get_collector()
    try:
        data = json.loads(result)
        data["score"] = max(0, min(100, int(data.get("score", 0))))
        record_id = collector.save_score(req.resume, req.profile, data, latency_ms, token_count)
        data["_record_id"] = record_id
        return data
    except (json.JSONDecodeError, ValueError):
        import re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                data["score"] = max(0, min(100, int(data.get("score", 0))))
                record_id = collector.save_score(req.resume, req.profile, data, latency_ms, token_count)
                data["_record_id"] = record_id
                return data
            except (json.JSONDecodeError, ValueError):
                pass
        logger.error(f"简历评分解析失败: {result[:500]}")
        raise HTTPException(500, "评分解析失败，请重试")


# ==================== 岗位研究（带缓存）====================

@app.post("/api/research")
async def research_position(req: ResearchRequest, user_ai: AIClient = Depends(get_user_ai),
                            current_user: dict = Depends(get_current_user)):
    position = req.position.strip()
    if not position:
        raise HTTPException(400, "请输入目标岗位")

    # 查缓存（除非指定 refresh=true）
    if not req.refresh:
        cached = await db.cache_get(position)
        if cached:
            logger.info(f"缓存命中: {position}")
            return cached

    logger.info(f"全网搜索: {position}")
    research = WebResearch(user_ai)
    try:
        profile = await research.search_position(position)
        # 只有生成了实质内容才缓存
        if profile.get("required_skills") or profile.get("common_interview_topics"):
            await db.cache_set(position, profile)
            # 记录搜索历史（关联 user_id）
            await db.save_search_history(position, profile, user_id=current_user["id"])
        return profile
    except Exception as e:
        logger.error(f"岗位分析失败: {e}", exc_info=True)
        raise HTTPException(502, f"岗位分析失败: {str(e)}")
    finally:
        await research.close()

@app.get("/api/cache/stats")
async def cache_stats():
    return await db.cache_stats()

@app.post("/api/cache/clear")
async def cache_clear():
    await db.cache_clear()
    return {"message": "缓存已清空"}

@app.get("/api/search/history")
async def search_history(current_user: dict = Depends(get_current_user)):
    """获取搜索历史（仅当前用户）"""
    return {"records": await db.get_search_history(limit=30, user_id=current_user["id"])}


# ==================== 面试 ====================

@app.post("/api/interview/start")
async def start_interview(req: StartInterview, user_ai: AIClient = Depends(get_user_ai),
                          current_user: dict = Depends(get_current_user)):
    """开始一场新面试"""
    session_id = uuid.uuid4().hex[:12]
    profile = req.profile or {"position": req.position}
    engine = InterviewEngine(user_ai)
    tts = TTSEngine(user_ai)
    uid = current_user["id"]

    # 自定义题目模式
    if req.custom_question_ids:
        custom_questions = await db.list_custom_question_ids(req.custom_question_ids)
        if not custom_questions:
            raise HTTPException(400, "未找到指定的自定义题目")
        question = custom_questions[0]
        session = {
            "id": session_id,
            "position": req.position,
            "company": req.company,
            "resume": req.resume,
            "profile": profile,
            "round": "custom",
            "history": [],
            "current_question": question,
            "current_index": 0,
            "custom_questions": custom_questions,
            "created_at": datetime.now().isoformat(),
        }
        await db.save_session(session_id, session, user_id=uid)
        return {
            "session_id": session_id,
            "question": question,
            "question_index": 0,
            "round": "custom",
            "audio_url": None,
        }

    round_name = req.round

    # 笔试：先出 5 题秒开，答题时后台继续生成
    if round_name == "written":
        questions_initial = await engine.pre_generate_written(5, req.resume, profile)
        question = questions_initial[0]
        # 不再后台预生成，答题时池中余量不足会自动触发下一批
        session = {
            "id": session_id,
            "position": req.position,
            "company": req.company,
            "resume": req.resume,
            "profile": profile,
            "round": round_name,
            "history": [],
            "current_question": question,
            "current_index": 0,
            "written_questions": questions_initial,
            "written_total": 20,
            "created_at": datetime.now().isoformat(),
        }
        await db.save_session(session_id, session, user_id=uid)
        return {
            "session_id": session_id,
            "question": question,
            "question_index": 0,
            "round": round_name,
            "audio_url": None,
        }

    question = await engine.generate_first_question(req.resume, profile, round_name)
    enable_tts = req.enable_tts
    audio_path = await tts.synthesize(question["question"], session_id, 0) if enable_tts else None

    # 初始化题库池
    total_needed = ROUND_TOTALS.get(round_name, 8)
    pool = QuestionPool(total_needed=total_needed)
    cached = load_pool_cache(req.resume, req.position, round_name)
    if cached:
        pool.import_cached(cached)
        logger.info(f"题库缓存加载: {len(cached)} 题 (session={session_id})")
    _question_pools[session_id] = pool
    if pool.needs_refill():
        asyncio.create_task(background_refill(session_id, pool, req.resume, profile, round_name))

    session = {
        "id": session_id,
        "position": req.position,
        "company": req.company,
        "resume": req.resume,
        "profile": profile,
        "round": round_name,
        "history": [],
        "current_question": question,
        "current_index": 0,
        "enable_tts": enable_tts,
        "question_pool": pool.to_dict(),
        "created_at": datetime.now().isoformat(),
    }
    await db.save_session(session_id, session, user_id=uid)

    return {
        "session_id": session_id,
        "question": question,
        "question_index": 0,
        "round": round_name,
        "audio_url": f"/api/audio/{session_id}_q000.wav" if audio_path else None,
    }

@app.post("/api/interview/answer")
async def submit_answer(req: AnswerSubmission, user_ai: AIClient = Depends(get_user_ai),
                        current_user: dict = Depends(get_current_user)):
    """提交回答，获取评估和下一题"""
    session = await db.load_session(req.session_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")
    uid = current_user["id"]

    # 实时更新 TTS 偏好（来自面试页面的即时开关）
    if req.enable_tts is not None:
        session["enable_tts"] = req.enable_tts

    current_q = session.get("current_question", {})
    question_text = current_q.get("question", "")
    engine = InterviewEngine(user_ai)
    tts = TTSEngine(user_ai)

    context = {"profile": session.get("profile", {}), "hint_used": req.hint_used}
    round_name = session.get("round", "tech_1")
    evaluation = await engine.evaluate_answer(question_text, req.answer, context, round_name, question_data=current_q)
    logger.info(f"提交回答: session={req.session_id}, q_index={req.question_index}, "
                f"score={evaluation.get('overall_score','?')}, "
                f"record_id={evaluation.get('_record_id','none')}")

    session["history"].append({
        "q": question_text,
        "a": req.answer,
        "score": evaluation,
        "type": current_q.get("type", ""),
        "topic": current_q.get("topic", ""),
    })

    # 自定义题目模式：从预加载列表取下一题，不 AI 生成
    custom_qs = session.get("custom_questions", [])
    if custom_qs:
        next_index = session["current_index"] + 1
        if next_index < len(custom_qs):
            next_q = custom_qs[next_index]
        else:
            next_q = None
        session["current_question"] = next_q
        session["current_index"] = next_index
        await db.save_session(req.session_id, session, user_id=uid)
        return {
            "evaluation": evaluation,
            "next_question": next_q,
            "next_index": next_index,
            "audio_url": None,
        }

    # 笔试预生成模式：从池取题 + 后台补充
    written_qs = session.get("written_questions", [])
    written_total = session.get("written_total", 0)
    if round_name == "written" and written_qs:
        next_index = session["current_index"] + 1

        # 合并后台已完成的生成结果
        bg_qs = _written_bg_results.pop(req.session_id, None)
        if bg_qs:
            written_qs.extend(bg_qs)
            session["written_questions"] = written_qs

        # 从池取下一题
        if next_index < len(written_qs):
            next_q = written_qs[next_index]
        elif next_index < written_total:
            # 等后台任务（最多 5s），超时则 on-the-fly 生成 1 题
            task = _written_bg_tasks.get(req.session_id)
            if task and not task.done():
                try:
                    await asyncio.wait_for(task, timeout=5)
                except asyncio.TimeoutError:
                    pass
            bg_qs = _written_bg_results.pop(req.session_id, []) or []
            if bg_qs:
                written_qs.extend(bg_qs)
                session["written_questions"] = written_qs
            if next_index < len(written_qs):
                next_q = written_qs[next_index]
            else:
                # 后台没赶上，即时生成 1 题
                next_q = await engine.generate_next_question(
                    session["history"], session.get("resume", ""), session.get("profile", {}),
                    round_name="written",
                )
        else:
            next_q = None

        # 池中余量不足时触发下一批后台生成
        remaining = len(written_qs) - next_index
        if remaining <= 4 and len(written_qs) < written_total \
           and req.session_id not in _written_bg_tasks:
            batch_count = min(5, written_total - len(written_qs))
            used = {h["q"] for h in session.get("history", [])} | {q["question"] for q in written_qs}
            task = asyncio.create_task(
                _background_written_batch(req.session_id, batch_count,
                                          session.get("resume", ""), session.get("profile", {}),
                                          used)
            )
            _written_bg_tasks[req.session_id] = task

        session["current_question"] = next_q
        session["current_index"] = next_index
        await db.save_session(req.session_id, session, user_id=uid)
        return {
            "evaluation": evaluation,
            "next_question": next_q,
            "next_index": next_index,
            "audio_url": None,
        }

    next_index = session["current_index"] + 1

    # 从题库池取题（按难度匹配）
    pool = _question_pools.get(req.session_id)
    if pool is None:
        pool_dict = session.get("question_pool")
        if pool_dict:
            pool = QuestionPool.from_dict(pool_dict)
            _question_pools[req.session_id] = pool

    if pool:
        last_score = evaluation.get("overall_score", 5)
        if last_score >= 7:
            next_diff = "hard"
        elif last_score >= 4:
            next_diff = "medium"
        else:
            next_diff = "easy"

        next_q = pool.pop(next_diff)
        if next_q is None:
            # 目标难度无题，降级取其他难度
            for diff in ["medium", "easy", "hard"]:
                if diff != next_diff:
                    next_q = pool.pop(diff)
                    if next_q:
                        break
        logger.info(f"从题库取题: diff={next_diff}, result={'命中' if next_q else '未命中'} "
                    f"(池中: easy={len(pool.easy)} medium={len(pool.medium)} hard={len(pool.hard)})")

        # 触发后台补题
        if pool.needs_refill() and not pool.is_saturated():
            asyncio.create_task(background_refill(
                req.session_id, pool, session.get("resume", ""),
                session.get("profile", {}), session.get("round", "tech_1"),
            ))
    else:
        next_q = None

    if next_q is None:
        next_q = await engine.generate_next_question(
            session["history"], session.get("resume", ""), session.get("profile", {}),
            round_name=session.get("round", "tech_1"),
        )

    audio_path = await tts.synthesize(next_q["question"], req.session_id, next_index) \
        if session.get("enable_tts", True) else None

    session["current_question"] = next_q
    session["current_index"] = next_index
    if pool:
        session["question_pool"] = pool.to_dict()
    await db.save_session(req.session_id, session, user_id=uid)

    return {
        "evaluation": evaluation,
        "next_question": next_q,
        "next_index": next_index,
        "audio_url": f"/api/audio/{req.session_id}_q{next_index:03d}.wav" if audio_path else None,
    }

@app.post("/api/interview/end")
async def end_interview(req: EndInterview, user_ai: AIClient = Depends(get_user_ai),
                        current_user: dict = Depends(get_current_user)):
    """结束面试，生成报告"""
    session = await db.load_session(req.session_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    engine = InterviewEngine(user_ai)
    report = await engine.end_interview(session["history"], session.get("profile", {}),
                                        round_name=session.get("round", "tech_1"))
    session["report"] = report

    # 缓存盈余题目到复用池
    pool = _question_pools.pop(req.session_id, None)
    if pool is None:
        pool_dict = session.get("question_pool")
        if pool_dict:
            pool = QuestionPool.from_dict(pool_dict)
    if pool:
        surplus = pool.surplus()
        if surplus:
            save_pool_cache(session.get("resume", ""), session.get("position", ""),
                           session.get("round", ""), surplus)
            logger.info(f"缓存盈余: {len(surplus)} 题 (session={req.session_id})")

    await db.save_session(req.session_id, session, user_id=current_user["id"])

    return {"report": report, "history": session["history"], "round": session.get("round", "")}

@app.post("/api/interview/hint")
async def get_hint(req: HintRequest, user_ai: AIClient = Depends(get_user_ai)):
    """获取面试题提示"""
    session = await db.load_session(req.session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    current_q = session.get("current_question", {})
    question_text = current_q.get("question", "")
    question_type = current_q.get("type", "")
    question_topic = current_q.get("topic", "")

    engine = InterviewEngine(user_ai)
    hint = await engine.generate_hint(question_text, question_type, question_topic)
    return {"hint": hint}

# ==================== 题目收藏 ====================

@app.post("/api/favorites")
async def create_favorite(req: FavoriteCreate, current_user: dict = Depends(get_current_user)):
    """收藏题目"""
    fav_id = await db.save_favorite(req.model_dump(), user_id=current_user["id"])
    return {"id": fav_id, "message": "已收藏"}

@app.get("/api/favorites")
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    search: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的收藏题目（支持分页和搜索）"""
    return await db.list_favorites(user_id=current_user["id"], page=page, page_size=page_size, search=search)

@app.delete("/api/favorites/{fav_id}")
async def delete_favorite(fav_id: int, current_user: dict = Depends(get_current_user)):
    """删除收藏题目"""
    if not await db.delete_favorite(fav_id, user_id=current_user["id"]):
        raise HTTPException(404, "收藏不存在")
    return {"message": "已取消收藏"}

# ==================== 自定义题目 ====================

@app.post("/api/custom/questions")
async def create_custom_question(req: CustomQuestionCreate, current_user: dict = Depends(get_current_user)):
    """创建自定义题目"""
    qid = await db.create_custom_question(req.model_dump(), user_id=current_user["id"])
    return {"id": qid, "message": "题目已创建"}

@app.get("/api/custom/questions")
async def list_custom_questions(current_user: dict = Depends(get_current_user)):
    """获取当前用户的自定义题目"""
    return {"questions": await db.list_custom_questions(user_id=current_user["id"])}

@app.get("/api/custom/questions/{qid}")
async def get_custom_question(qid: int):
    """获取单个自定义题目"""
    q = await db.get_custom_question(qid)
    if not q:
        raise HTTPException(404, "题目不存在")
    return q

@app.put("/api/custom/questions/{qid}")
async def update_custom_question(qid: int, req: CustomQuestionUpdate, current_user: dict = Depends(get_current_user)):
    """更新自定义题目"""
    if not await db.update_custom_question(qid, req.model_dump(), user_id=current_user["id"]):
        raise HTTPException(404, "题目不存在")
    return {"message": "题目已更新"}

@app.delete("/api/custom/questions/{qid}")
async def delete_custom_question(qid: int, current_user: dict = Depends(get_current_user)):
    """删除自定义题目"""
    if not await db.delete_custom_question(qid, user_id=current_user["id"]):
        raise HTTPException(404, "题目不存在")
    return {"message": "题目已删除"}

@app.get("/api/interview/session/{session_id}")
async def get_session(session_id: str):
    """获取面试会话详情"""
    session = await db.load_session(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    # 剥离内部字段避免泄漏到前端
    cq = session.get("current_question")
    if isinstance(cq, dict):
        cq = {k: v for k, v in cq.items() if not k.startswith("__")}
    return {
        "id": session["id"],
        "position": session.get("position"),
        "company": session.get("company"),
        "date": session.get("created_at", ""),
        "round": session.get("round", ""),
        "history": session.get("history", []),
        "report": session.get("report"),
        "current_question": cq,
        "current_index": session.get("current_index", 0),
        "custom_questions": session.get("custom_questions", []),
    }


# ==================== 语音 ====================

@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    audio_path = DATA_DIR / "audios" / filename
    if not audio_path.exists():
        raise HTTPException(404, "音频不存在")
    return FileResponse(str(audio_path), media_type="audio/wav", filename=filename)


# ==================== 历史记录 ====================

@app.get("/api/history")
async def list_history(current_user: dict = Depends(get_current_user)):
    """获取当前用户的历史面试记录"""
    return {"sessions": await db.list_sessions(user_id=current_user["id"])}

@app.delete("/api/history/{session_id}")
async def delete_history(session_id: str, current_user: dict = Depends(get_current_user)):
    """删除面试记录"""
    if await db.delete_session(session_id, user_id=current_user["id"]):
        return {"message": "已删除"}
    raise HTTPException(404, "记录不存在")


# ==================== 微调数据反馈 ====================

@app.post("/api/feedback/submit")
async def submit_feedback(req: FeedbackRequest):
    """提交点赞/点踩反馈"""
    collector = get_collector()
    ok = collector.submit_feedback(req.record_type, req.record_id, req.rating, req.corrections)
    if not ok:
        raise HTTPException(404, "反馈目标不存在")
    return {"message": "反馈已记录"}

@app.post("/api/training/data")
async def list_training_data(req: FeedbackDataRequest):
    """获取训练数据列表"""
    collector = get_collector()
    records = collector.list_records(req.record_type, req.quality, req.source)
    return {"records": records}

@app.get("/api/training/stats")
async def training_stats():
    """获取训练数据统计"""
    collector = get_collector()
    return collector.get_stats()


# ==================== 前端 ====================

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ==================== 启动 ====================

def _get_lan_ip() -> str:
    """获取本机局域网 IP 地址，用于显示在启动横幅中。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main():
    # Windows asyncio 补丁：压制 ProactorEventLoop 在客户端强制断开连接时的 ConnectionResetError 噪音
    if sys.platform == 'win32':
        from asyncio import proactor_events
        _orig_ccl = proactor_events._ProactorBasePipeTransport._call_connection_lost
        def _patched_ccl(self, exc):
            try:
                _orig_ccl(self, exc)
            except ConnectionResetError:
                pass
        proactor_events._ProactorBasePipeTransport._call_connection_lost = _patched_ccl

    import uvicorn
    lan_ip = _get_lan_ip()
    print(f"""
    +-----------------------------------+
    |        MockMate v1.0              |
    |     AI 面试模拟陪练                |
    +-----------------------------------+

    本机:     http://127.0.0.1:{PORT}
    局域网:   http://{lan_ip}:{PORT}
    提供商:   {ai.provider}
    MiMo:     {'[OK]' if ai.mimo.ready else '[  ]'}
    DeepSeek: {'[OK]' if ai.deepseek.ready else '[  ]'}
    Qwen:     {'[OK]' if ai.qwen.ready else '[  ]'}
    Zhipu:    {'[OK]' if ai.zhipu.ready else '[  ]'}
    日志:     {log_file}

    局域网其他设备请使用 http://{lan_ip}:{PORT} 访问
    """)
    if lan_ip != "127.0.0.1":
        print(f"    [提示] 如果无法访问，请检查 Windows 防火墙是否放行了 TCP 端口 {PORT}")
        print()
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
    )

if __name__ == "__main__":
    main()
