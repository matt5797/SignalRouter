#!/usr/bin/env python3
"""
Railway 배포용 시작 스크립트
환경에 따라 웹훅 서버 또는 대시보드를 실행
"""

import os
import sys
import uvicorn
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.api.main import create_app


def main():
    """메인 실행 함수"""
    
    # 환경변수에서 설정 읽기
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    # 배포 환경 확인
    is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
    
    print(f"🚀 Starting SignalRouter on {host}:{port}")
    print(f"📊 Environment: {'Railway' if is_railway else 'Unknown'}")
    print(f"🗄️  Database: {'PostgreSQL' if os.getenv('DATABASE_URL') else 'SQLite'}")
    
    # FastAPI 앱 생성
    app = create_app("config/config.yaml")
    
    # 서버 실행
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=True
    )


if __name__ == "__main__":
    main()