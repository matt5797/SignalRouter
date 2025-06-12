"""
Account - 계좌별 관리 클래스
브로커 API를 통한 계좌 특화 기능 제공
"""

from typing import Dict, List, Optional
from enum import Enum
import logging
from datetime import datetime
from .kis_broker import KisBroker
from .exceptions import AccountError

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """계좌 유형"""
    STOCK = "STOCK"
    FUTURES = "FUTURES"


class Account:
    """계좌 관리 클래스"""
    
    def __init__(
        self, 
        account_id: str, 
        name: str, 
        account_type: AccountType,
        secret_identifier: str = None,  # 변경: secret_file_path → secret_identifier
        is_virtual: bool = False,
        is_active: bool = True,
        token_storage_path: str = "secrets/tokens/"
    ):
        """
        Account 초기화
        
        Args:
            account_id: 계좌 ID
            name: 계좌 이름
            account_type: 계좌 타입
            secret_identifier: 계좌 설정 식별자 (None이면 account_id 사용)
            is_virtual: 모의투자 여부
            is_active: 계좌 활성화 여부
            token_storage_path: 토큰 저장 경로
        """
        self.account_id = account_id
        self.name = name
        self.account_type = AccountType(account_type) if isinstance(account_type, str) else account_type
        self.is_virtual = is_virtual
        self.is_active = is_active
        
        # Broker 인스턴스 생성
        self.broker = KisBroker(
            account_id=account_id, 
            secret_identifier=secret_identifier or account_id,  # None이면 account_id 사용
            is_virtual=is_virtual,
            token_storage_path=token_storage_path
        )
        
        logger.info(f"Account initialized: {account_id} ({name}) - Virtual: {is_virtual}")
    
    # ========== 조회 메서드 ==========
    
    def get_balance(self) -> Dict:
        """계좌 잔고 조회"""
        if not self.is_active:
            logger.warning(f"Account {self.account_id} is inactive")
            return {
                'total_balance': 0.0,
                'available_balance': 0.0, 
                'currency': 'KRW',
                'status': 'account_inactive',
                'reliable': False,
                'error': 'Account is inactive'
            }
        
        balance_result = self.broker.get_balance()
        
        # broker 응답 구조: {'data': {}, 'status': 'success/cached/error_fallback', 'error': None}
        balance_data = balance_result['data']
        
        # 신뢰성 정보 추가
        return {
            **balance_data,
            'status': balance_result['status'],
            'reliable': balance_result['status'] in ['success', 'cached'],
            'cache_age': balance_result.get('cache_age'),
            'timestamp': balance_result.get('timestamp'),
            'error': balance_result.get('error')
        }
    
    def get_positions(self) -> List[Dict]:
        """보유 포지션 조회"""
        if not self.is_active:
            logger.warning(f"Account {self.account_id} is inactive")
            return []
        
        positions_result = self.broker.get_positions()
        return positions_result['data']  # 단순히 데이터만 반환
    
    def get_positions_with_meta(self) -> Dict:
        """포지션 조회 + 메타 정보"""
        if not self.is_active:
            return {
                'data': [],
                'status': 'account_inactive',
                'reliable': False,
                'error': 'Account is inactive'
            }
        
        return self.broker.get_positions()
    
    def get_position_for_symbol(self, symbol: str) -> Dict:
        """특정 종목의 포지션 조회"""
        positions = self.get_positions()
        for position in positions:
            if position['symbol'] == symbol:
                return position
        
        return {
            'symbol': symbol,
            'quantity': 0,
            'avg_price': 0.0,
            'current_value': 0.0,
            'unrealized_pnl': 0.0
        }
    
    def get_orderable_amount(self, symbol: str, price: float = None) -> Dict:
        """매수 가능 금액/수량 조회 - 에러시 0 반환"""
        if not self.is_active:
            return {
                'symbol': symbol, 
                'orderable_quantity': 0, 
                'orderable_amount': 0.0, 
                'unit_price': 0.0,
                'status': 'account_inactive',
                'reliable': False
            }
        
        orderable_result = self.broker.get_orderable_amount(symbol, price)
        
        # 신뢰성 정보 추가
        orderable_data = orderable_result['data']
        return {
            **orderable_data,
            'status': orderable_result['status'],
            'reliable': orderable_result['status'] == 'success',
            'error': orderable_result.get('error')
        }
    
    # ========== 거래 가능 여부 판단 ==========
    
    def can_trade(self, amount: float) -> Dict:
        """거래 가능 여부 확인"""
        if not self.is_active:
            return {
                'can_trade': False,
                'reason': 'account_inactive',
                'reliable': True  # 계좌 상태는 신뢰할 수 있음
            }
        
        balance = self.get_balance()
        
        # 데이터가 신뢰할 수 없는 경우 거래 차단
        if not balance.get('reliable', False):
            logger.warning(f"Cannot determine trading capability due to unreliable balance data")
            return {
                'can_trade': False,
                'reason': 'unreliable_balance_data',
                'reliable': False,
                'balance_status': balance.get('status'),
                'balance_error': balance.get('error')
            }
        
        available = balance.get('available_balance', 0.0)
        can_trade = available >= amount
        
        return {
            'can_trade': can_trade,
            'reason': 'sufficient_balance' if can_trade else 'insufficient_balance',
            'reliable': True,
            'available_balance': available,
            'required_amount': amount,
            'balance_status': balance.get('status')
        }
    
    def is_balance_reliable(self) -> bool:
        """잔고 데이터 신뢰성 확인"""
        balance = self.get_balance()
        return balance.get('reliable', False)
    
    def is_data_stale(self, max_age_seconds: int = 60) -> bool:
        """데이터 신선도 확인"""
        balance = self.get_balance()
        cache_age = balance.get('cache_age')
        
        if cache_age is None:
            return False  # 실시간 데이터이므로 fresh
        
        return cache_age > max_age_seconds
    
    # ========== 포트폴리오 계산 ==========
    
    def get_total_portfolio_value(self) -> Dict:
        """총 포트폴리오 가치"""
        try:
            balance = self.get_balance()
            positions_meta = self.get_positions_with_meta()
            
            # 둘 다 신뢰할 수 있는 경우만 계산
            balance_reliable = balance.get('reliable', False)
            positions_reliable = positions_meta.get('status') in ['success', 'cached']
            
            if balance_reliable and positions_reliable:
                cash_value = balance.get('total_balance', 0.0)
                position_value = sum(pos.get('current_value', 0.0) 
                                   for pos in positions_meta['data'])
                
                return {
                    'total_value': cash_value + position_value,
                    'cash_value': cash_value,
                    'position_value': position_value,
                    'reliable': True,
                    'status': 'success'
                }
            else:
                logger.warning("Cannot calculate reliable portfolio value due to data issues")
                return {
                    'total_value': 0.0,
                    'cash_value': 0.0,
                    'position_value': 0.0,
                    'reliable': False,
                    'status': 'unreliable_data',
                    'balance_reliable': balance_reliable,
                    'positions_reliable': positions_reliable
                }
                
        except Exception as e:
            logger.error(f"Failed to calculate portfolio value: {e}")
            return {
                'total_value': 0.0,
                'cash_value': 0.0,
                'position_value': 0.0,
                'reliable': False,
                'status': 'error',
                'error': str(e)
            }
    
    def get_total_unrealized_pnl(self) -> Dict:
        """총 미실현 손익"""
        try:
            positions_meta = self.get_positions_with_meta()
            
            if positions_meta.get('status') in ['success', 'cached']:
                pnl = sum(pos.get('unrealized_pnl', 0.0) 
                         for pos in positions_meta['data'])
                
                return {
                    'unrealized_pnl': pnl,
                    'reliable': True,
                    'status': positions_meta['status'],
                    'cache_age': positions_meta.get('cache_age')
                }
            else:
                return {
                    'unrealized_pnl': 0.0,
                    'reliable': False,
                    'status': positions_meta.get('status', 'error'),
                    'error': positions_meta.get('error')
                }
                
        except Exception as e:
            logger.error(f"Failed to calculate unrealized PnL: {e}")
            return {
                'unrealized_pnl': 0.0,
                'reliable': False,
                'status': 'error',
                'error': str(e)
            }
    
    # ========== 캐시 관리 ==========
    
    def refresh_data(self) -> None:
        """데이터 강제 새로고침"""
        self.broker.force_refresh()
        logger.info(f"Data refreshed for account {self.account_id}")
    
    def sync_balance(self) -> None:
        """잔고 정보 동기화 (캐시 갱신)"""
        self.refresh_data()
    
    # ========== 기존 메서드들 (단순화) ==========
    
    def is_stock_account(self) -> bool:
        """주식 계좌 여부"""
        return self.account_type == AccountType.STOCK
    
    def is_futures_account(self) -> bool:
        """선물 계좌 여부"""
        return self.account_type == AccountType.FUTURES
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        balance = self.get_balance()
        positions = self.get_positions()
        
        return {
            'account_id': self.account_id,
            'name': self.name,
            'account_type': self.account_type.value,
            'is_virtual': self.is_virtual,
            'is_active': self.is_active,
            'balance': {
                'total': balance.get('total_balance', 0.0),
                'available': balance.get('available_balance', 0.0),
                'reliable': balance.get('reliable', False),
                'status': balance.get('status')
            },
            'positions_count': len(positions),
            'data_reliable': balance.get('reliable', False)
        }
    
    # ========== 디버깅 및 모니터링 ==========
    
    def get_data_health(self) -> Dict:
        """데이터 상태 진단"""
        balance = self.get_balance()
        positions_meta = self.get_positions_with_meta()
        
        return {
            'account_id': self.account_id,
            'is_active': self.is_active,
            'balance_status': balance.get('status'),
            'balance_reliable': balance.get('reliable', False),
            'balance_cache_age': balance.get('cache_age'),
            'positions_status': positions_meta.get('status'),
            'positions_reliable': positions_meta.get('status') in ['success', 'cached'],
            'positions_cache_age': positions_meta.get('cache_age'),
            'last_check': datetime.now().isoformat()
        }
    
    def force_error_state_reset(self) -> None:
        """에러 상태 강제 리셋 (비상용)"""
        logger.warning(f"Forcing error state reset for account {self.account_id}")
        self.broker.invalidate_cache()
        self.is_active = True