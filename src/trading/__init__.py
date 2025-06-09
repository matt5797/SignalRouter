"""
Trading 모듈 - 거래 실행 및 계좌 관리
"""

# KisBroker를 기본 Broker로 사용
from .kis_broker import KisBroker as Broker  # 기존 코드 호환성 유지
from .kis_broker import KisBroker  # 명시적 사용을 위한 임포트

# 기존 컴포넌트
from .account import Account, AccountType
from .trade_executor import TradeExecutor
from .position_manager import PositionManager
from .exceptions import (
    TradingError, BrokerError, AccountError, OrderError, RiskManagementError,
    InsufficientBalanceError, PositionLimitExceededError, 
    DailyLossLimitExceededError, InvalidOrderError, OrderTimeoutError
)

# KIS API 인증 관련
from .kis_auth import KisAuth
from .secret_loader import SecretLoader
from .auth_factory import AuthFactory

__all__ = [
    # 핵심 브로커 클래스 (KisBroker를 Broker로 노출)
    'Broker',  # KisBroker alias
    'KisBroker',  # 명시적 사용
    
    # 기존 핵심 클래스
    'Account', 
    'AccountType',
    'TradeExecutor',
    'PositionManager',
    
    # 예외 클래스
    'TradingError',
    'BrokerError', 
    'AccountError',
    'OrderError',
    'RiskManagementError',
    'InsufficientBalanceError',
    'PositionLimitExceededError',
    'DailyLossLimitExceededError', 
    'InvalidOrderError',
    'OrderTimeoutError',
    
    # KIS API 전용 예외 클래스
    'KisApiError',
    'KisAuthError',
    'KisOrderError', 
    'KisInsufficientBalanceError',
    'KisMarketClosedError',
    'KisRateLimitError',
    'KisAccountTypeError',
    'KisSymbolNotFoundError',
    
    # KIS 인증
    'KisAuth',
    'SecretLoader', 
    'AuthFactory'
]