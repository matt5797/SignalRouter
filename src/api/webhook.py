from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime

from ..core.executor import SignalExecutor
from ..models.signal import Signal

logger = logging.getLogger(__name__)


def create_app(config_path: str = "config/config.yaml") -> FastAPI:
    app = FastAPI(
        title="Signal Executor",
        description="Simple webhook receiver for TradingView signals",
        version="2.0.0"
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    executor = SignalExecutor(config_path)
    app.state.executor = executor
    
    @app.post("/webhook")
    async def receive_signal(request: Request):
        try:
            payload = await request.json()
            logger.info(f"Webhook received: {payload}")
            
            signal = Signal.from_webhook(payload)
            result = executor.execute(signal)
            
            if result.success:
                return {
                    "status": "ok",
                    "order_id": result.order_id,
                    "filled": result.filled,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "error",
                        "message": result.error,
                        "order_id": result.order_id,
                        "timestamp": datetime.now().isoformat()
                    }
                )
        
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/health")
    async def health_check():
        status = executor.get_status()
        return {
            "status": "healthy" if not status['emergency_stop'] else "stopped",
            "timestamp": datetime.now().isoformat(),
            **status
        }
    
    @app.post("/emergency-stop")
    async def emergency_stop():
        executor.emergency_stop()
        return {
            "status": "stopped",
            "message": "Emergency stop activated",
            "timestamp": datetime.now().isoformat()
        }
    
    @app.post("/resume")
    async def resume_trading():
        executor.resume()
        return {
            "status": "resumed",
            "message": "Trading resumed",
            "timestamp": datetime.now().isoformat()
        }
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("Signal Executor API started")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Signal Executor API shutting down")
    
    return app


if __name__ == "__main__":
    import uvicorn
    import os
    
    app = create_app()
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting server at {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")