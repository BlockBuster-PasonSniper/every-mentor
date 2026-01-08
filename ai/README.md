# AI FastAPI

## 실행

PowerShell에서 아래 순서대로 실행하세요.

```powershell
cd "c:\Users\dhrwn\OneDrive\문서\every-mentor\ai"
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
  - 건강보험 자격득실 이미지와 자격증 이미지를 받아 OCR → 모듈형 커리큘럼(주차/단계 제목 없음)과 재직 이력을 기반으로 추정한 대표 강점 기술을 반환합니다.

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

## LM Studio & Tesseract 설정

- LM Studio(OpenAI 호환 서버)가 `http://127.0.0.1:1234`에서 동작해야 합니다.
- 기본 모델은 `qwen2.5-vl-7b-instruct`로 설정되어 있습니다.
- Tesseract OCR이 설치되어 있어야 하며, PATH에 없으면 `TESSERACT_CMD` 환경변수로 경로를 지정하세요.

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```
