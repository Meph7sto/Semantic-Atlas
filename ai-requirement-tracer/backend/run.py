#!/usr/bin/env python3
"""
Backend Entry Point - 后端入口文件
后端服务启动文件

文件功能：
- Flask应用启动入口
- 配置服务器监听地址和端口
- 注意：现在主要使用autodl_model_integration.py作为主服务
"""
import os
from app import create_app

# 创建Flask应用
app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

if __name__ == '__main__':
    # 开发环境运行
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=True
    )
