"""
Broker 클래스 테스트
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가 (이게 핵심!)
project_root = Path(__file__).parent.parent  # tests 폴더에서 한 단계 위로
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.trading.broker import Broker


@pytest.fixture
def mock_pykis():
    """PyKis Mock 객체"""
    with patch('src.trading.broker.PyKis') as mock:
        pykis_instance = Mock()
        mock.return_value = pykis_instance
        yield pykis_instance


@pytest.fixture
def broker(mock_pykis):
    """Broker 인스턴스"""
    return Broker("test_account", "test_secret.json", is_virtual=True)


class TestBroker:
    """Broker 클래스 테스트"""
    
    def test_init_broker(self, broker, mock_pykis):
        """브로커 초기화 테스트"""
        assert broker.account_id == "test_account"
        assert broker.is_virtual is True
        assert broker._kis == mock_pykis
    
    def test_buy_market_order(self, broker, mock_pykis):
        """시장가 매수 주문 테스트"""
        # Mock 설정
        mock_stock = Mock()
        mock_order = Mock()
        mock_stock.buy.return_value = mock_order
        mock_pykis.stock.return_value = mock_stock
        
        with patch.object(broker, '_extract_order_id', return_value='order_123'):
            order_id = broker.buy("005930", 10)
        
        mock_stock.buy.assert_called_once_with(qty=10)
        assert order_id == 'order_123'
    
    def test_buy_limit_order(self, broker, mock_pykis):
        """지정가 매수 주문 테스트"""
        # Mock 설정
        mock_stock = Mock()
        mock_order = Mock()
        mock_stock.buy.return_value = mock_order
        mock_pykis.stock.return_value = mock_stock
        
        with patch.object(broker, '_extract_order_id', return_value='order_456'):
            order_id = broker.buy("005930", 10, 75000)
        
        mock_stock.buy.assert_called_once_with(price=75000, qty=10)
        assert order_id == 'order_456'
    
    def test_sell_market_order(self, broker, mock_pykis):
        """시장가 매도 주문 테스트"""
        # Mock 설정
        mock_stock = Mock()
        mock_order = Mock()
        mock_quote = Mock()
        mock_quote.price = 75000
        mock_stock.sell.return_value = mock_order
        mock_stock.quote.return_value = mock_quote
        mock_pykis.stock.return_value = mock_stock
        
        with patch.object(broker, '_extract_order_id', return_value='order_789'):
            order_id = broker.sell("005930", 10)
        
        # 시장가 매도는 현재가 대비 10% 하락가로 주문
        mock_stock.sell.assert_called_once_with(price=67500.0, qty=10)
        assert order_id == 'order_789'
    
    def test_get_positions(self, broker, mock_pykis):
        """포지션 조회 테스트"""
        # Mock 설정
        mock_account = Mock()
        mock_balance = Mock()
        mock_stock = Mock()
        mock_stock.symbol = "005930"
        mock_stock.qty = 10
        mock_stock.price = 75000
        mock_stock.amount = 750000
        mock_stock.profit = 50000
        
        mock_balance.stocks = [mock_stock]
        mock_account.balance.return_value = mock_balance
        mock_pykis.account.return_value = mock_account
        
        positions = broker.get_positions()
        
        assert len(positions) == 1
        assert positions[0]['symbol'] == "005930"
        assert positions[0]['quantity'] == 10
        assert positions[0]['avg_price'] == 75000.0
    
    def test_get_balance(self, broker, mock_pykis):
        """잔고 조회 테스트"""
        # Mock 설정
        mock_account = Mock()
        mock_balance = Mock()
        mock_deposit = Mock()
        mock_deposit.amount = 1000000
        
        mock_balance.deposits = {'KRW': mock_deposit}
        mock_account.balance.return_value = mock_balance
        mock_pykis.account.return_value = mock_account
        
        balance = broker.get_balance()
        
        assert balance['total_balance'] == 1000000.0
        assert balance['currency'] == 'KRW'
    
    def test_get_order_status(self, broker, mock_pykis):
        """주문 상태 조회 테스트"""
        # Mock 설정
        mock_account = Mock()
        mock_pending_orders = Mock()
        mock_order = Mock()
        mock_order.executed_qty = 5
        mock_order.qty = 10
        
        mock_pending_orders.orders = [mock_order]
        mock_account.pending_orders.return_value = mock_pending_orders
        mock_pykis.account.return_value = mock_account
        
        with patch.object(broker, '_extract_order_id', return_value='test_order'):
            status = broker.get_order_status('test_order')
        
        assert status['status'] == 'PENDING'
        assert status['filled_quantity'] == 5
        assert status['remaining_quantity'] == 5
    
    def test_cancel_order(self, broker, mock_pykis):
        """주문 취소 테스트"""
        # Mock 설정
        mock_account = Mock()
        mock_pending_orders = Mock()
        mock_order = Mock()
        mock_pending_orders.orders = [mock_order]
        mock_account.pending_orders.return_value = mock_pending_orders
        mock_pykis.account.return_value = mock_account
        
        with patch.object(broker, '_extract_order_id', return_value='test_order'):
            result = broker.cancel_order('test_order')
        
        mock_order.cancel.assert_called_once()
        assert result is True
    
    def test_get_orderable_amount(self, broker, mock_pykis):
        """매수 가능 금액 조회 테스트"""
        # Mock 설정
        mock_stock = Mock()
        mock_orderable = Mock()
        mock_orderable.qty = 13
        mock_orderable.amount = 975000
        mock_orderable.unit_price = 75000
        
        mock_stock.orderable_amount.return_value = mock_orderable
        mock_pykis.stock.return_value = mock_stock
        
        result = broker.get_orderable_amount("005930", 75000)
        
        assert result['orderable_quantity'] == 13
        assert result['orderable_amount'] == 975000.0
        assert result['unit_price'] == 75000.0