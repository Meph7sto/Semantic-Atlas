from core.engine import DeepSeekEngine
from core.config import settings

# Global Model Container
# This module acts as a singleton holder for the model engine.
# It is initialized during the startup event in main.py.

model_engine = DeepSeekEngine(model_path=settings.MODEL_PATH)
