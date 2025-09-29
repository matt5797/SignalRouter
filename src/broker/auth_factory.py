from typing import Optional
import logging
from .auth import KisAuth
from .secrets import SecretLoader

logger = logging.getLogger(__name__)


class AuthFactory:
    @staticmethod
    def create_from_secret(secret_identifier: str, 
                          token_storage_path: str = "secrets/tokens/") -> KisAuth:
        try:
            secret_data = SecretLoader.load_secret(secret_identifier)
            
            if not SecretLoader.validate_secret(secret_data):
                raise ValueError(f"Invalid secret data for: {secret_identifier}")
            
            auth = KisAuth(
                app_key=secret_data['app_key'],
                app_secret=secret_data['app_secret'],
                account_number=secret_data['account_number'],
                account_product=secret_data['account_product'],
                is_virtual=secret_data.get('is_virtual', False),
                token_storage_path=token_storage_path
            )
            
            logger.info(f"KisAuth created for account {secret_data['account_number']}")
            return auth
        
        except Exception as e:
            logger.error(f"Failed to create KisAuth from {secret_identifier}: {e}")
            raise
    
    @staticmethod
    def create_virtual_with_real_reference(virtual_secret_identifier: str,
                                         default_real_secret_identifier: Optional[str] = None,
                                         token_storage_path: str = "secrets/tokens/") -> KisAuth:
        try:
            virtual_secret = SecretLoader.load_secret(virtual_secret_identifier)
            
            if not virtual_secret.get('is_virtual', False):
                logger.info(f"Account {virtual_secret_identifier} is real account")
                return AuthFactory.create_from_secret(virtual_secret_identifier, token_storage_path)
            
            real_secret_identifier = SecretLoader.get_real_account_secret(virtual_secret_identifier)
            if not real_secret_identifier and default_real_secret_identifier:
                real_secret_identifier = default_real_secret_identifier
            
            if not real_secret_identifier:
                logger.warning(f"No real account reference found for {virtual_secret_identifier}")
                return AuthFactory.create_from_secret(virtual_secret_identifier, token_storage_path)
            
            real_secret = SecretLoader.load_secret(real_secret_identifier)
            
            auth = KisAuth(
                app_key=real_secret['app_key'],
                app_secret=real_secret['app_secret'],
                account_number=virtual_secret['account_number'],
                account_product=virtual_secret['account_product'],
                is_virtual=True,
                token_storage_path=token_storage_path
            )
            
            logger.info(f"Virtual KisAuth created with real account reference")
            return auth
        
        except Exception as e:
            logger.error(f"Failed to create virtual KisAuth: {e}")
            raise
    
    @staticmethod
    def validate_auth_config(secret_identifier: str) -> bool:
        try:
            secret_data = SecretLoader.load_secret(secret_identifier)
            return SecretLoader.validate_secret(secret_data)
        except Exception:
            return False
    
    @staticmethod
    def list_available_accounts() -> list:
        return SecretLoader.list_available_accounts()