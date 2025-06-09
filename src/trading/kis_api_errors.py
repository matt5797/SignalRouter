"""
KIS API 전용 에러 클래스들
"""

from .exceptions import BrokerError, OrderError, TradingError


class KisApiError(BrokerError):
    """KIS API 관련 기본 예외"""
    pass


class KisAuthError(KisApiError):
    """KIS 인증 관련 예외"""
    pass


class KisOrderError(KisApiError, OrderError):
    """KIS 주문 관련 예외"""
    pass


class KisInsufficientBalanceError(KisOrderError):
    """KIS 잔고 부족 예외"""
    pass


class KisMarketClosedError(KisApiError):
    """시장 휴장 예외"""
    pass


class KisRateLimitError(KisApiError):
    """API 호출 제한 예외"""
    pass


class KisAccountTypeError(KisApiError):
    """지원하지 않는 계좌 타입 예외"""
    pass


class KisSymbolNotFoundError(KisApiError):
    """종목 코드 오류 예외"""
    pass


# 에러 코드별 매핑
KIS_ERROR_CODE_MAPPING = {
    'APBK0013': KisInsufficientBalanceError,
    'APBK0015': KisInsufficientBalanceError,
    'APBK0919': KisMarketClosedError,
    'APBK0545': KisRateLimitError,
    'APBK0551': KisSymbolNotFoundError,
}


def get_kis_exception(error_code: str, message: str) -> Exception:
    """에러 코드에 따른 적절한 예외 반환"""
    exception_class = KIS_ERROR_CODE_MAPPING.get(error_code, KisApiError)
    return exception_class(f"[{error_code}] {message}")
