import json
import os

# 尝试自动加载项目根目录的 .env，便于本地开发/测试
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # 若未安装则忽略，由 requirements 安装后生效
    load_dotenv = None

if load_dotenv:
    _ROOT_ENV_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    load_dotenv(_ROOT_ENV_PATH, override=False)


class Settings:
    # 获取项目根目录 (假设结构为: root/backend_inference/core/config.py)
    # 通过多次调用 os.path.dirname 回溯到根目录
    BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    # 模型提供方，local 使用本地权重；chutes / deepseek 为 API 调用
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "local").lower()
    CLASSIFICATION_PROVIDER = os.getenv("CLASSIFICATION_PROVIDER", MODEL_PROVIDER).lower()

    # 生成式模型（冲突/追溯等）路径配置
    MODEL_RELATIVE_PATH = os.getenv(
        "LLM_MODEL_RELATIVE_PATH",
        os.path.join("data", "models", "deepseek_conflict"),
    )
    MODEL_PATH = os.path.join(BASE_DIR, MODEL_RELATIVE_PATH)

    # 远程 API（可选）——用于 provider=chutes/deepseek 时
    CHUTES_API_URL = os.getenv("CHUTES_API_URL", "")
    CHUTES_API_TOKEN = os.getenv("CHUTES_API_TOKEN", "")
    DEEPSEEK_API_URL = os.getenv(
        "DEEPSEEK_API_URL",
        "https://api.deepseek.com/v1/chat/completions",
    )
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # 需求分类模型配置（本地 encoder 模型）
    CLASSIFICATION_MODEL_RELATIVE_PATH = os.getenv(
        "CLASSIFICATION_MODEL_RELATIVE_PATH",
        os.path.join("data", "models", "deberta-v3-large"),
    )
    CLASSIFICATION_MODEL_PATH = os.path.join(
        BASE_DIR, CLASSIFICATION_MODEL_RELATIVE_PATH
    )
    CLASSIFICATION_LABEL_ENCODER_PATH = os.getenv(
        "CLASSIFICATION_LABEL_ENCODER_PATH",
        os.path.join(CLASSIFICATION_MODEL_PATH, "label_encoder.pkl"),
    )
    CLASSIFICATION_BATCH_SIZE = int(os.getenv("CLASSIFICATION_BATCH_SIZE", "32"))
    CLASSIFICATION_MAX_SEQ_LEN = int(os.getenv("CLASSIFICATION_MAX_SEQ_LEN", "256"))
    CLASSIFICATION_LABELS = []
    CLASSIFICATION_OTHER_LABEL = os.getenv("CLASSIFICATION_OTHER_LABEL", "其他")

    _labels_raw = os.getenv("CLASSIFICATION_LABELS", "")
    if _labels_raw:
        try:
            parsed = json.loads(_labels_raw)
            if isinstance(parsed, list):
                CLASSIFICATION_LABELS = [str(item).strip() for item in parsed if str(item).strip()]
            else:
                CLASSIFICATION_LABELS = [s.strip() for s in _labels_raw.split(",") if s.strip()]
        except json.JSONDecodeError:
            CLASSIFICATION_LABELS = [s.strip() for s in _labels_raw.split(",") if s.strip()]

    # 模型参数默认配置
    DEFAULT_MAX_TOKENS = 8096
    DEFAULT_SYSTEM_PROMPT = "你是一个有用的中文助手。"


# 实例化配置对象，供其他模块使用
settings = Settings()
