import os

# 尝试自动加载项目根目录的 .env，便于本地开发/测试
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # 若未安装则忽略，由 requirements 安装后生效
    load_dotenv = None

if load_dotenv:
    _ROOT_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    load_dotenv(_ROOT_ENV_PATH, override=False)

class Settings:
    # 获取项目根目录 (假设结构为: root/backend_inference/core/config.py)
    # 通过多次调用 os.path.dirname 回溯到根目录
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 模型提供方，local 使用本地权重；chutes / deepseek 为 API 调用
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "local").lower()

    # 模型路径配置
    # 定义模型相对于项目根目录的路径
    MODEL_RELATIVE_PATH = os.path.join("data", "models", "deepseek_conflict")
    # 拼接绝对路径
    MODEL_PATH = os.path.join(BASE_DIR, MODEL_RELATIVE_PATH)
    
    # Chutes API 配置
    CHUTES_API_URL = os.getenv("CHUTES_API_URL", "https://llm.chutes.ai/v1/chat/completions")
    CHUTES_API_TOKEN = os.getenv("CHUTES_API_TOKEN") or os.getenv("CHUTES_API_KEY")

    # DeepSeek API 占位配置
    DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

    # 模型参数默认配置
    DEFAULT_MAX_TOKENS = 8096
    DEFAULT_SYSTEM_PROMPT = "你是一个有用的中文助手。"

# 实例化配置对象，供其他模块使用
settings = Settings()
