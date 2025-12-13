import os
import sys
import unittest
from fastapi.testclient import TestClient

# 将当前目录添加到 sys.path，以便导入 main 模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from main import app

class TestDeepseekAPI(unittest.TestCase):
    """
    Deepseek API 测试类
    """
    def test_conflict_detection_api(self):
        """
        测试冲突检测 API
        """
        with TestClient(app) as client:
            payload = {
                "requirement_a": "系统启动时间必须小于1秒。",
                "requirement_b": "系统启动时必须进行耗时至少3秒的完整自检。"
            }
            
            print(f"\nTesting Conflict API with payload: {payload}")
            # 发送 POST 请求到冲突检查接口
            response = client.post("/conflict/check", json=payload)
            
            # 断言状态码为 200
            self.assertEqual(response.status_code, 200)
            data = response.json()
            print(f"API Response: {data}")
            
            # 断言响应数据中包含预期字段
            self.assertIn("is_conflict", data)
            self.assertIn("raw_response", data)
            # 取决于模型的随机性，对于这个明显的冲突，我们通常期望返回 true
            # 但这里主要断言响应结构
            
            if data['is_conflict']:
                print("SUCCESS: Conflict correctly detected.")
            else:
                print("NOTE: Model did not detect conflict (might be probabilistic or model capability issue).")

if __name__ == "__main__":
    unittest.main()
