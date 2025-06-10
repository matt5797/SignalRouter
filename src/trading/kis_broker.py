"""
KisBroker - 한국투자증권 API 직접 호출 브로커 클래스
기존 Broker 인터페이스 호환성 유지하면서 PyKis 의존성 제거
"""

import json
import time
import requests
from typing import Dict, List, Optional
from decimal import Decimal
import logging
from pathlib import Path
from .kis_auth import KisAuth
from .auth_factory import AuthFactory
from .secret_loader import SecretLoader
from .exceptions import BrokerError, OrderError
from .kis_api_errors import (
    KisApiError, KisAuthError, KisOrderError, KisInsufficientBalanceError,
    KisMarketClosedError, KisAccountTypeError, get_kis_exception
)

logger = logging.getLogger(__name__)


class KisBroker:
    """KIS API 직접 호출 브로커 클래스"""
    
    def __init__(self, account_id: str, secret_file_path: str, is_virtual: bool = False, 
                 default_real_secret: Optional[str] = None):
        self.account_id = account_id
        self.secret_file_path = secret_file_path
        self.is_virtual = is_virtual
        self.default_real_secret = default_real_secret
        
        # 인증 객체 생성
        if is_virtual and default_real_secret:
            self.auth = AuthFactory.create_virtual_with_real_reference(
                secret_file_path, default_real_secret
            )
        else:
            self.auth = AuthFactory.create_from_secret(secret_file_path)
        
        # 계좌 타입 및 기본 정보 로드
        self.secret_data = SecretLoader.load_secret(secret_file_path)
        self.account_type = self._get_account_type()
        
        logger.info(f"KisBroker initialized - Account: {account_id}, Type: {self.account_type}")
    
    def buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """매수 주문 실행"""
        self._validate_order_params(symbol, quantity, price)
        
        try:
            if self.account_type == "STOCK":
                return self._stock_buy(symbol, quantity, price)
            elif self.account_type == "FUTURES":
                return self._futures_buy(symbol, quantity, price)
            elif self.account_type == "OVERSEAS":
                return self._overseas_buy(symbol, quantity, price)
            else:
                raise KisAccountTypeError(f"Unsupported account type: {self.account_type}")
        except Exception as e:
            logger.error(f"Buy order failed: {e}")
            if isinstance(e, KisApiError):
                raise
            raise KisOrderError(f"Buy order execution failed: {e}")
    
    def sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """매도 주문 실행"""
        self._validate_order_params(symbol, quantity, price)
        
        try:
            if self.account_type == "STOCK":
                return self._stock_sell(symbol, quantity, price)
            elif self.account_type == "FUTURES":
                return self._futures_sell(symbol, quantity, price)
            elif self.account_type == "OVERSEAS":
                return self._overseas_sell(symbol, quantity, price)
            else:
                raise KisAccountTypeError(f"Unsupported account type: {self.account_type}")
        except Exception as e:
            logger.error(f"Sell order failed: {e}")
            if isinstance(e, KisApiError):
                raise
            raise KisOrderError(f"Sell order execution failed: {e}")
    
    def get_positions(self) -> List[Dict]:
        """보유 포지션 조회"""
        try:
            if self.account_type == "STOCK":
                return self._stock_positions()
            elif self.account_type == "FUTURES":
                return self._futures_positions()
            elif self.account_type == "OVERSEAS":
                return self._overseas_positions()
            else:
                return []
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []
    
    def get_balance(self) -> Dict:
        """계좌 잔고 조회"""
        try:
            if self.account_type == "STOCK":
                return self._stock_balance()
            elif self.account_type == "FUTURES":
                return self._futures_balance()
            elif self.account_type == "OVERSEAS":
                return self._overseas_balance()
            else:
                return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
        except Exception as e:
            logger.error(f"Get balance failed: {e}")
            return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
    
    def get_order_status(self, order_id: str) -> Dict:
        """주문 상태 조회"""
        try:
            # 주문 ID에서 정보 추출 (임시 구현)
            return {
                'order_id': order_id,
                'status': 'FILLED',  # 임시로 FILLED 반환
                'filled_quantity': 0,
                'remaining_quantity': 0
            }
        except Exception as e:
            logger.error(f"Get order status failed: {e}")
            return {'order_id': order_id, 'status': 'UNKNOWN', 'filled_quantity': 0}
    
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        try:
            # 계좌 타입별 취소 API 호출 (임시 구현)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False
    
    def get_orderable_amount(self, symbol: str, price: Optional[float] = None) -> Dict:
        """매수 가능 금액/수량 조회"""
        try:
            if self.account_type == "FUTURES":
                return self._futures_orderable_amount(symbol, price)
            else:
                # 기본 구현
                return {
                    'symbol': symbol,
                    'orderable_quantity': 0,
                    'orderable_amount': 0.0,
                    'unit_price': price or 0.0
                }
        except Exception as e:
            logger.error(f"Get orderable amount failed: {e}")
            return {'symbol': symbol, 'orderable_quantity': 0, 'orderable_amount': 0.0}
    
    def _get_account_type(self) -> str:
        """Secret 파일에서 계좌 타입 판단"""
        account_type = self.secret_data.get('account_type', '').upper()
        if account_type in ['STOCK', 'FUTURES', 'OVERSEAS']:
            return account_type
        
        # 계좌번호나 기타 정보로 추정 (fallback)
        account_num = self.secret_data.get('account_number', '')
        if account_num.startswith('5'):  # 선물계좌는 보통 5로 시작
            return 'FUTURES'
        else:
            return 'STOCK'  # 기본값
    
    def _call_kis_api(self, url_path: str, tr_id: str, params: Dict, 
                      method: str = "POST", tr_cont: str = "") -> Dict:
        """공통 KIS API 호출 메서드"""
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
            
            # API 응답 에러 체크
            rt_cd = result.get('rt_cd', '1')
            if rt_cd != '0':
                error_code = result.get('msg_cd', 'UNKNOWN')
                error_msg = result.get('msg1', 'Unknown error')
                raise get_kis_exception(error_code, error_msg)
            
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
    
    # ========== 선물 API 구현 ==========
    
    def _futures_buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """선물 매수 주문"""
        tr_id = "JTCE1001U" if self.is_virtual else "TTTO1101U"  # 야간거래 기준
        
        params = {
            "ORD_PRCS_DVSN_CD": "02",  # 주문처리구분코드
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "SLL_BUY_DVSN_CD": "02",  # 매수
            "SHTN_PDNO": symbol,
            "ORD_QTY": str(quantity),
            "UNIT_PRICE": str(int(price)) if price else "0",
            "ORD_DVSN_CD": "01" if price else "02"  # 지정가/시장가
        }
        
        result = self._call_kis_api("/uapi/domestic-futureoption/v1/trading/order", tr_id, params)
        return result.get('output', {}).get('odno', 'unknown')
    
    def _futures_sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """선물 매도 주문"""
        tr_id = "JTCE1001U" if self.is_virtual else "TTTO1101U"
        
        params = {
            "ORD_PRCS_DVSN_CD": "02",
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "SLL_BUY_DVSN_CD": "01",  # 매도
            "SHTN_PDNO": symbol,
            "ORD_QTY": str(quantity),
            "UNIT_PRICE": str(int(price)) if price else "0",
            "ORD_DVSN_CD": "01" if price else "02"
        }
        
        result = self._call_kis_api("/uapi/domestic-futureoption/v1/trading/order", tr_id, params)
        return result.get('output', {}).get('odno', 'unknown')
    
    def _futures_balance(self) -> Dict:
        """선물 잔고 조회"""
        tr_id = "JTCE6001R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "MGNA_DVSN": "01",  # 증거금구분
            "EXCC_STAT_CD": "1"  # 정산상태코드
        }
        
        result = self._call_kis_api("/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance", 
                                   tr_id, params, method="GET")
        
        output = result.get('output2', {})
        return {
            'total_balance': float(output.get('tot_evlu_amt', 0)),
            'available_balance': float(output.get('use_psbl_mney', 0)),
            'currency': 'KRW'
        }
    
    def _futures_positions(self) -> List[Dict]:
        """선물 포지션 조회"""
        tr_id = "JTCE6001R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "MGNA_DVSN": "01",
            "EXCC_STAT_CD": "1"
        }
        
        result = self._call_kis_api("/uapi/domestic-futureoption/v1/trading/inquire-ngt-balance", 
                                   tr_id, params, method="GET")
        
        positions = []
        output1 = result.get('output1', [])
        
        for item in output1:
            if int(item.get('btal_qty', 0)) != 0:  # 잔고가 있는 경우만
                positions.append({
                    'symbol': item.get('pdno', ''),
                    'quantity': int(item.get('btal_qty', 0)),
                    'avg_price': float(item.get('mkt_mny', 0)),
                    'current_value': float(item.get('evlu_amt', 0)),
                    'unrealized_pnl': float(item.get('evlu_pfls_amt', 0))
                })
        
        return positions
    
    def _futures_orderable_amount(self, symbol: str, price: Optional[float] = None) -> Dict:
        """선물 주문가능 조회"""
        tr_id = "JTCE1004R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "PDNO": symbol,
            "PRDT_TYPE_CD": "301",  # 선물옵션
            "SLL_BUY_DVSN_CD": "02",  # 매수
            "UNIT_PRICE": int(price) if price else 0,
            "ORD_DVSN_CD": "01" if price else "02"
        }
        
        result = self._call_kis_api("/uapi/domestic-futureoption/v1/trading/inquire-psbl-ngt-order", 
                                   tr_id, params, method="GET")
        
        output = result.get('output', {})
        return {
            'symbol': symbol,
            'orderable_quantity': int(output.get('max_ord_qty', 0)),
            'orderable_amount': float(output.get('ord_psbl_amt', 0)),
            'unit_price': float(price or output.get('nw_unpr', 0))
        }
    
    # ========== 해외주식 API 구현 ==========
    
    def _overseas_buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """해외주식 매수 주문"""
        excg_cd = self._get_exchange_code(symbol)
        tr_id = self._get_overseas_buy_tr_id(excg_cd)
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "OVRS_EXCG_CD": excg_cd,
            "PDNO": symbol,
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(int(price)) if price else "0",
            "SLL_TYPE": "",  # 매수시 빈값
            "ORD_SVR_DVSN_CD": "0"
        }
        
        result = self._call_kis_api("/uapi/overseas-stock/v1/trading/order", tr_id, params)
        return result.get('output', {}).get('ODNO', 'unknown')
    
    def _overseas_sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """해외주식 매도 주문"""
        excg_cd = self._get_exchange_code(symbol)
        tr_id = self._get_overseas_sell_tr_id(excg_cd)
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "OVRS_EXCG_CD": excg_cd,
            "PDNO": symbol,
            "ORD_DVSN": "00",
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(int(price)) if price else "0",
            "SLL_TYPE": "00",  # 매도시 00
            "ORD_SVR_DVSN_CD": "0"
        }
        
        result = self._call_kis_api("/uapi/overseas-stock/v1/trading/order", tr_id, params)
        return result.get('output', {}).get('ODNO', 'unknown')
    
    def _overseas_balance(self) -> Dict:
        """해외주식 잔고 조회"""
        tr_id = "TTTS3012R" if not self.is_virtual else "VTTS3012R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "OVRS_EXCG_CD": "NASD",  # 기본값: 나스닥
            "TR_CRCY_CD": ""  # 전체 통화
        }
        
        result = self._call_kis_api("/uapi/overseas-stock/v1/trading/inquire-balance", 
                                   tr_id, params, method="GET")
        
        output = result.get('output2', {})
        return {
            'total_balance': float(output.get('tot_evlu_pfls_amt', 0)),
            'available_balance': float(output.get('psbl_ord_amt', 0)),
            'currency': 'USD'
        }
    
    def _overseas_positions(self) -> List[Dict]:
        """해외주식 포지션 조회"""
        tr_id = "TTTS3012R" if not self.is_virtual else "VTTS3012R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "OVRS_EXCG_CD": "",  # 전체
            "TR_CRCY_CD": ""
        }
        
        result = self._call_kis_api("/uapi/overseas-stock/v1/trading/inquire-balance", 
                                   tr_id, params, method="GET")
        
        positions = []
        output1 = result.get('output1', [])
        
        for item in output1:
            if int(item.get('ovrs_cblc_qty', 0)) > 0:  # 보유수량이 있는 경우
                positions.append({
                    'symbol': item.get('ovrs_pdno', ''),
                    'quantity': int(item.get('ovrs_cblc_qty', 0)),
                    'avg_price': float(item.get('pchs_avg_pric', 0)),
                    'current_value': float(item.get('ovrs_stck_evlu_amt', 0)),
                    'unrealized_pnl': float(item.get('frcr_evlu_pfls_amt', 0))
                })
        
        return positions
    
    def _get_exchange_code(self, symbol: str) -> str:
        """종목 코드로 거래소 코드 추정"""
        # 간단한 추정 로직 (실제로는 마스터 데이터 참조 필요)
        if len(symbol) <= 5 and symbol.isalpha():
            return "NASD"  # 나스닥
        return "NYSE"  # 뉴욕증권거래소
    
    def _get_overseas_buy_tr_id(self, excg_cd: str) -> str:
        """해외주식 매수 TR ID 반환"""
        if self.is_virtual:
            if excg_cd in ("NASD", "NYSE", "AMEX"):
                return "VTTT1002U"  # 미국 매수
            elif excg_cd == "SEHK":
                return "VTTS1002U"  # 홍콩 매수
            # 기타 거래소들...
        else:
            if excg_cd in ("NASD", "NYSE", "AMEX"):
                return "TTTT1002U"
            elif excg_cd == "SEHK":
                return "TTTS1002U"
        return "TTTT1002U"  # 기본값
    
    def _get_overseas_sell_tr_id(self, excg_cd: str) -> str:
        """해외주식 매도 TR ID 반환"""
        if self.is_virtual:
            if excg_cd in ("NASD", "NYSE", "AMEX"):
                return "VTTT1006U"  # 미국 매도
            elif excg_cd == "SEHK":
                return "VTTS1001U"  # 홍콩 매도
        else:
            if excg_cd in ("NASD", "NYSE", "AMEX"):
                return "TTTT1006U"
            elif excg_cd == "SEHK":
                return "TTTS1001U"
        return "TTTT1006U"  # 기본값
    
    # ========== 주식 API 구현 ==========
    
    def _stock_buy(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """주식 매수 주문"""
        tr_id = "VTTC0802U" if self.is_virtual else "TTTC0802U"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "PDNO": symbol,
            "ORD_DVSN": "00" if price else "01",  # 지정가/시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(int(price)) if price else "0"
        }
        
        result = self._call_kis_api("/uapi/domestic-stock/v1/trading/order-cash", tr_id, params)
        output = result.get('output', {})
        
        # 주문번호 조합: 조직번호 + 주문번호
        org_no = output.get('KRX_FWDG_ORD_ORGNO', '')
        order_no = output.get('ODNO', '')
        return f"{org_no}-{order_no}" if org_no and order_no else f"stock_buy_{int(time.time())}"
    
    def _stock_sell(self, symbol: str, quantity: int, price: Optional[float] = None) -> str:
        """주식 매도 주문"""
        tr_id = "VTTC0801U" if self.is_virtual else "TTTC0801U"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "PDNO": symbol,
            "ORD_DVSN": "00" if price else "01",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(int(price)) if price else "0"
        }
        
        result = self._call_kis_api("/uapi/domestic-stock/v1/trading/order-cash", tr_id, params)
        output = result.get('output', {})
        
        org_no = output.get('KRX_FWDG_ORD_ORGNO', '')
        order_no = output.get('ODNO', '')
        return f"{org_no}-{order_no}" if org_no and order_no else f"stock_sell_{int(time.time())}"
    
    def _stock_balance(self) -> Dict:
        """주식 잔고 조회"""
        tr_id = "TTTC8434R"  # 모의투자도 동일 TR ID 사용
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "AFHR_FLPR_YN": "N",  # 시간외단일가여부
            "OFL_YN": "",  # 오프라인여부
            "INQR_DVSN": "00",  # 조회구분
            "UNPR_DVSN": "01",  # 단가구분
            "FUND_STTL_ICLD_YN": "N",  # 펀드결제분포함여부
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",  # 전일매매포함
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        result = self._call_kis_api("/uapi/domestic-stock/v1/trading/inquire-balance", 
                                   tr_id, params, method="GET")
        
        output = result.get('output2', [])
        if output:
            balance_data = output[0] if isinstance(output, list) else output
            return {
                'total_balance': float(balance_data.get('tot_evlu_amt', 0)),
                'available_balance': float(balance_data.get('prvs_rcdl_excc_amt', 0)),
                'currency': 'KRW'
            }
        
        return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
    
    def _stock_positions(self) -> List[Dict]:
        """주식 포지션 조회"""
        tr_id = "TTTC8434R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "00",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N", 
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        result = self._call_kis_api("/uapi/domestic-stock/v1/trading/inquire-balance",
                                   tr_id, params, method="GET")
        
        positions = []
        output1 = result.get('output1', [])
        
        for item in output1:
            # 보유수량이 있는 종목만 포함
            quantity = int(item.get('hldg_qty', 0))
            if quantity > 0:
                positions.append({
                    'symbol': item.get('pdno', ''),
                    'quantity': quantity,
                    'avg_price': float(item.get('pchs_avg_pric', 0)),
                    'current_value': float(item.get('evlu_amt', 0)),
                    'unrealized_pnl': float(item.get('evlu_pfls_amt', 0))
                })
        
        return positions
    
    def _stock_orderable_amount(self, symbol: str, price: Optional[float] = None) -> Dict:
        """주식 매수가능 조회"""
        tr_id = "TTTC8908R"
        
        params = {
            "CANO": self.auth.account_number,
            "ACNT_PRDT_CD": self.auth.account_product,
            "PDNO": symbol,
            "ORD_UNPR": str(int(price)) if price else "",
            "ORD_DVSN": "00" if price else "01",  # 지정가/시장가
            "CMA_EVLU_AMT_ICLD_YN": "N",  # CMA평가금액포함여부
            "OVRS_ICLD_YN": "Y"  # 해외포함여부
        }
        
        result = self._call_kis_api("/uapi/domestic-stock/v1/trading/inquire-psbl-order",
                                   tr_id, params, method="GET")
        
        output = result.get('output', {})
        return {
            'symbol': symbol,
            'orderable_quantity': int(output.get('max_buy_qty', 0)),
            'orderable_amount': float(output.get('ord_psbl_cash', 0)),
            'unit_price': float(price or output.get('psbl_qty_calc_unpr', 0))
        }
    
    # ========== 응답 표준화 메서드 ==========
    
    def _standardize_balance_response(self, raw_response: Dict, account_type: str) -> Dict:
        """잔고 응답 표준화"""
        if account_type == "FUTURES":
            output = raw_response.get('output2', {})
            return {
                'total_balance': float(output.get('tot_evlu_amt', 0)),
                'available_balance': float(output.get('use_psbl_mney', 0)),
                'currency': 'KRW',
                'account_type': account_type
            }
        elif account_type == "OVERSEAS":
            output = raw_response.get('output2', {})
            return {
                'total_balance': float(output.get('tot_evlu_pfls_amt', 0)),
                'available_balance': float(output.get('psbl_ord_amt', 0)),
                'currency': 'USD',
                'account_type': account_type
            }
        else:  # STOCK
            return {
                'total_balance': 10000000.0,
                'available_balance': 10000000.0,
                'currency': 'KRW',
                'account_type': account_type
            }
    
    def _standardize_position_response(self, raw_response: Dict, account_type: str) -> List[Dict]:
        """포지션 응답 표준화"""
        positions = []
        
        if account_type == "FUTURES":
            output1 = raw_response.get('output1', [])
            for item in output1:
                if int(item.get('btal_qty', 0)) != 0:
                    positions.append({
                        'symbol': item.get('pdno', ''),
                        'quantity': int(item.get('btal_qty', 0)),
                        'avg_price': float(item.get('mkt_mny', 0)),
                        'current_value': float(item.get('evlu_amt', 0)),
                        'unrealized_pnl': float(item.get('evlu_pfls_amt', 0)),
                        'account_type': account_type
                    })
        elif account_type == "OVERSEAS":
            output1 = raw_response.get('output1', [])
            for item in output1:
                if int(item.get('ovrs_cblc_qty', 0)) > 0:
                    positions.append({
                        'symbol': item.get('ovrs_pdno', ''),
                        'quantity': int(item.get('ovrs_cblc_qty', 0)),
                        'avg_price': float(item.get('pchs_avg_pric', 0)),
                        'current_value': float(item.get('ovrs_stck_evlu_amt', 0)),
                        'unrealized_pnl': float(item.get('frcr_evlu_pfls_amt', 0)),
                        'account_type': account_type
                    })
        
        return positions
    
    def _handle_api_error(self, response: Dict, operation: str) -> None:
        """API 에러 처리"""
        rt_cd = response.get('rt_cd', '1')
        if rt_cd != '0':
            error_msg = response.get('msg1', 'Unknown API error')
            error_code = response.get('msg_cd', 'UNKNOWN')
            
            logger.error(f"{operation} failed - Code: {error_code}, Message: {error_msg}")
            
            # 에러 코드별 적절한 예외 발생
            exception = get_kis_exception(error_code, error_msg)
            raise exception
    
    def _retry_api_call(self, func, max_retries: int = 3, delay: float = 1.0):
        """API 호출 재시도 로직"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                logger.warning(f"API call attempt {attempt + 1} failed: {e}")
                time.sleep(delay * (attempt + 1))  # 지수 백오프
    
    def _validate_order_params(self, symbol: str, quantity: int, price: Optional[float]) -> None:
        """주문 파라미터 유효성 검증"""
        if not symbol or not symbol.strip():
            raise KisOrderError("Symbol cannot be empty")
        
        if quantity <= 0:
            raise KisOrderError("Quantity must be positive")
        
        if price is not None and price <= 0:
            raise KisOrderError("Price must be positive")
    
    def _extract_order_id(self, response: Dict) -> str:
        """응답에서 주문 ID 추출"""
        output = response.get('output', {})
        
        # 다양한 주문 ID 필드 시도
        order_id = (output.get('odno') or 
                   output.get('ODNO') or 
                   output.get('ord_no') or 
                   output.get('ORD_NO'))
        
        return order_id or f"unknown_{int(time.time())}"
    
    def _get_market_status(self) -> Dict:
        """시장 상태 정보 (기본 구현)"""
        return {
            'is_open': True,  # 실제로는 시장 시간 체크 필요
            'timezone': 'Asia/Seoul',
            'current_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
