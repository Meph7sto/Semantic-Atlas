from flask import Blueprint, request, jsonify
import requests
import os

# 创建一个 Blueprint (蓝图)，用于组织冲突检测相关的路由
conflict_bp = Blueprint('conflict', __name__)

# 配置
# 从环境变量读取推理服务的 URL，默认为 localhost:8000
INFERENCE_SERVICE_URL = os.getenv("INFERENCE_URL", "http://localhost:8000")

@conflict_bp.route('/check', methods=['POST'])
def check_conflict():
    """
    检查冲突接口
    代理请求到推理后端 (Inference Backend)
    """
    try:
        # 获取请求的 JSON 数据
        data = request.json
        # 转发请求到推理后端
        # 注意: 推理后端的路径是 /conflict/check
        # 这里的蓝图前缀处理了 /api/conflict，所以实际请求路径会对应
        
        # 向推理服务发起 POST 请求
        resp = requests.post(f"{INFERENCE_SERVICE_URL}/conflict/check", json=data)
        
        # Try to parse JSON, if not, return text
        try:
            resp_data = resp.json()
        except ValueError:
            resp_data = {"detail": f"Upstream Inference Error: {resp.text}"}

        return jsonify(resp_data), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"detail": f"Cannot connect to Inference Service at {INFERENCE_SERVICE_URL}. Is it running?"}), 503
    except Exception as e:
        return jsonify({"detail": f"Business Backend Error: {str(e)}"}), 500
