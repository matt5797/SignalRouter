"""
Account 및 TradeExecutor 클래스 통합 테스트
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가 (이게 핵심!)
project_root = Path(__file__).parent.parent  # tests 폴더에서 한 단계 위로
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from src.trading.account import Account, AccountType
from src.trading.trade_executor import TradeExecutor
from src.models import TradeOrder, TransitionType


@pytest.fixture
def mock_broker():
    """Broker Mock 객체"""
    broker = Mock()
    broker.get_balance.return_value = {
        'total_balance': 1000000.0,
        'available_balance': 900000.0, 
        'currency': 'KRW'
    }
    broker.get_positions.return_value = [
        {
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0,
            'current_value': 750000.0,
            'unrealized_pnl': 50000.0
        }
    ]
    return broker


@pytest.fixture  
def account(mock_broker):
    """Account 인스턴스"""
    with patch('src.trading.account.Broker', return_value=mock_broker):
        return Account(
            account_id="test_account",
            name="테스트 계좌",
            account_type=AccountType.STOCK,
            secret_file_path="test_secret.json",
            is_virtual=True
        )


@pytest.fixture
def mock_db():
    """TradingDB Mock 객체"""
    db = Mock()
    db.get_strategy_by_token.return_value = {
        'id': 1,
        'name': 'TEST_STRATEGY',
        'max_position_ratio': 0.2,
        'max_daily_loss': 500000
    }
    db.get_position.return_value = {
        'account_id': 'test_account',
        'symbol': '005930',
        'quantity': 0,
        'avg_price': 0
    }
    db.save_trade.return_value = 1
    db.get_daily_pnl.return_value = -100000
    return db


@pytest.fixture
def trade_executor(mock_db):
    """TradeExecutor 인스턴스"""
    return TradeExecutor(mock_db)


class TestAccount:
    """Account 클래스 테스트"""
    
    def test_init_account(self, account):
        """계좌 초기화 테스트"""
        assert account.account_id == "test_account"
        assert account.name == "테스트 계좌"
        assert account.account_type == AccountType.STOCK
        assert account.is_virtual is True
        assert account.is_active is True
    
    def test_get_balance(self, account, mock_broker):
        """잔고 조회 테스트"""
        balance = account.get_balance()
        
        assert balance['total_balance'] == 1000000.0
        assert balance['available_balance'] == 900000.0
        assert balance['currency'] == 'KRW'
        mock_broker.get_balance.assert_called_once()
    
    def test_get_positions(self, account, mock_broker):
        """포지션 조회 테스트"""
        positions = account.get_positions()
        
        assert len(positions) == 1
        assert positions[0]['symbol'] == '005930'
        assert positions[0]['quantity'] == 10
        mock_broker.get_positions.assert_called_once()
    
    def test_can_trade_sufficient_balance(self, account):
        """거래 가능 - 충분한 잔고"""
        result = account.can_trade(500000.0)
        assert result is True
    
    def test_can_trade_insufficient_balance(self, account):
        """거래 불가 - 부족한 잔고"""
        result = account.can_trade(1000000.0)
        assert result is False
    
    def test_can_trade_inactive_account(self, account):
        """거래 불가 - 비활성 계좌"""
        account.is_active = False
        result = account.can_trade(100000.0)
        assert result is False
    
    def test_get_position_for_symbol_existing(self, account):
        """기존 포지션 조회"""
        position = account.get_position_for_symbol('005930')
        
        assert position['symbol'] == '005930'
        assert position['quantity'] == 10
        assert position['avg_price'] == 75000.0
    
    def test_get_position_for_symbol_not_existing(self, account):
        """존재하지 않는 포지션 조회"""
        position = account.get_position_for_symbol('000660')
        
        assert position['symbol'] == '000660'
        assert position['quantity'] == 0
        assert position['avg_price'] == 0.0
    
    def test_get_total_portfolio_value(self, account):
        """총 포트폴리오 가치 계산"""
        total_value = account.get_total_portfolio_value()
        
        # 현금(1,000,000) + 포지션 가치(750,000) = 1,750,000
        assert total_value == 1750000.0
    
    def test_get_total_unrealized_pnl(self, account):
        """총 미실현 손익 계산"""
        pnl = account.get_total_unrealized_pnl()
        assert pnl == 50000.0
    
    def test_account_types(self, account):
        """계좌 유형 확인"""
        assert account.is_stock_account() is True
        assert account.is_futures_account() is False


class TestTradeExecutor:
    """TradeExecutor 클래스 테스트"""
    
    def test_init_trade_executor(self, trade_executor, mock_db):
        """TradeExecutor 초기화 테스트"""
        assert trade_executor.db == mock_db
    
    def test_calculate_transition_type_entry(self, trade_executor):
        """포지션 전환 타입 - 신규 진입"""
        current_position = {'quantity': 0}
        signal_data = {'action': 'BUY'}
        
        transition_type = trade_executor._calculate_transition_type(current_position, signal_data)
        assert transition_type == TransitionType.ENTRY
    
    def test_calculate_transition_type_exit_long(self, trade_executor):
        """포지션 전환 타입 - 롱 포지션 청산"""
        current_position = {'quantity': 10}
        signal_data = {'action': 'SELL'}
        
        transition_type = trade_executor._calculate_transition_type(current_position, signal_data)
        assert transition_type == TransitionType.EXIT
    
    def test_calculate_transition_type_exit_short(self, trade_executor):
        """포지션 전환 타입 - 숏 포지션 청산"""
        current_position = {'quantity': -10}
        signal_data = {'action': 'BUY'}
        
        transition_type = trade_executor._calculate_transition_type(current_position, signal_data)
        assert transition_type == TransitionType.EXIT
    
    def test_check_position_limit_pass(self, trade_executor, account):
        """포지션 한도 체크 - 통과"""
        # 총 포트폴리오 1,750,000원 중 300,000원 투자 (약 17%)
        result = trade_executor.check_position_limit(account, '005930', 300000.0)
        assert result is True
    
    def test_check_position_limit_fail(self, trade_executor, account):
        """포지션 한도 체크 - 실패"""
        # 총 포트폴리오 1,750,000원 중 600,000원 투자 (약 34% > 30% 제한)
        result = trade_executor.check_position_limit(account, '005930', 600000.0)
        assert result is False
    
    def test_check_daily_loss_limit_pass(self, trade_executor, mock_db):
        """일일 손실 한도 체크 - 통과"""
        mock_db.get_daily_pnl.return_value = -100000  # 10만원 손실
        
        result = trade_executor.check_daily_loss_limit('test_account', 100000.0)
        assert result is True
    
    def test_check_daily_loss_limit_fail(self, trade_executor, mock_db):
        """일일 손실 한도 체크 - 실패"""
        mock_db.get_daily_pnl.return_value = -600000  # 60만원 손실 (50만원 제한 초과)
        
        result = trade_executor.check_daily_loss_limit('test_account', 100000.0)
        assert result is False
    
    def test_calculate_position_size(self, trade_executor, account, mock_broker):
        """포지션 크기 계산"""
        mock_broker.get_orderable_amount.return_value = {
            'orderable_quantity': 12,
            'orderable_amount': 900000.0,
            'unit_price': 75000.0
        }
        
        quantity = trade_executor.calculate_position_size(account, '005930', 0.5)
        
        # 90만원의 50% = 45만원 / 75,000원 = 6주
        assert quantity == 6
    
    def test_place_order_buy(self, trade_executor, account, mock_broker):
        """매수 주문 실행"""
        mock_broker.buy.return_value = 'order_123'
        
        order_data = {
            'symbol': '005930',
            'action': 'BUY',
            'quantity': 10,
            'price': 75000
        }
        
        order_id = trade_executor.place_order(account, order_data)
        
        assert order_id == 'order_123'
        mock_broker.buy.assert_called_once_with(
            symbol='005930',
            quantity=10,
            price=75000
        )
    
    def test_place_order_sell(self, trade_executor, account, mock_broker):
        """매도 주문 실행"""
        mock_broker.sell.return_value = 'order_456'
        
        order_data = {
            'symbol': '005930',
            'action': 'SELL',
            'quantity': 5,
            'price': None
        }
        
        order_id = trade_executor.place_order(account, order_data)
        
        assert order_id == 'order_456'
        mock_broker.sell.assert_called_once_with(
            symbol='005930',
            quantity=5,
            price=None
        )
    
    def test_wait_for_fill_success(self, trade_executor, account, mock_broker):
        """주문 체결 대기 - 성공"""
        mock_broker.get_order_status.return_value = {'status': 'FILLED'}
        
        result = trade_executor.wait_for_fill(account, 'order_123', timeout_seconds=5)
        assert result is True
    
    def test_wait_for_fill_failed(self, trade_executor, account, mock_broker):
        """주문 체결 대기 - 실패"""
        mock_broker.get_order_status.return_value = {'status': 'FAILED'}
        
        result = trade_executor.wait_for_fill(account, 'order_123', timeout_seconds=5)
        assert result is False
    
    @patch('time.sleep')
    @patch('time.time')
    def test_wait_for_fill_timeout(self, mock_time, mock_sleep, trade_executor, account, mock_broker):
        """주문 체결 대기 - 타임아웃"""
        mock_time.side_effect = [0, 70]  # 시작 시간과 70초 후
        mock_broker.get_order_status.return_value = {'status': 'PENDING'}
        
        result = trade_executor.wait_for_fill(account, 'order_123', timeout_seconds=60)
        assert result is False