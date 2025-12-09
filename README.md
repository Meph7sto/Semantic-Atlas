# Semantic-Atlas
├── data/                          # 【数据中心】物理存储大文件 (安全存储在数据盘)
│   ├── models/                    # DeBERTa-v3 模型权重存放处
│   │   └── deberta-v3-large/
│   │       ├── config.json        # 模型配置文件
│   │       └── pytorch_model.bin  # 模型权重文件
│   ├── ollama_home/               # DeepSeek-7B 模型实际存储地 (OLLAMA_MODELS 环境变量指向这里)
│   ├── pg_data/                   # PostgreSQL 数据库持久化存储文件
│   └── datasets/                  # 训练/测试数据集 (如 CSV 文件)
│
├── deploy/                        # 【部署与启动】
│   ├── nginx.conf                 # Nginx 配置文件 (单端口 6006 转发配置)
│   └── start.sh                   # 一键启动所有服务的脚本
│
├── frontend/                      # 【前端展示层】Vue 3 + ECharts (Nginx Service)
│   ├── src/
│   │   ├── assets/                # 静态资源、样式文件
│   │   ├── components/            # 可复用 UI 组件
│   │   │   ├── charts/            # ECharts 图表组件
│   │   │   │   ├── TraceGraph.vue # 追溯图谱可视化组件
│   │   │   │   └── Heatmap.vue    # 分类热力图/关联强度图
│   │   │   └── FileUpload.vue     # 文件上传与进度条组件
│   │   ├── stores/                # Pinia 状态管理模块
│   │   │   └── reqStore.js        # 核心状态 (存储分类结果、追溯数据、冲突列表)
│   │   ├── views/                 # 页面级组件 (三视图布局)
│   │   │   ├── Classification.vue # 需求分类主页
│   │   │   ├── Traceability.vue   # 需求追溯主页 (三视图联动核心逻辑)
│   │   │   └── ConflictDetection.vue # 冲突检测主页
│   │   └── utils/
│   │       └── api.js             # Axios 封装 (BaseURL 配置为 /api)
│   └── package.json
│
├── backend_business/              # 【业务逻辑层】Flask (Port: 5000)
│   ├── app.py                     # Flask 应用入口 (注册路由、配置)
│   ├── config.py                  # 数据库连接、端口等配置
│   ├── routes/                    # 路由定义 (处理 HTTP 请求)
│   │   ├── file_route.py          # /api/upload_csv, /api/download_result 
│   │   └── analysis_route.py      # /api/trigger_analysis (调用 FastAPI 推理)
│   └── services/                  # 业务服务层
│       ├── db_service.py          # PostgreSQL 增删改查逻辑
│       └── ai_proxy.py            # 转发请求到 FastAPI :8000 的客户端
│
└── backend_inference/             # 【模型推理层】FastAPI (Port: 8000)
    ├── main.py                    # FastAPI 应用启动入口
    ├── schemas/                   # Pydantic 模型 (定义结构化输出的 JSON 格式)
    │   ├── classification.py      # 分类结果 Pydantic 模型
    │   ├── trace_output.py        # 追溯结果模型 (nodes/links/relations 结构)
    │   └── conflict_report.py     # 冲突检测报告模型
    ├── core/                      # 模型核心组件
    │   ├── model_loader.py        # 加载 DeBERTa-v3 模型到内存
    │   └── ollama_client.py       # DeepSeek (Ollama) API 客户端封装
    └── tasks/                     # 核心 AI 任务逻辑
        ├── classify.py            # 需求分类逻辑 (调用 DeBERTa)
        ├── trace.py               # 需求追溯逻辑 (调用 DeepSeek, 构造思维链 Prompt)
        └── conflict.py            # 需求冲突检测逻辑 (调用 DeepSeek)