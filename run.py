"""로컬 실행 진입점.

사용법:
    python run.py
브라우저에서 http://127.0.0.1:8000 접속.
"""

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    print(f"대시보드: http://{s.app_host}:{s.app_port}")
    uvicorn.run("app.main:app", host=s.app_host, port=s.app_port, reload=False)
