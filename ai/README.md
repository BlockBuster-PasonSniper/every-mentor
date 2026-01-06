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
