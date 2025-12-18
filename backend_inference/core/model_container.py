from core.engine_tr import DeepSeekEngine
from core.config import settings

# 全局模型容器
# 此模块充当模型引擎的单例持有者。
# 它在 main.py 的启动事件期间被初始化。

model_engine = DeepSeekEngine(model_path=settings.MODEL_PATH)
