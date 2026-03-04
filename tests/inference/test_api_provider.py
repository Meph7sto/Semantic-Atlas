import os
import sys
import unittest

# 将 backend_inference 加入 sys.path 以导入引擎与配置
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend_inference"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.config import settings
from core.engine import DeepSeekEngine


CHUTES_TOKEN = os.getenv("CHUTES_API_TOKEN") or os.getenv("CHUTES_API_KEY")


class TestChutesAPI(unittest.TestCase):
    """测试 Chutes API 调用是否能返回内容（需要环境变量 CHUTES_API_TOKEN）"""

    @unittest.skipUnless(CHUTES_TOKEN, "CHUTES_API_TOKEN not set; skipping live API test")
    def test_chutes_generate(self):
        engine = DeepSeekEngine(
            model_path=settings.MODEL_PATH,
            provider="chutes",
            chutes_api_url=os.getenv("CHUTES_API_URL", settings.CHUTES_API_URL),
            chutes_api_token=CHUTES_TOKEN,
        )

        prompt = "请用一句话总结测试目的。"
        system_prompt = "你是一个精简回答的助手。"

        result = engine.generate(prompt=prompt, system_prompt=system_prompt, max_new_tokens=64)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result.strip()), 0, "API 返回内容为空")


if __name__ == "__main__":
    unittest.main()
