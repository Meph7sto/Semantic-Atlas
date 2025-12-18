import os

class Settings:
    # 获取项目根目录 (假设结构为: root/backend_inference/core/config.py)
    # 通过多次调用 os.path.dirname 回溯到根目录
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Model Path
    # 默认期望一个可用于 AutoModelForCausalLM/Seq2SeqLM 的大模型目录（例如 DeepSeek/Qwen 等）。
    # 可通过环境变量 INFERENCE_MODEL_PATH 覆盖，便于在不同机器/容器中挂载模型目录。
    MODEL_RELATIVE_PATH = os.path.join("data", "models", "deepseek_conflict")
    MODEL_PATH = os.environ.get("INFERENCE_MODEL_PATH") or os.path.join(BASE_DIR, MODEL_RELATIVE_PATH)
    
    # 模型参数默认配置
    DEFAULT_MAX_TOKENS = 128
    DEFAULT_SYSTEM_PROMPT = "你是一个有用的中文助手。"

# 实例化配置对象，供其他模块使用
settings = Settings()
