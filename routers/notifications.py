from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from auth import get_current_user
from database import get_db_client
from models import ErrorResponse
import logging
import json
import asyncio
from datetime import datetime
from enum import Enum

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/notifications", tags=["通知"])

class NotificationType(str, Enum):
    """通知类型枚举"""
    MESSAGE_RECEIVED = "message_received"
    CONVERSATION_UPDATED = "conversation_updated"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    SYSTEM_NOTIFICATION = "system_notification"

class NotificationEvent:
    """通知事件模型"""
    def __init__(self, 
                 event_type: NotificationType, 
                 data: Dict[Any, Any], 
                 user_id: str = None,
                 conversation_id: str = None):
        self.event_type = event_type
        self.data = data
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.timestamp = datetime.utcnow().isoformat()
        self.event_id = f"{event_type}_{int(datetime.utcnow().timestamp() * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp
        }

# 全局事件存储（生产环境中应使用Redis或其他消息队列）
class EventStore:
    def __init__(self):
        self.events: List[NotificationEvent] = []
        self.subscribers: Dict[str, List[asyncio.Queue]] = {}
    
    async def publish_event(self, event: NotificationEvent):
        """发布事件到所有订阅者"""
        self.events.append(event)
        
        # 保持最近1000个事件
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
        
        # 通知订阅者
        user_id = event.user_id or "global"
        if user_id in self.subscribers:
            for queue in self.subscribers[user_id]:
                try:
                    await queue.put(event)
                except Exception as e:
                    logger.error(f"Failed to notify subscriber: {e}")
    
    def subscribe(self, user_id: str) -> asyncio.Queue:
        """订阅用户事件"""
        if user_id not in self.subscribers:
            self.subscribers[user_id] = []
        
        queue = asyncio.Queue(maxsize=100)
        self.subscribers[user_id].append(queue)
        return queue
    
    def unsubscribe(self, user_id: str, queue: asyncio.Queue):
        """取消订阅"""
        if user_id in self.subscribers:
            try:
                self.subscribers[user_id].remove(queue)
                if not self.subscribers[user_id]:
                    del self.subscribers[user_id]
            except ValueError:
                pass
    
    def get_recent_events(self, user_id: str, limit: int = 50) -> List[NotificationEvent]:
        """获取最近的事件"""
        user_events = [e for e in self.events if e.user_id == user_id or e.user_id is None]
        return user_events[-limit:]

# 全局事件存储实例
event_store = EventStore()

@router.get("/recent")
async def get_recent_notifications(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """获取最近的通知事件（轮询方式）"""
    try:
        user_id = current_user["id"]
        events = event_store.get_recent_events(user_id, limit)
        
        return {
            "events": [event.to_dict() for event in events],
            "count": len(events),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"获取通知失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取通知失败"
        )

@router.get("/stream")
async def stream_notifications(
    current_user: dict = Depends(get_current_user)
):
    """Server-Sent Events (SSE) 流式通知（为未来扩展预留）"""
    user_id = current_user["id"]
    
    async def event_generator():
        queue = event_store.subscribe(user_id)
        try:
            # 发送连接确认
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"
            
            while True:
                try:
                    # 等待新事件，设置超时以发送心跳
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_data = json.dumps(event.to_dict())
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                except Exception as e:
                    logger.error(f"SSE stream error: {e}")
                    break
        finally:
            event_store.unsubscribe(user_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

# 辅助函数：发布事件
async def publish_notification(
    event_type: NotificationType,
    data: Dict[Any, Any],
    user_id: str = None,
    conversation_id: str = None
):
    """发布通知事件的辅助函数"""
    event = NotificationEvent(
        event_type=event_type,
        data=data,
        user_id=user_id,
        conversation_id=conversation_id
    )
    await event_store.publish_event(event)
    logger.info(f"Published notification: {event_type} for user {user_id}")

# 示例：消息接收通知
async def notify_message_received(user_id: str, conversation_id: str, message_data: Dict[Any, Any]):
    """通知用户收到新消息"""
    await publish_notification(
        event_type=NotificationType.MESSAGE_RECEIVED,
        data={
            "message": message_data,
            "conversation_id": conversation_id
        },
        user_id=user_id,
        conversation_id=conversation_id
    )

# 示例：对话更新通知
async def notify_conversation_updated(user_id: str, conversation_id: str, update_data: Dict[Any, Any]):
    """通知用户对话已更新"""
    await publish_notification(
        event_type=NotificationType.CONVERSATION_UPDATED,
        data={
            "conversation_id": conversation_id,
            "updates": update_data
        },
        user_id=user_id,
        conversation_id=conversation_id
    )