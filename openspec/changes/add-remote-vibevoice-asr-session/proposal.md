## Why

当前项目缺少对语音/视频内容的自动转写能力，用户上传音频或 MP4 后无法直接得到文本结果，也无法形成可复用的会话记录。由于 ASR 模型推理部署在远端 AutoDL，系统需要建立稳定的“本地业务端-远端推理端”异步协作链路，才能在现有启动方式（本地 `deploy/start.ps1` + 已配置 FRP）下提供端到端可用能力。

## What Changes

- 新增媒体转写流程：支持上传音频/视频文件（如 WAV、MP3、M4A、MP4）并触发远端 `microsoft/VibeVoice-ASR-HF` 转写任务。
- 新增远端推理编排：本地业务后端将文件与任务请求通过已配置 FRP 通道转发至远端推理服务，拉取或接收转写结果并落库。
- 新增转写会话模型：每次转写形成可追踪 session，保存输入文件元数据、任务状态、全文文本、时间戳片段（若可用）、错误信息。
- 新增结果管理能力：前端可查看会话列表与详情；支持将转写结果导出/保存到本地（如 TXT/JSON）。
- 新增失败恢复与可观测性：定义任务状态机（queued/running/succeeded/failed/timeout），补充日志、超时和重试策略。

## Capabilities

### New Capabilities
- `remote-asr-session-management`: 管理本地上传、远端 VibeVoice ASR 推理、结果回传、转写会话持久化与本地导出。

### Modified Capabilities
- None.

## Impact

- Affected code:
  - `backend_business/`: 新增转写业务 API、任务编排、session 持久化、导出接口。
  - `backend_inference/`: 新增或扩展 ASR 推理 API（VibeVoice 模型加载、推理、结果结构化输出）。
  - `frontend/`: 新增上传/会话列表/结果查看/导出 UI 与 API 调用。
  - `deploy/`: 补充本地-远端服务地址、鉴权与超时配置说明（与已有 FRP 配置协同）。
- Data/API:
  - 新增转写 session 数据表（或等价存储结构）。
  - 新增转写相关 REST API。
- Dependencies:
  - 远端推理环境需安装并可运行 `microsoft/VibeVoice-ASR-HF` 所需依赖。
  - 文件上传与任务调用链路需满足现有网络与带宽约束。
