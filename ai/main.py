from __future__ import annotations

import os
import io
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
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
    return "\n[과목 힌트]\n" + "\n".join(lines) + "\n"


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
            "\n[주의]\n"
            "보험 문서에 '직장피부양자' 또는 '피부양자' 표현이 보입니다.\n"
            "이는 표에 나온 일부 회사가 가족의 사업장일 수 있으니, 사용자의 직접 재직 정보로 단정하지 말고 강점 추정과 커리큘럼 설계에서 제외하세요.\n"
        )

    subject_hints = _cert_subject_hints_from_texts(certificate_texts)

    return (
        "당신은 실무 친화적인 커리큘럼 설계자입니다.\n"
        "아래 텍스트(건강보험/재직 정보와 선택적인 자격증 OCR 텍스트)를 참고하여 학습자가 실제로 가르칠 수 있는 강좌 커리큘럼을 제시하세요.\n"
        f"커리큘럼은 약 {weeks}주 분량을 커버한다는 가정으로 구성하되, 주차나 단계 제목은 사용하지 마세요.\n\n"
        "작성 지침:\n"
        "- 결과는 한국어로 작성합니다.\n"
        "- 커리큘럼은 '모듈 1 제목:'처럼 문장 내 표기로 구분하고, 줄마다 하이픈(-), 별표(*), 번호 목록을 사용하지 않습니다.\n"
        "- 각 모듈은 목표, 주요 학습 주제, 실습/과제 아이디어, 참고 자료를 한두 문장으로 자연스럽게 설명합니다.\n"
        "- 자격증 관련 단어나 과목 힌트가 있다면 별도 모듈을 마련하거나 관련 모듈 내에 대비 활동을 명확히 포함합니다.\n"
        "- 건강보험 재직 정보(피부양자 표기는 제외)를 활용해 학습자가 보유했을 가능성이 높은 '대표 강점 기술'을 하나 선택하고, 근거와 함께 별도 단락으로 제시합니다.\n"
        "- 강점 기술을 설명할 때는 관련 회사명, 기간, 역할 등 근거를 문장으로 덧붙이되, 근거가 부족하면 추가 정보가 필요함을 밝혀주세요.\n"
        "- 선택한 강점 기술을 강화하거나 확장할 수 있도록 커리큘럼 모듈과의 연결 지점을 명확히 설명합니다.\n"
        "- 정보가 부족한 부분은 '추가 정보 요청' 문단에서 구체적으로 요청합니다.\n"
        "- 주민등록번호 등 민감 정보는 반복하지 않습니다.\n"
        "- Markdown 제목 기호(#, ##, ### 등), 굵게/기울임 서식, 코드 블록, 목록 표기(-, *)는 사용하지 않습니다.\n"
        f"{goal_line}"
        f"{dependent_hint}"
        f"{subject_hints}"
        "\n[참고 텍스트 - 건강보험/재직]\n"
        f"{insurance_text}\n"
        "\n[참고 텍스트 - 자격증]\n"
        f"{cert_block if cert_block else '(자료 없음)'}\n"
    )


def _looks_like_dependent_insurance(text: str) -> bool:
    t = (text or "").replace(" ", "")
    keywords = ["직장피부양자", "피부양자", "직장피부양"]
    return any(k in t for k in keywords)


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


@dataclass
class OCRResponse:
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


async def _generate_career_curriculum(
    *,
    insurance_file: UploadFile,
    certificate_files: list[UploadFile] | None,
    certificate_hints: list[str] | None,
    dependent_mode: str,
    ocr_lang: str,
    ocr_psm: int,
    ocr_oem: int,
    ocr_dpi: int,
    weeks: int,
    goal: str | None,
) -> str:
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

    return _extract_chat_text(cur_data)


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
    return await _generate_career_curriculum(
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
