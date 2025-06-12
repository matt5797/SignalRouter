"""
AuthFactory - KisAuth 인스턴스 생성 팩토리 (환경변수 우선)
"""

from typing import Optional
import logging
from .kis_auth import KisAuth
from .secret_loader import SecretLoader

logger = logging.getLogger(__name__)


class AuthFactory:
    """KisAuth 인스턴스 생성 팩토리"""
    
    @staticmethod
    def create_from_secret(secret_identifier: str, 
                          token_storage_path: str = "secrets/tokens/") -> KisAuth:
        """
        Secret에서 KisAuth 인스턴스 생성
        
        Args:
            secret_identifier: 계좌 ID 또는 파일 경로
            token_storage_path: 토큰 저장 경로
            
        Returns:
            KisAuth 인스턴스
        """
        try:
            # Secret 데이터 로드 (환경변수 우선, 파일 fallback)
            secret_data = SecretLoader.load_secret(secret_identifier)
            
            # 유효성 검증
            if not SecretLoader.validate_secret(secret_data):
                raise ValueError(f"Invalid secret data for: {secret_identifier}")
            
            # KisAuth 인스턴스 생성
            auth = KisAuth(
                app_key=secret_data['app_key'],
                app_secret=secret_data['app_secret'],
                account_number=secret_data['account_number'],
                account_product=secret_data['account_product'],
                is_virtual=secret_data.get('is_virtual', False),
                token_storage_path=token_storage_path
            )
            
            logger.info(f"KisAuth created for account {secret_data['account_number']} from {secret_identifier}")
            return auth
            
        except Exception as e:
            logger.error(f"Failed to create KisAuth from {secret_identifier}: {e}")
            raise
    
    @staticmethod
    def create_virtual_with_real_reference(virtual_secret_identifier: str,
                                         default_real_secret_identifier: Optional[str] = None,
                                         token_storage_path: str = "secrets/tokens/") -> KisAuth:
        """
        모의투자 계좌용 KisAuth 생성 (실전계좌 참조)
        
        Args:
            virtual_secret_identifier: 모의계좌 ID 또는 파일 경로
            default_real_secret_identifier: 기본 실전계좌 ID (선택)
            token_storage_path: 토큰 저장 경로
            
        Returns:
            KisAuth 인스턴스
        """
        try:
            # 모의투자 계좌 정보 로드
            virtual_secret = SecretLoader.load_secret(virtual_secret_identifier)
            
            if not virtual_secret.get('is_virtual', False):
                # 실전계좌면 일반 생성
                logger.info(f"Account {virtual_secret_identifier} is real account, using normal auth")
                return AuthFactory.create_from_secret(virtual_secret_identifier, token_storage_path)
            
            # 실전계좌 참조 경로 찾기
            real_secret_identifier = SecretLoader.get_real_account_secret(virtual_secret_identifier)
            if not real_secret_identifier and default_real_secret_identifier:
                real_secret_identifier = default_real_secret_identifier
            
            if not real_secret_identifier:
                logger.warning(f"No real account reference found for {virtual_secret_identifier} - using virtual credentials")
                return AuthFactory.create_from_secret(virtual_secret_identifier, token_storage_path)
            
            # 실전계좌 정보로 인증 생성 (모의투자 플래그 유지)
            real_secret = SecretLoader.load_secret(real_secret_identifier)
            
            auth = KisAuth(
                app_key=real_secret['app_key'],  # 실전계좌 앱키 사용
                app_secret=real_secret['app_secret'],  # 실전계좌 앱시크리트 사용
                account_number=virtual_secret['account_number'],  # 모의계좌 번호 사용
                account_product=virtual_secret['account_product'],  # 모의계좌 상품코드 사용
                is_virtual=True,  # 모의투자 플래그
                token_storage_path=token_storage_path
            )
            
            logger.info(f"Virtual KisAuth created for {virtual_secret_identifier} with real account reference {real_secret_identifier}")
            return auth
            
        except Exception as e:
            logger.error(f"Failed to create virtual KisAuth: {e}")
            raise
    
    @staticmethod
    def validate_auth_config(secret_identifier: str) -> bool:
        """인증 설정 유효성 사전 검증"""
        try:
            secret_data = SecretLoader.load_secret(secret_identifier)
            return SecretLoader.validate_secret(secret_data)
        except Exception:
            return False
    
    @staticmethod
    def list_available_accounts() -> list:
        """사용 가능한 계좌 목록 반환"""
        return SecretLoader.list_available_accounts()