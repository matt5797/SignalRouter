"""
Broker - PyKis API 래퍼 클래스
한국투자증권 API 호출을 단순화하고 표준화된 인터페이스 제공
"""

from typing import Dict, List, Optional
from decimal import Decimal
import logging
from pykis import PyKis, KisAuth, KisStock, KisAccount, KisOrder

logger = logging.getLogger(__name__)


class Broker:
    """PyKis API 래퍼 클래스"""
    
    def __init__(self, account_id: str, secret_file_path: str, is_virtual: bool = False):
        self.account_id = account_id
        self.secret_file_path = secret_file_path
        self.is_virtual = is_virtual
        self._kis = self._init_pykis()
        logger.info(f"Broker initialized for account {account_id}")
    
    def _init_pykis(self) -> PyKis:
        """PyKis 객체 초기화"""
        try:
            if self.is_virtual:
                # 모의투자용 초기화
                return PyKis(self.secret_file_path, keep_token=True)
            else:
                # 실전투자용 초기화
                return PyKis(self.secret_file_path, keep_token=True)
        except Exception as e:
            logger.error(f"Failed to initialize PyKis: {e}")
            raise
    
    def buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """매수 주문 실행"""
        try:
            stock = self._create_stock_object(symbol)
            if price is None:
                # 시장가 매수
                order = stock.buy(qty=quantity)
            else:
                # 지정가 매수
                order = stock.buy(price=price, qty=quantity)
            
            logger.info(f"Buy order placed: {symbol} x{quantity} @ {price or 'MARKET'}")
            return self._extract_order_id(order)
        except Exception as e:
            logger.error(f"Failed to place buy order: {e}")
            raise
    
    def sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """매도 주문 실행"""
        try:
            stock = self._create_stock_object(symbol)
            if price is None:
                # 시장가 매도 (전량 또는 지정 수량)
                if quantity == 0:
                    order = stock.sell()  # 전량 매도
                else:
                    # PyKis는 지정 수량 시장가 매도를 위해 가격을 설정해야 할 수 있음
                    current_price = stock.quote().price
                    order = stock.sell(price=current_price * 0.9, qty=quantity)  # 현재가 대비 10% 하락가로 시장가 효과
            else:
                # 지정가 매도
                order = stock.sell(price=price, qty=quantity)
            
            logger.info(f"Sell order placed: {symbol} x{quantity} @ {price or 'MARKET'}")
            return self._extract_order_id(order)
        except Exception as e:
            logger.error(f"Failed to place sell order: {e}")
            raise
    
    def get_positions(self) -> List[Dict]:
        """보유 포지션 조회"""
        try:
            account = self._kis.account()
            balance = account.balance()
            
            positions = []
            for stock in balance.stocks:
                positions.append({
                    'symbol': stock.symbol,
                    'quantity': int(stock.qty),
                    'avg_price': float(stock.price),
                    'current_value': float(stock.amount),
                    'unrealized_pnl': float(stock.profit)
                })
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_balance(self) -> Dict:
        """계좌 잔고 조회"""
        try:
            account = self._kis.account()
            balance = account.balance()
            
            # KRW 예수금 정보 추출
            krw_deposit = balance.deposits.get('KRW')
            if krw_deposit:
                return {
                    'total_balance': float(krw_deposit.amount),
                    'available_balance': float(krw_deposit.amount),  # PyKis에서 매수가능금액 별도 조회 필요
                    'currency': 'KRW'
                }
            return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
    
    def get_order_status(self, order_id: str) -> Dict:
        """주문 상태 조회"""
        try:
            # PyKis의 미체결 주문 조회를 통해 상태 확인
            account = self._kis.account()
            pending_orders = account.pending_orders()
            
            for order in pending_orders.orders:
                if self._extract_order_id(order) == order_id:
                    return {
                        'order_id': order_id,
                        'status': 'PENDING',
                        'filled_quantity': int(order.executed_qty),
                        'remaining_quantity': int(order.qty) - int(order.executed_qty)
                    }
            
            # 미체결에 없으면 체결 완료 또는 취소된 것으로 간주
            return {'order_id': order_id, 'status': 'FILLED', 'filled_quantity': 0, 'remaining_quantity': 0}
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return {'order_id': order_id, 'status': 'UNKNOWN', 'filled_quantity': 0, 'remaining_quantity': 0}
    
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        try:
            # PyKis의 주문 취소 기능 (order 객체가 필요)
            # 간단한 구현을 위해 모든 미체결 주문을 조회하여 해당 주문 찾아서 취소
            account = self._kis.account()
            pending_orders = account.pending_orders()
            
            for order in pending_orders.orders:
                if self._extract_order_id(order) == order_id:
                    order.cancel()
                    logger.info(f"Order cancelled: {order_id}")
                    return True
            
            logger.warning(f"Order not found for cancellation: {order_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False
    
    def _create_stock_object(self, symbol: str) -> KisStock:
        """종목 객체 생성"""
        return self._kis.stock(symbol)
    
    def _extract_order_id(self, order: KisOrder) -> str:
        """주문 객체에서 주문 ID 추출"""
        # PyKis Order 객체의 구조에 따라 조정 필요
        if hasattr(order, 'order_number'):
            return f"{order.order_number.branch}-{order.order_number.number}"
        return str(id(order))  # 임시 방편
    
    def get_orderable_amount(self, symbol: str, price: Optional[float] = None) -> Dict:
        """매수 가능 금액/수량 조회"""
        try:
            stock = self._create_stock_object(symbol)
            orderable = stock.orderable_amount(price=price) if price else stock.orderable_amount()
            
            return {
                'symbol': symbol,
                'orderable_quantity': int(orderable.qty),
                'orderable_amount': float(orderable.amount),
                'unit_price': float(orderable.unit_price)
            }
        except Exception as e:
            logger.error(f"Failed to get orderable amount: {e}")
            return {'symbol': symbol, 'orderable_quantity': 0, 'orderable_amount': 0.0, 'unit_price': 0.0}