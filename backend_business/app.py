from flask import Flask, jsonify
from flask_cors import CORS
from routes.conflict_routes import conflict_bp

# 初始化 Flask 应用实例
app = Flask(__name__)
# 启用跨域资源共享 (CORS) 支持
CORS(app)

# 配置项
# 定义业务后端服务的运行端口
BUSINESS_PORT = 5001

@app.route('/health', methods=['GET'])
def health():
    """
    健康检查接口
    返回服务的运行状态
    """
    return jsonify({"status": "business_backend_ok"})

# 注册蓝图 (Blueprints)
# 将 /api/conflict/check 映射到 conflict_bp.check_conflict
# url_prefix 设置了该蓝图下所有路由的前缀
app.register_blueprint(conflict_bp, url_prefix='/api/conflict')

if __name__ == '__main__':
    # 使用 0.0.0.0 监听所有网络接口，使服务在外部可访问
    # 为了更好的实践移除了 debug=True，如果有需要可以使用环境变量配置
    app.run(host='0.0.0.0', port=BUSINESS_PORT)
