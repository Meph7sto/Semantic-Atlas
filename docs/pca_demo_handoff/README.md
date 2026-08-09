# PCA 演示改动交接总览

这组文档说明 PCA 患者自控镇痛输液泵 demo 是怎么接到系统里的，方便另一个人把同样效果部署到服务器。

## 演示目标

演示项目固定为：

```text
project_id: demo-pca-infusion-pump-project
project_name: Demo · PCA患者自控镇痛输液泵
session_id: demo-pca-infusion-pump-session
```

当前 demo 覆盖 4 个页面/能力：

1. 需求条目化和需求列表：启动时直接写入 PCA 项目、顶层需求、底层需求和追溯链接。
2. 需求分析：点击分析按钮后，生成追溯、冲突检测、需求分类结果。
3. 音频转文字：上传音频并点击开始转写后，直接展示对应会议纪要文本；退出再进不会提前显示旧 demo 痕迹。
4. 需求图谱：初始只显示结构图，点击生成图谱后增加推理关系边。

## 文档结构

```text
docs/pca_demo_handoff/
  01_frontend/README.md
  02_backend/README.md
  03_database/README.md
  04_deployment/README.md
  05_verification/README.md
```

推荐交接阅读顺序：

1. 先读 `03_database`，理解库表怎么被写成 demo。
2. 再读 `02_backend`，理解按钮点击后后端为什么直接出效果。
3. 再读 `01_frontend`，理解页面上怎么触发和隐藏痕迹。
4. 最后读 `04_deployment` 和 `05_verification`，按步骤部署和验收。

## 核心源码入口

```text
backend_business/scripts/seed_pca_demo.py
deploy/start.ps1
frontend/src/composables/useRequirementsAnalysis.js
frontend/src/views/beta/MultimodalIngestionView.vue
frontend/src/views/beta/RequirementsView.vue
backend_business/api/routers/analysis.py
backend_business/api/routers/asr.py
backend_business/services/requirement_graph/orchestrator.py
```
