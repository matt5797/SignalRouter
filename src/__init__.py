# src/__init__.py
"""
SignalRouter 자동매매 시스템
메인 패키지 초기화 및 공통 임포트
"""

# 버전 정보
__version__ = "0.1.0"
__author__ = "Cho Sangjun"

# 공통 모델들을 최상위에서 임포트 가능하게 함
from .models import TradeSignal, Position, TradeOrder, TransitionType, TradeStatus
from .database import TradingDB
from .config import ConfigLoader, AccountConfig, StrategyConfig

# 편의를 위한 단축 임포트
__all__ = [
    # 모델
    'TradeSignal',
    'Position', 
    'TradeOrder',
    'TransitionType',
    'TradeStatus',
    
    # 데이터베이스
    'TradingDB',
    
    # 설정
    'ConfigLoader',
    'AccountConfig',
    'StrategyConfig',
]

# 패키지 정보 출력 (디버그용)
def get_package_info():
    """패키지 정보 반환"""
    return {
        'name': 'SignalRouter',
        'version': __version__,
        'author': __author__,
        'components': __all__
    }