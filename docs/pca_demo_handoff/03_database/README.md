# 数据库写入说明

PCA demo 的数据库入口是：

```text
backend_business/scripts/seed_pca_demo.py
```

## 固定标识

```text
project_id: demo-pca-infusion-pump-project
project_name: Demo · PCA患者自控镇痛输液泵
session_id: demo-pca-infusion-pump-session
initial_graph_snapshot_id: demo-pca-initial-structure-graph
```

## 启动 seed 后形成的数据

正常 seed 后应该得到：

```text
顶层需求: 12 条，分布在 L1/L2/L3
底层需求: 55 条，作为 L4
追溯关系: 66 条
项目管理需求: 67 条，全部 status=draft
初始需求图谱: 66 条 REFINES 结构边
```

## seed 前会清理的表

为了让每次演示都回到初始状态，脚本会先清理当前 PCA session/project 的旧数据：

```text
requirements_analysis_runs
trace_analysis
conflict_analysis
classification_analysis
requirement_graph_relations
manage_requirements
low_level_requirement_links
low_level_requirements
requirements_l123
```

注意：清理范围限定在：

```text
session_id = demo-pca-infusion-pump-session
project_id = demo-pca-infusion-pump-project
```

不会清空其他项目。

## seed 会写入的表

### manage_projects

写入/更新 PCA 演示项目：

```text
name = Demo · PCA患者自控镇痛输液泵
status = active
current_session_id = demo-pca-infusion-pump-session
```

### manage_branch_refs

给演示项目补一个主分支：

```text
ref_name = main
ref_type = branch
```

### requirements_l123

写入 12 条顶层需求。

这次专门把顶层需求拆成 L1/L2/L3，不再只有 L3：

```text
L1: H-01, H-02, H-04, H-07
L2: H-05, H-06, H-08, H-09
L3: H-03, H-10, H-11, H-12
```

实际 req_id 会转换成：

```text
PCA-H-01 ... PCA-H-12
```

### low_level_requirements

写入 55 条底层需求：

```text
PCA-L-01 ... PCA-L-55
```

其中 open questions 会写入 `open_questions` 和 `meta`，用于演示待确认项。

### low_level_requirement_links

写入顶层到底层的追溯映射。

这里有一对多和多对一关系，所以总关系数是 66，不是 55。

### manage_requirements

把 12 条顶层需求和 55 条底层需求同步到项目管理需求表。

关键字段：

```text
requirement_type = top_level / low_level
status = draft
source_level = L1/L2/L3/L4
parent_id = 底层需求的主顶层需求
source_req_id = 原始 req_id
custom_fields = 原始来源、分类、待确认项等演示信息
```

所以需求列表页面初始看到的是 67 条需求，并且全部处于待处理。

### requirement_graph_relations

seed 阶段只写初始结构图：

```text
snapshot_id = demo-pca-initial-structure-graph
relation_mode = llm
relation_type = REFINES
source_kind = structural
source_detail = pca_demo.initial_trace_structure
edge_count = 66
is_active = true
```

点击“生成图谱”后，后端会保存新的 snapshot，并把边数扩展到 82。

### user_project_scopes

把非 super_admin 用户授权到 PCA 演示项目：

```text
can_edit = true
```

### manage_audit_logs

写入一条 seed 记录，方便排查当前 demo 数据是否被初始化过：

```text
target_type = pca_demo
action = seed
```

## 点击按钮后会新增的数据

### 点击需求分析

写入：

```text
trace_analysis
conflict_analysis
classification_analysis
requirements_analysis_runs
```

触发条件：

```text
meta.source = pca_demo_click_analysis
```

### 点击音频转文字

写入/更新转写相关表，关键标记：

```text
remote_request_id = pca-demo-transcript
transcript_metadata.source = pca_demo_audio_transcription
```

前端会根据这个标记隐藏历史 demo 记录。

### 点击生成图谱

新增一批 `requirement_graph_relations`，包含初始 66 条结构边和 16 条推理关系边。

最终效果：

```text
node_count = 67
edge_count = 82
```
