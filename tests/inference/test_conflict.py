import os
import sys
import unittest
from fastapi.testclient import TestClient

# 将 backend_inference 加入 sys.path 以导入 main 应用
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend_inference"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from main import app


class TestConflictAPI(unittest.TestCase):
    """基本冲突检测接口回归测试"""

    def test_conflict_detection_api(self):
        payload = {
            "requirement_a": "系统启动时间必须小于1秒。",
            "requirement_b": "系统启动时必须进行耗时至少3秒的完整自检。"
        }

        with TestClient(app) as client:
            response = client.post("/conflict/check", json=payload)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn("is_conflict", data)
            self.assertIn("raw_response", data)

            # 若模型检测到冲突则为 True；此处重点验证响应结构与接口可用性


if __name__ == "__main__":
    unittest.main()
