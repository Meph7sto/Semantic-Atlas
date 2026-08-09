# 后端改动说明

后端改动的核心是：启动时写入基础 demo 数据，按钮点击后再生成演示结果。

## PCA 数据种子脚本

文件：

```text
backend_business/scripts/seed_pca_demo.py
```

作用：

1. 读取 PCA 原始需求清单 md。
2. 读取 PCA 会议纪要 txt。
3. 解析出顶层需求、底层需求和追溯关系。
4. 写入项目管理、需求条目化、需求追溯、初始图谱相关表。
5. 清理旧的 PCA demo 分析和图谱结果，保证每次启动都是初始演示状态。

支持配置：

```text
PCA_DEMO_MD_PATH
PCA_DEMO_TXT_PATH
```

也可以命令行传：

```powershell
python backend_business/scripts/seed_pca_demo.py --md "D:\demo\demo_PCA输液泵原始需求清单.md" --txt "D:\demo\demo_PCA输液泵需求调研会议记录.txt"
```

## 一键启动自动 seed

文件：

```text
deploy/start.ps1
```

启动业务服务前会执行：

```powershell
python backend_business/scripts/seed_pca_demo.py --skip-if-missing
```

如果服务器没有放 demo md 文件，脚本会跳过，不会阻断启动。正式演示服务器必须配置 `PCA_DEMO_MD_PATH` 和 `PCA_DEMO_TXT_PATH`，或者把文件放到默认路径。

可以用下面环境变量跳过 demo seed：

```text
SKIP_PCA_DEMO_SEED=1
```

## 需求分析保存接口

文件：

```text
backend_business/api/routers/analysis.py
```

改动逻辑：

当前端保存分析结果并带上：

```text
meta.source = pca_demo_click_analysis
```

后端会额外把结果写入：

```text
trace_analysis
conflict_analysis
classification_analysis
requirements_analysis_runs
```

这样页面点击分析后，不只前端有展示，数据库中也有完整分析记录。

## 音频转文字接口

文件：

```text
backend_business/api/routers/asr.py
backend_business/api/routers/schemas/asr_schemas.py
backend_business/services/db_service_parts/transcription.py
```

改动逻辑：

1. 创建转写会话接口增加查询参数：

```text
demo=pca
```

2. 如果是 PCA demo，后端直接读取会议纪要文本并完成转写会话。

3. 转写记录写入标记：

```text
remote_request_id = pca-demo-transcript
transcript_metadata.source = pca_demo_audio_transcription
```

4. 会话列表接口返回 `remote_request_id` 和 `transcript_metadata`，前端用它过滤历史 demo 痕迹。

会议纪要文本路径支持：

```text
PCA_DEMO_TRANSCRIPT_PATH
```

通常可以和 `PCA_DEMO_TXT_PATH` 配成同一个文件。

## 需求图谱服务

文件：

```text
backend_business/services/requirement_graph/orchestrator.py
```

改动逻辑：

1. 如果 project/session 是 PCA demo，图谱生成接口走确定性演示分支。
2. 初始基础图来自数据库里的需求节点和 `low_level_requirement_links`，结构边是 `REFINES`。
3. 点击生成图谱后，流式追加 16 条关系边。
4. 追加关系类型包括：

```text
DEPENDS_ON
CONFLICTS_WITH
SIMILAR_TO
VALIDATES_WITH
IMPACTS
INCLUDES
```

5. PCA 演示分支关闭本地向量候选召回，避免服务器首次点击时下载模型或等待真实推理。
