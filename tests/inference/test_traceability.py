import os
import sys
import unittest

from fastapi.testclient import TestClient

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from main import app


class TestTraceabilityAPI(unittest.TestCase):
    def test_traceability_relation_api_structure(self):
        """
        只验证接口可用性与返回结构（不强行断言模型一定能判断出关系）。
        如果本地未加载模型，期望返回 503。
        """
        with TestClient(app) as client:
            payload = {
                "high_level_requirement": "系统应提供用户登录功能。",
                "low_level_requirement": "实现用户名密码校验与会话管理。",
                "max_new_tokens": 256,
            }
            resp = client.post("/traceability/relation", json=payload)

            if resp.status_code == 503:
                # 模型未加载/不可用是允许的
                self.assertIn("detail", resp.json())
                return

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            for k in [
                "high_level_requirement",
                "low_level_requirement",
                "has_relation",
                "relation_type",
                "confidence",
                "summary",
                "analysis_details",
                "keywords",
                "suggestions",
                "trace_network",
            ]:
                self.assertIn(k, data)
            self.assertIn("nodes", data["trace_network"])
            self.assertIn("links", data["trace_network"])

    def test_traceability_batch_api_structure(self):
        with TestClient(app) as client:
            payload = {
                "high_level_requirements": [
                    "系统应提供用户登录功能。",
                    "系统应支持权限管理。",
                ],
                "low_level_requirements": [
                    "实现用户名密码校验与会话管理。",
                    "实现角色-权限映射表。",
                ],
                "max_new_tokens": 512,
            }
            resp = client.post("/traceability/batch-relation", json=payload)

            if resp.status_code == 503:
                self.assertIn("detail", resp.json())
                return

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            for k in ["summary", "statistics", "relations", "trace_network"]:
                self.assertIn(k, data)
            self.assertIn("total_combinations", data["statistics"])
            self.assertIn("relations_found", data["statistics"])
            self.assertIn("relation_rate", data["statistics"])
            self.assertIn("nodes", data["trace_network"])
            self.assertIn("links", data["trace_network"])


if __name__ == "__main__":
    unittest.main()


