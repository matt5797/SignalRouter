# 🤖 SignalRouter

개인용 자동매매 시스템입니다. TradingView에서 오는 웹훅 시그널을 받아서 한국투자증권 API를 통해 자동으로 주문을 넣어주는 프로그램입니다.

## ⚠️ 주의사항

**이 프로젝트는 개인 학습/투자 목적으로 제작되었습니다.**
- 실제 투자 목적으로 사용하지 마세요
- 투자 손실에 대한 책임지지 않습니다
- 사용은 본인 책임하에 하세요

## 🛠️ 기술 스택

- **Backend**: Python, FastAPI
- **Database**: PostgreSQL / SQLite  
- **Dashboard**: Streamlit
- **API**: 한국투자증권 KIS API
- **Deploy**: Railway

## 📋 주요 기능

- TradingView 웹훅 수신
- 실시간 주문 실행
- 리스크 관리 (손실 제한, 포지션 제한)
- 실시간 대시보드
- 다중 계좌 지원

## 🚀 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt

# 웹훅 서버 실행
python start.py

# 대시보드 실행
python run_dashboard.py
```
