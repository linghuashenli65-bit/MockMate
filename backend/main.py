"""MockMate 主服务"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import io

from pypdf import PdfReader
from docx import Document

from .config import HOST, PORT, DATA_DIR
from .ai_client import AIClient
from .web_research import WebResearch
from .interview_engine import InterviewEngine
from .tts import TTSEngine
from .database import db

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
research = WebResearch(ai)
engine = InterviewEngine(ai)
tts = TTSEngine(ai)


# ---------- Request Models ----------

class ConfigUpdate(BaseModel):
    mimo_api_key: str = ""
    deepseek_api_key: str = ""
    provider: str = ""

class ResearchRequest(BaseModel):
    position: str
    refresh: bool = False

class ResumeText(BaseModel):
    text: str

class StartInterview(BaseModel):
    resume: str
    position: str
    company: str = ""
    profile: dict = {}
    round: str = "written"

class AnswerSubmission(BaseModel):
    session_id: str
    question_index: int
    answer: str

class EndInterview(BaseModel):
    session_id: str


# ---------- FastAPI ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    logger.info("MockMate 服务启动")
    logger.info(f"  日志文件: {log_file}")
    logger.info(f"  数据库:   {'MySQL' if db.available else 'JSON 文件'}")
    for name, client in [("MiMo API", ai.mimo), ("DeepSeek", ai.deepseek)]:
        logger.info(f"  {name}:    {'已配置' if client.ready else '未配置'}")
    logger.info(f"  当前提供商:   {ai.provider}")
    stats = await db.cache_stats()
    logger.info(f"  缓存:         {stats['valid']} 条有效")
    yield
    await ai.close()
    await research.close()
    await db.close()

app = FastAPI(title="MockMate", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ==================== 基础 ====================

@app.get("/api/status")
async def get_status():
    stats = await db.cache_stats()
    return {
        "status": "ok",
        "provider": ai.provider,
        "mimo_ready": ai.mimo.ready,
        "deepseek_ready": ai.deepseek.ready,
        "db": "mysql" if db.available else "json",
        "cache": stats,
    }

@app.post("/api/config")
def update_config(cfg: ConfigUpdate):
    if cfg.mimo_api_key:
        ai.update_api_key("mimo", cfg.mimo_api_key)
    if cfg.deepseek_api_key:
        ai.update_api_key("deepseek", cfg.deepseek_api_key)
    if cfg.provider in ("mimo", "deepseek"):
        ai.provider = cfg.provider
    return {"message": "配置已更新"}


# ==================== 简历 ====================

@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    contents = await file.read()
    ext = Path(file.filename).suffix.lower()

    if ext in (".jpg", ".jpeg", ".png"):
        text = await ai.extract_text_from_image(contents)
        if text:
            return {"text": text, "source": "ocr"}
        raise HTTPException(503, "图片识别需要配置 MiMo API Key")

    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return {"text": text.strip(), "source": "pdf"}
            raise HTTPException(400, "无法从 PDF 中提取文字（可能为扫描件）")
        except Exception as e:
            logger.error(f"PDF 解析失败: {e}")
            raise HTTPException(400, f"PDF 解析失败: {str(e)}")

    if ext == ".docx":
        try:
            doc = Document(io.BytesIO(contents))
            text = "\n".join(p.text for p in doc.paragraphs)
            if text.strip():
                return {"text": text.strip(), "source": "docx"}
            raise HTTPException(400, "无法从 Word 文档中提取文字")
        except Exception as e:
            logger.error(f"DOCX 解析失败: {e}")
            raise HTTPException(400, f"Word 文档解析失败: {str(e)}")

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
async def analyze_resume(req: ResumeText):
    if not req.text.strip():
        raise HTTPException(400, "简历内容不能为空")
    prompt = f"""分析以下简历，输出 JSON：
{req.text[:4000]}
{{"skills":[],"experience_years":"","projects":[],"strengths":[],"weaknesses":[]}}"""
    result = await ai.reason([{"role": "user", "content": prompt}], max_tokens=2048)
    if not result:
        raise HTTPException(503, "AI 不可用")
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"raw": result, "skills": []}


# ==================== 岗位研究（带缓存）====================

@app.post("/api/research")
async def research_position(req: ResearchRequest):
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
    try:
        profile = await research.search_position(position)
        # 只有生成了实质内容才缓存
        if profile.get("required_skills") or profile.get("common_interview_topics"):
            await db.cache_set(position, profile)
            # 记录搜索历史
            await db.save_search_history(position, profile)
        return profile
    except Exception as e:
        logger.error(f"岗位分析失败: {e}", exc_info=True)
        raise HTTPException(502, f"岗位分析失败: {str(e)}")

@app.get("/api/cache/stats")
async def cache_stats():
    return await db.cache_stats()

@app.post("/api/cache/clear")
async def cache_clear():
    await db.cache_clear()
    return {"message": "缓存已清空"}

@app.get("/api/search/history")
async def search_history():
    """获取搜索历史"""
    return {"records": await db.get_search_history(limit=30)}


# ==================== 面试 ====================

@app.post("/api/interview/start")
async def start_interview(req: StartInterview):
    """开始一场新面试"""
    session_id = uuid.uuid4().hex[:12]
    profile = req.profile or {"position": req.position}

    round_name = req.round if hasattr(req, 'round') and req.round else "written"
    question = await engine.generate_first_question(req.resume, profile, round_name)
    audio_path = await tts.synthesize(question["question"], session_id, 0)

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
        "created_at": datetime.now().isoformat(),
    }
    await db.save_session(session_id, session)

    return {
        "session_id": session_id,
        "question": question,
        "question_index": 0,
        "round": round_name,
        "audio_url": f"/api/audio/{session_id}_q000.mp3" if audio_path else None,
    }

@app.post("/api/interview/answer")
async def submit_answer(req: AnswerSubmission):
    """提交回答，获取评估和下一题"""
    session = await db.load_session(req.session_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    current_q = session.get("current_question", {})
    question_text = current_q.get("question", "")

    context = {"profile": session.get("profile", {})}
    round_name = session.get("round", "tech_1")
    evaluation = await engine.evaluate_answer(question_text, req.answer, context, round_name)

    session["history"].append({
        "q": question_text,
        "a": req.answer,
        "score": evaluation,
        "type": current_q.get("type", ""),
        "topic": current_q.get("topic", ""),
    })

    next_index = session["current_index"] + 1
    next_q = await engine.generate_next_question(
        session["history"], session.get("resume", ""), session.get("profile", {}),
        round_name=session.get("round", "written"),
    )
    audio_path = await tts.synthesize(next_q["question"], req.session_id, next_index)

    session["current_question"] = next_q
    session["current_index"] = next_index
    await db.save_session(req.session_id, session)

    return {
        "evaluation": evaluation,
        "next_question": next_q,
        "next_index": next_index,
        "audio_url": f"/api/audio/{req.session_id}_q{next_index:03d}.mp3" if audio_path else None,
    }

@app.post("/api/interview/end")
async def end_interview(req: EndInterview):
    """结束面试，生成报告"""
    session = await db.load_session(req.session_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    report = await engine.end_interview(session["history"], session.get("profile", {}))
    session["report"] = report
    await db.save_session(req.session_id, session)

    return {"report": report, "history": session["history"], "round": session.get("round", "")}

@app.get("/api/interview/session/{session_id}")
async def get_session(session_id: str):
    """获取面试会话详情"""
    session = await db.load_session(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    return {
        "id": session["id"],
        "position": session.get("position"),
        "company": session.get("company"),
        "date": session.get("created_at", ""),
        "round": session.get("round", ""),
        "history": session.get("history", []),
        "report": session.get("report"),
        "current_question": session.get("current_question"),
        "current_index": session.get("current_index", 0),
    }


# ==================== 语音 ====================

@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    audio_path = DATA_DIR / "audios" / filename
    if not audio_path.exists():
        raise HTTPException(404, "音频不存在")
    return FileResponse(str(audio_path), media_type="audio/mpeg", filename=filename)


# ==================== 历史记录 ====================

@app.get("/api/history")
async def list_history():
    return {"sessions": await db.list_sessions()}

@app.delete("/api/history/{session_id}")
async def delete_history(session_id: str):
    if await db.delete_session(session_id):
        return {"message": "已删除"}
    raise HTTPException(404, "记录不存在")


# ==================== 前端 ====================

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ==================== 启动 ====================

def main():
    import uvicorn
    print(f"""
    +-----------------------------------+
    |        MockMate v1.0              |
    |     AI 面试模拟陪练                |
    +-----------------------------------+

    服务地址: http://{HOST}:{PORT}
    提供商:   {ai.provider}
    MiMo:     {'[OK]' if ai.mimo.ready else '[  ]'}
    DeepSeek: {'[OK]' if ai.deepseek.ready else '[  ]'}
    缓存:     {len([])} 条有效
    日志:     {log_file}

    浏览器打开 http://{HOST}:{PORT}
    """)
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
    )

if __name__ == "__main__":
    main()
