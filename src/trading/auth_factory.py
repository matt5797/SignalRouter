"""
AuthFactory - KisAuth 인스턴스 생성 팩토리
Secret 파일에서 KisAuth 객체를 쉽게 생성할 수 있는 헬퍼 클래스
"""

from typing import Optional
import logging
from .kis_auth import KisAuth
from .secret_loader import SecretLoader

logger = logging.getLogger(__name__)


class AuthFactory:
    """KisAuth 인스턴스 생성 팩토리"""
    
    @staticmethod
    def create_from_secret(secret_file_path: str, 
                          token_storage_path: str = "secrets/tokens/") -> KisAuth:
        """Secret 파일에서 KisAuth 인스턴스 생성"""
        try:
            # Secret 데이터 로드
            secret_data = SecretLoader.load_secret(secret_file_path)
            
            # 유효성 검증
            if not SecretLoader.validate_secret(secret_data):
                raise ValueError(f"Invalid secret data in {secret_file_path}")
            
            # KisAuth 인스턴스 생성
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
            logger.error(f"Failed to create KisAuth from {secret_file_path}: {e}")
            raise
    
    @staticmethod
    def create_virtual_with_real_reference(virtual_secret_path: str,
                                         default_real_secret_path: Optional[str] = None,
                                         token_storage_path: str = "secrets/tokens/") -> KisAuth:
        """모의투자 계좌용 KisAuth 생성 (실전계좌 참조)"""
        try:
            # 모의투자 계좌 정보 로드
            virtual_secret = SecretLoader.load_secret(virtual_secret_path)
            
            if not virtual_secret.get('is_virtual', False):
                # 실전계좌면 일반 생성
                return AuthFactory.create_from_secret(virtual_secret_path, token_storage_path)
            
            # 실전계좌 참조 경로 찾기
            real_secret_path = SecretLoader.get_real_account_secret(virtual_secret_path)
            if not real_secret_path and default_real_secret_path:
                real_secret_path = default_real_secret_path
            
            if not real_secret_path:
                logger.warning("No real account reference found - using virtual credentials")
                return AuthFactory.create_from_secret(virtual_secret_path, token_storage_path)
            
            # 실전계좌 정보로 인증 생성 (모의투자 플래그 유지)
            real_secret = SecretLoader.load_secret(real_secret_path)
            
            auth = KisAuth(
                app_key=real_secret['app_key'],  # 실전계좌 앱키 사용
                app_secret=real_secret['app_secret'],  # 실전계좌 앱시크리트 사용
                account_number=virtual_secret['account_number'],  # 모의계좌 번호 사용
                account_product=virtual_secret['account_product'],  # 모의계좌 상품코드 사용
                is_virtual=True,  # 모의투자 플래그
                token_storage_path=token_storage_path
            )
            
            logger.info(f"Virtual KisAuth created with real account reference")
            return auth
            
        except Exception as e:
            logger.error(f"Failed to create virtual KisAuth: {e}")
            raise
    
    @staticmethod
    def validate_auth_config(secret_file_path: str) -> bool:
        """인증 설정 유효성 사전 검증"""
        try:
            secret_data = SecretLoader.load_secret(secret_file_path)
            return SecretLoader.validate_secret(secret_data)
        except Exception:
            return False
