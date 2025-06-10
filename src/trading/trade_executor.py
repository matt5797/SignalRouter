"""
TradeExecutor - 주문 실행 및 리스크 관리 클래스
시그널 기반 주문 실행과 기본적인 리스크 체크 제공
"""

import time
from typing import Dict, Optional, Tuple
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
    
    def wait_for_fill(self, account: Account, order_id: str, timeout_seconds: int = 60) -> Tuple[bool, Dict]:
        """주문 체결 대기 - 체결 정보도 함께 반환"""
        start_time = time.time()
        last_status = {}
        
        while time.time() - start_time < timeout_seconds:
            try:
                status = account.broker.get_order_status(order_id)
                last_status = status
                
                if status['status'] == 'FILLED':
                    logger.info(f"Order filled: {order_id}")
                    return True, status
                elif status['status'] in ['FAILED', 'REJECTED', 'CANCELLED']:
                    logger.error(f"Order failed: {order_id} - {status['status']}")
                    return False, status
                
                time.sleep(2)  # 2초 간격으로 체크
                
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                time.sleep(5)
        
        logger.warning(f"Order wait timeout: {order_id}")
        return False, last_status
    
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
            filled, fill_info = self.wait_for_fill(account, order_id)
            
            # 상태 업데이트
            fill_data = {
                'broker_order_id': order_id,
                'filled_quantity': fill_info.get('filled_quantity', trade_order.quantity if filled else 0),
                'avg_fill_price': fill_info.get('avg_fill_price', trade_order.price),
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
        """포지션 방향 전환 실행 - 완성된 버전"""
        logger.info(f"Starting position reversal for {trade_order.symbol}")
        
        try:
            # 1단계: 기존 포지션 확인 및 청산
            current_position = account.get_position_for_symbol(trade_order.symbol)
            exit_success = False
            exit_order_id = None
            
            if current_position['quantity'] != 0:
                logger.info(f"Existing position found: {current_position['quantity']} shares")
                
                # 청산 주문 생성
                exit_action = 'SELL' if current_position['quantity'] > 0 else 'BUY'
                exit_order = {
                    'symbol': trade_order.symbol,
                    'action': exit_action,
                    'quantity': abs(current_position['quantity']),
                    'price': None  # 시장가로 확실한 청산
                }
                
                # 청산 주문 실행
                try:
                    exit_order_id = self.place_order(account, exit_order)
                    logger.info(f"Exit order placed: {exit_order_id}")
                    
                    # 청산 체결 대기
                    exit_filled, exit_fill_info = self.wait_for_fill(account, exit_order_id, timeout_seconds=120)
                    
                    if exit_filled:
                        exit_success = True
                        logger.info(f"Position successfully closed: {exit_order_id}")
                    else:
                        # 부분 체결 상황 처리
                        filled_qty = exit_fill_info.get('filled_quantity', 0)
                        if filled_qty > 0:
                            logger.warning(f"Partial exit fill: {filled_qty}/{exit_order['quantity']}")
                            # 부분 체결이라도 진행 (남은 포지션은 추후 처리)
                            exit_success = True
                        else:
                            logger.error(f"Exit order completely failed: {exit_order_id}")
                            # 청산 실패 시 포지션 전환 중단
                            self._update_failed_reverse_position(trade_id, "Exit order failed")
                            return False
                            
                except Exception as e:
                    logger.error(f"Failed to place exit order: {e}")
                    self._update_failed_reverse_position(trade_id, f"Exit order placement failed: {e}")
                    return False
            else:
                logger.info("No existing position to close")
                exit_success = True
            
            # 2단계: 새 포지션 진입 (청산 성공한 경우만)
            if exit_success:
                # 잠시 대기 (시장 안정화)
                time.sleep(1)
                
                try:
                    entry_order_id = self.place_order(account, trade_order.to_broker_format())
                    logger.info(f"Entry order placed: {entry_order_id}")
                    
                    # 진입 체결 대기
                    entry_filled, entry_fill_info = self.wait_for_fill(account, entry_order_id)
                    
                    # 최종 결과 업데이트
                    if entry_filled:
                        logger.info(f"Position reversal completed successfully")
                        fill_data = {
                            'broker_order_id': entry_order_id,
                            'filled_quantity': entry_fill_info.get('filled_quantity', trade_order.quantity),
                            'avg_fill_price': entry_fill_info.get('avg_fill_price', trade_order.price),
                            'fill_time': datetime.now(),
                            'exit_order_id': exit_order_id  # 청산 주문 ID도 기록
                        }
                        self.db.update_trade_status(trade_id, TradeStatus.FILLED.value, fill_data)
                        return True
                    else:
                        # 진입 실패 - 청산은 되었지만 새 포지션 진입 실패
                        logger.error(f"Entry order failed after successful exit")
                        fill_data = {
                            'broker_order_id': entry_order_id,
                            'filled_quantity': 0,
                            'avg_fill_price': 0,
                            'fill_time': datetime.now(),
                            'exit_order_id': exit_order_id,
                            'error': 'Entry failed after exit'
                        }
                        self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, fill_data)
                        return False
                        
                except Exception as e:
                    logger.error(f"Failed to place entry order: {e}")
                    # 청산은 성공했지만 진입 실패
                    self._update_failed_reverse_position(
                        trade_id, f"Entry order failed: {e}", exit_order_id
                    )
                    return False
            
        except Exception as e:
            logger.error(f"Unexpected error in position reversal: {e}")
            self._update_failed_reverse_position(trade_id, f"Unexpected error: {e}")
            return False
    
    def _update_failed_reverse_position(self, trade_id: int, error_msg: str, exit_order_id: str = None) -> None:
        """포지션 전환 실패 시 상태 업데이트"""
        fill_data = {
            'broker_order_id': 'failed',
            'filled_quantity': 0,
            'avg_fill_price': 0,
            'fill_time': datetime.now(),
            'error': error_msg
        }
        
        if exit_order_id:
            fill_data['exit_order_id'] = exit_order_id
            
        self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, fill_data)
    
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
    
    def force_close_position(self, account: Account, symbol: str) -> bool:
        """강제 포지션 청산 (비상 시 사용)"""
        try:
            current_position = account.get_position_for_symbol(symbol)
            if current_position['quantity'] == 0:
                logger.info(f"No position to close for {symbol}")
                return True
            
            # 시장가로 강제 청산
            action = 'SELL' if current_position['quantity'] > 0 else 'BUY'
            order_data = {
                'symbol': symbol,
                'action': action,
                'quantity': abs(current_position['quantity']),
                'price': None  # 시장가
            }
            
            order_id = self.place_order(account, order_data)
            filled, _ = self.wait_for_fill(account, order_id, timeout_seconds=30)
            
            if filled:
                logger.info(f"Position force closed: {symbol}")
            else:
                logger.error(f"Failed to force close position: {symbol}")
            
            return filled
            
        except Exception as e:
            logger.error(f"Error in force close position: {e}")
            return False