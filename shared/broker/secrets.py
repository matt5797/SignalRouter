import json
import os
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class SecretLoader:
    _accounts_cache = None
    
    @staticmethod
    def load_secret(secret_identifier: str) -> Dict:
        try:
            account_data = SecretLoader._load_from_env(secret_identifier)
            if account_data:
                logger.debug(f"Secret loaded from environment: {secret_identifier}")
                return account_data
            
            raise FileNotFoundError(f"Secret not found: {secret_identifier}")
        
        except Exception as e:
            logger.error(f"Failed to load secret {secret_identifier}: {e}")
            raise
    
    @staticmethod
    def _load_from_env(account_id: str) -> Optional[Dict]:
        try:
            if SecretLoader._accounts_cache is None:
                accounts_json = os.getenv('ACCOUNTS_CONFIG')
                if not accounts_json:
                    return None
                
                accounts_list = json.loads(accounts_json)
                if not isinstance(accounts_list, list):
                    logger.error("ACCOUNTS_CONFIG must be a JSON array")
                    return None
                
                SecretLoader._accounts_cache = {
                    account.get('id', ''): account 
                    for account in accounts_list 
                    if isinstance(account, dict) and account.get('id')
                }
                
                logger.info(f"Loaded {len(SecretLoader._accounts_cache)} accounts from environment")
            
            account_data = SecretLoader._accounts_cache.get(account_id)
            if account_data:
                if SecretLoader.validate_secret(account_data):
                    return account_data
                else:
                    logger.error(f"Invalid account data for {account_id}")
            
            return None
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid ACCOUNTS_CONFIG JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading from environment: {e}")
            return None
    
    @staticmethod
    def validate_secret(secret_data: Dict) -> bool:
        try:
            required_fields = ['app_key', 'app_secret', 'account_number', 'account_product']
            if not all(field in secret_data for field in required_fields):
                return False
            
            if not all(str(secret_data[field]).strip() for field in required_fields):
                return False
            
            if len(str(secret_data['account_number'])) != 8:
                return False
            
            if len(str(secret_data['account_product'])) != 2:
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Secret validation error: {e}")
            return False
    
    @staticmethod
    def get_account_by_token(webhook_token: str) -> Optional[Dict]:
        try:
            if SecretLoader._accounts_cache is None:
                SecretLoader._load_from_env('dummy')
            
            if not SecretLoader._accounts_cache:
                return None
            
            for account_id, account_data in SecretLoader._accounts_cache.items():
                if account_data.get('webhook_token') == webhook_token:
                    return account_data
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to get account by token: {e}")
            return None
    
    @staticmethod
    def list_available_accounts() -> List[str]:
        account_ids = []
        
        try:
            if SecretLoader._accounts_cache is None:
                SecretLoader._load_from_env('dummy')
            
            if SecretLoader._accounts_cache:
                account_ids.extend(SecretLoader._accounts_cache.keys())
        except Exception:
            pass
        
        return account_ids
    
    @staticmethod
    def clear_cache():
        SecretLoader._accounts_cache = None