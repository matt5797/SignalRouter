import json
import requests
from datetime import datetime
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class KisAuth:
    def __init__(self, app_key: str, app_secret: str, account_number: str,
                 account_product: str, is_virtual: bool = False):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_number = account_number
        self.account_product = account_product
        self.is_virtual = is_virtual
        
        if is_virtual:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
        
        self._cached_token = None
        self._cached_expiry = None
        
        logger.info(f"KisAuth initialized - Virtual: {is_virtual}")
    
    def get_valid_token(self) -> str:
        try:
            if self._cached_token and self._is_token_valid_by_time(self._cached_expiry):
                logger.debug("Using cached token")
                return self._cached_token
            
            token, expired_time = self._request_new_token()
            self._cached_token = token
            self._cached_expiry = expired_time
            return token
        
        except Exception as e:
            logger.error(f"Failed to get valid token: {e}")
            raise
    
    def get_request_headers(self, tr_id: str, tr_cont: str = "") -> Dict[str, str]:
        token = self.get_valid_token()
        
        if self.is_virtual and tr_id.startswith(('T', 'J', 'C')):
            tr_id = 'V' + tr_id[1:]
        
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "tr_cont": tr_cont
        }
    
    def _request_new_token(self) -> Tuple[str, str]:
        url = f"{self.base_url}/oauth2/tokenP"
        
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8"
        }
        
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Token request failed: {response.status_code}")
        
        data = response.json()
        token = data.get('access_token')
        expired_time = data.get('access_token_token_expired')
        
        if not token or not expired_time:
            raise Exception("Invalid token response")
        
        logger.info("New token acquired successfully")
        return token, expired_time
    
    def _is_token_valid_by_time(self, expired_time: str) -> bool:
        if not expired_time:
            return False
        
        try:
            exp_dt = datetime.strptime(expired_time, '%Y-%m-%d %H:%M:%S')
            now_dt = datetime.now()
            return exp_dt > now_dt
        except Exception:
            return False