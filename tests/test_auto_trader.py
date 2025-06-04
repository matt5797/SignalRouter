"""
AutoTrader 클래스 테스트
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.core.auto_trader import AutoTrader
from src.trading import Account, AccountType


@pytest.fixture
def mock_config_loader():
    """ConfigLoader Mock 객체"""
    mock = Mock()
    mock.get_database_config.return_value = {'path': ':memory:'}
    mock.get_all_accounts.return_value = {
        'test_account': Mock(
            account_id='test_account',
            name='Test Account',
            type='STOCK',
            secret_file='test.json',
            is_virtual=True,
            is_active=True
        )
    }
    mock.get_strategy_by_token.return_value = Mock(
        name='TEST_STRATEGY',
        account_id='test_account',
        is_active=True
    )
    return mock


@pytest.fixture
def mock_trading_db():
    """TradingDB Mock 객체"""
    mock = Mock()
    mock.get_strategy_by_token.return_value = {
        'id': 1,
        'name': 'TEST_STRATEGY',
        'account_id': 'test_account',
        'is_active': True
    }
    return mock


@pytest.fixture
def auto_trader():
    """AutoTrader 인스턴스 (Mock 의존성 포함)"""
    with patch('src.core.auto_trader.ConfigLoader') as mock_config_class, \
         patch('src.core.auto_trader.TradingDB') as mock_db_class, \
         patch('src.core.auto_trader.PositionManager') as mock_pm_class, \
         patch('src.core.auto_trader.TradeExecutor') as mock_te_class, \
         patch('src.core.auto_trader.Account') as mock_account_class:
        
        # Mock 설정 - config.yaml 참고
        mock_config = Mock()
        mock_config.get_database_config.return_value = {'path': ':memory:'}
        mock_config.get_all_accounts.return_value = {
            'stock_virtual_01': Mock(
                account_id='stock_virtual_01',
                name='주식 모의 계좌',
                type='STOCK',
                secret_file='secrets/stock_virtual_01.json',
                is_virtual=True,
                is_active=True
            )
        }
        # 전략 설정 - config.yaml의 TEST_STRATEGY 참고
        def mock_get_strategy_by_token(token):
            if token == 'webhook_token_3':
                return Mock(
                    name='TEST_STRATEGY',
                    account_id='stock_virtual_01',
                    is_active=True
                )
            return None
        
        mock_config.get_strategy_by_token.side_effect = mock_get_strategy_by_token
        mock_config_class.return_value = mock_config
        
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        
        mock_pm = Mock()
        mock_pm_class.return_value = mock_pm
        
        mock_te = Mock()
        mock_te_class.return_value = mock_te
        
        # 실제 계정과 일치하는 mock 계정
        mock_account = Mock()
        mock_account.account_id = 'stock_virtual_01'
        mock_account.name = '주식 모의 계좌'
        mock_account.account_type.value = 'STOCK'
        mock_account.is_active = True
        mock_account_class.return_value = mock_account
        
        trader = AutoTrader()
        trader.accounts = {'stock_virtual_01': mock_account}
        
        return trader


class TestAutoTrader:
    """AutoTrader 클래스 테스트"""
    
    def test_init_auto_trader(self, auto_trader):
        """AutoTrader 초기화 테스트"""
        assert auto_trader is not None
        assert hasattr(auto_trader, 'config')
        assert hasattr(auto_trader, 'db')
        assert hasattr(auto_trader, 'position_manager')
        assert hasattr(auto_trader, 'trade_executor')
        assert hasattr(auto_trader, 'accounts')
    
    def test_get_account_exists(self, auto_trader):
        """존재하는 계좌 조회"""
        account = auto_trader.get_account('stock_virtual_01')
        assert account is not None
        assert account.account_id == 'stock_virtual_01'
    
    def test_get_account_not_exists(self, auto_trader):
        """존재하지 않는 계좌 조회"""
        account = auto_trader.get_account('nonexistent')
        assert account is None
    
    def test_get_all_positions(self, auto_trader):
        """모든 포지션 조회"""
        # Mock 계좌 설정
        mock_account = auto_trader.accounts['stock_virtual_01']
        mock_account.get_positions.return_value = [
            {'symbol': 'AAPL', 'quantity': 10, 'avg_price': 150.0}
        ]
        
        positions = auto_trader.get_all_positions()
        
        assert 'stock_virtual_01' in positions
        assert len(positions['stock_virtual_01']) == 1
    
    def test_get_portfolio_summary(self, auto_trader):
        """포트폴리오 요약 조회"""
        # Mock 계좌 설정
        mock_account = auto_trader.accounts['stock_virtual_01']
        mock_account.get_total_portfolio_value.return_value = 1000000.0
        mock_account.get_total_unrealized_pnl.return_value = 50000.0
        mock_account.get_positions.return_value = [{'symbol': 'AAPL'}]
        mock_account.name = '주식 모의 계좌'
        mock_account.account_type.value = 'STOCK'
        
        summary = auto_trader.get_portfolio_summary()
        
        assert summary['total_accounts'] == 1
        assert summary['active_accounts'] == 1
        assert summary['total_portfolio_value'] == 1000000.0
        assert summary['total_unrealized_pnl'] == 50000.0
        assert 'stock_virtual_01' in summary['accounts_detail']
    
    def test_emergency_stop_all(self, auto_trader):
        """비상 정지 테스트"""
        auto_trader.emergency_stop_all()
        
        assert auto_trader._emergency_stop is True
        assert auto_trader.accounts['stock_virtual_01'].is_active is False
    
    def test_resume_trading(self, auto_trader):
        """거래 재개 테스트"""
        # 먼저 비상 정지 상태로 만들기
        auto_trader._emergency_stop = True
        auto_trader.accounts['stock_virtual_01'].is_active = False
        
        # 거래 재개
        auto_trader.resume_trading()
        
        assert auto_trader._emergency_stop is False
        # 계좌 활성화는 설정에 따라 결정됨
    
    def test_process_signal_emergency_stop(self, auto_trader):
        """비상 정지 상태에서 시그널 처리"""
        auto_trader._emergency_stop = True
        
        signal_data = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'webhook_token': 'test_token'
        }
        
        result = auto_trader.process_signal(signal_data)
        assert result is False
    
    def test_process_signal_invalid(self, auto_trader):
        """유효하지 않은 시그널 처리"""
        signal_data = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'INVALID_ACTION',  # 유효하지 않은 액션
            'quantity': 10,
            'webhook_token': 'test_token'
        }
        
        result = auto_trader.process_signal(signal_data)
        assert result is False
    
    def test_process_signal_success(self, auto_trader):
        """성공적인 시그널 처리"""
        # Mock 설정
        auto_trader.trade_executor.execute_signal.return_value = True
        
        signal_data = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'webhook_token': 'webhook_token_3'  # config.yaml의 TEST_STRATEGY 토큰
        }
        
        result = auto_trader.process_signal(signal_data)
        assert result is True
        auto_trader.trade_executor.execute_signal.assert_called_once()
    
    def test_route_signal_to_account_no_token(self, auto_trader):
        """토큰 없는 시그널 라우팅"""
        signal_data = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'BUY',
            'quantity': 10
        }
        
        account = auto_trader._route_signal_to_account(signal_data)
        assert account is None
    
    def test_route_signal_to_account_invalid_token(self, auto_trader):
        """유효하지 않은 토큰으로 시그널 라우팅"""
        auto_trader.config.get_strategy_by_token.return_value = None
        
        signal_data = {
            'webhook_token': 'invalid_token'
        }
        
        account = auto_trader._route_signal_to_account(signal_data)
        assert account is None
    
    def test_route_signal_to_account_inactive_strategy(self, auto_trader):
        """비활성화된 전략으로 시그널 라우팅"""
        mock_strategy = Mock()
        mock_strategy.is_active = False
        auto_trader.config.get_strategy_by_token.return_value = mock_strategy
        
        signal_data = {
            'webhook_token': 'test_token'
        }
        
        account = auto_trader._route_signal_to_account(signal_data)
        assert account is None
    
    def test_route_signal_to_account_success(self, auto_trader):
        """성공적인 시그널 라우팅"""
        mock_strategy = Mock()
        mock_strategy.is_active = True
        mock_strategy.account_id = 'stock_virtual_01'
        auto_trader.config.get_strategy_by_token.return_value = mock_strategy
        
        signal_data = {
            'webhook_token': 'webhook_token_3'
        }
        
        account = auto_trader._route_signal_to_account(signal_data)
        assert account is not None
        assert account.account_id == 'stock_virtual_01'