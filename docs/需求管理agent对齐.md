 - 运行时执行图不是“由拓扑图实例化”出来的。方案里运行图应以执行拓扑图为蓝本推进；现在 RequirementAgent 直接
    create_runtime_graph()，拓扑结构接口只是独立的“查看/校验/导出”能力，没有参与实际执行。graph_recorder.py:132
    graph_structure_builder.py:66 execution_graph.py:408
  - subgraph 这一层完全没落地。方案里“拓扑图中的一个节点 = 执行图中的一个 subgraph”；当前 schema 只有 graph/container/
    node/edge 四层，container 直接挂 node，没有 subgraph 实体和持久化模型。execution_schema.py:144
    execution_schema.py:242 graph_structure_builder.py:112
  - 边模型不一致。方案要求容器内部用 seq，容器间才用 call/return/retry；现在 schema 只允许 call/return/retry，
    RequirementAgent 自己的顺序步骤也被写成 call/return，而且同容器边在结构编译时会被直接丢弃，导致“容器内执行序列”无法
    被正确表达。execution_graph_service.py:26 execution_graph_schemas.py:11 tool_loop_runner.py:125 service.py:421
    edge_processor.py:144
  - 边的数据语义也和方案相反。方案里边“不携带业务数据，只表达流转事实”；但当前拓扑校验强制 call 边要有 param_mapping、
    return 边要有 result_mapping、retry 边要有 retry_config。edge_processor.py:40 edge_processor.py:237
  - handoff / invoke / Waiting 没真正进入需求管理 agent 的运行主链。当前主链实际只产出 start -> llm(rounds) -> end；需要
    澄清时只是把 graph 状态改成 suspended，没有显式 handoff 节点；工具调用也是在 llm 节点里同步执行，不是独立 invoke 节
    点，更没有 Waiting 状态。service.py:416 tool_loop_runner.py:64 tool_loop_runner.py:180 service.py:529
    execution_schema.py:19
  - RequirementActor 没被建模成执行图里的独立 system container。方案要求需求管理 agent 通过 call/return 与
    RequirementActor 交互；现在工具层直接 actor_query_fn/actor_write_fn 调 ActorManager，执行图里只把结果记在当前 llm 节
    点的 tool_call_results，没有 Actor 容器、没有 Actor 节点、没有 Actor 边。runtime_graph_recorder.py:21
    requirement_agent_tools.py:368 requirement_agent_tools.py:403 actor_runtime.py:71
  - 需求管理 agent 的执行参与者太少，和方案里的协作骨架不一致。当前工具集只有 list/search/get/update 四类，运行图容器也
    只有 human_input / conductor / requirements_agent / requirements_tools，没有质检 agent、冲突检测 agent、影响分析
    agent，也没有“质检失败 -> retry 回需求管理 agent”的图结构。requirement_agent_tools.py:139
    requirement_agent_tools.py:189 runtime_graph_recorder.py:21 requirement_actor.py:332
  - 状态和节点枚举也有漂移。方案里的执行状态是 Running/Waiting/Suspended/Succeeded/Failed，节点类型是 start/llm/handoff/
    invoke/end；代码 schema 里多了 draft/active 和 node/decision，却没有 waiting。execution_graph_service.py:25
    execution_graph_service.py:28 execution_schema.py:15 execution_schema.py:151