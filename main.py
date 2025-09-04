from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from config import validate_settings
from routers import auth_router, chat_router
from routers.notifications import router as notifications_router
import logging
import os
import uvicorn
from typing import List


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 验证环境变量
try:
    validate_settings()
    logger.info("环境变量验证成功")
except ValueError as e:
    logger.error(f"环境变量验证失败: {e}")
    # 在开发环境中，我们允许继续运行但会记录警告
    logger.warning("继续运行，但某些功能可能不可用")

# 创建FastAPI应用实例
app = FastAPI(
    title="AI Language Learning App",
    description="A minimal AI language learning web application with chat functionality",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://127.0.0.1:3000", 
        "http://localhost:3001", 
        "http://127.0.0.1:3001",  # 本地开发服务器
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # 允许所有 Vercel 域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由器
app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")

# 健康检查端点
@app.get("/")
async def root():
    return {"message": "AI Language Learning App API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/info")
async def api_info():
    return {
        "name": "AI Language Learning App API",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/api/auth",
            "chat": "/api/chat"
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
