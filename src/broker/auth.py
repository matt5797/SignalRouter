import os
import json
import yaml
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class KisAuth:
    def __init__(self, app_key: str, app_secret: str, account_number: str,
                 account_product: str, is_virtual: bool = False,
                 token_storage_path: str = "secrets/tokens/"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_number = account_number
        self.account_product = account_product
        self.is_virtual = is_virtual
        self.token_storage_path = Path(token_storage_path)
        
        if is_virtual:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
        
        self.token_storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"KisAuth initialized - Virtual: {is_virtual}")
    
    def get_valid_token(self) -> str:
        try:
            saved_token = self._load_saved_token()
            if saved_token and self._is_token_valid(saved_token):
                return saved_token
            
            token, expired_time = self._request_new_token()
            self._save_token(token, expired_time)
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
    
    def _save_token(self, token: str, expired_time: str) -> None:
        token_file = self.token_storage_path / f"kis_{self.account_number}_{datetime.now().strftime('%Y%m%d')}.yaml"
        
        token_data = {
            'token': token,
            'expired_time': expired_time,
            'account_number': self.account_number,
            'is_virtual': self.is_virtual,
            'created_at': datetime.now().isoformat()
        }
        
        with open(token_file, 'w', encoding='utf-8') as f:
            yaml.dump(token_data, f, default_flow_style=False)
        
        self._cleanup_old_tokens(keep_days=7)
        
        logger.debug(f"Token saved to {token_file}")
    
    def _load_saved_token(self) -> Optional[str]:
        try:
            token_file = self.token_storage_path / f"kis_{self.account_number}_{datetime.now().strftime('%Y%m%d')}.yaml"
            
            if not token_file.exists():
                return None
            
            with open(token_file, 'r', encoding='utf-8') as f:
                token_data = yaml.safe_load(f)
            
            token = token_data.get('token')
            if token and self._is_token_valid_by_time(token_data.get('expired_time')):
                return token
            
            return None
        
        except Exception as e:
            logger.warning(f"Failed to load saved token: {e}")
            return None
    
    def _is_token_valid(self, token: str) -> bool:
        return bool(token and len(token) > 50)
    
    def _is_token_valid_by_time(self, expired_time: str) -> bool:
        if not expired_time:
            return False
        
        try:
            exp_dt = datetime.strptime(expired_time, '%Y-%m-%d %H:%M:%S')
            now_dt = datetime.now()
            return exp_dt > now_dt
        except Exception:
            return False
    
    def _cleanup_old_tokens(self, keep_days: int = 7) -> None:
        try:
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            pattern = f"kis_{self.account_number}_*.yaml"
            
            for token_file in self.token_storage_path.glob(pattern):
                try:
                    date_str = token_file.stem.split('_')[-1]
                    file_date = datetime.strptime(date_str, '%Y%m%d')
                    
                    if file_date < cutoff_date:
                        token_file.unlink()
                        logger.debug(f"Deleted old token file: {token_file}")
                except (ValueError, IndexError):
                    continue
        
        except Exception as e:
            logger.warning(f"Failed to cleanup old tokens: {e}")