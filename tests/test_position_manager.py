"""
PositionManager 클래스 테스트
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.trading.position_manager import PositionManager
from src.models import TransitionType


@pytest.fixture
def mock_db():
    """TradingDB Mock 객체"""
    db = Mock()
    return db


@pytest.fixture
def position_manager(mock_db):
    """PositionManager 인스턴스"""
    return PositionManager(mock_db)


class TestPositionManager:
    """PositionManager 클래스 테스트"""
    
    def test_init_position_manager(self, position_manager, mock_db):
        """PositionManager 초기화 테스트"""
        assert position_manager.db == mock_db
    
    def test_get_current_position_existing(self, position_manager, mock_db):
        """기존 포지션 조회 테스트"""
        # Mock 설정
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0,
            'last_updated': datetime.now().isoformat()
        }
        
        position = position_manager.get_current_position('test_account', '005930')
        
        assert position['symbol'] == '005930'
        assert position['quantity'] == 10
        assert position['avg_price'] == 75000.0
        assert position['position_type'] == 'LONG'
    
    def test_get_current_position_flat(self, position_manager, mock_db):
        """플랫 포지션 조회 테스트"""
        # Mock 설정 - 수량이 0인 포지션
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 0,
            'avg_price': 0.0
        }
        
        position = position_manager.get_current_position('test_account', '005930')
        
        assert position['symbol'] == '005930'
        assert position['quantity'] == 0
        assert position['position_type'] == 'FLAT'
    
    def test_calculate_transition_type_entry_from_flat(self, position_manager):
        """전환 타입 계산 - 플랫에서 진입"""
        current = {'quantity': 0}
        target = {'action': 'BUY', 'quantity': 10}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.ENTRY
    
    def test_calculate_transition_type_exit_long_partial(self, position_manager):
        """전환 타입 계산 - 롱 포지션 부분 청산"""
        current = {'quantity': 10}
        target = {'action': 'SELL', 'quantity': 5}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.EXIT
    
    def test_calculate_transition_type_exit_long_full(self, position_manager):
        """전환 타입 계산 - 롱 포지션 전량 청산"""
        current = {'quantity': 10}
        target = {'action': 'SELL', 'quantity': 10}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.EXIT
    
    def test_calculate_transition_type_reverse_long_to_short(self, position_manager):
        """전환 타입 계산 - 롱에서 숏으로 역전"""
        current = {'quantity': 10}
        target = {'action': 'SELL', 'quantity': 15}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.REVERSE
    
    def test_calculate_transition_type_entry_add_long(self, position_manager):
        """전환 타입 계산 - 롱 포지션 추가 매수"""
        current = {'quantity': 10}
        target = {'action': 'BUY', 'quantity': 5}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.ENTRY
    
    def test_calculate_transition_type_exit_short_partial(self, position_manager):
        """전환 타입 계산 - 숏 포지션 부분 청산"""
        current = {'quantity': -10}
        target = {'action': 'BUY', 'quantity': 5}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.EXIT
    
    def test_calculate_transition_type_reverse_short_to_long(self, position_manager):
        """전환 타입 계산 - 숏에서 롱으로 역전"""
        current = {'quantity': -10}
        target = {'action': 'BUY', 'quantity': 15}
        
        transition_type = position_manager.calculate_transition_type(current, target)
        assert transition_type == TransitionType.REVERSE
    
    def test_update_position_after_trade_new_buy(self, position_manager, mock_db):
        """거래 후 포지션 업데이트 - 신규 매수"""
        # Mock 설정 - 기존 포지션 없음
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 0,
            'avg_price': 0.0
        }
        
        trade_data = {
            'account_id': 'test_account',
            'symbol': '005930',
            'action': 'BUY',
            'filled_quantity': 10,
            'avg_fill_price': 75000.0
        }
        
        position_manager.update_position_after_trade(trade_data)
        
        mock_db.update_position.assert_called_once_with(
            'test_account', '005930', 10, 75000.0
        )
    
    def test_update_position_after_trade_add_to_long(self, position_manager, mock_db):
        """거래 후 포지션 업데이트 - 롱 포지션 추가"""
        # Mock 설정 - 기존 롱 포지션
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 70000.0
        }
        
        trade_data = {
            'account_id': 'test_account',
            'symbol': '005930',
            'action': 'BUY',
            'filled_quantity': 5,
            'avg_fill_price': 80000.0
        }
        
        position_manager.update_position_after_trade(trade_data)
        
        # 평균 단가: (10*70000 + 5*80000) / 15 = 73333.33
        expected_avg_price = (10 * 70000 + 5 * 80000) / 15
        mock_db.update_position.assert_called_once_with(
            'test_account', '005930', 15, expected_avg_price
        )
    
    def test_update_position_after_trade_partial_sell(self, position_manager, mock_db):
        """거래 후 포지션 업데이트 - 부분 매도"""
        # Mock 설정 - 기존 롱 포지션
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0
        }
        
        trade_data = {
            'account_id': 'test_account',
            'symbol': '005930',
            'action': 'SELL',
            'filled_quantity': 3,
            'avg_fill_price': 80000.0
        }
        
        position_manager.update_position_after_trade(trade_data)
        
        # 부분 매도 시 기존 평균가 유지
        mock_db.update_position.assert_called_once_with(
            'test_account', '005930', 7, 75000.0
        )
    
    def test_update_position_after_trade_full_close(self, position_manager, mock_db):
        """거래 후 포지션 업데이트 - 전량 청산"""
        # Mock 설정 - 기존 롱 포지션
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0
        }
        
        trade_data = {
            'account_id': 'test_account',
            'symbol': '005930',
            'action': 'SELL',
            'filled_quantity': 10,
            'avg_fill_price': 80000.0
        }
        
        position_manager.update_position_after_trade(trade_data)
        
        # 전량 청산 시 수량 0, 평균가 0
        mock_db.update_position.assert_called_once_with(
            'test_account', '005930', 0, 0.0
        )
    
    def test_get_portfolio_summary(self, position_manager, mock_db):
        """포트폴리오 요약 조회 테스트"""
        # Mock 설정
        mock_db.get_all_positions.return_value = [
            {
                'account_id': 'test_account',
                'symbol': '005930',
                'quantity': 10,
                'avg_price': 75000.0
            },
            {
                'account_id': 'test_account',
                'symbol': '000660',
                'quantity': -5,
                'avg_price': 180000.0
            }
        ]
        
        summary = position_manager.get_portfolio_summary('test_account')
        
        assert summary['account_id'] == 'test_account'
        assert summary['total_positions'] == 2
        assert summary['long_positions'] == 1
        assert summary['short_positions'] == 1
        assert '005930' in summary['symbols']
        assert '000660' in summary['symbols']
        
        # 총 시장 가치: (10 * 75000) + (5 * 180000) = 1,650,000
        expected_market_value = (10 * 75000) + (5 * 180000)
        assert summary['total_market_value'] == expected_market_value
    
    def test_get_position_exposure_long(self, position_manager, mock_db):
        """포지션 익스포저 조회 - 롱 포지션"""
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0
        }
        
        exposure = position_manager.get_position_exposure('test_account', '005930')
        
        assert exposure['symbol'] == '005930'
        assert exposure['exposure'] == 750000.0  # 10 * 75000
        assert exposure['direction'] == 'LONG'
        assert exposure['quantity'] == 10
    
    def test_get_position_exposure_short(self, position_manager, mock_db):
        """포지션 익스포저 조회 - 숏 포지션"""
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '000660',
            'quantity': -5,
            'avg_price': 180000.0
        }
        
        exposure = position_manager.get_position_exposure('test_account', '000660')
        
        assert exposure['symbol'] == '000660'
        assert exposure['exposure'] == 900000.0  # 5 * 180000
        assert exposure['direction'] == 'SHORT'
        assert exposure['quantity'] == -5
    
    def test_get_position_exposure_flat(self, position_manager, mock_db):
        """포지션 익스포저 조회 - 플랫 포지션"""
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 0,
            'avg_price': 0.0
        }
        
        exposure = position_manager.get_position_exposure('test_account', '005930')
        
        assert exposure['symbol'] == '005930'
        assert exposure['exposure'] == 0.0
        assert exposure['direction'] == 'FLAT'
        assert exposure['quantity'] == 0
    
    def test_is_position_flat_true(self, position_manager, mock_db):
        """포지션 플랫 상태 확인 - True"""
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 0,
            'avg_price': 0.0
        }
        
        is_flat = position_manager.is_position_flat('test_account', '005930')
        assert is_flat is True
    
    def test_is_position_flat_false(self, position_manager, mock_db):
        """포지션 플랫 상태 확인 - False"""
        mock_db.get_position.return_value = {
            'account_id': 'test_account',
            'symbol': '005930',
            'quantity': 10,
            'avg_price': 75000.0
        }
        
        is_flat = position_manager.is_position_flat('test_account', '005930')
        assert is_flat is False
    
    def test_get_total_exposure(self, position_manager, mock_db):
        """총 익스포저 계산 테스트"""
        mock_db.get_all_positions.return_value = [
            {
                'account_id': 'test_account',
                'symbol': '005930',
                'quantity': 10,
                'avg_price': 75000.0
            },
            {
                'account_id': 'test_account',
                'symbol': '000660',
                'quantity': -5,
                'avg_price': 180000.0
            }
        ]
        
        total_exposure = position_manager.get_total_exposure('test_account')
        
        # 총 익스포저: (10 * 75000) + (5 * 180000) = 1,650,000
        expected_exposure = (10 * 75000) + (5 * 180000)
        assert total_exposure == expected_exposure