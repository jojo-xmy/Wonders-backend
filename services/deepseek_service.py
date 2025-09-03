import openai
from typing import List, Dict, Any, Optional
from config import settings
from models import MessageRole
import logging
import asyncio
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class DeepSeekService:
    """DeepSeek API服务类"""
    
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化OpenAI客户端（用于DeepSeek API）"""
        try:
            self.client = openai.AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url
            )
            logger.info("DeepSeek客户端初始化成功")
        except Exception as e:
            logger.error(f"DeepSeek客户端初始化失败: {e}")
            raise
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> Dict[str, Any]:
        """生成AI响应"""
        try:
            if not self.client:
                self._initialize_client()
            
            # 确保消息格式正确
            formatted_messages = self._format_messages(messages)
            
            logger.info(f"发送请求到DeepSeek API，消息数量: {len(formatted_messages)}")
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            
            if stream:
                return {"stream": response}
            else:
                result = {
                    "content": response.choices[0].message.content,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "finish_reason": response.choices[0].finish_reason,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                logger.info(f"DeepSeek API响应成功，使用tokens: {result['usage']['total_tokens']}")
                return result
        
        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            raise
    
    def _format_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """格式化消息为OpenAI API格式"""
        formatted = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 确保角色名称符合OpenAI API规范
            if role == MessageRole.USER.value:
                formatted.append({"role": "user", "content": content})
            elif role == MessageRole.ASSISTANT.value:
                formatted.append({"role": "assistant", "content": content})
            elif role == MessageRole.SYSTEM.value:
                formatted.append({"role": "system", "content": content})
            else:
                # 默认作为用户消息处理
                formatted.append({"role": "user", "content": content})
        
        return formatted
    
    async def generate_streaming_response(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        """生成流式AI响应"""
        try:
            response_data = await self.generate_response(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            stream = response_data["stream"]
            full_content = ""
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_content += content
                    yield {
                        "content": content,
                        "full_content": full_content,
                        "finished": False
                    }
            
            # 发送完成信号
            yield {
                "content": "",
                "full_content": full_content,
                "finished": True
            }
        
        except Exception as e:
            logger.error(f"流式响应生成失败: {e}")
            yield {
                "error": str(e),
                "finished": True
            }
    
    def create_system_message(self, content: str) -> Dict[str, str]:
        """创建系统消息"""
        return {
            "role": MessageRole.SYSTEM.value,
            "content": content
        }
    
    def create_language_learning_system_prompt(self, target_language: str = "English") -> str:
        """创建语言学习系统提示"""
        return f"""你是一个专业的{target_language}语言学习助手。请遵循以下指导原则：

1. 根据用户的语言水平调整回答的复杂度
2. 在适当的时候纠正用户的语法或用词错误
3. 提供实用的语言学习建议和练习
4. 鼓励用户多使用目标语言进行对话
5. 解释语言规则和文化背景
6. 保持耐心和鼓励的态度

请用简洁、友好的方式回应用户，并在必要时提供例句和解释。"""
    
    async def health_check(self) -> bool:
        """检查DeepSeek API连接状态"""
        try:
            test_messages = [
                {"role": "user", "content": "Hello"}
            ]
            
            response = await self.generate_response(
                messages=test_messages,
                max_tokens=10
            )
            
            return response is not None and "content" in response
        
        except Exception as e:
            logger.error(f"DeepSeek API健康检查失败: {e}")
            return False

# 创建全局DeepSeek服务实例
deepseek_service = DeepSeekService()

# 便捷函数
async def get_deepseek_service() -> DeepSeekService:
    """获取DeepSeek服务实例"""
    return deepseek_service