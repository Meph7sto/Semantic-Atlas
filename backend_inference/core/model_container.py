from .engine import DeepSeekEngine
from .classification_engine import RequirementClassificationEngine
from .config import settings


# 全局模型容器，支持本地模型或远程 API 模式
model_engine = DeepSeekEngine(
    model_path=settings.MODEL_PATH,
    provider=settings.MODEL_PROVIDER,
    chutes_api_url=settings.CHUTES_API_URL,
    chutes_api_token=settings.CHUTES_API_TOKEN,
    deepseek_api_url=settings.DEEPSEEK_API_URL,
    deepseek_api_key=settings.DEEPSEEK_API_KEY,
    deepseek_model=getattr(settings, "DEEPSEEK_MODEL", "deepseek-reasoner"),
)
# 全局模型容器
# 此模块充当模型引擎的单例持有者。
# 它在 main.py 的启动事件期间被初始化。

classification_engine = RequirementClassificationEngine(
    model_path=settings.CLASSIFICATION_MODEL_PATH,
    label_encoder_path=settings.CLASSIFICATION_LABEL_ENCODER_PATH,
    batch_size=settings.CLASSIFICATION_BATCH_SIZE,
    max_seq_len=settings.CLASSIFICATION_MAX_SEQ_LEN,
    provider=settings.CLASSIFICATION_PROVIDER,
    chutes_api_url=settings.CHUTES_API_URL,
    chutes_api_token=settings.CHUTES_API_TOKEN,
    deepseek_api_url=settings.DEEPSEEK_API_URL,
    deepseek_api_key=settings.DEEPSEEK_API_KEY,
    deepseek_model=getattr(settings, "DEEPSEEK_MODEL", "deepseek-reasoner"),
    labels=settings.CLASSIFICATION_LABELS,
    other_label=settings.CLASSIFICATION_OTHER_LABEL,
)
