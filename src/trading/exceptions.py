"""
Trading 관련 커스텀 예외 클래스들
"""


class TradingError(Exception):
    """거래 관련 기본 예외"""
    pass


class BrokerError(TradingError):
    """브로커 API 관련 예외"""
    pass


class AccountError(TradingError):
    """계좌 관련 예외"""
    pass


class OrderError(TradingError):
    """주문 관련 예외"""
    pass


class RiskManagementError(TradingError):
    """리스크 관리 관련 예외"""
    pass


class InsufficientBalanceError(AccountError):
    """잔고 부족 예외"""
    pass


class PositionLimitExceededError(RiskManagementError):
    """포지션 한도 초과 예외"""
    pass


class DailyLossLimitExceededError(RiskManagementError):
    """일일 손실 한도 초과 예외"""
    pass


class InvalidOrderError(OrderError):
    """유효하지 않은 주문 예외"""
    pass


class OrderTimeoutError(OrderError):
    """주문 타임아웃 예외"""
    pass