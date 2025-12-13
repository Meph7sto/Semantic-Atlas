import os

class Settings:
    # 获取项目根目录 (假设结构为: root/backend_inference/core/config.py)
    # 通过多次调用 os.path.dirname 回溯到根目录
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 模型路径配置
    # 定义模型相对于项目根目录的路径
    MODEL_RELATIVE_PATH = os.path.join("data", "models", "deepseek_conflict")
    # 拼接绝对路径
    MODEL_PATH = os.path.join(BASE_DIR, MODEL_RELATIVE_PATH)
    
    # 模型参数默认配置
    DEFAULT_MAX_TOKENS = 128
    DEFAULT_SYSTEM_PROMPT = "你是一个有用的中文助手。"

# 实例化配置对象，供其他模块使用
settings = Settings()
