from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import shutil
import os
import logging
import asyncio
import uuid
from datetime import datetime
from dotenv import load_dotenv
from gemini_validator import validate_case
from openai import OpenAI
from openai_client import analyze_case
from prompt import build_argument
from pdf_generator import create_pdf

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('ai_legal_drafter')

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load .env and read OPENAI_API_KEY
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file or environment variables.")

client = OpenAI(api_key=openai_api_key)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

file_id_store = None
case_json_store = None
generated_text = None
original_case_path = None
validation_tasks = {}  # {task_id: {"status": "pending|complete|error", "result": ..., "error": ...}}

@app.post("/oovalidate")
async def oovalidate():
    logger.info('oovalidate started')
    try:
        if not case_json_store:
            raise ValueError('case_json_store missing; run analyze first')
        if not original_case_path or not os.path.exists(original_case_path):
            raise ValueError('Original uploaded case PDF not found; upload should be run first')

        result = validate_case(
            original_case_path,
            "output_case.pdf",
            case_json_store
        )

        logger.info('oovalidate completed successfully')
        return {"validation": result}
    except Exception as e:
        logger.error('oovalidate failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}


async def _run_validation_task(task_id):
    """Background task to run validation"""
    logger.info('Validation background task started for task_id=%s', task_id)
    try:
        if not case_json_store or not generated_text:
            raise ValueError('case_json_store or generated_text missing; run analyze first')
        if not original_case_path or not os.path.exists(original_case_path):
            raise ValueError('Original uploaded case PDF not found; upload should be run first')

        create_pdf(generated_text, "output_case.pdf")    

        validation = validate_case(
            original_case_path,
            "output_case.pdf",
            case_json_store
        )

        logger.debug('Gemini validate_case result: %s', validation)

        # combine and store validation report in a PDF
        validation_text = f"\n\nVALIDATION REPORT\n\n{validation}"
        final_text = generated_text + validation_text
        create_pdf(final_text, "validated_case.pdf")

        validation_tasks[task_id] = {
            "status": "complete",
            "result": validation
        }
        logger.info('Validation task completed for task_id=%s', task_id)

    except Exception as e:
        logger.error('Validation task failed for task_id=%s: %s', task_id, e, exc_info=True)
        validation_tasks[task_id] = {
            "status": "error",
            "error": str(e)
        }


@app.post("/validate/start")
async def validate_start():
    """Start validation task in background"""
    logger.info('Validation start endpoint called')
    try:
        task_id = str(uuid.uuid4())
        logger.info('Created task_id=%s for validation', task_id)

        validation_tasks[task_id] = {"status": "pending"}

        # Start background task
        asyncio.create_task(_run_validation_task(task_id))

        logger.info('Background validation task created for task_id=%s', task_id)
        return {"task_id": task_id, "status": "pending"}

    except Exception as e:
        logger.error('validate_start failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/validate/status/{task_id}")
async def validate_status(task_id: str):
    """Check validation task status"""
    logger.debug('Validation status check for task_id=%s', task_id)
    try:
        if task_id not in validation_tasks:
            logger.warning('task_id=%s not found', task_id)
            return {"status": "error", "message": "Task not found"}

        task_info = validation_tasks[task_id]
        logger.debug('task_id=%s status=%s', task_id, task_info.get("status"))

        return task_info

    except Exception as e:
        logger.error('validate_status failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}



@app.post("/upload")
async def upload(file: UploadFile):
    logger.info('Upload started')
    try:
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)

        path = os.path.join(uploads_dir, file.filename)
        logger.debug('Saving uploaded file to %s', path)

        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info('File saved locally')

        uploaded = client.files.create(
            file=open(path, "rb"),
            purpose="assistants"
        )
        logger.info('Uploaded file to OpenAI with id %s', uploaded.id)

        global file_id_store
        global original_case_path
        file_id_store = uploaded.id
        original_case_path = path

        logger.info('Upload completed successfully; original_case_path=%s', original_case_path)
        return {"status": "uploaded"}

    except Exception as e:
        logger.error('Upload failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.post("/analyze")
async def analyze():
    logger.info('Analysis started')
    try:
        global case_json_store
        global generated_text

        if not file_id_store:
            raise ValueError('file_id_store is empty, upload must be done first')

        logger.debug('Calling analyze_case with file_id %s', file_id_store)
        case_json_store = analyze_case(file_id_store)

        logger.debug('Building argument text')
        generated_text = build_argument(case_json_store)

        logger.info('Analysis completed successfully')
        return {
            "text": generated_text,
            "citations": case_json_store["citations"]
        }

    except Exception as e:
        logger.error('Analysis failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.post("/oogenerate_pdf")
async def oogenerate_pdf():
    logger.info('oogenerate_pdf started')
    try:
        if not generated_text:
            raise ValueError('generated_text is empty; run analyze first')

        path = "output_case.pdf"
        create_pdf(generated_text, path)

        logger.info('oogenerate_pdf completed successfully: %s', path)
        return {"pdf": path}

    except Exception as e:
        logger.error('oogenerate_pdf failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.post("/generate_pdf")
async def generate_pdf():
    logger.info('generate_pdf started')
    try:
        if not generated_text:
            raise ValueError('generated_text is empty; run analyze first')

        downloads_dir = os.path.expanduser("~/Downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"legal_argument_{timestamp}.pdf"
        path = os.path.join(downloads_dir, filename)

        create_pdf(generated_text, path)

        logger.info('generate_pdf completed successfully: %s', path)
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=filename
        )

    except Exception as e:
        logger.error('generate_pdf failed: %s', e, exc_info=True)
        return {"status": "error", "message": str(e)}
