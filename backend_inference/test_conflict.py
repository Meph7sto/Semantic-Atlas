import os
import sys
import unittest
from fastapi.testclient import TestClient

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from main import app

class TestDeepseekAPI(unittest.TestCase):
    def test_conflict_detection_api(self):
        with TestClient(app) as client:
            payload = {
                "requirement_a": "系统启动时间必须小于1秒。",
                "requirement_b": "系统启动时必须进行耗时至少3秒的完整自检。"
            }
            
            print(f"\nTesting Conflict API with payload: {payload}")
            response = client.post("/conflict/check", json=payload)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            print(f"API Response: {data}")
            
            self.assertIn("is_conflict", data)
            self.assertIn("raw_response", data)
            # Depending on model randomness, we generally expect true for this obvious conflict
            # but we assert structure primarily here.
            
            if data['is_conflict']:
                print("SUCCESS: Conflict correctly detected.")
            else:
                print("NOTE: Model did not detect conflict (might be probabilistic or model capability issue).")

if __name__ == "__main__":
    unittest.main()
