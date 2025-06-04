"""
FastAPI 메인 애플리케이션
웹훅 서버 라우트 설정 및 앱 구성
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
import logging
import os
from ..core import AutoTrader
from .webhook_handler import WebhookHandler

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(config_path: str = "config/config.yaml") -> FastAPI:
    """FastAPI 애플리케이션 생성 및 구성"""
    
    # AutoTrader 및 WebhookHandler 초기화
    auto_trader = AutoTrader(config_path)
    webhook_handler = WebhookHandler(auto_trader)
    
    # FastAPI 앱 생성
    app = FastAPI(
        title="SignalRouter Auto Trading System",
        description="TradingView signal webhook receiver and auto trading system",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS 미들웨어 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 운영환경에서는 제한할 것
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 글로벌 객체 저장 (대시보드에서 접근 가능하도록)
    app.state.auto_trader = auto_trader
    app.state.webhook_handler = webhook_handler
    
    # ==================== 라우트 정의 ====================
    
    @app.post("/webhook/signal")
    async def receive_signal(request: Request):
        """트레이딩뷰 시그널 수신"""
        try:
            payload = await request.json()
            return await webhook_handler.receive_signal(payload)
        except Exception as e:
            logger.error(f"Signal webhook error: {e}")
            raise HTTPException(status_code=400, detail="Invalid signal payload")
    
    @app.get("/health")
    async def health_check():
        """서버 헬스 체크"""
        return await webhook_handler.health_check()
    
    @app.post("/emergency-stop")
    async def emergency_stop():
        """비상 정지"""
        return await webhook_handler.emergency_stop()
    
    @app.post("/resume-trading")  
    async def resume_trading():
        """거래 재개"""
        return await webhook_handler.resume_trading()
    
    @app.get("/portfolio")
    async def get_portfolio():
        """포트폴리오 요약 조회"""
        try:
            summary = auto_trader.get_portfolio_summary()
            return {"status": "success", "data": summary}
        except Exception as e:
            logger.error(f"Portfolio query error: {e}")
            raise HTTPException(status_code=500, detail="Portfolio query failed")
    
    @app.get("/positions")
    async def get_positions():
        """모든 포지션 조회"""
        try:
            positions = auto_trader.get_all_positions()
            return {"status": "success", "data": positions}
        except Exception as e:
            logger.error(f"Positions query error: {e}")
            raise HTTPException(status_code=500, detail="Positions query failed")
    
    @app.get("/accounts/{account_id}")
    async def get_account_info(account_id: str):
        """특정 계좌 정보 조회"""
        try:
            account = auto_trader.get_account(account_id)
            if not account:
                raise HTTPException(status_code=404, detail="Account not found")
            
            return {
                "status": "success",
                "data": {
                    "account_info": account.to_dict(),
                    "balance": account.get_balance(),
                    "positions": account.get_positions()
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Account query error: {e}")
            raise HTTPException(status_code=500, detail="Account query failed")
    
    # ==================== 에러 핸들러 ====================
    
    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception):
        """내부 서버 에러 핸들러"""
        logger.error(f"Internal server error: {exc}")
        return {"status": "error", "message": "Internal server error"}
    
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):
        """404 에러 핸들러"""
        return {"status": "error", "message": "Resource not found"}
    
    # ==================== 시작 및 종료 이벤트 ====================
    
    @app.on_event("startup")
    async def startup_event():
        """앱 시작 시 실행"""
        logger.info("SignalRouter AutoTrading System started")
        logger.info(f"Portfolio: {auto_trader.get_portfolio_summary()}")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """앱 종료 시 실행"""
        logger.info("SignalRouter AutoTrading System shutting down")
        # 필요시 리소스 정리
        
    return app


# 개발용 직접 실행
if __name__ == "__main__":
    import uvicorn
    
    app = create_app()
    
    # 환경변수 또는 기본값으로 설정
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting server at {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        reload=False  # 운영환경에서는 False
    )