# AI FastAPI

## 실행

PowerShell에서 아래 순서대로 실행하세요.

```powershell
cd "c:\Users\dhrwn\OneDrive\문서\every-mentor\ai"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 확인

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs

## OCR (Tesseract)

이 서버의 `/ocr`는 로컬에 설치된 Tesseract OCR로 텍스트를 추출한 뒤, 그 텍스트를 LM Studio로 보내 커리큘럼까지 한 번에 생성합니다.

### 자격증 OCR이 잘 안 나올 때

- 먼저 자격증 이미지 **단독**으로 `/ocr/text`를 호출해서 OCR이 제대로 나오는지 확인하세요.
- 자격증/짧은 문구는 `psm=6`보다 `psm=7` 또는 `psm=11`이 더 잘 나오는 경우가 많습니다.
  - 예: `psm=7`(한 줄), `psm=11`(흩어진 텍스트)

> 참고: 서버는 원본/약한 전처리/강한 전처리 결과 중 더 좋은 텍스트를 자동 선택합니다. 응답의 `raw.selected_variant`로 어떤 변형이 선택됐는지 확인할 수 있습니다.

### 테스트

```powershell
$img = "C:\path\to\sample.png"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ocr" -Form @{ file = Get-Item $img; ocr_lang = "kor+eng"; weeks = 6; target_level = "beginner"; ocr_psm = 6; ocr_oem = 3; ocr_dpi = 300 }
```

커리큘럼만 바로 보고 싶으면:

```powershell
$img = "C:\path\to\sample.png"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ocr/curriculum" -Form @{ file = Get-Item $img; ocr_lang = "kor+eng"; weeks = 6; target_level = "beginner" }
```

### OCR 품질이 안 좋을 때 팁

- 이미지가 작거나(저해상도) 표/선이 많으면 Tesseract가 자주 깨집니다. 가능하면 더 큰 해상도(예: 2~3배)로 캡처하세요.
- `ocr_psm` 값을 바꿔보세요. 문서 전체는 보통 `6`이 무난하고, 레이아웃이 복잡하면 `4` 또는 `11`이 나을 때가 있습니다.

예:

```powershell
$img = "C:\path\to\sample.png"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ocr" -Form @{ file = Get-Item $img; ocr_lang = "kor+eng"; weeks = 4; target_level = "beginner"; ocr_psm = 4 }
```

### Tesseract 경로 지정(필요할 때만)

Windows에서 Tesseract가 PATH에 없으면 환경변수로 지정할 수 있습니다.

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Tesseract가 어디 설치됐는지 모르겠으면 아래로 먼저 확인하세요.

```powershell
where.exe tesseract
```

매번 설정하기 귀찮으면(새 터미널에도 유지) 아래처럼 영구 설정할 수 있습니다.

```powershell
setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## 커리큘럼 생성 (LM Studio)

`/curriculum` (텍스트→커리큘럼) 및 `/curriculum/from-image` (이미지→커리큘럼, `/ocr`와 동일 동작)는 LM Studio(OpenAI 호환 API)를 호출합니다.

- 기본 URL: `http://127.0.0.1:1234`
- 기본 모델: `qwen2.5-vl-7b-instruct`

## 직무 추정 + 커리큘럼 (추천)

건강보험 자격득실(회사명/기간) + 자격증 파일을 함께 올려서, "어떤 업무를 했을 가능성이 높은지"를 **추정**하고 그에 맞는 커리큘럼을 생성합니다.

- `/career/curriculum` : JSON 응답
- `/career/curriculum/text` : 커리큘럼만 `text/plain` (펼치지 않고 바로 보기 좋음)

자격증 OCR이 잘 안 읽히면, 자격증 "과목/키워드"를 수동으로 같이 넣을 수 있습니다.

- `certificate_hints`: 예) `"정보처리기사"`, `"SQL"`, `"네트워크"`, `"리눅스"` 처럼 여러 개를 추가

### (옵션) OCR 결과 텍스트로 바로 보내기

OCR 결과를 이미 갖고 있다면(또는 자격증 OCR 디버깅), 건강보험 텍스트 + 자격증 텍스트를 합쳐 **한 번에** LLM에 넣을 수 있습니다.

- `/career/curriculum/from-text` : JSON 응답
- `/career/curriculum/from-text/text` : 커리큘럼만 `text/plain`

### PowerShell 예시 (커리큘럼 텍스트만)

````powershell
$insurance = "C:\path\to\health_insurance.png"
$cert1 = "C:\path\to\certificate1.png"
$cert2 = "C:\path\to\certificate2.png"

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/career/curriculum/text" -Form @{
	insurance_file = Get-Item $insurance
	# PowerShell 해시테이블은 같은 키를 2번 쓸 수 없어서(마지막 값만 남음)
	# 여러 자격증 파일은 배열로 전달하세요.
	certificate_files = @(Get-Item $cert1, Get-Item $cert2)
	# OCR이 약하면 자격증 과목/키워드를 수동으로 보강할 수 있음
	certificate_hints = @("정보처리기사", "SQL", "네트워크")
	weeks = 8
	goal = "원하는 방향(예: 데이터/자동화 쪽 전환)"
	ocr_lang = "kor+eng"
}

### 직장피부양자(부모/가족 회사) 제외

건강보험 문서에 `직장피부양자`/`피부양자`가 포함되면, 표에 나오는 회사명이 **본인 경력**이 아닐 수 있습니다.
서버는 이 경우 회사명/기간을 본인 경력으로 단정하지 않도록 보수적으로 처리합니다.

## 가르칠 수 있는 과목/자격증 뽑기

- `/career/teaching-profile` : (이미지 업로드) 보험/자격증 기반으로 "가르칠 수 있는 과목"과 "가르칠 수 있는 자격증(시험 대비)"을 JSON으로 반환
- `/career/teaching-profile/from-text` : (텍스트 입력) OCR 결과 텍스트가 이미 있을 때

PowerShell 예시:

```powershell
$insurance = "C:\path\to\health_insurance.png"
$cert1 = "C:\path\to\certificate1.png"

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/career/teaching-profile" -Form @{
	insurance_file = Get-Item $insurance
	certificate_files = @(Get-Item $cert1)
	certificate_hints = @("SQL", "네트워크")
}
````

# 텍스트로 바로 보내기 예시

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/career/curriculum/from-text/text" -ContentType "application/json" -Body (@{
insurance_text = "..."
certificate_texts = @("...", "...")
weeks = 8
goal = "원하는 방향(예: 데이터/자동화 쪽 전환)"
} | ConvertTo-Json)

```

```
