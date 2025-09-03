from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from database import db_client
import logging
import uuid

# 配置日志
logger = logging.getLogger(__name__)

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()

class AuthManager:
    """认证管理器"""
    
    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_minutes = settings.jwt_access_token_expire_minutes
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.expire_minutes)
        to_encode.update({"exp": expire})
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            logger.info(f"为用户 {data.get('sub')} 创建访问令牌")
            return encoded_jwt
        except Exception as e:
            logger.error(f"创建访问令牌失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token创建失败"
            )
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的认证凭据",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return payload
        except JWTError as e:
            logger.error(f"Token验证失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭据",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def hash_password(self, password: str) -> str:
        """哈希密码"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)
    
    async def authenticate_supabase_user(self, token: str) -> Dict[str, Any]:
        """通过Supabase认证用户"""
        try:
            # 使用Supabase客户端验证用户
            client = db_client.get_client()
            user_response = client.auth.get_user(token)
            
            if user_response.user:
                return {
                    "id": user_response.user.id,
                    "email": user_response.user.email,
                    "created_at": user_response.user.created_at
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Supabase用户认证失败"
                )
        except Exception as e:
            logger.error(f"Supabase用户认证失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户认证失败"
            )
    
    def create_anonymous_user(self) -> Dict[str, Any]:
        """创建匿名用户"""
        user_id = str(uuid.uuid4())
        user_data = {
            "id": user_id,
            "email": None,
            "is_anonymous": True,
            "created_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"创建匿名用户: {user_id}")
        return user_data

# 创建全局认证管理器实例
auth_manager = AuthManager()

# 依赖注入函数
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """获取当前用户信息"""
    token = credentials.credentials
    payload = auth_manager.verify_token(token)
    
    # 如果是匿名用户，直接返回payload中的信息
    if payload.get("is_anonymous"):
        return {
            "id": payload.get("sub"),
            "email": None,
            "is_anonymous": True
        }
    
    # 如果是Supabase用户，可以进一步验证
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "is_anonymous": False
    }

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取可选的用户信息（允许匿名访问）"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None