from __future__ import annotations

import os
import io
import re
import shutil
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None  # type: ignore[assignment]
    process = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
import httpx
import pytesseract
from PIL import Image
from PIL import ImageOps

app = FastAPI(title="every-mentor ai api")


# Use uvicorn's logger so INFO lines reliably show up in the terminal.
logger = logging.getLogger("uvicorn.error")


if load_dotenv is not None:
    # Prefer ai/.env, then repo root .env (both should be gitignored)
    _here = Path(__file__).resolve().parent
    for _p in [_here / ".env", _here.parent / ".env"]:
        if _p.exists():
            load_dotenv(dotenv_path=_p, override=False)
            break

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen2.5-vl-7b-instruct")

# LLM provider selection
# - auto: use Anthropic when ANTHROPIC_API_KEY is set, else fallback to LM Studio
# - anthropic: force Claude
# - lmstudio: force LM Studio
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()

ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None
# NOTE: Model availability varies by Anthropic account. If you get 404 model-not-found,
# set ANTHROPIC_MODEL in ai/.env to a model your key has access to.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


LM_STUDIO_TIMEOUT_CONNECT = _env_float("LM_STUDIO_TIMEOUT_CONNECT", 5.0)
LM_STUDIO_TIMEOUT_READ = _env_float("LM_STUDIO_TIMEOUT_READ", 600.0)
LM_STUDIO_TIMEOUT_WRITE = _env_float("LM_STUDIO_TIMEOUT_WRITE", 60.0)
LM_STUDIO_TIMEOUT_POOL = _env_float("LM_STUDIO_TIMEOUT_POOL", 5.0)

TESSERACT_CMD = os.getenv("TESSERACT_CMD")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


OCR_DEBUG_LOG = _env_bool("OCR_DEBUG_LOG", False)
OCR_DEBUG_LOG_MAX_CHARS = _env_int("OCR_DEBUG_LOG_MAX_CHARS", 1500)

LM_STUDIO_SUBJECTS_FALLBACK = _env_bool("LM_STUDIO_SUBJECTS_FALLBACK", False)
LM_STUDIO_SUBJECTS_FALLBACK_MAX = _env_int("LM_STUDIO_SUBJECTS_FALLBACK_MAX", 8)


@app.on_event("startup")
async def _startup_log_settings() -> None:
    if OCR_DEBUG_LOG:
        logger.info(
            "OCR_DEBUG_LOG is enabled (max_chars=%s)",
            OCR_DEBUG_LOG_MAX_CHARS,
        )


def _mask_sensitive_text(text: str) -> str:
    s = text or ""
    # 주민등록번호 형태(######-####### 또는 13자리) 마스킹
    s = re.sub(r"\b(\d{6})-?(\d{7})\b", r"\1-*******", s)
    # 긴 숫자열(계좌/식별번호 등) 마스킹
    s = re.sub(r"\b\d{10,}\b", "**********", s)
    return s


def _normalize_company_name(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return s

    # Remove leading indices like '6 ' from OCR tables
    s = re.sub(r"^\s*\d+\s+", "", s)

    # Remove insurance-role prefixes that OCR often includes
    role_prefixes = [
        "직장가입자",
        "직장피부양자",
        "피부양자",
        "지역가입자",
        "사업장",
        "사업장명",
    ]
    for p in role_prefixes:
        if s.startswith(p):
            s = s[len(p) :].strip()

    # Remove common OCR noise characters
    s = re.sub(r"[\|‘’“”\"~`]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Drop known note fragments
    s = s.replace("입사일퇴직일과 다를 수 있습니다", "").strip()
    s = s.replace("입사일퇴직일과다를수있습니다", "").strip()

    # Drop common table header fragments that may leak into lines
    for frag in ["칭", "자격취득일", "자격상실일", "취득일", "상실일", "입사일", "퇴직일"]:
        if frag in s and len(s) > 6:
            s = s.split(frag, 1)[0].strip()

    # Normalize corporate markers
    s = re.sub(r"^주식회사\s*(.+)$", r"\1(주)", s)
    s = re.sub(r"^㈜\s*(.+)$", r"(주) \1", s)
    s = re.sub(r"^\(주\)\s*", "(주) ", s)
    s = re.sub(r"\s*㈜$", " (주)", s)

    # Common OCR typo: (수) -> (주)
    s = s.replace("(수)", "(주)")

    # Remove dates if they leaked into the name
    s = re.sub(r"\b\d{4}[-./]\d{2}[-./]\d{2}\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Keep only reasonable characters
    s = re.sub(r"[^가-힣A-Za-z0-9\(\)\-\s]", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()

    return s


_FAMOUS_COMPANIES: set[str] = {
    # Common major Korean companies (add more as needed)
    "엘지전자(주)",
    "삼성전자(주)",
    "현대자동차(주)",
    "기아(주)",
    "에스케이하이닉스(주)",
    "네이버(주)",
    "카카오(주)",
    "포스코(주)",
}


def _company_rank_score(name: str, *, freq: int = 1) -> int:
    n = _normalize_company_name(name)
    if not n:
        return -10**9
    score = 0
    if n in _FAMOUS_COMPANIES:
        score += 10_000
    # Boost names that contain well-known tokens even if formatting differs
    for token in ["엘지", "LG", "삼성", "현대", "기아", "SK", "네이버", "카카오", "포스코"]:
        if token.lower() in n.lower():
            score += 2_000
            break
    # Prefer corporate-marked names
    if "(주)" in n or "주식회사" in n or "㈜" in n:
        score += 200
    # Prefer longer (more specific) names a bit
    score += min(len(n), 30)
    # Prefer companies seen multiple times in OCR
    score += min(freq, 10) * 20
    return score


def _company_key(name: str) -> str:
    """Key used for deduping company names across OCR variants.

    Collapses whitespace and removes common corporate markers so that
    '이레특장' and '(주) 이레특장' are treated as the same company.
    """
    s = _normalize_company_name(name)
    s = re.sub(r"\s+", "", s)
    s = s.replace("주식회사", "")
    s = s.replace("(주)", "")
    s = s.replace("㈜", "")
    return s


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        k = _compact(it)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _extract_company_candidates(text: str) -> list[str]:
    """Best-effort extraction of company names from insurance OCR text.

    This is heuristic and intentionally conservative.
    """
    t = (text or "")
    if not t.strip():
        return []

    candidates: list[str] = []

    # 1) Prefer employment table rows: <company> <YYYY-MM-DD> <YYYY-MM-DD>
    date_pat = r"\d{4}[-./]\d{2}[-./]\d{2}"
    row_re = re.compile(rf"(?P<name>.+?)\s+(?P<s>{date_pat})\s+(?P<e>{date_pat})")
    for raw_line in t.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if any(k in line for k in ["신청인", "주소", "자격취득", "사항", "자격증", "주민", "보험"]):
            continue

        m = row_re.search(line)
        if not m:
            continue
        name = _normalize_company_name(m.group("name"))
        if 2 <= len(name) <= 50:
            candidates.append(name)

    # 2) Fallback: explicit company markers (process line-by-line to avoid spanning newlines)
    marker_patterns = [
        r"(주식회사[ \t]*[가-힣A-Za-z0-9\(\)\- ]{2,40})",
        r"(\(주\)[ \t]*[가-힣A-Za-z0-9\(\)\- ]{2,40})",
        r"(㈜[ \t]*[가-힣A-Za-z0-9\(\)\- ]{2,40})",
        r"([가-힣A-Za-z0-9\(\)\-]{2,40}[ \t]*㈜)",
        r"([가-힣A-Za-z0-9\(\)\-]{2,40}[ \t]*\(주\))",
    ]
    for raw_line in t.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        for pat in marker_patterns:
            for m in re.findall(pat, line):
                name = _normalize_company_name(str(m))
                if 2 <= len(name) <= 50:
                    candidates.append(name)

    # 2-1) Fallback: lines that start with role prefixes often contain the company name
    for raw_line in t.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if any(line.startswith(p) for p in ["직장가입자", "직장피부양자", "피부양자", "지역가입자"]):
            name = _normalize_company_name(line)
            if 2 <= len(name) <= 50:
                candidates.append(name)

    # 3) Fallback: lines containing '사업장' (workplace)
    for raw_line in t.splitlines():
        if "사업장" not in raw_line:
            continue
        line = re.sub(r"\s+", " ", raw_line).strip()
        parts = re.split(r"사업장명|사업장", line)
        if len(parts) < 2:
            continue
        tail = _normalize_company_name(parts[-1])
        if 2 <= len(tail) <= 50:
            candidates.append(tail)

    normalized = [_normalize_company_name(x) for x in candidates]
    normalized = [x for x in normalized if x]

    # Count frequency (before dedupe) for ranking
    freq: dict[str, int] = {}
    for x in normalized:
        k = _company_key(x)
        freq[k] = freq.get(k, 0) + 1

    # Deduplicate while preserving first-seen order using company-specific key
    unique: list[str] = []
    seen: set[str] = set()
    for x in normalized:
        k = _company_key(x)
        if not k or k in seen:
            continue
        seen.add(k)
        unique.append(x)

    unique.sort(key=lambda n: _company_rank_score(n, freq=freq.get(_company_key(n), 1)), reverse=True)
    return unique[:30]


def _format_subjects_response(*, company_names: list[str], subjects_block: str) -> str:
    # Company names are deduped using company-key (ignores (주)/㈜ variants)
    raw = [_normalize_company_name(c) for c in company_names if c and c.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    for c in raw:
        k = _company_key(c)
        if not k or k in seen:
            continue
        seen.add(k)
        cleaned.append(c)
    company_line = "\n".join(cleaned) if cleaned else "(기업명 미확인)"
    subjects_block = (subjects_block or "").strip()
    if not subjects_block:
        subjects_block = "(자격증 없음)"
    return "\n".join(
        [
            "기업명",
            company_line,
            "#####",
            "자격증-과목",
            subjects_block,
        ]
    )


def _log_ocr_text(*, filename: str | None, kind: str, text: str, meta: dict[str, Any]) -> None:
    if not OCR_DEBUG_LOG:
        return
    safe = _mask_sensitive_text(text)
    safe = safe.strip()
    if OCR_DEBUG_LOG_MAX_CHARS > 0 and len(safe) > OCR_DEBUG_LOG_MAX_CHARS:
        safe = safe[: OCR_DEBUG_LOG_MAX_CHARS] + "\n...(truncated)"
    selected_variant = meta.get("selected_variant")
    length = meta.get("length") or len((text or "").strip())
    logger.info(
        "[OCR][%s]%s variant=%s length=%s\n%s",
        kind,
        f" {filename}" if filename else "",
        selected_variant,
        length,
        safe,
    )


_CERT_SUBJECT_MAP: dict[str, list[str]] = {
    # 대표 학습 영역(시험 대비 관점) 힌트용
    "전기기능사": ["전기이론", "전기기기", "전기설비"],
    "정보처리산업기사": [
        "정보시스템 기반 기술",
        "프로그래밍 언어 활용",
        "데이터베이스 활용",
        "정보시스템 구축 관리",
    ],
    "생산자동화기능사": ["기계요소", "공압/유압", "전기/전자 기초", "PLC 기초", "자동화 실무"],
    "자동화설비기능사": ["기계요소", "공압/유압", "전기/전자 기초", "센서/제어 기초", "PLC 기초", "자동화 실무"],
    "설비보전기능사": ["기계 보전", "전기 보전", "유공압/윤활", "설비 관리", "안전"],
    "전자기기기능사": ["전자회로 기초", "디지털/마이크로컨트롤러 기초", "측정/계측", "전자기기 수리"],
    "컴퓨터응용밀링기능사": ["도면 해독", "가공 공정", "공구/절삭", "측정", "안전"],
    "컴퓨터응용선반기능사": ["도면 해독", "선반 가공 공정", "공구/절삭", "측정", "안전"],
    "정보처리기능사": ["컴퓨터 기초", "소프트웨어 기초", "데이터/DB 기초", "네트워크 기초", "문제풀이"],
    "공유압기능사": ["공압 기초", "유압 기초", "회로 해독", "기기/밸브", "안전"],
}


_CERT_ALIASES: dict[str, list[str]] = {
    "전기기능사": ["기기능사"],
    "생산자동화기능사": ["생산자동화"],
    "자동화설비기능사": ["자동화설비"],
    "전자기기기능사": ["전자기능사"],
    "정보처리기능사": ["프로그래밍기능사"],
}


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def _canonical_cert_names() -> list[str]:
    return list(_CERT_SUBJECT_MAP.keys())


def _resolve_cert_name(name: str) -> str | None:
    """Resolve OCR'd certificate name to a canonical key in _CERT_SUBJECT_MAP.

    - Exact match / alias match
    - Whitespace-insensitive match
    - Optional fuzzy match (RapidFuzz) when installed
    """
    n0 = _normalize_cert_name(name)
    if not n0:
        return None

    if n0 in _CERT_SUBJECT_MAP:
        return n0

    n0c = _compact(n0)

    for cert, aliases in _CERT_ALIASES.items():
        if n0 in aliases or n0c in {_compact(a) for a in aliases}:
            return cert

    for cert in _CERT_SUBJECT_MAP.keys():
        if n0c == _compact(cert):
            return cert

    if process is not None and fuzz is not None:
        choices = _canonical_cert_names()
        # Compare on compacted strings to be robust to spacing/line breaks.
        mapping = {c: _compact(c) for c in choices}
        best = process.extractOne(n0c, mapping, scorer=fuzz.ratio)
        if best:
            choice_key, score, _idx = best
            if score >= 90:
                return str(choice_key)

    return None


_subjects_llm_cache: dict[str, str] = {}


async def _infer_subjects_with_lmstudio(cert_name: str) -> str:
    """Best-effort inference for unknown certificates.

    Returns exactly one line: '자격증 - 과목, 과목' or '자격증 - (과목 정보 없음)'.
    Mark as '(추정)' when inferred.
    """
    key = _compact(cert_name)
    if key in _subjects_llm_cache:
        return _subjects_llm_cache[key]

    if not LM_STUDIO_SUBJECTS_FALLBACK:
        line = f"{cert_name} - (과목표 미등록)"
        _subjects_llm_cache[key] = line
        return line

    prompt = (
        "너는 한국 국가기술자격/민간자격 과목 요약 도우미다.\n"
        "아래 자격증의 대표 시험 과목/학습 영역을 3~7개로 요약해라.\n"
        "출력은 반드시 한 줄이고, 정확히 아래 형식만 사용한다.\n"
        "형식: 자격증명 - 과목1, 과목2, 과목3\n"
        "확실하지 않으면 다음만 출력: 자격증명 - (과목 정보 없음)\n"
        "추정으로 과목을 제시하는 경우 각 과목명 뒤에 '(추정)'를 붙이지 말고, 줄 끝에 ' (추정)'만 한 번 붙여라.\n\n"
        f"자격증명: {cert_name}\n"
    )

    timeout = httpx.Timeout(
        connect=LM_STUDIO_TIMEOUT_CONNECT,
        read=LM_STUDIO_TIMEOUT_READ,
        write=LM_STUDIO_TIMEOUT_WRITE,
        pool=LM_STUDIO_TIMEOUT_POOL,
    )

    text = await _llm_generate_text(
        prompt=prompt,
        temperature=0.0,
        max_tokens=128,
        timeout=timeout,
    )
    # Basic sanitization: keep first line only
    line = (text.splitlines()[0] if text else "").strip()
    if not line:
        line = f"{cert_name} - (과목 정보 없음)"
    # Ensure it starts with cert_name; otherwise, force format.
    if not line.startswith(cert_name):
        line = f"{cert_name} - {line}" if " - " not in line else line
    _subjects_llm_cache[key] = line
    return line


def _extract_cert_title_candidates(text: str) -> list[str]:
    # Conservative heuristic: find Korean certificate-like titles in whitespace-compacted text
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []

    # e.g. 전기기능사, 전기산업기사, 정보처리기사, 건설기계정비기능사 ...
    matches = re.findall(r"[가-힣]{2,30}(?:기능사|산업기사|기사|기술사)", compact)
    out: list[str] = []
    seen: set[str] = set()
    for m in matches:
        n = _normalize_cert_name(m)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _subjects_only_text(*, insurance_text: str, certificate_texts: list[str]) -> str:
    blob = "\n".join([insurance_text or "", *[t for t in certificate_texts if t]]).strip()
    if not blob:
        return "인식된 자격증이 없습니다."

    blob_compact = _compact(blob)

    lines: list[str] = []
    for cert, subjects in _CERT_SUBJECT_MAP.items():
        aliases = _CERT_ALIASES.get(cert, [])
        cert_compact = _compact(cert)
        aliases_compact = [_compact(a) for a in aliases]
        if (
            cert in blob
            or any(a in blob for a in aliases)
            or cert_compact in blob_compact
            or any(a in blob_compact for a in aliases_compact)
        ):
            lines.append(f"{cert} - " + ", ".join(subjects))

    # Try to surface more via candidate extraction (unmapped will be omitted here)
    candidates = _extract_cert_title_candidates(blob)
    for c in candidates:
        resolved = _resolve_cert_name(c)
        if resolved and all(not l.startswith(resolved + " - ") for l in lines):
            lines.append(f"{resolved} - " + ", ".join(_CERT_SUBJECT_MAP[resolved]))

    return "\n".join(lines) if lines else "인식된 자격증이 없습니다."


async def _subjects_detected_text(*, insurance_text: str, certificate_texts: list[str]) -> str:
    blob = "\n".join([insurance_text or "", *[t for t in certificate_texts if t]]).strip()
    if not blob:
        return "인식된 자격증이 없습니다."

    mapped_lines: list[str] = []
    mapped_certs: set[str] = set()

    blob_compact = _compact(blob)
    for cert, subjects in _CERT_SUBJECT_MAP.items():
        aliases = _CERT_ALIASES.get(cert, [])
        cert_compact = _compact(cert)
        aliases_compact = [_compact(a) for a in aliases]
        if (
            cert in blob
            or any(a in blob for a in aliases)
            or cert_compact in blob_compact
            or any(a in blob_compact for a in aliases_compact)
        ):
            mapped_lines.append(f"{cert} - " + ", ".join(subjects))
            mapped_certs.add(cert)

    candidates = _extract_cert_title_candidates(blob)
    resolved_candidates: list[str] = []
    unknown_candidates: list[str] = []
    for c in candidates:
        resolved = _resolve_cert_name(c)
        if resolved:
            resolved_candidates.append(resolved)
        else:
            unknown_candidates.append(c)

    # Add any resolved-but-not-yet-included mapped certs
    for rc in resolved_candidates:
        if rc not in mapped_certs:
            mapped_lines.append(f"{rc} - " + ", ".join(_CERT_SUBJECT_MAP[rc]))
            mapped_certs.add(rc)

    # For truly unknown certs, optionally infer subjects via LM Studio.
    unmapped_lines: list[str] = []
    for c in unknown_candidates[: max(0, LM_STUDIO_SUBJECTS_FALLBACK_MAX)]:
        # This may return '(과목표 미등록)' when fallback disabled.
        # If enabled, returns a single inferred line.
        # Note: we keep it as-is to make debugging transparent.
        # (추정) marking is handled by the LLM instruction.
        unmapped_lines.append(await _infer_subjects_with_lmstudio(c))

    lines = [*mapped_lines, *unmapped_lines]
    return "\n".join(lines) if lines else "인식된 자격증이 없습니다."


def _subjects_all_text() -> str:
    lines = [f"{cert} - " + ", ".join(subjects) for cert, subjects in _CERT_SUBJECT_MAP.items()]
    return "\n".join(lines)


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
            lines.append(f"{cert} - " + ", ".join(subjects))
    if not lines:
        return ""
    return "\n[자격증 과목]\n" + "\n".join(lines) + "\n"


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
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail=(
                    "LM Studio 응답이 시간 초과되었습니다. "
                    "(네트워크/모델 처리 지연) LM_STUDIO_TIMEOUT_READ 값을 늘려보세요."
                ),
            ) from e
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "").strip()
            body = body[:2000] if body else ""
            raise HTTPException(
                status_code=502,
                detail=f"LM Studio 오류 응답: HTTP {e.response.status_code} {body}",
            ) from e
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"LM Studio 연결 오류: {type(e).__name__}",
            ) from e


def _extract_chat_text(data: dict[str, Any]) -> str:
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


def _extract_anthropic_text(data: dict[str, Any]) -> str:
    # Anthropic Messages API returns: { content: [ {type: 'text', text: '...'}, ... ] }
    parts: list[str] = []
    for item in (data.get("content") or []):
        if isinstance(item, dict) and item.get("type") == "text":
            txt = (item.get("text") or "").strip()
            if txt:
                parts.append(txt)
    return "\n".join(parts).strip()


def _selected_llm_provider() -> str:
    p = (LLM_PROVIDER or "auto").strip().lower()
    if p in {"anthropic", "claude"}:
        return "anthropic"
    if p in {"lmstudio", "lm", "openai"}:
        return "lmstudio"
    # auto
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return "lmstudio"


async def _anthropic_messages(
    *,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: httpx.Timeout,
) -> dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY가 설정되지 않았습니다. .env에 ANTHROPIC_API_KEY를 추가하세요.",
        )

    url = f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"
    payload: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail=(
                    "Claude(Anthropic) 응답이 시간 초과되었습니다. "
                    "(네트워크/모델 처리 지연) LM_STUDIO_TIMEOUT_READ 값을 늘려보세요."
                ),
            ) from e
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "").strip()
            body = body[:2000] if body else ""
            if e.response.status_code == 404:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Claude(Anthropic) 모델을 찾을 수 없습니다. "
                        "ai/.env의 ANTHROPIC_MODEL 값을 현재 계정에서 사용 가능한 모델로 바꿔주세요. "
                        f"(현재: {ANTHROPIC_MODEL}) {body}"
                    ),
                ) from e
            raise HTTPException(
                status_code=502,
                detail=f"Claude(Anthropic) 오류 응답: HTTP {e.response.status_code} {body}",
            ) from e
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Claude(Anthropic) 연결 오류: {type(e).__name__}",
            ) from e


async def _llm_generate_text(
    *,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: httpx.Timeout,
) -> str:
    provider = _selected_llm_provider()
    if provider == "anthropic":
        data = await _anthropic_messages(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return _extract_anthropic_text(data)

    data = await _lmstudio_chat_completions(
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return _extract_chat_text(data)


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
        _log_ocr_text(filename=file.filename, kind="image", text=ocr.text, meta=ocr.raw)
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

    timeout = httpx.Timeout(
        connect=LM_STUDIO_TIMEOUT_CONNECT,
        read=LM_STUDIO_TIMEOUT_READ,
        write=LM_STUDIO_TIMEOUT_WRITE,
        pool=LM_STUDIO_TIMEOUT_POOL,
    )
    return await _llm_generate_text(
        prompt=prompt,
        temperature=0.2,
        max_tokens=1200,
        timeout=timeout,
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
    result_type: str = Form("subjects"),
) -> str:
    result_type_norm = (result_type or "curriculum").strip().lower()
    if result_type_norm in {"subjects_all", "all_subjects", "subjects:all", "all"}:
        insurance_text, _insurance_meta = await _extract_text_from_upload(
            file=insurance_file,
            ocr_lang=ocr_lang,
            ocr_psm=ocr_psm,
            ocr_oem=ocr_oem,
            ocr_dpi=ocr_dpi,
        )
        companies = _extract_company_candidates(insurance_text)
        return _format_subjects_response(company_names=companies, subjects_block=_subjects_all_text())

    if result_type_norm in {"subjects_detected", "detected", "subjects+unknown", "subjects_unknown"}:
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

        companies = _extract_company_candidates(insurance_text)
        block = await _subjects_detected_text(insurance_text=insurance_text, certificate_texts=cert_texts)
        return _format_subjects_response(company_names=companies, subjects_block=block)

    if result_type_norm in {"subjects", "subject", "courses", "only_subjects"}:
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

        companies = _extract_company_candidates(insurance_text)
        block = _subjects_only_text(insurance_text=insurance_text, certificate_texts=cert_texts)
        return _format_subjects_response(company_names=companies, subjects_block=block)

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
