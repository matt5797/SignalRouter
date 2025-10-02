import time
import requests
import logging
from typing import Dict, Optional, Set
from datetime import datetime, time as dt_time, date

from .auth import KisAuth
from .auth_factory import AuthFactory
from .secrets import SecretLoader

logger = logging.getLogger(__name__)


class KisApiError(Exception):
    pass


class KisBroker:
    TR_MAPPING = {
        ('FUTURES', 'DAY', False, 'ORDER'): 'TTTO1101U',
        ('FUTURES', 'NIGHT', False, 'ORDER'): 'TTTN1101U',
        ('FUTURES', 'DAY', True, 'ORDER'): 'VTTO1101U',
        
        ('FUTURES', 'DAY', False, 'INQUIRY'): 'TTTO5201R',
        ('FUTURES', 'DAY', True, 'INQUIRY'): 'VTTO5201R',
        ('FUTURES', 'NIGHT', False, 'INQUIRY'): 'STTN5201R',
    }
    
    _holiday_cache = {}
    _holiday_cache_date = None
    
    def __init__(self, account_id: str, secret_identifier: str = None, 
                 is_virtual: bool = False, token_storage_path: str = "secrets/tokens/"):
        self.account_id = account_id
        self.secret_identifier = secret_identifier or account_id
        self.is_virtual = is_virtual
        
        self.auth = AuthFactory.create_from_secret(
            self.secret_identifier, 
            token_storage_path
        )
        
        self.secret_data = SecretLoader.load_secret(self.secret_identifier)
        self.account_type = self._get_account_type()
        
        logger.info(f"KisBroker initialized: {account_id} (Type: {self.account_type}, Virtual: {is_virtual})")
    
    def buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        if self.account_type == "FUTURES":
            return self._futures_buy(symbol, quantity, price)
        else:
            raise KisApiError(f"Unsupported account type: {self.account_type}")
    
    def sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        if self.account_type == "FUTURES":
            return self._futures_sell(symbol, quantity, price)
        else:
            raise KisApiError(f"Unsupported account type: {self.account_type}")
    
    def get_order_status(self, order_id: str) -> Dict:
        if not order_id or order_id == 'unknown':
            return {
                'data': {'status': 'INVALID', 'order_id': order_id},
                'status': 'error',
                'error': 'Invalid order ID'
            }
        
        try:
            if self.account_type == "FUTURES":
                result = self._futures_order_status(order_id)
            else:
                result = {'status': 'UNKNOWN', 'order_id': order_id}
            
            return {
                'data': result,
                'status': 'success',
                'error': None
            }
        
        except Exception as e:
            logger.error(f"Get order status failed: {e}")
            return {
                'data': {'status': 'ERROR', 'order_id': order_id},
                'status': 'error',
                'error': str(e)
            }
    
    def _futures_buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        tr_id = self._get_tr_id('ORDER')
        
        params = {
            "ORD_PRCS_DVSN_CD": "02",
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "SLL_BUY_DVSN_CD": "02",
            "SHTN_PDNO": symbol,
            "ORD_QTY": str(quantity),
            "UNIT_PRICE": str(int(price)) if price else "0",
            "ORD_DVSN_CD": "01" if price else "02"
        }
        
        result = self._call_kis_api(
            "/uapi/domestic-futureoption/v1/trading/order", 
            tr_id, 
            params
        )
        
        order_id = result.get('output', {}).get('ODNO', 'unknown')
        logger.info(f"Futures buy order: {order_id}")
        return order_id
    
    def _futures_sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        tr_id = self._get_tr_id('ORDER')
        
        params = {
            "ORD_PRCS_DVSN_CD": "02",
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "SLL_BUY_DVSN_CD": "01",
            "SHTN_PDNO": symbol,
            "ORD_QTY": str(quantity),
            "UNIT_PRICE": str(int(price)) if price else "0",
            "ORD_DVSN_CD": "01" if price else "02"
        }
        
        result = self._call_kis_api(
            "/uapi/domestic-futureoption/v1/trading/order", 
            tr_id, 
            params
        )
        
        order_id = result.get('output', {}).get('ODNO', 'unknown')
        logger.info(f"Futures sell order: {order_id}")
        return order_id
    
    def _futures_order_status(self, order_id: str) -> Dict:
        tr_id = self._get_tr_id('INQUIRY')
        
        today = datetime.today().strftime("%Y%m%d")
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "STRT_ORD_DT": today,
            "END_ORD_DT": today,
            "SLL_BUY_DVSN_CD": "00",
            "CCLD_NCCS_DVSN": "00",
            "SORT_SQN": "DS",
            "STRT_ODNO": "",
            "PDNO": "",
            "MKET_ID_CD": "",
            "FUOP_DVSN_CD": "",
            "SCRN_DVSN": "02",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        result = self._call_kis_api(
            "/uapi/domestic-futureoption/v1/trading/inquire-ngt-ccnl", 
            tr_id, 
            params, 
            method="GET"
        )
        
        orders = result.get('output1', [])

        try:
            search_order_num = int(order_id.strip().lstrip('0') or '0')
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid order_id format: {order_id}, error: {e}")
            return {'status': 'INVALID', 'order_id': order_id}
        
        for order in orders:
            found_odno = order.get('odno', '').strip()
            
            try:
                found_order_num = int(found_odno.lstrip('0') or '0')
                
                if found_order_num == search_order_num:
                    return {
                        'status': self._map_futures_status(order.get('ord_dvsn_name', '')),
                        'order_id': order_id,
                        'symbol': order.get('pdno', ''),
                        'quantity': int(order.get('ord_qty', 0)),
                        'filled_quantity': int(order.get('tot_ccld_qty', 0)),
                        'price': float(order.get('avg_idx', 0)),
                        'order_time': order.get('ord_tmd', ''),
                        'side': 'BUY' if order.get('sll_buy_dvsn_cd') == '02' else 'SELL'
                    }
                    
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse odno '{found_odno}': {e}")
                continue
        
        return {'status': 'NOT_FOUND', 'order_id': order_id}
    
    def _get_tr_id(self, action: str, force_session: str = None) -> str:
        if force_session:
            session = force_session
        else:
            session = self._get_market_session()
        
        if session == 'CLOSED' and not force_session:
            logger.warning("Market is closed. Using NIGHT session as fallback.")
            session = 'NIGHT'
        
        key = (self.account_type, session, self.is_virtual, action)
        tr_id = self.TR_MAPPING.get(key)
        
        if not tr_id:
            fallback_key = (self.account_type, 'NIGHT', self.is_virtual, action)
            tr_id = self.TR_MAPPING.get(fallback_key)
            logger.warning(f"TR ID not found for {key}, using fallback: {tr_id}")
        
        if not tr_id:
            raise KisApiError(f"No TR ID found for {key}")
        
        return tr_id
    
    def _get_market_session(self, target_time: datetime = None) -> str:
        if target_time is None:
            target_time = datetime.now()
        
        if target_time.weekday() >= 5:
            return 'CLOSED'
        
        current_time = target_time.time()
        
        if dt_time(9, 0) <= current_time <= dt_time(15, 30):
            return 'DAY'
        
        if current_time >= dt_time(18, 0) or current_time <= dt_time(6, 0):
            return 'NIGHT'
        
        return 'CLOSED'
    
    def _call_kis_api(self, url_path: str, tr_id: str, params: Dict, 
                      method: str = "POST", tr_cont: str = "") -> Dict:
        try:
            url = f"{self.auth.base_url}{url_path}"
            headers = self.auth.get_request_headers(tr_id, tr_cont)
            
            if method.upper() == "POST":
                response = requests.post(url, json=params, headers=headers, timeout=30)
            else:
                response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code != 200:
                raise KisApiError(f"HTTP {response.status_code}: API call failed")
            
            result = response.json()
            
            rt_cd = result.get('rt_cd', '1')
            if rt_cd != '0':
                error_code = result.get('msg_cd', 'UNKNOWN')
                error_msg = result.get('msg1', 'Unknown error')
                raise KisApiError(f"[{error_code}] {error_msg}")
            
            return result
        
        except requests.exceptions.Timeout:
            raise KisApiError("API call timeout")
        except requests.exceptions.ConnectionError:
            raise KisApiError("API connection failed")
        except Exception as e:
            if isinstance(e, KisApiError):
                raise
            logger.error(f"KIS API call failed: {e}")
            raise KisApiError(f"API call failed: {str(e)}")
    
    def _get_account_type(self) -> str:
        account_type = self.secret_data.get('account_type', '').upper()
        if account_type in ['STOCK', 'FUTURES', 'OVERSEAS']:
            return account_type
        
        account_num = self.secret_data.get('account_number', '')
        if account_num.startswith('5'):
            return 'FUTURES'
        else:
            return 'STOCK'
    
    def _map_futures_status(self, status_name: str) -> str:
        status_map = {
            '': 'PENDING',
            '': 'FILLED',
            '': 'REJECTED',
            '': 'CANCELLED',
            '': 'PARTIAL_FILLED'
        }
        return status_map.get(status_name, 'UNKNOWN')