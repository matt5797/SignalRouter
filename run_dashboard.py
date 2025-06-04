#!/usr/bin/env python3
"""
SignalRouter Dashboard 실행 스크립트
Streamlit 대시보드를 시작하는 메인 실행 파일
"""

import sys
import subprocess
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """대시보드 메인 실행"""
    try:
        # 환경 설정
        dashboard_host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
        dashboard_port = os.getenv("DASHBOARD_PORT", "8501")
        
        # Streamlit 명령어 구성
        cmd = [
            "streamlit", "run",
            "src/dashboard/dashboard.py",
            "--server.address", dashboard_host,
            "--server.port", dashboard_port,
            "--server.headless", "true",
            "--server.fileWatcherType", "none",
            "--browser.gatherUsageStats", "false"
        ]
        
        print(f"🚀 Starting SignalRouter Dashboard at http://{dashboard_host}:{dashboard_port}")
        print(f"📊 Dashboard URL: http://localhost:{dashboard_port}")
        print("Press Ctrl+C to stop the dashboard")
        
        # Streamlit 실행
        subprocess.run(cmd, check=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start dashboard: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Streamlit not found. Please install with: pip install streamlit")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
