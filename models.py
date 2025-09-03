from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatMessage(BaseModel):
    """聊天消息模型"""
    id: Optional[int] = None
    user_id: str
    role: MessageRole
    content: str
    conversation_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True

class ChatMessageCreate(BaseModel):
    """创建聊天消息的请求模型"""
    content: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None

class ChatMessageResponse(BaseModel):
    """聊天消息响应模型"""
    id: int
    role: MessageRole
    content: str
    conversation_id: Optional[str]
    created_at: datetime
    
    class Config:
        use_enum_values = True

class ConversationHistory(BaseModel):
    """对话历史模型"""
    conversation_id: str
    messages: List[ChatMessageResponse]
    total_messages: int

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None
    model: str = Field(default="deepseek-chat", description="使用的AI模型")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成温度")
    max_tokens: int = Field(default=2000, ge=1, le=4000, description="最大token数")

class ChatResponse(BaseModel):
    """聊天响应模型"""
    message: str
    conversation_id: str
    user_message_id: int
    assistant_message_id: int
    model_used: str
    tokens_used: Optional[int] = None

class UserProfile(BaseModel):
    """用户资料模型"""
    id: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None

class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None