"""
PositionManager - 포지션 상태 추적 및 관리 클래스
포지션 전환 로직과 포트폴리오 요약 기능 제공
"""

from typing import Dict, List
import logging
from datetime import datetime
from .account import Account
from ..database import TradingDB
from ..models import Position, TransitionType

logger = logging.getLogger(__name__)


class PositionManager:
    """포지션 상태 추적 및 관리 클래스"""
    
    def __init__(self, db: TradingDB, accounts: Dict[str, Account]):
        self.db = db
        self.accounts = accounts
        logger.info("PositionManager initialized")
    
    def get_current_position(self, account_id: str, symbol: str) -> Dict:
        """현재 포지션 조회"""
        try:
            position_data = self.accounts[account_id].get_position_for_symbol(symbol)
            
            # Position 객체로 변환하여 추가 메서드 활용 가능
            if position_data['quantity'] != 0:
                position = Position(
                    account_id=position_data['account_id'],
                    symbol=position_data['symbol'],
                    quantity=position_data['quantity'],
                    avg_price=position_data['avg_price'],
                    last_updated=datetime.fromisoformat(position_data.get('last_updated', datetime.now().isoformat()))
                )
                return position.to_dict()
            
            # 포지션이 없는 경우 빈 포지션 반환
            return {
                'account_id': account_id,
                'symbol': symbol,
                'quantity': 0,
                'avg_price': 0.0,
                'position_type': 'FLAT'
            }
            
        except Exception as e:
            logger.error(f"Failed to get current position: {e}")
            return {'account_id': account_id, 'symbol': symbol, 'quantity': 0, 'avg_price': 0.0}
    
    def calculate_transition_type(self, current: Dict, target: Dict) -> TransitionType:
        """포지션 전환 타입 계산"""
        current_qty = current.get('quantity', 0)
        target_action = target.get('action', '').upper()
        target_qty = target.get('quantity', 0)
        
        # 현재 포지션이 없는 경우 - 신규 진입
        if current_qty == 0:
            return TransitionType.ENTRY
        
        # 현재 롱 포지션
        if current_qty > 0:
            if target_action == 'SELL':
                if target_qty >= current_qty:
                    # 전량 또는 초과 매도 - 청산 또는 역전
                    return TransitionType.REVERSE if target_qty > current_qty else TransitionType.EXIT
                else:
                    # 부분 매도 - 청산
                    return TransitionType.EXIT
            else:  # BUY
                # 추가 매수 - 진입
                return TransitionType.ENTRY
        
        # 현재 숏 포지션
        else:
            if target_action == 'BUY':
                if target_qty >= abs(current_qty):
                    # 전량 또는 초과 매수 - 청산 또는 역전
                    return TransitionType.REVERSE if target_qty > abs(current_qty) else TransitionType.EXIT
                else:
                    # 부분 매수 - 청산
                    return TransitionType.EXIT
            else:  # SELL
                # 추가 매도 - 진입
                return TransitionType.ENTRY
    
    def update_position_after_trade(self, trade_data: Dict) -> None:
        """거래 후 포지션 업데이트"""
        try:
            account_id = trade_data['account_id']
            symbol = trade_data['symbol']
            action = trade_data['action']
            filled_qty = trade_data.get('filled_quantity', 0)
            avg_fill_price = trade_data.get('avg_fill_price', 0.0)
            
            if filled_qty == 0:
                logger.warning("No filled quantity to update position")
                return
            
            # 현재 포지션 조회
            current_position = self.db.get_position(account_id, symbol)
            current_qty = current_position.get('quantity', 0)
            current_avg_price = current_position.get('avg_price', 0.0)
            
            # 포지션 계산
            if action.upper() == 'BUY':
                new_qty = current_qty + filled_qty
            else:  # SELL
                new_qty = current_qty - filled_qty
            
            # 평균 단가 계산
            if new_qty == 0:
                new_avg_price = 0.0
            elif current_qty == 0:
                new_avg_price = avg_fill_price
            elif (current_qty > 0 and action.upper() == 'BUY') or (current_qty < 0 and action.upper() == 'SELL'):
                # 같은 방향 추가 매매 - 평균 단가 계산
                total_cost = (abs(current_qty) * current_avg_price) + (filled_qty * avg_fill_price)
                total_qty = abs(current_qty) + filled_qty
                new_avg_price = total_cost / total_qty if total_qty > 0 else 0.0
            else:
                # 반대 방향 매매 - 기존 평균가 유지 또는 새 평균가
                new_avg_price = avg_fill_price if abs(new_qty) > abs(current_qty) else current_avg_price
            
            # 데이터베이스 업데이트
            self.db.update_position(account_id, symbol, new_qty, new_avg_price)
            logger.info(f"Position updated: {symbol} {current_qty} -> {new_qty} @ {new_avg_price}")
            
        except Exception as e:
            logger.error(f"Failed to update position after trade: {e}")
    
    def get_portfolio_summary(self, account_id: str) -> Dict:
        """포트폴리오 요약 정보"""
        try:
            positions = self.db.get_all_positions(account_id)
            
            summary = {
                'account_id': account_id,
                'total_positions': len(positions),
                'long_positions': 0,
                'short_positions': 0,
                'symbols': [],
                'total_market_value': 0.0,
                'total_cost_basis': 0.0,
                'positions_detail': []
            }
            
            for pos_data in positions:
                position = Position(
                    account_id=pos_data['account_id'],
                    symbol=pos_data['symbol'],
                    quantity=pos_data['quantity'],
                    avg_price=pos_data['avg_price']
                )
                
                # 포지션 분류
                if position.is_long():
                    summary['long_positions'] += 1
                elif position.is_short():
                    summary['short_positions'] += 1
                
                # 종목 리스트
                summary['symbols'].append(position.symbol)
                
                # 가치 계산 (현재가가 없으므로 평균가 기준)
                market_value = abs(position.quantity) * position.avg_price
                cost_basis = abs(position.quantity) * position.avg_price
                
                summary['total_market_value'] += market_value
                summary['total_cost_basis'] += cost_basis
                
                # 상세 정보
                position_detail = position.to_dict()
                position_detail.update({
                    'market_value': market_value,
                    'cost_basis': cost_basis
                })
                summary['positions_detail'].append(position_detail)
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get portfolio summary: {e}")
            return {
                'account_id': account_id,
                'total_positions': 0,
                'long_positions': 0,
                'short_positions': 0,
                'symbols': [],
                'total_market_value': 0.0,
                'total_cost_basis': 0.0,
                'positions_detail': []
            }
    
    def get_position_exposure(self, account_id: str, symbol: str) -> Dict:
        """특정 종목의 익스포저 정보"""
        try:
            position = self.get_current_position(account_id, symbol)
            
            if position['quantity'] == 0:
                return {
                    'symbol': symbol,
                    'exposure': 0.0,
                    'direction': 'FLAT',
                    'quantity': 0,
                    'avg_price': 0.0
                }
            
            exposure = abs(position['quantity']) * position['avg_price']
            direction = 'LONG' if position['quantity'] > 0 else 'SHORT'
            
            return {
                'symbol': symbol,
                'exposure': exposure,
                'direction': direction,
                'quantity': position['quantity'],
                'avg_price': position['avg_price']
            }
            
        except Exception as e:
            logger.error(f"Failed to get position exposure: {e}")
            return {'symbol': symbol, 'exposure': 0.0, 'direction': 'FLAT', 'quantity': 0, 'avg_price': 0.0}
    
    def is_position_flat(self, account_id: str, symbol: str) -> bool:
        """포지션이 플랫(없음) 상태인지 확인"""
        position = self.get_current_position(account_id, symbol)
        return position['quantity'] == 0
    
    def get_total_exposure(self, account_id: str) -> float:
        """계좌의 총 익스포저 계산"""
        try:
            summary = self.get_portfolio_summary(account_id)
            return summary['total_market_value']
        except Exception as e:
            logger.error(f"Failed to calculate total exposure: {e}")
            return 0.0