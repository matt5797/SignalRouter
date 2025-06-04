"""
TradeExecutor - 주문 실행 및 리스크 관리 클래스
시그널 기반 주문 실행과 기본적인 리스크 체크 제공
"""

import time
from typing import Dict, Optional
from datetime import datetime, date
import logging
from ..database import TradingDB
from ..models import TradeOrder, TransitionType, TradeStatus
from .account import Account

logger = logging.getLogger(__name__)


class TradeExecutor:
    """주문 실행 및 리스크 관리 클래스"""
    
    def __init__(self, db: TradingDB):
        self.db = db
        logger.info("TradeExecutor initialized")
    
    def execute_signal(self, account: Account, signal_data: Dict) -> bool:
        """시그널 실행 메인 로직"""
        try:
            # 전략 설정 조회
            strategy_config = self.db.get_strategy_by_token(signal_data.get('webhook_token', ''))
            if not strategy_config:
                logger.error(f"Strategy not found for token: {signal_data.get('webhook_token')}")
                return False
            
            # 포지션 전환 타입 결정
            current_position = self.db.get_position(account.account_id, signal_data['symbol'])
            transition_type = self._calculate_transition_type(current_position, signal_data)
            
            # 주문 생성
            trade_order = TradeOrder.from_signal(signal_data, account.account_id, transition_type)
            
            # 리스크 체크
            if not self._check_all_risks(account, trade_order, strategy_config):
                return False
            
            # 주문 실행
            return self._execute_trade_order(account, trade_order, strategy_config)
            
        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            return False
    
    def place_order(self, account: Account, order_data: Dict) -> str:
        """단일 주문 실행"""
        try:
            if order_data['action'] == 'BUY':
                order_id = account.broker.buy(
                    symbol=order_data['symbol'],
                    quantity=order_data['quantity'],
                    price=order_data.get('price')
                )
            else:  # SELL
                order_id = account.broker.sell(
                    symbol=order_data['symbol'],
                    quantity=order_data['quantity'],
                    price=order_data.get('price')
                )
            
            logger.info(f"Order placed: {order_id}")
            return order_id
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    def wait_for_fill(self, account: Account, order_id: str, timeout_seconds: int = 60) -> bool:
        """주문 체결 대기"""
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            try:
                status = account.broker.get_order_status(order_id)
                
                if status['status'] == 'FILLED':
                    logger.info(f"Order filled: {order_id}")
                    return True
                elif status['status'] == 'FAILED':
                    logger.error(f"Order failed: {order_id}")
                    return False
                
                time.sleep(2)  # 2초 간격으로 체크
                
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                time.sleep(5)
        
        logger.warning(f"Order wait timeout: {order_id}")
        return False
    
    def check_position_limit(self, account: Account, symbol: str, amount: float) -> bool:
        """포지션 한도 체크"""
        try:
            portfolio_value = account.get_total_portfolio_value()
            if portfolio_value == 0:
                return False
            
            position_ratio = amount / portfolio_value
            max_ratio = 0.3  # 기본 30% 제한
            
            if position_ratio > max_ratio:
                logger.warning(f"Position limit exceeded: {position_ratio:.2%} > {max_ratio:.2%}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to check position limit: {e}")
            return False
    
    def check_daily_loss_limit(self, account_id: str, amount: float) -> bool:
        """일일 손실 한도 체크"""
        try:
            daily_pnl = self.db.get_daily_pnl(account_id, date.today())
            if daily_pnl < -500000:  # 기본 50만원 손실 제한
                logger.warning(f"Daily loss limit reached: {daily_pnl}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to check daily loss limit: {e}")
            return True  # 체크 실패 시 거래 허용
    
    def calculate_position_size(self, account: Account, symbol: str, ratio: float) -> int:
        """포지션 크기 계산"""
        try:
            orderable = account.get_orderable_amount(symbol)
            max_amount = orderable['orderable_amount'] * ratio
            unit_price = orderable['unit_price']
            
            if unit_price > 0:
                quantity = int(max_amount / unit_price)
                return min(quantity, orderable['orderable_quantity'])
            
            return 0
        except Exception as e:
            logger.error(f"Failed to calculate position size: {e}")
            return 0
    
    def _execute_trade_order(self, account: Account, trade_order: TradeOrder, strategy_config: Dict) -> bool:
        """거래 주문 실행"""
        # 거래 기록 저장
        trade_data = {
            'account_id': account.account_id,
            'strategy_id': strategy_config['id'],
            'symbol': trade_order.symbol,
            'action': trade_order.action,
            'transition_type': trade_order.transition_type.value,
            'quantity': trade_order.quantity,
            'price': trade_order.price,
            'signal_time': datetime.now()
        }
        trade_id = self.db.save_trade(trade_data)
        
        try:
            # 포지션 전환이 필요한 경우
            if trade_order.transition_type == TransitionType.REVERSE:
                return self._execute_reverse_position(account, trade_order, trade_id)
            
            # 일반 주문 실행
            order_id = self.place_order(account, trade_order.to_broker_format())
            
            # 체결 대기
            filled = self.wait_for_fill(account, order_id)
            
            # 상태 업데이트
            fill_data = {
                'broker_order_id': order_id,
                'filled_quantity': trade_order.quantity if filled else 0,
                'avg_fill_price': trade_order.price,
                'fill_time': datetime.now()
            }
            status = TradeStatus.FILLED.value if filled else TradeStatus.FAILED.value
            self.db.update_trade_status(trade_id, status, fill_data)
            
            return filled
            
        except Exception as e:
            logger.error(f"Failed to execute trade order: {e}")
            self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, {})
            return False
    
    def _execute_reverse_position(self, account: Account, trade_order: TradeOrder, trade_id: int) -> bool:
        """포지션 방향 전환 실행"""
        try:
            # 1. 기존 포지션 청산
            current_position = account.get_position_for_symbol(trade_order.symbol)
            if current_position['quantity'] != 0:
                exit_action = 'SELL' if current_position['quantity'] > 0 else 'BUY'
                exit_order = {
                    'symbol': trade_order.symbol,
                    'action': exit_action,
                    'quantity': abs(current_position['quantity']),
                    'price': None  # 시장가로 청산
                }
                
                exit_order_id = self.place_order(account, exit_order)
                if not self.wait_for_fill(account, exit_order_id):
                    logger.error("Failed to exit existing position")
                    return False
            
            # 2. 새 포지션 진입
            entry_order_id = self.place_order(account, trade_order.to_broker_format())
            filled = self.wait_for_fill(account, entry_order_id)
            
            # 상태 업데이트
            fill_data = {
                'broker_order_id': entry_order_id,
                'filled_quantity': trade_order.quantity if filled else 0,
                'avg_fill_price': trade_order.price,
                'fill_time': datetime.now()
            }
            status = TradeStatus.FILLED.value if filled else TradeStatus.FAILED.value
            self.db.update_trade_status(trade_id, status, fill_data)
            
            return filled
            
        except Exception as e:
            logger.error(f"Failed to execute reverse position: {e}")
            return False
    
    def _calculate_transition_type(self, current_position: Dict, signal_data: Dict) -> TransitionType:
        """포지션 전환 타입 계산"""
        current_qty = current_position.get('quantity', 0)
        signal_action = signal_data['action'].upper()
        
        if current_qty == 0:
            return TransitionType.ENTRY
        
        # 현재 롱 포지션
        if current_qty > 0:
            if signal_action == 'SELL':
                return TransitionType.EXIT
            else:  # BUY - 추가 매수는 ENTRY로 처리
                return TransitionType.ENTRY
        
        # 현재 숏 포지션
        else:
            if signal_action == 'BUY':
                return TransitionType.EXIT
            else:  # SELL - 추가 매도는 ENTRY로 처리
                return TransitionType.ENTRY
    
    def _check_all_risks(self, account: Account, trade_order: TradeOrder, strategy_config: Dict) -> bool:
        """모든 리스크 체크"""
        # 계좌 활성화 상태
        if not account.is_active:
            logger.warning(f"Account {account.account_id} is inactive")
            return False
        
        # 거래 가능 금액 체크
        estimated_amount = trade_order.get_estimated_value()
        if estimated_amount > 0 and not account.can_trade(estimated_amount):
            logger.warning("Insufficient balance for trade")
            return False
        
        # 포지션 한도 체크
        if not self.check_position_limit(account, trade_order.symbol, estimated_amount):
            return False
        
        # 일일 손실 한도 체크
        if not self.check_daily_loss_limit(account.account_id, estimated_amount):
            return False
        
        return True