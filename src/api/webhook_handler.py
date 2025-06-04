"""
WebhookHandler - FastAPI 기반 웹훅 수신 및 처리
트레이딩뷰 시그널을 수신하고 AutoTrader로 전달하는 API 핸들러
"""

from fastapi import FastAPI, HTTPException, Request, Response
from typing import Dict, Any
import logging
import json
from datetime import datetime
from ..core import AutoTrader

logger = logging.getLogger(__name__)


class WebhookHandler:
    """웹훅 수신 및 처리 클래스"""
    
    def __init__(self, auto_trader: AutoTrader):
        self.auto_trader = auto_trader
        logger.info("WebhookHandler initialized")
    
    async def receive_signal(self, payload: Dict[str, Any]) -> Response:
        """트레이딩뷰 시그널 수신 및 처리"""
        try:
            # 시그널 페이로드 파싱
            parsed_signal = self._parse_signal_payload(payload)
            
            # 웹훅 토큰 검증
            webhook_token = parsed_signal.get('webhook_token')
            if not self.validate_webhook_token(webhook_token):
                logger.error(f"Invalid webhook token: {webhook_token}")
                raise HTTPException(status_code=401, detail="Invalid webhook token")
            
            # 시그널 처리
            success = self.auto_trader.process_signal(parsed_signal)
            
            if success:
                logger.info(f"Signal processed successfully: {parsed_signal.get('symbol')}")
                return Response(
                    content=json.dumps({
                        "status": "success", 
                        "message": "Signal processed",
                        "timestamp": datetime.now().isoformat()
                    }),
                    status_code=200,
                    media_type="application/json"
                )
            else:
                logger.error(f"Signal processing failed: {parsed_signal}")
                return Response(
                    content=json.dumps({
                        "status": "error",
                        "message": "Signal processing failed",
                        "timestamp": datetime.now().isoformat()
                    }),
                    status_code=400,
                    media_type="application/json"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    async def health_check(self) -> Response:
        """서버 상태 확인"""
        try:
            # AutoTrader 상태 확인
            portfolio_summary = self.auto_trader.get_portfolio_summary()
            
            health_data = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "active_accounts": portfolio_summary.get('active_accounts', 0),
                "emergency_stop": self.auto_trader._emergency_stop
            }
            
            return Response(
                content=json.dumps(health_data),
                status_code=200,
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Response(
                content=json.dumps({
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }),
                status_code=503,
                media_type="application/json"
            )
    
    def validate_webhook_token(self, token: str) -> bool:
        """웹훅 토큰 유효성 검증"""
        if not token:
            return False
        
        try:
            # ConfigLoader를 통해 유효한 토큰인지 확인
            strategy_config = self.auto_trader.config.get_strategy_by_token(token)
            return strategy_config is not None and strategy_config.is_active
            
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False
    
    def _parse_signal_payload(self, payload: Dict) -> Dict:
        """시그널 페이로드 파싱 및 검증"""
        try:
            # 필수 필드 확인
            required_fields = ['strategy', 'symbol', 'action', 'quantity', 'webhook_token']
            missing_fields = [field for field in required_fields if field not in payload]
            
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # 데이터 타입 변환 및 정규화
            parsed = {
                'strategy': str(payload['strategy']).strip(),
                'symbol': str(payload['symbol']).strip().upper(),
                'action': str(payload['action']).strip().upper(),
                'quantity': int(payload['quantity']),
                'webhook_token': str(payload['webhook_token']).strip(),
                'timestamp': datetime.now().isoformat()
            }
            
            # 선택적 필드
            if 'price' in payload and payload['price'] is not None:
                parsed['price'] = float(payload['price'])
            
            # 액션 검증
            if parsed['action'] not in ['BUY', 'SELL']:
                raise ValueError(f"Invalid action: {parsed['action']}")
            
            # 수량 검증
            if parsed['quantity'] <= 0:
                raise ValueError(f"Invalid quantity: {parsed['quantity']}")
            
            return parsed
            
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Signal parsing error: {e}")
            raise ValueError(f"Invalid signal format: {e}")
    
    async def emergency_stop(self) -> Response:
        """비상 정지 엔드포인트"""
        try:
            self.auto_trader.emergency_stop_all()
            
            return Response(
                content=json.dumps({
                    "status": "emergency_stop_activated",
                    "message": "All trading halted",
                    "timestamp": datetime.now().isoformat()
                }),
                status_code=200,
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}")
            raise HTTPException(status_code=500, detail="Emergency stop failed")
    
    async def resume_trading(self) -> Response:
        """거래 재개 엔드포인트"""
        try:
            self.auto_trader.resume_trading()
            
            return Response(
                content=json.dumps({
                    "status": "trading_resumed",
                    "message": "Trading operations resumed",
                    "timestamp": datetime.now().isoformat()
                }),
                status_code=200,
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error(f"Resume trading failed: {e}")
            raise HTTPException(status_code=500, detail="Resume trading failed")