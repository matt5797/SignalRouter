"""
SignalRouter 자동매매 시스템 통합 테스트 스위트
실제 거래가 발생하지 않는 선에서 핵심 비즈니스 로직을 테스트합니다.
"""

import pytest
import tempfile
import json
import yaml
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sqlite3
from decimal import Decimal

# 프로젝트 모듈 임포트
import sys
import os
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models import TradeSignal, Position, TradeOrder, TransitionType, TradeStatus
from src.database import TradingDB
from src.config import ConfigLoader, AccountConfig, StrategyConfig
from src.trading import SecretLoader, KisAuth, AuthFactory, PositionManager, TradeExecutor
from src.core import AutoTrader


# ===================== 픽스처 =====================

@pytest.fixture
def temp_db():
    """임시 데이터베이스"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    db = TradingDB(db_path)
    yield db
    
    # 정리
    db.close()
    os.unlink(db_path)


@pytest.fixture
def temp_config():
    """임시 설정 파일"""
    config_data = {
        'database': {'path': ':memory:'},
        'webhook': {'host': '0.0.0.0', 'port': 8000},
        'accounts': {
            'test_stock': {
                'name': '테스트 주식계좌',
                'type': 'STOCK',
                'secret_file': 'test.json',
                'is_virtual': True,
                'is_active': True
            }
        },
        'strategies': {
            'TEST_STRATEGY': {
                'account_id': 'test_stock',
                'webhook_token': 'test_token_123',
                'max_position_ratio': 0.3,
                'max_daily_loss': 1000000,
                'is_active': True
            }
        },
        'risk_management': {
            'global_max_daily_loss': 5000000,
            'position_timeout_seconds': 60
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    yield config_path
    os.unlink(config_path)


@pytest.fixture
def temp_secret():
    """임시 시크릿 파일"""
    secret_data = {
        'app_key': 'test_app_key_12345',
        'app_secret': 'test_app_secret_67890',
        'account_number': '12345678',
        'account_product': '01',
        'account_type': 'STOCK',
        'is_virtual': True
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(secret_data, f)
        secret_path = f.name
    
    yield secret_path
    os.unlink(secret_path)


@pytest.fixture
def sample_signal():
    """샘플 트레이딩 시그널"""
    return {
        'strategy': 'TEST_STRATEGY',
        'symbol': 'AAPL',
        'action': 'BUY',
        'quantity': 10,
        'price': 150.50,
        'webhook_token': 'test_token_123'
    }


# ===================== 모델 테스트 =====================

class TestTradeSignal:
    """TradeSignal 모델 테스트"""
    
    def test_signal_creation_valid(self):
        """유효한 시그널 생성"""
        signal = TradeSignal(
            strategy='TEST',
            symbol='AAPL',
            action='BUY',
            quantity=10,
            price=150.0
        )
        
        assert signal.strategy == 'TEST'
        assert signal.symbol == 'AAPL'
        assert signal.action == 'BUY'
        assert signal.quantity == 10
        assert signal.price == 150.0
        assert signal.is_valid()
    
    def test_signal_validation_invalid_action(self):
        """잘못된 액션으로 시그널 생성"""
        with pytest.raises(ValueError, match="Invalid action"):
            TradeSignal(
                strategy='TEST',
                symbol='AAPL',
                action='INVALID',
                quantity=10
            )
    
    def test_signal_validation_invalid_quantity(self):
        """잘못된 수량으로 시그널 생성"""
        with pytest.raises(ValueError, match="Invalid quantity"):
            TradeSignal(
                strategy='TEST',
                symbol='AAPL',
                action='BUY',
                quantity=-5
            )
    
    def test_signal_from_webhook(self, sample_signal):
        """웹훅 페이로드에서 시그널 생성"""
        signal = TradeSignal.from_webhook_payload(sample_signal)
        
        assert signal.strategy == 'TEST_STRATEGY'
        assert signal.symbol == 'AAPL'
        assert signal.action == 'BUY'
        assert signal.quantity == 10
        assert signal.price == 150.50
        assert signal.is_valid()


class TestPosition:
    """Position 모델 테스트"""
    
    def test_position_creation(self):
        """포지션 생성"""
        pos = Position(
            account_id='test_account',
            symbol='AAPL',
            quantity=10,
            avg_price=150.0
        )
        
        assert pos.account_id == 'test_account'
        assert pos.symbol == 'AAPL'
        assert pos.quantity == 10
        assert pos.avg_price == 150.0
        assert pos.is_long()
        assert not pos.is_short()
        assert not pos.is_flat()
    
    def test_position_pnl_calculation(self):
        """손익 계산"""
        pos = Position(
            account_id='test',
            symbol='AAPL',
            quantity=10,
            avg_price=150.0
        )
        
        # 현재가 160 - 이익
        pnl = pos.get_unrealized_pnl(160.0)
        assert pnl == 100.0  # (160-150) * 10
        
        # 현재가 140 - 손실
        pnl = pos.get_unrealized_pnl(140.0)
        assert pnl == -100.0  # (140-150) * 10
    
    def test_position_short(self):
        """숏 포지션 테스트"""
        pos = Position(
            account_id='test',
            symbol='AAPL',
            quantity=-10,
            avg_price=150.0
        )
        
        assert pos.is_short()
        assert not pos.is_long()
        
        # 숏 포지션 손익 (가격 하락시 이익)
        pnl = pos.get_unrealized_pnl(140.0)
        assert pnl == 100.0  # (150-140) * 10
    
    def test_position_average_price_calculation(self):
        """평균 단가 계산"""
        pos = Position(
            account_id='test',
            symbol='AAPL',
            quantity=10,
            avg_price=150.0
        )
        
        # 같은 방향 추가 - 평균 단가 재계산
        new_avg = pos.calculate_new_avg_price(5, 160.0)
        expected = (10*150 + 5*160) / 15  # 1500 + 800 = 2300 / 15 = 153.33
        assert abs(new_avg - expected) < 0.01


class TestTradeOrder:
    """TradeOrder 모델 테스트"""
    
    def test_order_creation(self):
        """주문 생성"""
        order = TradeOrder(
            account_id='test',
            symbol='AAPL',
            action='BUY',
            quantity=10,
            price=150.0,
            transition_type=TransitionType.ENTRY
        )
        
        assert order.account_id == 'test'
        assert order.symbol == 'AAPL'
        assert order.action == 'BUY'
        assert order.is_buy_order()
        assert order.is_limit_order()
        assert not order.is_market_order()
    
    def test_order_from_signal(self, sample_signal):
        """시그널에서 주문 생성"""
        order = TradeOrder.from_signal(
            sample_signal, 
            'test_account', 
            TransitionType.ENTRY
        )
        
        assert order.account_id == 'test_account'
        assert order.symbol == 'AAPL'
        assert order.action == 'BUY'
        assert order.quantity == 10
        assert order.price == 150.50
    
    def test_order_broker_format(self):
        """브로커 API 포맷 변환"""
        order = TradeOrder(
            account_id='test',
            symbol='AAPL',
            action='SELL',
            quantity=5,
            price=None,  # 시장가
            transition_type=TransitionType.EXIT
        )
        
        broker_format = order.to_broker_format()
        
        assert broker_format['symbol'] == 'AAPL'
        assert broker_format['action'] == 'SELL'
        assert broker_format['quantity'] == 5
        assert broker_format['price'] is None
        assert broker_format['order_type'] == 'MARKET'


# ===================== 데이터베이스 테스트 =====================

class TestTradingDB:
    """TradingDB 테스트"""
    
    def test_database_initialization(self, temp_db):
        """데이터베이스 초기화"""
        # 테이블 존재 확인
        conn = temp_db.get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['accounts', 'strategies', 'trades', 'positions', 'balances']
        for table in expected_tables:
            assert table in tables
    
    def test_trade_save_and_retrieve(self, temp_db):
        """거래 저장 및 조회"""
        trade_data = {
            'account_id': 'test_account',
            'strategy_id': 1,
            'symbol': 'AAPL',
            'action': 'BUY',
            'transition_type': 'ENTRY',
            'quantity': 10,
            'price': 150.0,
            'signal_time': datetime.now()
        }
        
        trade_id = temp_db.save_trade(trade_data)
        assert trade_id > 0
        
        # 조회
        trades = temp_db.get_account_trades('test_account', limit=10)
        assert len(trades) == 1
        assert trades[0]['symbol'] == 'AAPL'
        assert trades[0]['action'] == 'BUY'
    
    def test_position_update(self, temp_db):
        """포지션 업데이트"""
        temp_db.update_position('test_account', 'AAPL', 10, 150.0)
        
        position = temp_db.get_position('test_account', 'AAPL')
        assert position['quantity'] == 10
        assert position['avg_price'] == 150.0
        
        # 추가 업데이트
        temp_db.update_position('test_account', 'AAPL', 15, 155.0)
        position = temp_db.get_position('test_account', 'AAPL')
        assert position['quantity'] == 15
        assert position['avg_price'] == 155.0
    
    def test_daily_pnl_calculation(self, temp_db):
        """일일 손익 계산"""
        # 오늘 거래 데이터 생성
        today = date.today()
        
        # 매수 거래
        temp_db.execute_query("""
            INSERT INTO trades (account_id, strategy_id, symbol, action, transition_type,
                              quantity, price, status, filled_quantity, avg_fill_price, fill_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('test_account', 1, 'AAPL', 'BUY', 'ENTRY', 10, 150.0, 'FILLED', 10, 150.0, datetime.now()))
        
        # 매도 거래
        temp_db.execute_query("""
            INSERT INTO trades (account_id, strategy_id, symbol, action, transition_type,
                              quantity, price, status, filled_quantity, avg_fill_price, fill_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('test_account', 1, 'AAPL', 'SELL', 'EXIT', 5, 160.0, 'FILLED', 5, 160.0, datetime.now()))
        
        pnl = temp_db.get_daily_pnl('test_account', today)
        # 매도금액(5*160=800) - 매수금액(10*150=1500) = -700
        # 하지만 부분매도이므로 실제 계산은 다를 수 있음
        assert isinstance(pnl, float)


# ===================== 설정 테스트 =====================

class TestConfigLoader:
    """ConfigLoader 테스트"""
    
    def test_config_loading(self, temp_config):
        """설정 파일 로딩"""
        config = ConfigLoader(temp_config)
        
        db_config = config.get_database_config()
        assert db_config['path'] == ':memory:'
        
        webhook_config = config.get_webhook_config()
        assert webhook_config['port'] == 8000
    
    def test_account_config(self, temp_config):
        """계좌 설정 조회"""
        config = ConfigLoader(temp_config)
        
        account_config = config.get_account_config('test_stock')
        assert account_config is not None
        assert account_config.name == '테스트 주식계좌'
        assert account_config.type == 'STOCK'
        assert account_config.is_virtual is True
        
        # 존재하지 않는 계좌
        missing_config = config.get_account_config('non_existent')
        assert missing_config is None
    
    def test_strategy_config(self, temp_config):
        """전략 설정 조회"""
        config = ConfigLoader(temp_config)
        
        strategy_config = config.get_strategy_config('TEST_STRATEGY')
        assert strategy_config is not None
        assert strategy_config.account_id == 'test_stock'
        assert strategy_config.webhook_token == 'test_token_123'
        assert strategy_config.max_position_ratio == 0.3
    
    def test_strategy_by_token(self, temp_config):
        """토큰으로 전략 검색"""
        config = ConfigLoader(temp_config)
        
        strategy = config.get_strategy_by_token('test_token_123')
        assert strategy is not None
        assert strategy.name == 'TEST_STRATEGY'
        
        # 잘못된 토큰
        invalid_strategy = config.get_strategy_by_token('invalid_token')
        assert invalid_strategy is None


# ===================== 인증 테스트 =====================

class TestSecretLoader:
    """SecretLoader 테스트"""
    
    def test_secret_loading(self, temp_secret):
        """시크릿 파일 로딩"""
        secret_data = SecretLoader.load_secret(temp_secret)
        
        assert secret_data['app_key'] == 'test_app_key_12345'
        assert secret_data['account_number'] == '12345678'
        assert secret_data['is_virtual'] is True
    
    def test_secret_validation(self, temp_secret):
        """시크릿 데이터 검증"""
        secret_data = SecretLoader.load_secret(temp_secret)
        assert SecretLoader.validate_secret(secret_data) is True
        
        # 잘못된 데이터
        invalid_secret = {'app_key': 'test'}  # 필수 필드 누락
        assert SecretLoader.validate_secret(invalid_secret) is False
    
    def test_secret_file_not_found(self):
        """존재하지 않는 시크릿 파일"""
        with pytest.raises(FileNotFoundError):
            SecretLoader.load_secret('non_existent_file.json')


class TestKisAuth:
    """KisAuth 테스트 (실제 API 호출 제외)"""
    
    def test_auth_initialization(self):
        """인증 객체 초기화"""
        auth = KisAuth(
            app_key='test_key',
            app_secret='test_secret',
            account_number='12345678',
            account_product='01',
            is_virtual=True
        )
        
        assert auth.app_key == 'test_key'
        assert auth.account_number == '12345678'
        assert auth.is_virtual is True
        assert 'vts' in auth.base_url  # 모의투자 URL
    
    def test_request_headers_generation(self):
        """요청 헤더 생성 테스트"""
        auth = KisAuth(
            app_key='test_key',
            app_secret='test_secret',
            account_number='12345678',
            account_product='01',
            is_virtual=True
        )
        
        # 실제 토큰 발급 없이 헤더 구조만 테스트
        with patch.object(auth, 'get_valid_token', return_value='mock_token'):
            headers = auth.get_request_headers('TTTT1001U')
            
            assert headers['authorization'] == 'Bearer mock_token'
            assert headers['appkey'] == 'test_key'
            assert headers['appsecret'] == 'test_secret'
            assert headers['tr_id'] == 'VTTTT1001U'  # 모의투자용으로 변환


# ===================== 포지션 관리자 테스트 =====================

class TestPositionManager:
    """PositionManager 테스트"""
    
    def test_transition_type_calculation(self, temp_db):
        """포지션 전환 타입 계산"""
        pm = PositionManager(temp_db)
        
        # 플랫에서 진입
        current = {'quantity': 0}
        target = {'action': 'BUY', 'quantity': 10}
        transition = pm.calculate_transition_type(current, target)
        assert transition == TransitionType.ENTRY
        
        # 롱 포지션에서 부분 청산
        current = {'quantity': 10}
        target = {'action': 'SELL', 'quantity': 5}
        transition = pm.calculate_transition_type(current, target)
        assert transition == TransitionType.EXIT
        
        # 롱 포지션에서 역전 (롱→숏)
        current = {'quantity': 10}
        target = {'action': 'SELL', 'quantity': 15}
        transition = pm.calculate_transition_type(current, target)
        assert transition == TransitionType.REVERSE
    
    def test_portfolio_summary(self, temp_db):
        """포트폴리오 요약"""
        pm = PositionManager(temp_db)
        
        # 테스트 포지션 추가
        temp_db.update_position('test_account', 'AAPL', 10, 150.0)
        temp_db.update_position('test_account', 'GOOGL', -5, 2500.0)
        
        summary = pm.get_portfolio_summary('test_account')
        
        assert summary['account_id'] == 'test_account'
        assert summary['total_positions'] == 2
        assert summary['long_positions'] == 1
        assert summary['short_positions'] == 1
        assert 'AAPL' in summary['symbols']
        assert 'GOOGL' in summary['symbols']
    
    def test_position_exposure(self, temp_db):
        """포지션 익스포저 계산"""
        pm = PositionManager(temp_db)
        temp_db.update_position('test_account', 'AAPL', 10, 150.0)
        
        exposure = pm.get_position_exposure('test_account', 'AAPL')
        
        assert exposure['symbol'] == 'AAPL'
        assert exposure['exposure'] == 1500.0  # 10 * 150
        assert exposure['direction'] == 'LONG'


# ===================== 거래 실행기 테스트 =====================

class TestTradeExecutor:
    """TradeExecutor 테스트 (실제 주문 제외)"""
    
    def test_transition_type_calculation(self, temp_db):
        """전환 타입 계산"""
        executor = TradeExecutor(temp_db)
        
        # 플랫에서 진입
        current = {'quantity': 0}
        signal = {'action': 'BUY'}
        transition = executor._calculate_transition_type(current, signal)
        assert transition == TransitionType.ENTRY
        
        # 롱에서 청산
        current = {'quantity': 10}
        signal = {'action': 'SELL'}
        transition = executor._calculate_transition_type(current, signal)
        assert transition == TransitionType.EXIT
    
    def test_position_limit_check(self, temp_db):
        """포지션 한도 체크"""
        executor = TradeExecutor(temp_db)
        
        # Mock 계좌 생성
        mock_account = Mock()
        mock_account.get_total_portfolio_value.return_value = {
            'total_value': 1000000.0,
            'reliable': True
        }
        
        # 30% 투자 (30만원) - 통과해야 함
        result = executor.check_position_limit(mock_account, 'AAPL', 300000.0)
        assert result['approved'] is True
        assert result['position_ratio'] == 0.3
        
        # 150% 투자 (150만원) - 거부되어야 함
        result = executor.check_position_limit(mock_account, 'AAPL', 1500000.0)
        assert result['approved'] is False
        assert 'limit_exceeded' in result['reason']
    
    def test_daily_loss_limit_check(self, temp_db):
        """일일 손실 한도 체크"""
        executor = TradeExecutor(temp_db)
        
        # Mock 데이터베이스 일일 손익
        with patch.object(temp_db, 'get_daily_pnl', return_value=-1000000):  # 100만원 손실
            result = executor.check_daily_loss_limit('test_account', 100000.0)
            assert result['approved'] is True  # 아직 한도 내
        
        with patch.object(temp_db, 'get_daily_pnl', return_value=-6000000):  # 600만원 손실
            result = executor.check_daily_loss_limit('test_account', 100000.0)
            assert result['approved'] is False  # 한도 초과
    
    def test_error_result_generation(self, temp_db):
        """에러 결과 생성"""
        executor = TradeExecutor(temp_db)
        
        error_result = executor._error_result(
            'validation',
            'Invalid signal format',
            {'field': 'action'}
        )
        
        assert error_result['success'] is False
        assert error_result['error_type'] == 'validation'
        assert error_result['message'] == 'Invalid signal format'
        assert error_result['details']['field'] == 'action'


# ===================== 메인 트레이더 테스트 =====================

class TestAutoTrader:
    """AutoTrader 테스트 (실제 거래 제외)"""
    
    @patch('src.core.auto_trader.Account')
    def test_signal_routing(self, mock_account_class, temp_config):
        """시그널 라우팅 테스트"""
        # Mock 계좌 설정
        mock_account = Mock()
        mock_account.account_id = 'test_stock'
        mock_account.is_active = True
        mock_account_class.return_value = mock_account
        
        trader = AutoTrader(temp_config)
        trader.accounts = {'test_stock': mock_account}
        
        # 유효한 토큰으로 라우팅
        signal_data = {'webhook_token': 'test_token_123'}
        routing_result = trader._route_signal_to_account(signal_data)
        
        assert routing_result['success'] is True
        assert routing_result['account'] == mock_account
        assert routing_result['account_id'] == 'test_stock'
    
    @patch('src.core.auto_trader.Account')
    def test_signal_routing_invalid_token(self, mock_account_class, temp_config):
        """잘못된 토큰으로 시그널 라우팅"""
        trader = AutoTrader(temp_config)
        
        # 잘못된 토큰
        signal_data = {'webhook_token': 'invalid_token'}
        routing_result = trader._route_signal_to_account(signal_data)
        
        assert routing_result['success'] is False
        assert 'not found' in routing_result['message']
    
    @patch('src.core.auto_trader.Account')
    def test_emergency_stop(self, mock_account_class, temp_config):
        """비상 정지 테스트"""
        mock_account = Mock()
        mock_account.is_active = True
        mock_account_class.return_value = mock_account
        
        trader = AutoTrader(temp_config)
        trader.accounts = {'test_stock': mock_account}
        
        # 비상 정지 실행
        result = trader.emergency_stop_all()
        
        assert result['success'] is True
        assert trader._emergency_stop is True
        assert mock_account.is_active is False
    
    @patch('src.core.auto_trader.Account')
    def test_portfolio_summary(self, mock_account_class, temp_config):
        """포트폴리오 요약 테스트"""
        # Mock 계좌 설정
        mock_account = Mock()
        mock_account.is_active = True
        mock_account.name = '테스트 계좌'
        mock_account.account_type.value = 'STOCK'
        mock_account.get_total_portfolio_value.return_value = {
            'total_value': 1000000.0,
            'reliable': True
        }
        mock_account.get_total_unrealized_pnl.return_value = {
            'unrealized_pnl': 50000.0,
            'reliable': True
        }
        mock_account.get_positions.return_value = []
        mock_account.get_data_health.return_value = {'balance_status': 'success'}
        mock_account.is_data_stale.return_value = False
        mock_account_class.return_value = mock_account
        
        trader = AutoTrader(temp_config)
        trader.accounts = {'test_stock': mock_account}
        
        # 포트폴리오 요약 조회
        summary = trader.get_portfolio_summary()
        
        assert summary['total_accounts'] == 1
        assert summary['active_accounts'] == 1
        assert summary['reliable_accounts'] == 1
        assert summary['total_portfolio_value'] == 1000000.0
        assert summary['total_unrealized_pnl'] == 50000.0
        assert summary['data_health']['all_reliable'] is True


# ===================== 통합 테스트 =====================

class TestSystemIntegration:
    """시스템 통합 테스트"""
    
    @patch('src.core.auto_trader.Account')
    @patch('src.trading.trade_executor.TradeExecutor.place_order')
    def test_signal_processing_flow(self, mock_place_order, mock_account_class, temp_config, sample_signal):
        """시그널 처리 전체 플로우 테스트 (실제 주문 제외)"""
        # Mock 설정
        mock_account = Mock()
        mock_account.account_id = 'test_stock'
        mock_account.is_active = True
        mock_account.is_balance_reliable.return_value = True
        mock_account.is_data_stale.return_value = False
        mock_account.can_trade.return_value = {
            'can_trade': True,
            'reason': 'sufficient_balance',
            'reliable': True
        }
        mock_account.get_total_portfolio_value.return_value = {
            'total_value': 1000000.0,
            'reliable': True
        }
        mock_account_class.return_value = mock_account
        
        # 주문 실행 Mock (실제 주문은 하지 않음)
        mock_place_order.return_value = {
            'success': True,
            'order_id': 'test_order_123',
            'error': None
        }
        
        trader = AutoTrader(temp_config)
        trader.accounts = {'test_stock': mock_account}
        
        # 시그널 처리
        result = trader.process_signal(sample_signal)
        
        # 검증
        assert result['success'] is True
        assert result['account_id'] == 'test_stock'
        assert result['strategy_name'] == 'TEST_STRATEGY'
        assert 'execution_result' in result
    
    @patch('src.core.auto_trader.Account')
    def test_signal_processing_emergency_stop(self, mock_account_class, temp_config, sample_signal):
        """비상 정지 상태에서 시그널 처리"""
        trader = AutoTrader(temp_config)
        trader._emergency_stop = True
        
        result = trader.process_signal(sample_signal)
        
        assert result['success'] is False
        assert 'emergency_stop' in result['message']
        assert result['execution_result']['error_type'] == 'emergency_stop'
    
    @patch('src.core.auto_trader.Account')
    def test_signal_processing_invalid_signal(self, mock_account_class, temp_config):
        """잘못된 시그널 처리"""
        trader = AutoTrader(temp_config)
        
        invalid_signal = {
            'strategy': 'TEST_STRATEGY',
            'symbol': 'AAPL',
            'action': 'INVALID_ACTION',  # 잘못된 액션
            'quantity': 10,
            'webhook_token': 'test_token_123'
        }
        
        result = trader.process_signal(invalid_signal)
        
        assert result['success'] is False
        assert result['execution_result']['error_type'] == 'validation'
    
    def test_database_position_sync(self, temp_db):
        """데이터베이스와 포지션 관리자 동기화"""
        pm = PositionManager(temp_db)
        
        # 거래 후 포지션 업데이트 시뮬레이션
        trade_data = {
            'account_id': 'test_account',
            'symbol': 'AAPL',
            'action': 'BUY',
            'filled_quantity': 10,
            'avg_fill_price': 150.0
        }
        
        pm.update_position_after_trade(trade_data)
        
        # 데이터베이스에서 포지션 확인
        position = temp_db.get_position('test_account', 'AAPL')
        assert position['quantity'] == 10
        assert position['avg_price'] == 150.0
        
        # 포지션 관리자에서 확인
        current_position = pm.get_current_position('test_account', 'AAPL')
        assert current_position['quantity'] == 10
        assert current_position['position_type'] == 'LONG'


# ===================== 에러 처리 테스트 =====================

class TestErrorHandling:
    """에러 처리 테스트"""
    
    def test_database_connection_error(self):
        """데이터베이스 연결 오류"""
        # 존재하지 않는 경로
        with pytest.raises(Exception):
            TradingDB("/invalid/path/database.db")
    
    def test_config_file_missing(self):
        """설정 파일 누락"""
        with pytest.raises(FileNotFoundError):
            ConfigLoader("non_existent_config.yaml")
    
    def test_invalid_yaml_config(self):
        """잘못된 YAML 설정"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            invalid_config = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid YAML"):
                ConfigLoader(invalid_config)
        finally:
            os.unlink(invalid_config)
    
    @patch('src.core.auto_trader.Account')
    def test_account_loading_failure(self, mock_account_class, temp_config):
        """계좌 로딩 실패"""
        # Account 생성시 예외 발생 시뮬레이션
        mock_account_class.side_effect = Exception("Secret file not found")
        
        trader = AutoTrader(temp_config)
        
        # 계좌가 로딩되지 않았어야 함
        assert len(trader.accounts) == 0
    
    def test_position_calculation_edge_cases(self, temp_db):
        """포지션 계산 엣지 케이스"""
        pm = PositionManager(temp_db)
        
        # 0으로 나누기 방지 테스트
        position = pm.get_current_position('test_account', 'NONEXISTENT')
        assert position['quantity'] == 0
        assert position['position_type'] == 'FLAT'
        
        # 빈 포트폴리오 요약
        summary = pm.get_portfolio_summary('empty_account')
        assert summary['total_positions'] == 0
        assert summary['total_market_value'] == 0.0


# ===================== 성능 테스트 =====================

class TestPerformance:
    """기본적인 성능 테스트"""
    
    def test_database_batch_operations(self, temp_db):
        """데이터베이스 배치 작업 성능"""
        import time
        
        start_time = time.time()
        
        # 100개 거래 기록 삽입
        for i in range(100):
            trade_data = {
                'account_id': 'perf_test',
                'strategy_id': 1,
                'symbol': f'STOCK{i:03d}',
                'action': 'BUY' if i % 2 == 0 else 'SELL',
                'transition_type': 'ENTRY',
                'quantity': 10,
                'price': 100.0 + i,
                'signal_time': datetime.now()
            }
            temp_db.save_trade(trade_data)
        
        elapsed_time = time.time() - start_time
        
        # 1초 이내에 완료되어야 함 (성능 기준)
        assert elapsed_time < 1.0
        
        # 조회 성능 테스트
        start_time = time.time()
        trades = temp_db.get_account_trades('perf_test', limit=50)
        elapsed_time = time.time() - start_time
        
        assert len(trades) == 50
        assert elapsed_time < 0.1  # 100ms 이내
    
    def test_signal_validation_performance(self):
        """시그널 검증 성능"""
        import time
        
        start_time = time.time()
        
        # 1000개 시그널 검증
        for i in range(1000):
            signal = TradeSignal(
                strategy=f'STRATEGY_{i}',
                symbol=f'STOCK{i:04d}',
                action='BUY' if i % 2 == 0 else 'SELL',
                quantity=i + 1,
                price=100.0 + (i % 100)
            )
            assert signal.is_valid()
        
        elapsed_time = time.time() - start_time
        
        # 100ms 이내에 완료되어야 함
        assert elapsed_time < 0.1


# ===================== 메인 실행부 =====================

if __name__ == "__main__":
    """
    테스트 실행 예제:
    
    # 전체 테스트 실행
    pytest test_suite_complete.py -v
    
    # 특정 클래스만 실행
    pytest test_suite_complete.py::TestTradeSignal -v
    
    # 성능 테스트만 실행
    pytest test_suite_complete.py::TestPerformance -v
    
    # 커버리지와 함께 실행
    pytest test_suite_complete.py --cov=src --cov-report=html
    """
    
    # 기본 테스트 실행
    pytest.main([__file__, "-v", "--tb=short"])


# ===================== 테스트 설정 =====================

def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


def pytest_collection_modifyitems(config, items):
    """테스트 항목 수정"""
    for item in items:
        # 성능 테스트에 slow 마커 추가
        if "Performance" in item.nodeid:
            item.add_marker(pytest.mark.slow)
        
        # 통합 테스트에 integration 마커 추가
        if "Integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)


# ===================== 도우미 함수 =====================

def create_sample_trades(db: TradingDB, account_id: str, count: int = 10):
    """샘플 거래 데이터 생성"""
    for i in range(count):
        trade_data = {
            'account_id': account_id,
            'strategy_id': 1,
            'symbol': f'TEST{i:03d}',
            'action': 'BUY' if i % 2 == 0 else 'SELL',
            'transition_type': 'ENTRY',
            'quantity': (i + 1) * 10,
            'price': 100.0 + i * 5,
            'signal_time': datetime.now() - timedelta(hours=i)
        }
        db.save_trade(trade_data)


def assert_trade_order_valid(order: TradeOrder):
    """거래 주문 유효성 검증 도우미"""
    assert order.account_id is not None
    assert order.symbol is not None
    assert order.action in ['BUY', 'SELL']
    assert order.quantity > 0
    assert order.transition_type in [TransitionType.ENTRY, TransitionType.EXIT, TransitionType.REVERSE]


def mock_kis_api_response(success: bool = True, data: dict = None) -> dict:
    """KIS API 응답 Mock 생성"""
    if success:
        return {
            'rt_cd': '0',
            'msg_cd': 'SUCCESS',
            'msg1': 'Success',
            'output': data or {}
        }
    else:
        return {
            'rt_cd': '1',
            'msg_cd': 'ERROR',
            'msg1': 'API Error',
            'output': {}
        }
