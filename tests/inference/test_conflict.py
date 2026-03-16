import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_inference.main import app


class TestConflictAPI(unittest.TestCase):
    """基本冲突检测接口回归测试"""

    def test_conflict_detection_api(self):
        payload = {
            "requirement_a": "系统启动时间必须小于1秒。",
            "requirement_b": "系统启动时必须进行耗时至少3秒的完整自检。"
        }

        with patch(
            "routers.conflict.conflict_service.check_conflict",
            return_value={
                "is_conflict": True,
                "raw_response": "冲突：启动时间约束与完整自检耗时不一致",
            },
        ):
            with TestClient(app) as client:
                response = client.post("/conflict/check", json=payload)
                self.assertEqual(response.status_code, 200)

                data = response.json()
                self.assertIn("is_conflict", data)
                self.assertIn("raw_response", data)

            # 若模型检测到冲突则为 True；此处重点验证响应结构与接口可用性


if __name__ == "__main__":
    unittest.main()
