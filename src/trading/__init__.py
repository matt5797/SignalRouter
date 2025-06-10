"""
Trading 모듈 - 거래 실행 및 계좌 관리
"""

# KisBroker를 기본 Broker로 사용
from .kis_broker import KisBroker

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
from .kis_api_errors import *

__all__ = [
    # 메인 브로커
    'KisBroker',
    
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