# Semantic-Atlas

## 目录结构

```
data/
├── models/
│   └── deberta-v3-large/
│       ├── config.json
│       └── pytorch_model.bin
├── ollama_home/
├── pg_data/
└── datasets/

deploy/
├── nginx.conf
└── start.sh

frontend/
├── src/
│   ├── assets/
│   ├── components/
│   │   ├── charts/
│   │   │   ├── TraceGraph.vue
│   │   │   └── Heatmap.vue
│   │   └── FileUpload.vue
│   ├── stores/
│   │   └── reqStore.js
│   ├── views/
│   │   ├── Classification.vue
│   │   ├── Traceability.vue
│   │   └── ConflictDetection.vue
│   └── utils/
│       └── api.js
└── package.json

backend_business/
├── app.py
├── config.py
├── routes/
│   ├── file_route.py
│   └── analysis_route.py
└── services/
    ├── db_service.py
    └── ai_proxy.py

backend_inference/
├── main.py
├── schemas/
│   ├── classification.py
│   ├── trace_output.py
│   └── conflict_report.py
├── core/
│   ├── model_loader.py
│   └── ollama_client.py
└── tasks/
    ├── classify.py
    ├── trace.py
    └── conflict.py
```