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


class KisOrderLimitError(KisOrderError):
    """주문 한도 초과 예외"""
    pass


class KisSystemError(KisApiError):
    """KIS 시스템 오류 예외"""
    pass


class KisDataError(KisApiError):
    """데이터 오류 예외"""
    pass


# 핵심 에러 코드별 매핑 (문서 기반 20개)
KIS_ERROR_CODE_MAPPING = {
    # === 잔고 관련 에러 ===
    'APBK0013': KisInsufficientBalanceError,  # 잔고부족
    'APBK0015': KisInsufficientBalanceError,  # 주문가능금액부족  
    'APBK0917': KisInsufficientBalanceError,  # 예수금부족
    'APBK0918': KisInsufficientBalanceError,  # 신용한도초과
    
    # === 주문 관련 에러 ===
    'APBK0551': KisSymbolNotFoundError,       # 종목코드오류
    'APBK0552': KisOrderError,                # 주문수량오류
    'APBK0553': KisOrderError,                # 주문가격오류
    'APBK0554': KisOrderLimitError,           # 주문한도초과
    'APBK0555': KisOrderError,                # 정정취소불가
    'APBK0556': KisOrderError,                # 주문구분오류
    
    # === 시장 관련 에러 ===
    'APBK0919': KisMarketClosedError,         # 장마감
    'APBK0920': KisMarketClosedError,         # 휴장일
    'APBK0921': KisMarketClosedError,         # 거래정지
    'APBK0922': KisMarketClosedError,         # 단일가시간
    
    # === 시스템 관련 에러 ===
    'APBK0545': KisRateLimitError,            # API호출한도초과
    'APBK0546': KisRateLimitError,            # 연속조회제한
    'APBK1234': KisSystemError,               # 시스템점검
    'APBK9999': KisSystemError,               # 서버오류
    
    # === 인증 관련 에러 ===
    'APBK0001': KisAuthError,                 # 인증실패
    'APBK0002': KisAuthError,                 # 토큰만료
}


# 에러 메시지 한글/영문 매핑
ERROR_MESSAGES = {
    'APBK0013': {
        'ko': '잔고가 부족합니다',
        'en': 'Insufficient balance'
    },
    'APBK0015': {
        'ko': '주문가능금액이 부족합니다', 
        'en': 'Insufficient orderable amount'
    },
    'APBK0551': {
        'ko': '종목코드를 확인해주세요',
        'en': 'Invalid symbol code'
    },
    'APBK0919': {
        'ko': '장마감 시간입니다',
        'en': 'Market is closed'
    },
    'APBK0545': {
        'ko': 'API 호출 한도를 초과했습니다',
        'en': 'API rate limit exceeded'
    },
    'APBK1234': {
        'ko': '시스템 점검중입니다',
        'en': 'System maintenance'
    }
}


def get_kis_exception(error_code: str, message: str, lang: str = 'ko') -> Exception:
    """
    에러 코드에 따른 적절한 예외 반환
    
    Args:
        error_code: KIS API 에러 코드
        message: 원본 에러 메시지  
        lang: 언어 코드 ('ko', 'en')
        
    Returns:
        적절한 예외 객체
    """
    # 1단계: 매핑된 예외 클래스 찾기
    exception_class = KIS_ERROR_CODE_MAPPING.get(error_code, KisApiError)
    
    # 2단계: 사용자 친화적 메시지 조합
    friendly_msg = ERROR_MESSAGES.get(error_code, {}).get(lang, message)
    full_message = f"[{error_code}] {friendly_msg}"
    
    # 3단계: 원본 메시지도 포함 (디버깅용)
    if friendly_msg != message and message:
        full_message += f" (원본: {message})"
    
    return exception_class(full_message)


def is_retryable_error(error_code: str) -> bool:
    """
    재시도 가능한 에러인지 판단
    
    Args:
        error_code: KIS API 에러 코드
        
    Returns:
        재시도 가능 여부
    """
    # 시스템/네트워크 관련 에러만 재시도
    retryable_codes = {
        'APBK0545',  # API호출한도 (잠시 후 재시도)
        'APBK0546',  # 연속조회제한
        'APBK1234',  # 시스템점검
        'APBK9999'   # 서버오류
    }
    
    return error_code in retryable_codes


def get_error_category(error_code: str) -> str:
    """
    에러 카테고리 반환
    
    Args:
        error_code: KIS API 에러 코드
        
    Returns:
        에러 카테고리 ('balance', 'order', 'market', 'system', 'auth', 'unknown')
    """
    if error_code in ['APBK0013', 'APBK0015', 'APBK0917', 'APBK0918']:
        return 'balance'
    elif error_code in ['APBK0551', 'APBK0552', 'APBK0553', 'APBK0554', 'APBK0555', 'APBK0556']:
        return 'order'
    elif error_code in ['APBK0919', 'APBK0920', 'APBK0921', 'APBK0922']:
        return 'market'
    elif error_code in ['APBK0545', 'APBK0546', 'APBK1234', 'APBK9999']:
        return 'system'
    elif error_code in ['APBK0001', 'APBK0002']:
        return 'auth'
    else:
        return 'unknown'