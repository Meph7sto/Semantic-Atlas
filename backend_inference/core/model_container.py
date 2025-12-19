from core.engine import DeepSeekEngine
from core.config import settings

# 全局模型容器，支持本地模型或远程 API 模式
model_engine = DeepSeekEngine(
    model_path=settings.MODEL_PATH,
    provider=settings.MODEL_PROVIDER,
    chutes_api_url=settings.CHUTES_API_URL,
    chutes_api_token=settings.CHUTES_API_TOKEN,
    deepseek_api_url=settings.DEEPSEEK_API_URL,
    deepseek_api_key=settings.DEEPSEEK_API_KEY,
)
