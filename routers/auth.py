from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from auth import auth_manager, get_current_user, get_optional_user
from models import UserProfile, ErrorResponse
import logging
import uuid

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/auth", tags=["认证"])

# 请求模型
class LoginRequest(BaseModel):
    """登录请求模型"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    supabase_token: Optional[str] = None
    anonymous: bool = False

class TokenResponse(BaseModel):
    """Token响应模型"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: Optional[str] = None
    is_anonymous: bool = False
    expires_in: int

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """用户登录"""
    try:
        if request.anonymous:
            # 匿名登录
            user_data = auth_manager.create_anonymous_user()
            token_data = {
                "sub": user_data["id"],
                "email": None,
                "is_anonymous": True
            }
            
            access_token = auth_manager.create_access_token(token_data)
            
            return TokenResponse(
                access_token=access_token,
                user_id=user_data["id"],
                email=None,
                is_anonymous=True,
                expires_in=auth_manager.expire_minutes * 60
            )
        
        elif request.supabase_token:
            # Supabase token登录
            user_data = await auth_manager.authenticate_supabase_user(request.supabase_token)
            token_data = {
                "sub": user_data["id"],
                "email": user_data["email"],
                "is_anonymous": False
            }
            
            access_token = auth_manager.create_access_token(token_data)
            
            return TokenResponse(
                access_token=access_token,
                user_id=user_data["id"],
                email=user_data["email"],
                is_anonymous=False,
                expires_in=auth_manager.expire_minutes * 60
            )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请提供有效的登录方式（匿名登录或Supabase token）"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录过程中发生错误"
        )

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user)
):
    """获取当前用户信息"""
    try:
        return UserProfile(
            id=current_user["id"],
            email=current_user.get("email"),
            created_at=None,  # 可以从数据库获取
            last_active=None   # 可以从数据库获取
        )
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户信息失败"
        )

@router.post("/refresh")
async def refresh_token(
    current_user: dict = Depends(get_current_user)
):
    """刷新访问令牌"""
    try:
        token_data = {
            "sub": current_user["id"],
            "email": current_user.get("email"),
            "is_anonymous": current_user.get("is_anonymous", False)
        }
        
        new_access_token = auth_manager.create_access_token(token_data)
        
        return TokenResponse(
            access_token=new_access_token,
            user_id=current_user["id"],
            email=current_user.get("email"),
            is_anonymous=current_user.get("is_anonymous", False),
            expires_in=auth_manager.expire_minutes * 60
        )
    
    except Exception as e:
        logger.error(f"刷新令牌失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刷新令牌失败"
        )

@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user)
):
    """用户登出"""
    try:
        # 对于JWT token，我们无法在服务端使其失效
        # 在实际应用中，可以维护一个黑名单或使用Redis存储token状态
        logger.info(f"用户 {current_user['id']} 登出")
        return {"message": "登出成功"}
    
    except Exception as e:
        logger.error(f"登出失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登出失败"
        )

@router.get("/validate")
async def validate_token(
    current_user: dict = Depends(get_current_user)
):
    """验证令牌有效性"""
    return {
        "valid": True,
        "user_id": current_user["id"],
        "is_anonymous": current_user.get("is_anonymous", False)
    }