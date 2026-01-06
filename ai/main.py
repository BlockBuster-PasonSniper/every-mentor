from __future__ import annotations

import os
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
import httpx
import pytesseract
from PIL import Image
from PIL import ImageOps

app = FastAPI(title="every-mentor ai api")


LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen2.5-vl-7b-instruct")

TESSERACT_CMD = os.getenv("TESSERACT_CMD")


_CERT_SUBJECT_MAP: dict[str, list[str]] = {
    # 대표 학습 영역(시험 대비 관점) 힌트용
    "전기기능사": ["전기이론", "전기기기", "전기설비"],
    "생산자동화기능사": ["기계요소", "공압/유압", "전기/전자 기초", "PLC 기초", "자동화 실무"],
    "전자기기기능사": ["전자회로 기초", "디지털/마이크로컨트롤러 기초", "측정/계측", "전자기기 수리"],
    "컴퓨터응용밀링기능사": ["도면 해독", "가공 공정", "공구/절삭", "측정", "안전"],
    "정보처리기능사": ["컴퓨터 기초", "소프트웨어 기초", "데이터/DB 기초", "네트워크 기초", "문제풀이"],
    "공유압기능사": ["공압 기초", "유압 기초", "회로 해독", "기기/밸브", "안전"],
}


def _normalize_cert_name(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return s
    # 흔한 OCR 오타 보정(명백한 경우만)
    replacements = {
        "일링": "밀링",
        "공유암": "공유압",
        "산엄": "산업",
        "산엽": "산업",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s


def _normalize_certificate_ocr_text(text: str) -> str:
    """Normalize obvious OCR typos for certificate titles inside longer OCR blobs.

    Keep this conservative (only when highly likely) to avoid over-correcting.
    """
    s = (text or "")
    if not s:
        return s
    # Common, high-confidence OCR mistakes observed in certificate titles
    s = re.sub(r"컴퓨터응용\s*일링\s*기능사", "컴퓨터응용밀링기능사", s)
    s = re.sub(r"공유\s*암\s*기능사", "공유압기능사", s)
    return s


def _is_dependent_mode(dependent_mode: str | None, insurance_text: str) -> bool:
    mode = (dependent_mode or "auto").strip().lower()
    if mode in {"true", "1", "yes", "y", "on"}:
        return True
    if mode in {"false", "0", "no", "n", "off"}:
        return False
    return _looks_like_dependent_insurance(insurance_text)


def _cert_subject_hints_from_texts(certificate_texts: list[str]) -> str:
    blob = "\n".join([t for t in certificate_texts if t]).strip()
    if not blob:
        return ""
    lines: list[str] = []
    for cert, subjects in _CERT_SUBJECT_MAP.items():
        if cert in blob:
            lines.append(f"- {cert}: " + ", ".join(subjects))
    if not lines:
        return ""
    return "\n[SUBJECT HINTS]\n" + "\n".join(lines) + "\n"


def _detect_tesseract_cmd() -> str | None:
    if TESSERACT_CMD:
        return TESSERACT_CMD

    which = shutil.which("tesseract")
    if which:
        return which

    candidates: list[Path] = []
    program_files = os.getenv("ProgramFiles")
    program_files_x86 = os.getenv("ProgramFiles(x86)")
    for root in [program_files, program_files_x86, "C:\\Program Files", "C:\\Program Files (x86)"]:
        if not root:
            continue
        candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")

    for p in candidates:
        if p.exists():
            return str(p)

    return None


_tesseract_cmd = _detect_tesseract_cmd()
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"message": "ai api is running"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


class LMStudioChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(256, ge=1, le=4096)


class LMStudioChatResponse(BaseModel):
    model: str
    text: str
    raw: dict[str, Any]


async def _lmstudio_chat_completions(
    *,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    timeout: httpx.Timeout,
) -> dict[str, Any]:
    url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def _extract_chat_text(data: dict[str, Any]) -> str:
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


def _build_curriculum_prompt(*, text: str, weeks: int, target_level: str) -> str:
    return (
        "You are a helpful education designer.\n"
        "Given the following OCR text, create a practical learning curriculum.\n"
        "Rules:\n"
        f"- Duration: {weeks} weeks\n"
        f"- Target level: {target_level}\n"
        "- Output in Korean\n"
        "- Use clear headings and bullet points\n"
        "- Include weekly goals, key topics, and exercises\n\n"
        "OCR TEXT:\n"
        f"{text}\n"
    )


def _build_career_curriculum_prompt(
    *,
    insurance_text: str,
    certificate_texts: list[str],
    weeks: int,
    goal: str | None,
    is_dependent: bool,
) -> str:
    cert_block = "\n\n".join([t.strip() for t in certificate_texts if t.strip()])
    goal_line = f"Goal: {goal}\n" if (goal and goal.strip()) else ""

    dependent_hint = ""
    if is_dependent:
        dependent_hint = (
            "\n[IMPORTANT CONTEXT]\n"
            "The insurance text contains terms like '직장피부양자/피부양자'.\n"
            "This often means the employer listed belongs to a family member (e.g., parent), not the user.\n"
            "DO NOT use employer names/dates as the user's work history evidence unless the document explicitly indicates the user is '직장가입자/본인/사업장 가입자'.\n"
        )

    subject_hints = _cert_subject_hints_from_texts(certificate_texts)

    return (
        "You are a career coach and curriculum designer.\n"
        "You will be given OCR/text from a Korean employment/insurance history document and optional certificate documents.\n"
        "Task: infer the user's likely job domain and typical responsibilities as hypotheses (do NOT present as certain facts), then design a learning curriculum.\n\n"
        "Rules:\n"
        "- Output in Korean\n"
        "- Be explicit about uncertainty: use phrases like '추정', '가능성', '문서상으로 보이는 정황'\n"
        "- First, summarize evidence you used (company names, dates, certificate titles)\n"
        "- If certificate OCR text is missing/too short/unclear, explicitly say so (e.g., '자격증 OCR이 충분히 읽히지 않았습니다') and do NOT hallucinate certificate names\n"
        "- You MAY correct obvious OCR typos in certificate names if highly confident (e.g., '일링→밀링', '공유암→공유압') and note it was corrected from OCR\n"
        "- Extract and list certificate titles/keywords you can read, and use them to refine the job-role hypotheses\n"
        "- IMPORTANT: If any certificate title/subject keywords exist, the curriculum MUST include a dedicated '자격증(과목) 대비 트랙' and weave those subjects into weekly tasks\n"
        "- Each week should contain: (1) 직무역량 학습/실습 and (2) 자격증 대비(과목별) 학습/문제풀이\n"
        "- If certificate text is insufficient, include a short section '자격증 정보 보강 요청' with exactly what to provide (자격증 이름/과목/시험범위) and still propose a generic exam-prep structure without naming specific certificates\n"
        "- Then provide 2-3 plausible job-role hypotheses and what tasks they likely did\n"
        f"- Then propose a {weeks}-week curriculum tailored to the hypotheses\n"
        "- Curriculum should include weekly goals, 핵심 스킬, 실습 과제\n"
        "- Keep personal data minimal; do not repeat resident registration numbers\n"
        f"{goal_line}"
        f"{dependent_hint}"
        f"{subject_hints}"
        "\n[INSURANCE / EMPLOYMENT TEXT]\n"
        f"{insurance_text}\n"
        "\n[CERTIFICATES TEXT (optional)]\n"
        f"{cert_block if cert_block else '(none)'}\n"
    )


def _looks_like_dependent_insurance(text: str) -> bool:
    t = (text or "").replace(" ", "")
    keywords = ["직장피부양자", "피부양자", "직장피부양"]
    return any(k in t for k in keywords)


def _build_teaching_profile_prompt(
    *,
    insurance_text: str,
    certificate_texts: list[str],
    goal: str | None,
    is_dependent: bool,
) -> str:
    cert_block = "\n\n".join([t.strip() for t in certificate_texts if t.strip()])
    goal_line = f"Goal: {goal}\n" if (goal and goal.strip()) else ""

    dependent_hint = ""
    if is_dependent:
        dependent_hint = (
            "The insurance text contains '직장피부양자/피부양자'. "
            "Assume the listed employers may belong to a family member. "
            "Do NOT treat employer history as the user's work history unless clearly stated as the user's own enrollment (직장가입자/본인).\n"
        )

    subject_hints = _cert_subject_hints_from_texts(certificate_texts)

    return (
        "You are a career coach tasked with generating a teaching profile.\n"
        "Given insurance/employment OCR text and certificate OCR text, infer what subjects and certifications the user can realistically teach.\n"
        "Rules:\n"
        "- Output MUST be valid JSON ONLY. No markdown, no extra text.\n"
        "- Output in Korean strings.\n"
        "- Do NOT hallucinate. If evidence is insufficient, lower confidence and ask for missing info.\n"
        "- Treat dependent insurance carefully. "
        f"{dependent_hint}"
        "- You MAY correct obvious OCR typos in certificate names if highly confident (e.g., '일링→밀링', '공유암→공유압') and note correction in evidence_summary/rationale\n"
        "- Focus on teachable subjects/skills and teachable certifications (exam-prep).\n"
        "- For each teachable certification, include a reasonable subject breakdown in 'subjects' (대표 과목/학습영역).\n"
        f"{subject_hints}"
        "JSON schema (exact keys):\n"
        "{\n"
        "  \"is_dependent_suspected\": true|false,\n"
        "  \"evidence_summary\": [\"...\"],\n"
        "  \"excluded_evidence\": [\"...\"],\n"
        "  \"teachable_subjects\": [\n"
        "    {\"name\":\"...\", \"confidence\":0.0, \"rationale\":\"...\"}\n"
        "  ],\n"
        "  \"teachable_certifications\": [\n"
        "    {\"name\":\"...\", \"confidence\":0.0, \"subjects\":[\"...\"], \"rationale\":\"...\"}\n"
        "  ],\n"
        "  \"missing_info_questions\": [\"...\"]\n"
        "}\n\n"
        f"{goal_line}"
        "[INSURANCE TEXT]\n"
        f"{insurance_text}\n\n"
        "[CERTIFICATE TEXTS]\n"
        f"{cert_block if cert_block else '(none)'}\n"
    )


def _build_teachable_certifications_prompt(
    *,
    insurance_text: str,
    certificate_texts: list[str],
    goal: str | None,
    is_dependent: bool,
) -> str:
    cert_block = "\n\n".join([t.strip() for t in certificate_texts if t.strip()])
    goal_line = f"Goal: {goal}\n" if (goal and goal.strip()) else ""

    dependent_hint = ""
    if is_dependent:
        dependent_hint = (
            "The insurance text contains '직장피부양자/피부양자'. "
            "Assume the listed employers may belong to a family member. "
            "Do NOT treat employer history as the user's work history unless clearly stated as the user's own enrollment (직장가입자/본인).\n"
        )

    subject_hints = _cert_subject_hints_from_texts(certificate_texts)

    return (
        "You are an exam-prep mentor.\n"
        "Given insurance/employment OCR text and certificate OCR text, identify which certifications the user can teach and list the subjects for each certification.\n"
        "Rules:\n"
        "- Output MUST be valid JSON ONLY. No markdown, no extra text.\n"
        "- Output in Korean strings.\n"
        "- Do NOT output weekly curriculum. Focus ONLY on certification -> subjects.\n"
        "- Do NOT hallucinate. If evidence is insufficient, lower confidence and ask for missing info.\n"
        "- You MAY correct obvious OCR typos in certificate names if highly confident (e.g., '일링→밀링', '공유암→공유압') and note correction in evidence_summary/rationale.\n"
        f"{dependent_hint}"
        "JSON schema (exact keys):\n"
        "{\n"
        "  \"is_dependent_suspected\": true|false,\n"
        "  \"evidence_summary\": [\"...\"],\n"
        "  \"teachable_certifications\": [\n"
        "    {\"name\":\"...\", \"confidence\":0.0, \"subjects\":[\"...\"], \"rationale\":\"...\"}\n"
        "  ],\n"
        "  \"missing_info_questions\": [\"...\"]\n"
        "}\n\n"
        f"{goal_line}"
        f"{subject_hints}"
        "[INSURANCE TEXT]\n"
        f"{insurance_text}\n\n"
        "[CERTIFICATE TEXTS]\n"
        f"{cert_block if cert_block else '(none)'}\n"
    )


def _extract_first_json_object(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    # Prefer direct parse
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Fallback: find first {...} block
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        raise ValueError("No JSON object found")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise ValueError("JSON is not an object")
    return obj


async def _extract_text_from_upload(
    *,
    file: UploadFile,
    ocr_lang: str,
    ocr_psm: int,
    ocr_oem: int,
    ocr_dpi: int,
) -> tuple[str, dict[str, Any]]:
    """Returns (text, meta). Uses Tesseract for images only."""
    ct = (file.content_type or "").lower()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail=f"Empty file: {file.filename}")

    if ct.startswith("image/"):
        # Recreate UploadFile-like wrapper for OCR helper by using in-memory bytes
        # (reuse existing OCR function by temporarily swapping file object)
        class _InMemoryUpload:
            def __init__(self, filename: str, content_type: str, b: bytes):
                self.filename = filename
                self.content_type = content_type
                self._b = b

            async def read(self) -> bytes:
                return self._b

        tmp = _InMemoryUpload(file.filename or "image", ct or "image/png", file_bytes)
        ocr = await _ocr_extract_text_from_image(file=tmp, lang=ocr_lang, psm=ocr_psm, oem=ocr_oem, dpi=ocr_dpi)
        return ocr.text, ocr.raw

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type. Please upload an image (PNG/JPG). Got: {file.content_type} ({file.filename})",
    )


@app.post("/lmstudio/chat", tags=["lmstudio"], response_model=LMStudioChatResponse)
async def lmstudio_chat(body: LMStudioChatRequest) -> LMStudioChatResponse:
    timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": body.prompt}],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout=timeout,
    )

    text = _extract_chat_text(data)
    return LMStudioChatResponse(model=data.get("model", LM_STUDIO_MODEL), text=text, raw=data)


class OCRResponse(BaseModel):
    model: str
    text: str
    raw: dict[str, Any]


async def _ocr_extract_text_from_image(
    *,
    file: UploadFile,
    lang: str,
    psm: int,
    oem: int,
    dpi: int,
) -> OCRResponse:
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    def _score_text(t: str) -> int:
        if not t:
            return 0
        # Prefer texts that contain Hangul/alphanumerics over punctuation/whitespace
        score = 0
        for ch in t:
            if "\uac00" <= ch <= "\ud7a3":
                score += 3
            elif ch.isalnum():
                score += 2
            elif ch.isspace():
                score += 0
            else:
                score += 1
        return score

    # Build a few image variants. Some certificate images get worse with hard thresholding.
    variants: list[tuple[str, Image.Image]] = []
    try:
        base = ImageOps.exif_transpose(image)
    except Exception:
        base = image

    variants.append(("raw", base))

    try:
        v = base.convert("L")
        v = v.resize((v.width * 2, v.height * 2))
        v = ImageOps.autocontrast(v)
        variants.append(("light", v))
    except Exception:
        pass

    try:
        v = base.convert("L")
        v = v.resize((v.width * 2, v.height * 2))
        v = ImageOps.autocontrast(v)
        v = v.point(lambda x: 0 if x < 160 else 255, mode="1").convert("L")
        variants.append(("binarized", v))
    except Exception:
        pass

    try:
        tess_config = f"--oem {oem} --psm {psm} --dpi {dpi} -c preserve_interword_spaces=1"

        best_name = "raw"
        best_text = ""
        best_score = -1
        candidate_meta: dict[str, Any] = {}
        for name, img in variants:
            t = pytesseract.image_to_string(img, lang=lang, config=tess_config)
            s = _score_text(t)
            candidate_meta[name] = {
                "score": s,
                "length": len(t.strip()),
            }
            if s > best_score:
                best_name = name
                best_text = t
                best_score = s

        text = best_text
    except pytesseract.TesseractNotFoundError:
        detected = _detect_tesseract_cmd()
        raise HTTPException(
            status_code=500,
            detail=(
                "Tesseract executable not found. Install Tesseract OCR and/or set TESSERACT_CMD env var. "
                "Example: TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe. "
                f"Detected: {detected!r}"
            ),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    return OCRResponse(
        model="tesseract",
        text=text.strip(),
        raw={
            "lang": lang,
            "psm": psm,
            "oem": oem,
            "dpi": dpi,
            "filename": file.filename,
            "selected_variant": best_name,
            "candidates": candidate_meta,
        },
    )


@app.post("/ocr/text", tags=["ocr"], response_model=OCRResponse)
async def ocr_image(
    file: UploadFile = File(...),
    lang: str = Form("kor+eng"),
    psm: int = Form(6),
    oem: int = Form(3),
    dpi: int = Form(300),
) -> OCRResponse:
    return await _ocr_extract_text_from_image(file=file, lang=lang, psm=psm, oem=oem, dpi=dpi)


class CurriculumRequest(BaseModel):
    text: str = Field(..., min_length=1, description="OCR 결과 텍스트")
    weeks: int = Field(4, ge=1, le=52)
    target_level: str = Field("beginner", description="beginner|intermediate|advanced")
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(768, ge=64, le=4096)


class CurriculumResponse(BaseModel):
    model: str
    curriculum: str
    raw: dict[str, Any]


@app.post("/curriculum", tags=["curriculum"], response_model=CurriculumResponse)
async def make_curriculum(body: CurriculumRequest) -> CurriculumResponse:
    prompt = _build_curriculum_prompt(text=body.text, weeks=body.weeks, target_level=body.target_level)

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout=timeout,
    )

    return CurriculumResponse(
        model=data.get("model", LM_STUDIO_MODEL),
        curriculum=_extract_chat_text(data),
        raw=data,
    )


class CurriculumFromImageResponse(BaseModel):
    ocr_text: str
    model: str
    curriculum: str
    raw_ocr: dict[str, Any]
    raw_curriculum: dict[str, Any]


class CareerCurriculumResponse(BaseModel):
    insurance_text: str
    certificate_texts: list[str]
    model: str
    curriculum: str
    raw_curriculum: dict[str, Any]


class TeachItem(BaseModel):
    name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str


class TeachableCertification(BaseModel):
    name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    subjects: list[str] = Field(default_factory=list)
    rationale: str


class TeachingProfileResponse(BaseModel):
    is_dependent_suspected: bool
    evidence_summary: list[str] = Field(default_factory=list)
    excluded_evidence: list[str] = Field(default_factory=list)
    teachable_subjects: list[TeachItem] = Field(default_factory=list)
    teachable_certifications: list[TeachableCertification] = Field(default_factory=list)
    missing_info_questions: list[str] = Field(default_factory=list)
    raw_text: str
    raw: dict[str, Any]


class TeachableCertificationsOnlyResponse(BaseModel):
    is_dependent_suspected: bool
    evidence_summary: list[str] = Field(default_factory=list)
    teachable_certifications: list[TeachableCertification] = Field(default_factory=list)
    missing_info_questions: list[str] = Field(default_factory=list)
    raw_text: str
    raw: dict[str, Any]


class CareerCurriculumFromTextRequest(BaseModel):
    insurance_text: str = Field(..., min_length=1, description="건강보험/자격득실 등 문서 OCR 텍스트")
    certificate_texts: list[str] = Field(default_factory=list, description="자격증 OCR 텍스트 목록")
    weeks: int = Field(6, ge=1, le=52)
    goal: str | None = Field(None, description="목표(선택)")
    dependent_mode: str = Field("auto", description="auto|true|false")
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(1200, ge=64, le=4096)


class TeachingProfileFromTextRequest(BaseModel):
    insurance_text: str = Field(..., min_length=1)
    certificate_texts: list[str] = Field(default_factory=list)
    goal: str | None = Field(None)
    dependent_mode: str = Field("auto", description="auto|true|false")
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(900, ge=64, le=4096)


@app.post("/ocr", tags=["ocr"], response_model=CurriculumFromImageResponse)
async def ocr_pipeline(
    file: UploadFile = File(...),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    weeks: int = Form(4),
    target_level: str = Form("beginner"),
) -> CurriculumFromImageResponse:
    ocr = await _ocr_extract_text_from_image(
        file=file,
        lang=ocr_lang,
        psm=ocr_psm,
        oem=ocr_oem,
        dpi=ocr_dpi,
    )

    prompt = _build_curriculum_prompt(text=ocr.text, weeks=weeks, target_level=target_level)
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    cur_data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=768,
        timeout=timeout,
    )

    return CurriculumFromImageResponse(
        ocr_text=ocr.text,
        model=cur_data.get("model", LM_STUDIO_MODEL),
        curriculum=_extract_chat_text(cur_data),
        raw_ocr=ocr.raw,
        raw_curriculum=cur_data,
    )


@app.post("/ocr/curriculum", tags=["ocr"], response_class=PlainTextResponse)
async def ocr_curriculum_text(
    file: UploadFile = File(...),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    weeks: int = Form(4),
    target_level: str = Form("beginner"),
) -> str:
    result = await ocr_pipeline(
        file=file,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        ocr_oem=ocr_oem,
        ocr_dpi=ocr_dpi,
        weeks=weeks,
        target_level=target_level,
    )
    return result.curriculum


@app.post("/curriculum/from-image", tags=["curriculum", "ocr"], response_model=CurriculumFromImageResponse)
async def curriculum_from_image(
    file: UploadFile = File(...),
    weeks: int = Form(4),
    target_level: str = Form("beginner"),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
) -> CurriculumFromImageResponse:
    ocr = await _ocr_extract_text_from_image(
        file=file,
        lang=ocr_lang,
        psm=ocr_psm,
        oem=ocr_oem,
        dpi=ocr_dpi,
    )

    cur_req = CurriculumRequest(text=ocr.text, weeks=weeks, target_level=target_level)
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    prompt = _build_curriculum_prompt(text=cur_req.text, weeks=cur_req.weeks, target_level=cur_req.target_level)
    cur_data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=cur_req.temperature,
        max_tokens=cur_req.max_tokens,
        timeout=timeout,
    )

    return CurriculumFromImageResponse(
        ocr_text=ocr.text,
        model=cur_data.get("model", LM_STUDIO_MODEL),
        curriculum=_extract_chat_text(cur_data),
        raw_ocr=ocr.raw,
        raw_curriculum=cur_data,
    )


@app.post("/career/curriculum", tags=["career"], response_model=CareerCurriculumResponse)
async def career_curriculum(
    insurance_file: UploadFile = File(...),
    certificate_files: list[UploadFile] | None = File(None),
    certificate_hints: list[str] | None = Form(None),
    dependent_mode: str = Form("auto"),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    weeks: int = Form(6),
    goal: str | None = Form(None),
) -> CareerCurriculumResponse:
    insurance_text, _insurance_meta = await _extract_text_from_upload(
        file=insurance_file,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        ocr_oem=ocr_oem,
        ocr_dpi=ocr_dpi,
    )

    cert_texts: list[str] = []
    if certificate_files:
        for f in certificate_files:
            t, _m = await _extract_text_from_upload(
                file=f,
                ocr_lang=ocr_lang,
                ocr_psm=ocr_psm,
                ocr_oem=ocr_oem,
                ocr_dpi=ocr_dpi,
            )
            if t.strip():
                cert_texts.append(_normalize_certificate_ocr_text(t))

    if certificate_hints:
        for h in certificate_hints:
            if h and h.strip():
                cert_texts.append(_normalize_cert_name(h.strip()))

    is_dep = _is_dependent_mode(dependent_mode, insurance_text)

    prompt = _build_career_curriculum_prompt(
        insurance_text=insurance_text,
        certificate_texts=cert_texts,
        weeks=weeks,
        goal=goal,
        is_dependent=is_dep,
    )
    timeout = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
    cur_data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1200,
        timeout=timeout,
    )

    return CareerCurriculumResponse(
        insurance_text=insurance_text,
        certificate_texts=cert_texts,
        model=cur_data.get("model", LM_STUDIO_MODEL),
        curriculum=_extract_chat_text(cur_data),
        raw_curriculum=cur_data,
    )


@app.post("/career/teaching-profile", tags=["career"], response_model=TeachingProfileResponse)
async def career_teaching_profile(
    insurance_file: UploadFile = File(...),
    certificate_files: list[UploadFile] | None = File(None),
    certificate_hints: list[str] | None = Form(None),
    dependent_mode: str = Form("auto"),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    goal: str | None = Form(None),
) -> TeachingProfileResponse:
    insurance_text, _insurance_meta = await _extract_text_from_upload(
        file=insurance_file,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        ocr_oem=ocr_oem,
        ocr_dpi=ocr_dpi,
    )

    cert_texts: list[str] = []
    if certificate_files:
        for f in certificate_files:
            t, _m = await _extract_text_from_upload(
                file=f,
                ocr_lang=ocr_lang,
                ocr_psm=ocr_psm,
                ocr_oem=ocr_oem,
                ocr_dpi=ocr_dpi,
            )
            if t.strip():
                cert_texts.append(_normalize_certificate_ocr_text(t))

    if certificate_hints:
        for h in certificate_hints:
            if h and h.strip():
                cert_texts.append(_normalize_cert_name(h.strip()))

    is_dep = _is_dependent_mode(dependent_mode, insurance_text)

    prompt = _build_teaching_profile_prompt(
        insurance_text=insurance_text,
        certificate_texts=cert_texts,
        goal=goal,
        is_dependent=is_dep,
    )

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=900,
        timeout=timeout,
    )
    raw_text = _extract_chat_text(data)

    try:
        obj = _extract_first_json_object(raw_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail={"message": f"LLM did not return valid JSON: {e}", "raw_text": raw_text})

    # Build response, keeping raw_text for debug
    teachable_certs: list[TeachableCertification] = [
        TeachableCertification(**x) for x in (obj.get("teachable_certifications") or []) if isinstance(x, dict)
    ]
    for c in teachable_certs:
        norm = _normalize_cert_name(c.name).replace(" ", "")
        for known, subjects in _CERT_SUBJECT_MAP.items():
            if norm == known.replace(" ", "") and not c.subjects:
                c.subjects = subjects

    return TeachingProfileResponse(
        is_dependent_suspected=bool(obj.get("is_dependent_suspected", False)),
        evidence_summary=[str(x) for x in (obj.get("evidence_summary") or [])],
        excluded_evidence=[str(x) for x in (obj.get("excluded_evidence") or [])],
        teachable_subjects=[TeachItem(**x) for x in (obj.get("teachable_subjects") or []) if isinstance(x, dict)],
        teachable_certifications=teachable_certs,
        missing_info_questions=[str(x) for x in (obj.get("missing_info_questions") or [])],
        raw_text=raw_text,
        raw=data,
    )


@app.post("/career/teaching-profile/from-text", tags=["career"], response_model=TeachingProfileResponse)
async def career_teaching_profile_from_text(body: TeachingProfileFromTextRequest) -> TeachingProfileResponse:
    is_dep = _is_dependent_mode(body.dependent_mode, body.insurance_text)
    cert_texts = [_normalize_certificate_ocr_text(t) for t in (body.certificate_texts or []) if t]
    prompt = _build_teaching_profile_prompt(
        insurance_text=body.insurance_text,
        certificate_texts=cert_texts,
        goal=body.goal,
        is_dependent=is_dep,
    )
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout=timeout,
    )
    raw_text = _extract_chat_text(data)

    try:
        obj = _extract_first_json_object(raw_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail={"message": f"LLM did not return valid JSON: {e}", "raw_text": raw_text})

    teachable_certs: list[TeachableCertification] = [
        TeachableCertification(**x) for x in (obj.get("teachable_certifications") or []) if isinstance(x, dict)
    ]
    for c in teachable_certs:
        norm = _normalize_cert_name(c.name).replace(" ", "")
        for known, subjects in _CERT_SUBJECT_MAP.items():
            if norm == known.replace(" ", "") and not c.subjects:
                c.subjects = subjects

    return TeachingProfileResponse(
        is_dependent_suspected=bool(obj.get("is_dependent_suspected", False)),
        evidence_summary=[str(x) for x in (obj.get("evidence_summary") or [])],
        excluded_evidence=[str(x) for x in (obj.get("excluded_evidence") or [])],
        teachable_subjects=[TeachItem(**x) for x in (obj.get("teachable_subjects") or []) if isinstance(x, dict)],
        teachable_certifications=teachable_certs,
        missing_info_questions=[str(x) for x in (obj.get("missing_info_questions") or [])],
        raw_text=raw_text,
        raw=data,
    )


@app.post("/career/teachable-certifications", tags=["career"], response_model=TeachableCertificationsOnlyResponse)
async def career_teachable_certifications(
    insurance_file: UploadFile = File(...),
    certificate_files: list[UploadFile] | None = File(None),
    certificate_hints: list[str] | None = Form(None),
    dependent_mode: str = Form("auto"),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    goal: str | None = Form(None),
) -> TeachableCertificationsOnlyResponse:
    insurance_text, _insurance_meta = await _extract_text_from_upload(
        file=insurance_file,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        ocr_oem=ocr_oem,
        ocr_dpi=ocr_dpi,
    )

    cert_texts: list[str] = []
    if certificate_files:
        for f in certificate_files:
            t, _m = await _extract_text_from_upload(
                file=f,
                ocr_lang=ocr_lang,
                ocr_psm=ocr_psm,
                ocr_oem=ocr_oem,
                ocr_dpi=ocr_dpi,
            )
            if t.strip():
                cert_texts.append(_normalize_certificate_ocr_text(t))

    if certificate_hints:
        for h in certificate_hints:
            if h and h.strip():
                cert_texts.append(_normalize_cert_name(h.strip()))

    is_dep = _is_dependent_mode(dependent_mode, insurance_text)
    prompt = _build_teachable_certifications_prompt(
        insurance_text=insurance_text,
        certificate_texts=cert_texts,
        goal=goal,
        is_dependent=is_dep,
    )

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=800,
        timeout=timeout,
    )
    raw_text = _extract_chat_text(data)

    try:
        obj = _extract_first_json_object(raw_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail={"message": f"LLM did not return valid JSON: {e}", "raw_text": raw_text})

    teachable_certs: list[TeachableCertification] = [
        TeachableCertification(**x) for x in (obj.get("teachable_certifications") or []) if isinstance(x, dict)
    ]
    for c in teachable_certs:
        norm = _normalize_cert_name(c.name).replace(" ", "")
        for known, subjects in _CERT_SUBJECT_MAP.items():
            if norm == known.replace(" ", "") and not c.subjects:
                c.subjects = subjects

    return TeachableCertificationsOnlyResponse(
        is_dependent_suspected=bool(obj.get("is_dependent_suspected", False)),
        evidence_summary=[str(x) for x in (obj.get("evidence_summary") or [])],
        teachable_certifications=teachable_certs,
        missing_info_questions=[str(x) for x in (obj.get("missing_info_questions") or [])],
        raw_text=raw_text,
        raw=data,
    )


@app.post(
    "/career/teachable-certifications/from-text",
    tags=["career"],
    response_model=TeachableCertificationsOnlyResponse,
)
async def career_teachable_certifications_from_text(body: TeachingProfileFromTextRequest) -> TeachableCertificationsOnlyResponse:
    is_dep = _is_dependent_mode(body.dependent_mode, body.insurance_text)
    cert_texts = [_normalize_certificate_ocr_text(t) for t in (body.certificate_texts or []) if t]
    prompt = _build_teachable_certifications_prompt(
        insurance_text=body.insurance_text,
        certificate_texts=cert_texts,
        goal=body.goal,
        is_dependent=is_dep,
    )

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=20.0, pool=5.0)
    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=body.temperature,
        max_tokens=min(body.max_tokens, 800),
        timeout=timeout,
    )
    raw_text = _extract_chat_text(data)

    try:
        obj = _extract_first_json_object(raw_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail={"message": f"LLM did not return valid JSON: {e}", "raw_text": raw_text})

    teachable_certs: list[TeachableCertification] = [
        TeachableCertification(**x) for x in (obj.get("teachable_certifications") or []) if isinstance(x, dict)
    ]
    for c in teachable_certs:
        norm = _normalize_cert_name(c.name).replace(" ", "")
        for known, subjects in _CERT_SUBJECT_MAP.items():
            if norm == known.replace(" ", "") and not c.subjects:
                c.subjects = subjects

    return TeachableCertificationsOnlyResponse(
        is_dependent_suspected=bool(obj.get("is_dependent_suspected", False)),
        evidence_summary=[str(x) for x in (obj.get("evidence_summary") or [])],
        teachable_certifications=teachable_certs,
        missing_info_questions=[str(x) for x in (obj.get("missing_info_questions") or [])],
        raw_text=raw_text,
        raw=data,
    )


@app.post("/career/curriculum/from-text", tags=["career"], response_model=CareerCurriculumResponse)
async def career_curriculum_from_text(body: CareerCurriculumFromTextRequest) -> CareerCurriculumResponse:
    is_dep = _is_dependent_mode(body.dependent_mode, body.insurance_text)
    prompt = _build_career_curriculum_prompt(
        insurance_text=body.insurance_text,
        certificate_texts=body.certificate_texts or [],
        weeks=body.weeks,
        goal=body.goal,
        is_dependent=is_dep,
    )

    timeout = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
    cur_data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout=timeout,
    )

    return CareerCurriculumResponse(
        insurance_text=body.insurance_text,
        certificate_texts=body.certificate_texts or [],
        model=cur_data.get("model", LM_STUDIO_MODEL),
        curriculum=_extract_chat_text(cur_data),
        raw_curriculum=cur_data,
    )


@app.post("/career/curriculum/text", tags=["career"], response_class=PlainTextResponse)
async def career_curriculum_text(
    insurance_file: UploadFile = File(...),
    certificate_files: list[UploadFile] | None = File(None),
    certificate_hints: list[str] | None = Form(None),
    dependent_mode: str = Form("auto"),
    ocr_lang: str = Form("kor+eng"),
    ocr_psm: int = Form(6),
    ocr_oem: int = Form(3),
    ocr_dpi: int = Form(300),
    weeks: int = Form(6),
    goal: str | None = Form(None),
) -> str:
    result = await career_curriculum(
        insurance_file=insurance_file,
        certificate_files=certificate_files,
        certificate_hints=certificate_hints,
        dependent_mode=dependent_mode,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        ocr_oem=ocr_oem,
        ocr_dpi=ocr_dpi,
        weeks=weeks,
        goal=goal,
    )
    return result.curriculum


@app.post("/career/curriculum/from-text/text", tags=["career"], response_class=PlainTextResponse)
async def career_curriculum_from_text_plain(body: CareerCurriculumFromTextRequest) -> str:
    result = await career_curriculum_from_text(body)
    return result.curriculum
