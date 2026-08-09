# 前端改动说明

前端改动主要是让 PCA 项目在页面上以“真实点击后产生结果”的方式演示，而不是一进页面就暴露所有结果。

## 需求分析页面

文件：

```text
frontend/src/composables/useRequirementsAnalysis.js
```

改动逻辑：

1. 识别固定 session：

```text
demo-pca-infusion-pump-session
```

2. 用户点击分析按钮后，不走普通异步推理链路，而是在前端构造 PCA 演示结果：

```text
追溯分析 trace_result
冲突检测 conflict_result
需求分类 classification_result
```

3. 保存分析结果时，`meta.source` 写成：

```text
pca_demo_click_analysis
```

后端看到这个标记后，会把结果同步落到追溯、冲突、分类相关表里，方便需求图谱和分析历史继续读取。

## 音频转文字页面

文件：

```text
frontend/src/views/beta/MultimodalIngestionView.vue
frontend/src/api/asr.js
```

改动逻辑：

1. 点击开始转写时，前端调用创建转写会话接口，并带上：

```text
demo=pca
```

2. 后端收到 `demo=pca` 后直接把会议纪要文本写成转写结果。

3. 为了防止“退出再进还有旧痕迹”，列表加载时会过滤历史 PCA demo 转写会话：

```text
remote_request_id = pca-demo-transcript
transcript_metadata.source = pca_demo_audio_transcription
```

只有本次点击创建出来的 session 会临时显示。

4. 页面右侧转写详情区域也做了演示友好调整，让文字区域更大，评委在投屏时更容易看清。

## 需求列表和卡片视图

文件：

```text
frontend/src/views/beta/RequirementsView.vue
```

改动逻辑：

1. 项目列表加载后，如果还没有选中项目，优先选中：

```text
Demo · PCA患者自控镇痛输液泵
```

2. 卡片拖拽时增加拖拽开始/结束状态，避免拖动过程中列表重新同步导致闪回。

3. 拖拽后先本地更新状态，再请求后端更新数据库；失败时再回滚本地状态。

4. 状态映射保持简单：

```text
第一栏/待处理 -> draft
第二栏/进行中 -> in_progress
第三栏/完成 -> completed
```

数据库 seed 后 PCA 需求默认全部是 `draft`，所以演示时初始都在待处理。
