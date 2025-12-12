import os

class Settings:
    # Get the project root directory (assuming structure: root/backend_inference/core/config.py)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Model Path
    MODEL_RELATIVE_PATH = os.path.join("data", "models", "deepseek_conflict")
    MODEL_PATH = os.path.join(BASE_DIR, MODEL_RELATIVE_PATH)
    
    # Model Parameters
    DEFAULT_MAX_TOKENS = 128
    DEFAULT_SYSTEM_PROMPT = "你是一个有用的中文助手。"

settings = Settings()
