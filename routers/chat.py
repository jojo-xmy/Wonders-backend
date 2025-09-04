from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional
from auth import get_current_user
from database import get_db_client
from services import get_deepseek_service
from models import (
    ChatRequest, ChatResponse, ChatMessageResponse, 
    ConversationHistory, MessageRole, ErrorResponse
)
from .notifications import publish_notification, NotificationType
import logging
import uuid
import json
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/chat", tags=["聊天"])

@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """发送聊天消息"""
    try:
        db = await get_db_client()
        user_id = current_user["id"]
        
        # 如果没有提供conversation_id，创建一个新的
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # 保存用户消息到数据库
        user_message = await db.create_chat_message(
            user_id=user_id,
            role=MessageRole.USER,
            content=request.message,
            conversation_id=conversation_id,
            is_anonymous=current_user.get("is_anonymous", False)
        )
        
        # 获取对话历史以提供上下文
        history_data = await db.get_conversation_history(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=10  # 获取最近10条消息作为上下文
        )
        
        # 构建消息历史
        messages = []
        
        # 添加系统提示（仅在新对话开始时）
        if not history_data:
            deepseek = await get_deepseek_service()
            system_prompt = deepseek.create_language_learning_system_prompt()
            messages.append(deepseek.create_system_message(system_prompt))
        
        # 添加历史消息
        for msg in history_data:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # 添加当前用户消息
        messages.append({
            "role": MessageRole.USER.value,
            "content": request.message
        })
        
        # 调用DeepSeek API
        deepseek = await get_deepseek_service()
        ai_response = await deepseek.generate_response(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        ai_response_content = ai_response["content"]
        tokens_used = ai_response["usage"]["total_tokens"]
        
        # 保存AI响应到数据库
        ai_message = await db.create_chat_message(
            user_id=user_id,
            role=MessageRole.ASSISTANT,
            content=ai_response_content,
            conversation_id=conversation_id,
            is_anonymous=current_user.get("is_anonymous", False)
        )
        
        # 发布新消息通知
        await publish_notification(
            event_type=NotificationType.MESSAGE_RECEIVED,
            title="收到新回复",
            message=f"AI助手回复了您的消息",
            metadata={
                "conversation_id": conversation_id,
                "message_id": ai_message["id"],
                "user_id": user_id
            }
        )
        
        return ChatResponse(
            message=ai_response_content,
            conversation_id=conversation_id,
            user_message_id=user_message["id"],
            assistant_message_id=ai_message["id"],
            model_used=request.model,
            tokens_used=tokens_used
        )
    
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="发送消息失败"
        )

@router.post("/send-stream")
async def send_message_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """发送聊天消息（流式响应）"""
    try:
        db = await get_db_client()
        user_id = current_user["id"]
        
        # 如果没有提供conversation_id，创建一个新的
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # 保存用户消息到数据库
        user_message = await db.create_chat_message(
            user_id=user_id,
            role=MessageRole.USER,
            content=request.message,
            conversation_id=conversation_id
        )
        
        # 获取对话历史
        history_data = await db.get_conversation_history(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=10
        )
        
        # 构建消息历史
        messages = []
        
        if not history_data:
            deepseek = await get_deepseek_service()
            system_prompt = deepseek.create_language_learning_system_prompt()
            messages.append(deepseek.create_system_message(system_prompt))
        
        for msg in history_data:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        messages.append({
            "role": MessageRole.USER.value,
            "content": request.message
        })
        
        # 流式响应生成器
        async def generate_stream():
            deepseek = await get_deepseek_service()
            full_content = ""
            
            async for chunk in deepseek.generate_streaming_response(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                if "error" in chunk:
                    yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                    break
                
                if chunk["finished"]:
                    full_content = chunk["full_content"]
                    # 保存完整的AI响应到数据库
                    ai_message = await db.create_chat_message(
                        user_id=user_id,
                        role=MessageRole.ASSISTANT,
                        content=full_content,
                        conversation_id=conversation_id,
                        is_anonymous=current_user.get("is_anonymous", False)
                    )
                    
                    yield f"data: {json.dumps({
                        'finished': True,
                        'conversation_id': conversation_id,
                        'user_message_id': user_message['id'],
                        'assistant_message_id': ai_message['id']
                    })}\n\n"
                else:
                    yield f"data: {json.dumps({
                        'content': chunk['content'],
                        'finished': False
                    })}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )
    
    except Exception as e:
        logger.error(f"流式发送消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="流式发送消息失败"
        )

@router.get("/history/{conversation_id}", response_model=ConversationHistory)
async def get_conversation_history(
    conversation_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """获取对话历史"""
    try:
        db = await get_db_client()
        user_id = current_user["id"]
        
        messages_data = await db.get_conversation_history(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=limit
        )
        
        messages = [
            ChatMessageResponse(
                id=msg["id"],
                role=MessageRole(msg["role"]),
                content=msg["content"],
                conversation_id=msg["conversation_id"],
                created_at=datetime.fromisoformat(msg["created_at"].replace('Z', '+00:00'))
            )
            for msg in messages_data
        ]
        
        return ConversationHistory(
            conversation_id=conversation_id,
            messages=messages,
            total_messages=len(messages)
        )
    
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取对话历史失败"
        )

@router.get("/conversations")
async def get_user_conversations(
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """获取用户的所有对话列表"""
    try:
        db = await get_db_client()
        user_id = current_user["id"]
        
        conversations = await db.get_user_conversations(
            user_id=user_id,
            limit=limit
        )
        
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    
    except Exception as e:
        logger.error(f"获取对话列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取对话列表失败"
        )

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """删除对话"""
    try:
        db = await get_db_client()
        user_id = current_user["id"]
        
        success = await db.delete_conversation(
            user_id=user_id,
            conversation_id=conversation_id
        )
        
        if success:
            return {"message": "对话删除成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在或删除失败"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除对话失败"
        )

@router.post("/conversations/new")
async def create_new_conversation(
    current_user: dict = Depends(get_current_user)
):
    """创建新对话"""
    try:
        conversation_id = str(uuid.uuid4())
        
        return {
            "conversation_id": conversation_id,
            "message": "新对话创建成功"
        }
    
    except Exception as e:
        logger.error(f"创建新对话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建新对话失败"
        )