# 服务器部署说明

这份说明假设服务器已经能正常启动 Semantic-Atlas，只补充 PCA demo 需要的文件和环境变量。

## 需要准备的演示源文件

服务器上需要放两个文件：

```text
demo_PCA输液泵原始需求清单.md
demo_PCA输液泵需求调研会议记录.txt
```

md 用于 seed 需求条目、追溯关系和初始图谱。

txt 用于 seed 会议来源信息，也用于音频转文字 demo 的最终转写文本。

## 推荐环境变量

Windows PowerShell 示例：

```powershell
$env:PCA_DEMO_MD_PATH = "D:\semantic-demo-data\demo_PCA输液泵原始需求清单.md"
$env:PCA_DEMO_TXT_PATH = "D:\semantic-demo-data\demo_PCA输液泵需求调研会议记录.txt"
$env:PCA_DEMO_TRANSCRIPT_PATH = "D:\semantic-demo-data\demo_PCA输液泵需求调研会议记录.txt"
```

Linux shell 示例：

```bash
export PCA_DEMO_MD_PATH="/opt/semantic-demo-data/demo_PCA输液泵原始需求清单.md"
export PCA_DEMO_TXT_PATH="/opt/semantic-demo-data/demo_PCA输液泵需求调研会议记录.txt"
export PCA_DEMO_TRANSCRIPT_PATH="/opt/semantic-demo-data/demo_PCA输液泵需求调研会议记录.txt"
```

## 一键脚本方式

Windows/PowerShell：

```powershell
cd D:\requirement-trace\Better\Semantic-Atlas
.\deploy\start.ps1
```

`start.ps1` 会在启动业务服务前执行：

```powershell
python backend_business/scripts/seed_pca_demo.py --skip-if-missing
```

如果不希望启动时重置 demo 数据：

```powershell
$env:SKIP_PCA_DEMO_SEED = "1"
.\deploy\start.ps1
```

## 手动 seed 方式

如果服务器不是通过 `deploy/start.ps1` 启动，可以在业务服务启动前手动跑：

```powershell
python backend_business/scripts/seed_pca_demo.py `
  --md "D:\semantic-demo-data\demo_PCA输液泵原始需求清单.md" `
  --txt "D:\semantic-demo-data\demo_PCA输液泵需求调研会议记录.txt"
```

Linux：

```bash
python backend_business/scripts/seed_pca_demo.py \
  --md "/opt/semantic-demo-data/demo_PCA输液泵原始需求清单.md" \
  --txt "/opt/semantic-demo-data/demo_PCA输液泵需求调研会议记录.txt"
```

## 数据库连接

seed 脚本使用项目现有配置：

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
DATABASE_URL
```

如果设置了 `DATABASE_URL`，优先使用它。

## 部署后的预期效果

启动后进入系统：

```text
项目管理能看到 Demo · PCA患者自控镇痛输液泵
需求列表初始 67 条需求，全部待处理
需求分析页面点击分析后才出现结果
音频转文字页面点击开始转写后才出现会议纪要文本
需求图谱初始 67 节点、66 条 REFINES；点击生成后变为 82 条边
```
