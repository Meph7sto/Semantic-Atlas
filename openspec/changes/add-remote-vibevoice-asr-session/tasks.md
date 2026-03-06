## 1. Data Model and API Contract

- [x] 1.1 在 `backend_business` 定义 transcription session 持久化模型（session 主表 + 可选 segments 结构）与状态枚举（queued/running/succeeded/failed/timeout）。
- [x] 1.2 新增转写 API 契约：创建任务、查询列表、查询详情、重试任务、导出 TXT/JSON。
- [x] 1.3 为上传参数与文件类型校验补充统一请求校验与错误码映射。

## 2. Business Backend Orchestration

- [x] 2.1 实现媒体上传后创建转写 session 的业务流程，确保快速返回 `session_id`。
- [x] 2.2 实现本地业务端到远端推理端的调用封装（FRP 地址、鉴权 header、超时参数、重试策略）。
- [x] 2.3 实现异步状态推进逻辑：queued -> running -> succeeded/failed/timeout。
- [x] 2.4 实现失败重试机制并保证幂等，不覆盖历史执行信息。

## 3. Remote Inference Service (VibeVoice)

- [x] 3.1 在 `backend_inference` 新增/扩展 VibeVoice ASR 推理接口，支持音频与 MP4 音轨转写。
- [x] 3.2 统一推理输出结构（text、segments、metadata、error）并返回稳定字段。
- [x] 3.3 增加远端 ASR 健康检查与模型预热逻辑，降低冷启动影响。

## 4. Result Persistence and Export

- [x] 4.1 在业务端实现转写结果落库（全文、片段、元数据、错误信息）。
- [x] 4.2 实现会话列表/详情查询接口的分页、排序与权限控制。
- [x] 4.3 实现导出下载接口，仅允许 `succeeded` 会话导出 TXT/JSON 文件。

## 5. Frontend Experience

- [x] 5.1 在 `frontend` 新增语音转写入口页面（文件上传 + 任务提交）。
- [x] 5.2 实现会话列表与详情页，展示状态、转写文本、错误信息与刷新机制。
- [x] 5.3 接入结果导出按钮与下载流程，处理未完成会话的前端错误提示。

## 6. Configuration, Security, and Observability

- [x] 6.1 新增/更新 `.env.example` 与部署文档，明确远端 ASR 地址、token、超时和重试配置项。
- [x] 6.2 增加关键链路日志与追踪字段（session_id、remote_request_id、latency、failure_reason）。
- [x] 6.3 对转写相关接口补充鉴权与文件大小限制，确保敏感内容处理安全。

## 7. Testing and Acceptance

- [x] 7.1 在 `tests` 新增业务 API 合约测试：创建、状态流转、详情查询、导出、错误场景。
- [x] 7.2 新增推理服务测试：模型接口响应格式、异常处理、超时行为。
- [ ] 7.3 完成端到端联调（本地 `deploy/start.ps1` + 远端 AutoDL），验证上传 MP4/音频到结果回传与本地导出。
