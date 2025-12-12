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
        # 返回推理服务的响应内容和状态码
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        # 如果连接推理服务失败，返回 503 服务不可用错误
        return jsonify({"detail": "Inference service unavailable"}), 503
    except Exception as e:
        # 捕获其他异常并返回 500 内部服务器错误
        return jsonify({"detail": str(e)}), 500
