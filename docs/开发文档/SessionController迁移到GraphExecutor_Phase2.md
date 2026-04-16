# Phase 2: SessionController 迁移到 GraphExecutor 实施方案

## 1. 文档定位

这份文档只描述 `SessionController -> GraphExecutor` 的后续迁移阶段。

它不覆盖 Phase 1 的 classic 收敛工作，也不表示 graph 已成为当前正式默认架构。

## 2. 当前状态

- `classic` 仍是生产默认链路
- `graph` 只能作为实验链路存在
- 实验链路必须由显式开关控制：`SESSION_CONTROLLER_GRAPH_ENABLED`
- 未开启时，公开 API 不接受 `execution_mode="graph"`

## 3. Phase 2 的目标

- 让 GraphExecutor 接管 SessionController 主流程
- 将 `clarify / suspend / final_reply` 变成图中的显式阶段
- 将子 Agent 委托从兼容工具调用升级为 runtime 原生调度
- 保留 classic 作为可回滚链路，直到 graph 满足切默认条件

## 4. 切默认前提

- 前后端明确切换到 `graph` 入口
- 核心依赖完成联调并验证：推理服务、工具调用提供方、Postgres、挂起恢复链路
- 回滚开关明确可用
- 验收口径从“实验可运行”升级为“默认主路径稳定”

## 5. 迁移约束

- Phase 1 未完成前，不应把 graph 当成当前正式架构
- 双轨并存期间，必须明确区分：生产默认、实验入口、回滚方式
