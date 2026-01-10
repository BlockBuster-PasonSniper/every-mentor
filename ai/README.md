# AI FastAPI

## 실행

PowerShell에서 아래 순서대로 실행하세요.

```powershell
cd "c:\Users\okjunseo\Documents\every-mentor\ai"
python -m venv .venv
\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 확인

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs

## 지원하는 주요 엔드포인트

- `POST /career/curriculum/text`
  - 기본값은 `result_type=subjects`이며 "자격증 - 과목, 과목" 형태로 과목만 반환합니다.
  - 커리큘럼이 필요하면 `result_type=curriculum`을 주세요.
  - 현재 서버에 등록된 자격증 과목표를 전부 보고 싶으면 `result_type=subjects_all`을 주세요.
  - OCR에서 자격증명이 더 잡히는지 확인하려면 `result_type=subjects_detected`를 주세요(과목표 미등록 자격증은 "(과목표 미등록)"으로 표시).

## 자격증 과목 자동화(오타 보정/미등록 처리)

- OCR 오타/띄어쓰기/줄바꿈을 완화하기 위해, 서버가 자격증명을 퍼지 매칭으로 보정합니다(`rapidfuzz` 사용).
- 과목표에 없는 자격증은 기본적으로 `(...미등록)`으로 표시됩니다.
- 미등록 자격증도 과목을 “추정”해서 뽑고 싶으면 LM Studio 폴백을 켤 수 있습니다.
  - `LM_STUDIO_SUBJECTS_FALLBACK=1`
  - `LM_STUDIO_SUBJECTS_FALLBACK_MAX=8`

## subjects 출력 포맷

- `result_type=subjects*` 계열 응답은 아래 포맷으로 반환됩니다.

```text
기업명
<보험 OCR에서 추출한 기업명(없으면 '(기업명 미확인)')>
#####
자격증-과목
전기기능사 - 전기이론, 전기기기, 전기설비
...
```

## 사용 방법

1. 건강보험 증명서 이미지를 `insurance_file`로 업로드합니다.
2. 자격증 이미지가 있으면 `certificate_files` 배열로 함께 올립니다.
3. OCR이 어려운 자격증 과목/키워드는 `certificate_hints`에 텍스트로 보강합니다.
4. 학습 기간(`weeks`), 목표(`goal`), OCR 파라미터(`ocr_lang`, `ocr_psm`, `ocr_oem`, `ocr_dpi`)는 필요에 따라 조정합니다.

```powershell
$insurance = "C:\path\to\health_insurance.png"
$cert1 = "C:\path\to\certificate1.png"

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/career/curriculum/text" -Form @{
    insurance_file = Get-Item $insurance
    certificate_files = @(Get-Item $cert1)
    certificate_hints = @("정보처리기사", "SQL")
    weeks = 8
    goal = "데이터 직무 전환"
    ocr_lang = "kor+eng"
}
```

> 건강보험 문서에 `직장피부양자`/`피부양자`가 포함되면, 해당 회사명이 가족의 사업장일 가능성이 높으므로 커리큘럼에 참고용으로만 활용됩니다.

## LLM 설정 (Claude/LM Studio)

- 기본 동작: `ai/.env`에 `ANTHROPIC_API_KEY`가 설정되어 있으면 Claude를 사용하고, 없으면 LM Studio를 사용합니다.
- 강제로 지정하려면 `LLM_PROVIDER`를 사용합니다.
  - `LLM_PROVIDER=auto` (권장)
  - `LLM_PROVIDER=anthropic` (Claude 강제)
  - `LLM_PROVIDER=lmstudio` (LM Studio 강제)
- 모델은 `ANTHROPIC_MODEL`로 바꿀 수 있습니다.
  - 모델 ID는 계정/키에 따라 달라질 수 있으니, 필요하면 `GET https://api.anthropic.com/v1/models`로 목록을 확인한 뒤 그 중 하나를 넣으세요.
  - 예: `ANTHROPIC_MODEL=claude-sonnet-4-5-20250929`

주의: API 키는 반드시 `ai/.env`에만 넣고, 코드/채팅/로그에는 절대 넣지 마세요. `.env`는 gitignore로 커밋되지 않습니다.

- LM Studio(OpenAI 호환 서버) 주소는 환경변수 `LM_STUDIO_BASE_URL`로 지정합니다.
  - 기본값: `http://127.0.0.1:1234`
  - 예: 포트포워딩한 서버를 쓰는 경우 `http://<PUBLIC_IP>:<PORT>`
- 기본 모델은 `LM_STUDIO_MODEL=qwen2.5-vl-7b-instruct`로 설정되어 있습니다.
- OCR 텍스트가 길거나 모델이 느리면 `/v1/chat/completions` 응답이 오래 걸릴 수 있습니다.
  - 이 경우 `LM_STUDIO_TIMEOUT_READ`(초)를 늘려보세요. 예: `LM_STUDIO_TIMEOUT_READ=1200`

## Tesseract 설정

- Tesseract OCR이 설치되어 있어야 하며, PATH에 없으면 `TESSERACT_CMD` 환경변수로 경로를 지정하세요.

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### .env 사용(권장)

- `ai/.env` 파일을 만들고 필요한 환경변수만 채우세요.
- `.env`는 [../.gitignore](../.gitignore)에 의해 커밋되지 않습니다.
