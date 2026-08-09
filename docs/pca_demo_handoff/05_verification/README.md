# 验证和排查

## 编译检查

后端 Python 文件：

```powershell
python -m py_compile backend_business/services/requirement_graph/orchestrator.py backend_business/scripts/seed_pca_demo.py
```

前端：

```powershell
cd frontend
npm run build
npm run lint
```

当前 lint 会有既有 warning，但应没有 error。

## 数据库检查 SQL

确认需求状态：

```sql
SELECT status, COUNT(*)
FROM manage_requirements
WHERE project_id = 'demo-pca-infusion-pump-project'
  AND deleted = FALSE
GROUP BY status
ORDER BY status;
```

预期：

```text
draft  67
```

确认初始图谱：

```sql
SELECT snapshot_id, relation_type, source_kind, COUNT(*)
FROM requirement_graph_relations
WHERE project_id = 'demo-pca-infusion-pump-project'
  AND session_id = 'demo-pca-infusion-pump-session'
  AND is_active = TRUE
GROUP BY snapshot_id, relation_type, source_kind
ORDER BY snapshot_id, relation_type, source_kind;
```

刚启动后预期：

```text
demo-pca-initial-structure-graph  REFINES  structural  66
```

点击生成图谱后预期会出现新的 snapshot，边数为：

```text
82
```

## 接口级验证

需求图谱初始加载接口：

```text
GET /api/v2/requirement-graph/latest?project_id=demo-pca-infusion-pump-project&session_id=demo-pca-infusion-pump-session
```

预期：

```text
nodes = 67
edges = 66
edge_counts.REFINES = 66
```

生成图谱接口：

```text
POST /api/v2/requirement-graph/stream
```

payload：

```json
{
  "project_id": "demo-pca-infusion-pump-project",
  "session_id": "demo-pca-infusion-pump-session"
}
```

预期事件：

```text
base_graph: 67 nodes, 66 edges
relation_decision: 16 次
snapshot_saved: edge_count=82
done: edge_count=82
```

## 常见问题

### 启动后看不到 PCA 项目

检查 md 文件路径是否存在。`start.ps1` 默认用 `--skip-if-missing`，如果文件不存在会跳过 seed。

解决：

```powershell
$env:PCA_DEMO_MD_PATH = "D:\semantic-demo-data\demo_PCA输液泵原始需求清单.md"
$env:PCA_DEMO_TXT_PATH = "D:\semantic-demo-data\demo_PCA输液泵需求调研会议记录.txt"
.\deploy\start.ps1
```

### 音频转文字没有出现会议纪要

检查：

```text
PCA_DEMO_TRANSCRIPT_PATH
```

这个文件必须存在且非空。

### 图谱点击生成很慢

PCA demo 分支已经关闭本地向量候选召回，不应该下载模型。如果仍然很慢，确认当前项目/session 是否是：

```text
demo-pca-infusion-pump-project
demo-pca-infusion-pump-session
```

如果不是，就会走普通图谱生成逻辑。

### 演示前想恢复初始状态

重新执行 seed 即可：

```powershell
python backend_business/scripts/seed_pca_demo.py --md "D:\semantic-demo-data\demo_PCA输液泵原始需求清单.md" --txt "D:\semantic-demo-data\demo_PCA输液泵需求调研会议记录.txt"
```
