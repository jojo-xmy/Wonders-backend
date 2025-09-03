from supabase import create_client, Client
from typing import Optional, List, Dict, Any
from config import settings
import logging
from models import ChatMessage, MessageRole
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase数据库客户端"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化Supabase客户端"""
        try:
            # 使用服务角色密钥来绕过RLS策略
            supabase_key = settings.supabase_service_role_key or settings.supabase_key
            self.client = create_client(
                supabase_url=settings.supabase_url,
                supabase_key=supabase_key
            )
            logger.info("Supabase客户端初始化成功")
        except Exception as e:
            logger.error(f"Supabase客户端初始化失败: {e}")
            raise
    
    async def ensure_user_exists(self, user_id: str, email: Optional[str] = None, is_anonymous: bool = False) -> Dict[str, Any]:
        """确保用户存在，如果不存在则创建"""
        try:
            # 首先检查用户是否存在
            result = self.client.table("users").select("*").eq("id", user_id).execute()
            
            if result.data:
                return result.data[0]
            
            # 用户不存在，创建新用户
            user_data = {
                "id": user_id,
                "email": email,
                "is_anonymous": is_anonymous,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.client.table("users").insert(user_data).execute()
            
            if result.data:
                logger.info(f"用户创建成功，ID: {user_id}")
                return result.data[0]
            else:
                raise Exception("用户创建失败，未返回数据")
                
        except Exception as e:
            logger.error(f"确保用户存在失败: {e}")
            raise
    
    async def create_chat_message(
        self, 
        user_id: str, 
        role: MessageRole, 
        content: str, 
        conversation_id: Optional[str] = None,
        is_anonymous: bool = False
    ) -> Dict[str, Any]:
        """创建聊天消息"""
        try:
            # 确保用户存在
            await self.ensure_user_exists(user_id, is_anonymous=is_anonymous)
            
            message_data = {
                "user_id": user_id,
                "role": role.value,
                "content": content,
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.client.table("chat_messages").insert(message_data).execute()
            
            if result.data:
                logger.info(f"消息创建成功，ID: {result.data[0]['id']}")
                return result.data[0]
            else:
                raise Exception("消息创建失败，未返回数据")
                
        except Exception as e:
            logger.error(f"创建聊天消息失败: {e}")
            raise
    
    async def get_conversation_history(
        self, 
        user_id: str, 
        conversation_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取对话历史"""
        try:
            result = (
                self.client.table("chat_messages")
                .select("*")
                .eq("user_id", user_id)
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            
            logger.info(f"获取到 {len(result.data)} 条对话历史")
            return result.data
            
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            raise
    
    async def get_user_conversations(
        self, 
        user_id: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取用户的所有对话列表"""
        try:
            result = (
                self.client.table("chat_messages")
                .select("conversation_id, created_at, content")
                .eq("user_id", user_id)
                .eq("role", "user")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            # 按conversation_id分组，获取每个对话的最新消息
            conversations = {}
            for msg in result.data:
                conv_id = msg["conversation_id"]
                if conv_id and conv_id not in conversations:
                    conversations[conv_id] = {
                        "conversation_id": conv_id,
                        "last_message": msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"],
                        "last_updated": msg["created_at"]
                    }
            
            logger.info(f"获取到 {len(conversations)} 个对话")
            return list(conversations.values())
            
        except Exception as e:
            logger.error(f"获取用户对话列表失败: {e}")
            raise
    
    async def delete_conversation(
        self, 
        user_id: str, 
        conversation_id: str
    ) -> bool:
        """删除对话"""
        try:
            result = (
                self.client.table("chat_messages")
                .delete()
                .eq("user_id", user_id)
                .eq("conversation_id", conversation_id)
                .execute()
            )
            
            logger.info(f"对话 {conversation_id} 删除成功")
            return True
            
        except Exception as e:
            logger.error(f"删除对话失败: {e}")
            raise
    
    def get_client(self) -> Client:
        """获取Supabase客户端实例"""
        if not self.client:
            self._initialize_client()
        return self.client

# 创建全局数据库客户端实例
db_client = SupabaseClient()

# 便捷函数
async def get_db_client() -> SupabaseClient:
    """获取数据库客户端实例"""
    return db_client