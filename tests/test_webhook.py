"""
WebhookHandler 및 FastAPI 앱 테스트
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from src.api.main import create_app
from src.api.webhook_handler import WebhookHandler
from src.core.auto_trader import AutoTrader


@pytest.fixture
def mock_auto_trader():
    """AutoTrader Mock 객체"""
    mock = Mock(spec=AutoTrader)
    mock._emergency_stop = False
    mock.config = Mock()
    mock.get_portfolio_summary.return_value = {
        'active_accounts': 2,
        'total_portfolio_value': 1000000
    }
    return mock


@pytest.fixture
def webhook_handler(mock_auto_trader):
    """WebhookHandler 인스턴스"""
    return WebhookHandler(mock_auto_trader)


@pytest.fixture 
def test_client():
    """FastAPI 테스트 클라이언트"""
    with patch('src.core.auto_trader.AutoTrader') as mock_trader_class:
        mock_trader = Mock()
        mock_trader._emergency_stop = False
        mock_trader.get_portfolio_summary.return_value = {'active_accounts': 1}
        mock_trader.get_all_positions.return_value = {}
        mock_trader_class.return_value = mock_trader
        
        app = create_app()
        return TestClient(app)


class TestWebhookHandler:
    """WebhookHandler 클래스 테스트"""
    
    def test_validate_webhook_token_valid(self, webhook_handler, mock_auto_trader):
        """유효한 웹훅 토큰 검증"""
        # Mock 설정
        mock_strategy = Mock()
        mock_strategy.is_active = True
        mock_auto_trader.config.get_strategy_by_token.return_value = mock_strategy
        
        result = webhook_handler.validate_webhook_token("valid_token")
        assert result is True
    
    def test_validate_webhook_token_invalid(self, webhook_handler, mock_auto_trader):
        """유효하지 않은 웹훅 토큰 검증"""
        mock_auto_trader.config.get_strategy_by_token.return_value = None
        
        result = webhook_handler.validate_webhook_token("invalid_token")
        assert result is False
    
    def test_parse_signal_payload_valid(self, webhook_handler):
        """유효한 시그널 페이로드 파싱"""
        payload = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'aapl',
            'action': 'buy',
            'quantity': 10,
            'webhook_token': 'test_token',
            'price': 150.50
        }
        
        result = webhook_handler._parse_signal_payload(payload)
        
        assert result['strategy'] == 'TEST_STRATEGY'
        assert result['symbol'] == 'AAPL'
        assert result['action'] == 'BUY'
        assert result['quantity'] == 10
        assert result['price'] == 150.50
    
    def test_parse_signal_payload_missing_fields(self, webhook_handler):
        """필수 필드 누락된 시그널 페이로드 파싱"""
        payload = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL'
            # action, quantity, webhook_token 누락
        }
        
        with pytest.raises(ValueError, match="Missing required fields"):
            webhook_handler._parse_signal_payload(payload)
    
    def test_parse_signal_payload_invalid_action(self, webhook_handler):
        """유효하지 않은 액션으로 시그널 파싱"""
        payload = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'INVALID',
            'quantity': 10,
            'webhook_token': 'test_token'
        }
        
        with pytest.raises(ValueError, match="Invalid action"):
            webhook_handler._parse_signal_payload(payload)
    
    @pytest.mark.asyncio
    async def test_receive_signal_success(self, webhook_handler, mock_auto_trader):
        """성공적인 시그널 수신 테스트"""
        # Mock 설정
        mock_strategy = Mock()
        mock_strategy.is_active = True
        mock_auto_trader.config.get_strategy_by_token.return_value = mock_strategy
        mock_auto_trader.process_signal.return_value = True
        
        payload = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'webhook_token': 'valid_token'
        }
        
        response = await webhook_handler.receive_signal(payload)
        
        assert response.status_code == 200
        mock_auto_trader.process_signal.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check(self, webhook_handler, mock_auto_trader):
        """헬스 체크 테스트"""
        response = await webhook_handler.health_check()
        
        assert response.status_code == 200
        mock_auto_trader.get_portfolio_summary.assert_called_once()


class TestFastAPIApp:
    """FastAPI 앱 엔드포인트 테스트"""
    
    def test_health_endpoint(self, test_client):
        """헬스 체크 엔드포인트"""
        response = test_client.get("/health")
        assert response.status_code == 200
    
    def test_webhook_signal_endpoint(self, test_client):
        """웹훅 시그널 엔드포인트"""
        with patch.object(test_client.app.state.webhook_handler, 'receive_signal') as mock_receive:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_receive.return_value = mock_response
            
            payload = {
                'strategy': 'TEST_STRATEGY',
                'symbol': 'AAPL',
                'action': 'BUY',
                'quantity': 10,
                'webhook_token': 'test_token'
            }
            
            response = test_client.post("/webhook/signal", json=payload)
            assert response.status_code == 200
    
    def test_portfolio_endpoint(self, test_client):
        """포트폴리오 엔드포인트"""
        response = test_client.get("/portfolio")
        assert response.status_code == 200
        assert "data" in response.json()
    
    def test_positions_endpoint(self, test_client):
        """포지션 조회 엔드포인트"""
        response = test_client.get("/positions")
        assert response.status_code == 200
        assert "data" in response.json()
    
    def test_emergency_stop_endpoint(self, test_client):
        """비상 정지 엔드포인트"""
        response = test_client.post("/emergency-stop")
        assert response.status_code == 200
    
    def test_resume_trading_endpoint(self, test_client):
        """거래 재개 엔드포인트"""
        response = test_client.post("/resume-trading")
        assert response.status_code == 200
    
    def test_account_info_endpoint(self, test_client):
        """계좌 정보 엔드포인트"""
        with patch.object(test_client.app.state.auto_trader, 'get_account') as mock_get_account:
            mock_account = Mock()
            mock_account.to_dict.return_value = {'account_id': 'test_account'}
            mock_account.get_balance.return_value = {'total_balance': 1000000}
            mock_account.get_positions.return_value = []
            mock_get_account.return_value = mock_account
            
            response = test_client.get("/accounts/test_account")
            assert response.status_code == 200
            assert "data" in response.json()
    
    def test_account_not_found(self, test_client):
        """존재하지 않는 계좌 조회"""
        with patch.object(test_client.app.state.auto_trader, 'get_account') as mock_get_account:
            mock_get_account.return_value = None
            
            response = test_client.get("/accounts/nonexistent")
            assert response.status_code == 404