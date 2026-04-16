# Agent 经验技能化方案

> 本方案将 Agent 执行过程中积累的成功经验，以 **Skill（.md）** 的形式沉淀下来，供后续同类任务复用。
> Skill 的产出单位为 **Container**（容器）。

---

## 一、背景与目标

### 1.1 问题

当前的 Multi-Agent 系统在完成任务后，只将执行轨迹（graph / node / edge）记录到数据库中。这些轨迹记录了「怎么做」，但没有提炼出「下次遇到类似任务应该怎么做」。

随着系统运行，积累了大量执行轨迹，但 Agent 每次执行新任务时，仍然从零开始，缺乏历史经验的指导。

### 1.2 目标

```
任务完成 → 自动提炼经验 → 写入 Skill 文件 → 下次同类任务 → 自动加载相关 Skill → Agent 像有经验的人一样工作
```

### 1.3 设计原则

- **经验 = Skill**：以 Skill（`.md` 文件）的形式存储经验，而非单独的数据库表
- **Container 为单位**：每个 Container 完成一次完整任务后，提炼为一个 Skill
- **对 Agent 透明**：经验提炼在后台静默完成，不打断用户流程
- **增量积累**：不替换已有 Skill，而是持续叠加，由 LLM 自行判断哪个更好

---

## 二、核心架构

### 2.1 整体流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户消息                                   │
│                    "帮我检测R-1和R-2的冲突"                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Session Controller                            │
│                         Container                                │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │  llm: 意图判断 → 路由到 Conflict Detection Container     │  │
│    │  invoke: 调用 Conflict Detection Container               │  │
│    │  llm: 汇总结果回复用户                                    │  │
│    └─────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          ▼                                    ▼
┌─────────────────────┐          ┌─────────────────────────────────┐
│  Conflict Detection  │          │       Skill 提炼触发             │
│     Container       │          │  （Container完成后自动触发）       │
│                     │          └──────────────┬──────────────────┘
│  [执行轨迹记录中...]  │                         │
└─────────────────────┘                         ▼
                                     ┌─────────────────────────────────┐
                                     │   提炼 Prompt（后台轻量模型）     │
                                     │   输入：user_message +          │
                                     │         tool_calls 轨迹 +       │
                                     │         conclusion              │
                                     │   输出：Skill.md 格式文本        │
                                     └──────────────┬──────────────────┘
                                                    │
                                                    ▼
                                     ┌─────────────────────────────────┐
                                     │   写入 Skill 文件               │
                                     │ 冲突检测/task_type目录           │
                                     └──────────────┬──────────────────┘
                                                    │
                                                    ▼  （下次同类任务）
                                     ┌─────────────────────────────────┐
                                     │   Skill 检索与注入               │
                                     │  在构建 System Prompt 时         │
                                     │  自动加载相关 Skill              │
                                     └─────────────────────────────────┘
```

### 2.2 Skill 存储结构

```
Semantic-Atlas/
├── .agent_skills/                          # Agent 经验技能库（项目级）
│   ├── _registry.yaml                      # Skill 注册表（索引）
│   ├── conflict_detection/                  # 冲突检测 Container 经验
│   │   ├── _skill.md                       # 主 Skill（Container 级别完整经验）
│   │   ├── _skill_v2.md                    # 增量版本（自动编号）
│   │   └── _skill_v3.md
│   ├── requirement_management/              # 需求管理 Container 经验
│   │   ├── _skill.md
│   │   └── ...
│   ├── requirement_classification/          # 需求分类 Container 经验
│   │   └── _skill.md
│   └── session_controller/                 # 会话控制 Container 经验
│       └── _skill.md
│
├── backend_business/
│   └── services/agent/
│       ├── experience/                      # 新增：经验管理模块
│       │   ├── __init__.py
│       │   ├── skill_compiler.py           # 提炼：将执行轨迹 → Skill 文本
│       │   ├── skill_store.py              # 存储：写入 .md 文件
│       │   ├── skill_retriever.py          # 检索：根据 task_type 找相关 Skill
│       │   ├── skill_loader.py             # 加载：将 Skill 注入 Prompt
│       │   └── registry.py                # 注册表管理（_registry.yaml）
│       └── execution/
│           └── container_completion_hook.py # 新增：Container 完成钩子
```

---

## 三、Skill 格式定义

每个 Skill 为标准的 `.md` 文件，包含固定的头部元数据 + 自由格式的经验内容。

### 3.1 Skill 头部元数据

```markdown
---
skill_id: exp_cd_20260315_001
container_type: conflict_detection
task_pattern: |
  用户要求检测两个或多个需求之间是否存在冲突。
  常见触发词：检测冲突 / 检查冲突 / 是否冲突 / conflict
trigger_conditions:
  - 用户消息包含"冲突"相关词汇
  - 用户明确指明了两个或多个具体需求（R-1 / R-2 / 这条 / 那个）
applicable_containers:
  - conflict_detection
success_indicators:
  - 正确识别了被检测的需求编号
  - 发现了所有冲突对（或正确判断无冲突）
  - 回复结构清晰，包含冲突描述和依据
key_steps:
  - "提取被检测需求的内容（title + description）"
  - "调用 conflict_detection 工具"
  - "将工具结果格式化为结构化回复"
pitfalls:
  - "用户修改需求属性时，不能误路由到冲突检测"
  - "只检测了单个需求时，应提示用户补充其他需求"
version: 3
derived_from_graph_ids:
  - "graph_abc123"
  - "graph_def456"
created_at: "2026-03-15T10:30:00Z"
invocation_count: 12
last_used_at: "2026-04-01T14:22:00Z"
---
```

### 3.2 经验正文格式（提炼 Prompt 的输出规范）

紧随元数据之后，为结构化的经验正文：

```markdown
## 经验概要

当用户要求检测需求冲突时，正确的处理流程如下：

### 适用场景
（什么情况下判定为冲突检测任务）

### 关键步骤
1. **意图确认**：先确认用户指的是哪两个需求
2. **内容提取**：获取需求的 title 和 description
3. **执行检测**：调用 conflict_detection 工具
4. **结果呈现**：如果有冲突，说明冲突点和依据；如果无冲突，给出确认

### 常见陷阱
- （本次任务中踩过的坑，下次如何避免）

### 扩展知识
- （相关的、可以进一步了解的内容）
```

### 3.3 注册表 `_registry.yaml`

```yaml
skills:
  conflict_detection:
    latest_version: 3
    skills:
      - skill_id: exp_cd_20260315_001
        version: 3
        file: conflict_detection/_skill_v3.md
        created_at: "2026-03-15T10:30:00Z"
        invocation_count: 12
        last_used_at: "2026-04-01T14:22:00Z"
        task_pattern_hash: "sha256:..."   # 用于判断是否重复
      - skill_id: exp_cd_20260401_002
        version: 2
        file: conflict_detection/_skill_v2.md
        ...

  requirement_management:
    latest_version: 1
    skills:
      - skill_id: exp_rm_20260401_001
        version: 1
        file: requirement_management/_skill.md
        ...

  session_controller:
    latest_version: 1
    ...
```

---

## 四、Skill 提炼触发机制

### 4.1 触发时机

在 `SubgraphRunner` 完成整个 Container 的执行后（`ContainerResult` 返回时），自动触发经验提炼。

触发点位于 `graph_executor.py` 中 Container 执行完成的分支。

### 4.2 提炼 Pipeline（含 Review Agent 评审）

```
Container 完成
    ↓
判断是否需要提炼（见 4.3）
    ↓
收集提炼素材
    ├── 原始用户消息（user_message）
    ├── Container 类型（container_type）
    ├── 执行的 tool_calls 序列
    ├── complete_phase 的 conclusion
    ├── scratchpad 内容
    └── 执行时长、任务复杂度（可选）
    ↓
调用提炼 Prompt（轻量模型，如 o4-mini 或 gpt-4o-mini）
    ↓
输出 Skill.md 格式文本（Skill 草稿）
    ↓
Review Agent 评审（见 4.5）
    ↓
通过 → 调用 SkillStore 写入文件
    ↓
更新注册表（registry.yaml）
    ↓
【静默完成，不打断用户】
```

### 4.3 提炼条件（防止低质量 Skill）

并非每次 Container 执行都触发提炼，设置以下门槛：

| 条件 | 说明 |
|------|------|
| **任务完成度** | `succeeded` 状态 |
| **最小 tool_calls 数** | 至少执行了 2 次 tool_call（排除简单查询） |
| **用户确认度**（可选） | 用户对结果有明确的正向反馈（如"好的"、"谢谢"） |
|| **非重复检测** | 单独大模型判断本次 task_pattern 与已有 Skill 是否高度重复，相似则跳过提炼（见 4.6） |

### 4.5 Review Agent 评审机制

#### 4.5.1 核心职责

Review Agent 是一个独立的轻量级评审 Agent，在 Skill 草稿生成后、写入文件前，对草稿进行质量审查。其核心职责：

- **可操作性判断**：经验是否包含可执行的步骤，而非泛泛而谈
- **完整性判断**：是否涵盖了关键步骤、常见陷阱、扩展知识等必备章节
- **质量评分**：输出 `quality_score`（0-100）和具体评审意见
- **修改建议**：对不通过的作品给出修改方向，可打回重炼

#### 4.5.2 评审 Pipeline

```
Skill 草稿生成
    ↓
Review Agent 评审
    ↓
quality_score >= 阈值（默认 60）？
    ├── yes → 通过 → 写入 Skill 文件 + 更新注册表
    └── no → 重炼机会（最多 N 次，如 2 次）
              ↓
              重炼后仍不通过 → 丢弃该次经验（不写入）
```

#### 4.5.3 Review Agent Prompt 示例

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是一个经验质量评审专家。你的任务是对一条待写入的 Agent 经验 Skill 进行质量评审。\n\n评审维度：\n1. 【可操作性】是否包含明确、可执行的步骤？不能是\"要仔细分析\"这种废话\n2. 【完整性】是否包含：适用场景、关键步骤、常见陷阱、扩展知识（至少3项有实质内容）\n3. 【去隐私化】是否已去除具体数据值（需求ID、数字、用户名等）？\n4. 【实用性】经验是否真的能在下次同类任务中发挥作用？\n\n输出格式（JSON）：\n{\n  \"quality_score\": 0-100的整数,\n  \"pass\": true/false,\n  \"dimension_scores\": {\n    \"actionable\": 0-25,\n    \"complete\": 0-25,\n    \"sanitized\": 0-25,\n    \"practical\": 0-25\n  },\n  \"issues\": [\"问题1\", \"问题2\"],\n  \"suggestions\": [\"修改建议1\", \"修改建议2\"]\n}\n\n【重要】你必须输出合法的JSON，不要有任何额外文字。"
    },
    {
      "role": "user",
      "content": "请评审以下 Skill 草稿：\n\n{skill_draft_content}\n\n给出你的评审结果。"
    }
  ]
}
```

#### 4.5.4 质量评分的价值

`quality_score` 不仅用于决定是否写入，还具有以下价值：

| 用途 | 说明 |
|------|------|
| **写入门槛** | `quality_score >= 60` 才允许写入，避免低质量 Skill 污染知识库 |
| **优先级标记** | 注册表中记录 score，高分 Skill 在加载时可优先注入 |
| **进化依据** | 定期筛选低分 Skill（长期 < 40）进行合并或降级 |
| **效果追踪** | Skill 被使用后，对比使用前后的执行质量，验证经验是否有效 |

#### 4.5.5 实施位置

- 新增文件：`backend_business/services/agent/experience/review_agent.py`
- 在 `container_completion_hook.py` 中调用，位于 Skill 草稿生成之后、SkillStore 写入之前

---

### 4.6 重复检测：大模型语义判断

#### 4.6.1 为什么不用 Hash

传统的 hash 相似度只能判断"表面是否相同"，无法处理以下情况：

- 用户换了表达方式，但任务本质相同
- 多个不同的 Skill 其实在描述同一类问题
- 新的任务模式实际上是已有 Skill 的子集

因此，改用**单独的大模型进行语义判断**。

#### 4.6.2 判断 Pipeline

```
新任务完成，触发提炼条件
    ↓
提取本次 task_pattern 语义描述
    ↓
发送给专用判断模型（或 Embedding）
判断请求：
"判断这个任务是否和已有的 {existing_skill_name} Skill 高度重复？
  本次任务：{task_description}
  已有Skill概要：{existing_skill_summary}
  输出 yes/no + 理由（限50字以内）"
    ↓
yes（高度重复）→ 跳过提炼，该 Skill 的 invocation_count + 1
no（不重复）→ 触发提炼流程，生成新 Skill
```

#### 4.6.3 判断 Prompt 示例

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是一个任务相似度判断专家。给定一个新任务和已有的Skill，判断它们是否\"高度重复\"。\n\n高度重复的定义：\n- 任务类型相同（如都是\"冲突检测\"）\n- 处理流程相同\n- 使用的工具和参数模式相同\n- 只是在具体数据值上有差异（如需求ID不同）\n\n如果只是\"领域不同但模式相同\"，不算高度重复（如从\"电商需求\"换成\"教育需求\"）。\n\n输出格式：\n{\n  \"is_duplicate\": true/false,\n  \"reason\": \"判断理由，限50字以内\",\n  \"confidence\": 0.0-1.0\n}\n\n【重要】必须输出合法JSON，不要有额外文字。"
    },
    {
      "role": "user",
      "content": "新任务：{new_task_description}\n\n已有Skill概要：{existing_skill_summary}\n\n请判断是否高度重复。"
    }
  ]
}
```

#### 4.6.4 实施位置

- 修改 `skill_compiler.py`：在提炼前增加重复检测步骤
- 或独立为 `skill_dedup.py`，在 `container_completion_hook` 中优先调用

### 4.7 完整提炼流程图

```
Container 完成
    ↓
┌─────────────────────────────┐
│ 提炼条件检查                  │
│  - succeeded 状态？          │
│  - tool_calls >= 2？         │
│  - 非重复检测（4.6 大模型判断）│
└──────────────┬──────────────┘
               ↓
        yes → 继续提炼
        no  → 丢弃，结束
               ↓
收集提炼素材
    ↓
提炼 Prompt → Skill 草稿
    ↓
Review Agent 评审（4.5）
    ↓
quality_score >= 60？
    ├── yes → 写入 Skill 文件
    └── no → 重炼（最多2次）
              ↓
              重炼仍不通过 → 丢弃
               ↓
更新注册表（registry.yaml）
    ↓
【静默完成，不打断用户】
```

---

## 五、Skill 检索与注入机制

### 5.1 检索时机

在 `SessionControllerPromptBuilder.build_system_prompt()` 中，构建 system prompt 时，在 `scratchpad_text` 注入之前，自动检索并注入相关 Skill。

### 5.2 检索流程

```
用户消息到达
    ↓
判断用户意图（路由到哪个 Container）
    ↓
获取目标 Container 类型（如 conflict_detection）
    ↓
SkillRetriever.retrieve(container_type=container_type)
    ↓
读取对应目录下的 _skill.md（最新版本主文件）
    ↓
将 Skill 内容格式化为 Prompt 片段
    ↓
追加到 System Prompt 的专属区域
```

### 5.3 Prompt 注入格式

```python
# 在 SessionControllerPromptBuilder.build_system_prompt() 中

# ... 原有 base_prompt 构建逻辑 ...

# 新增：Skill 注入
skill_text = skill_loader.get_skill_for_container(
    container_type=infer_container_type(user_message),
    context=context,
)
if skill_text:
    base_prompt += (
        "\n\n[历史经验]\n"
        "以下是你过去处理同类任务时积累的经验，请参考：\n\n"
        f"{skill_text}\n"
        "—— 经验结束 ——"
    )

# scratchpad 注入（保持原有逻辑）
scratchpad_text = context.get("_scratchpad_prompt_text") or ""
if scratchpad_text:
    base_prompt += (f"\n\n{scratchpad_text}")
```

### 5.4 Skill 命中逻辑

| 优先级 | 匹配方式 | 说明 |
|--------|----------|------|
| 1 | **精确匹配** | `container_type` 完全一致 → 直接加载对应目录的 `_skill.md` |
| 2 | **模糊匹配** | `container_type` 部分匹配 → 加载相似目录的 Skill |
| 3 | **降级 fallback** | 无匹配 → 不注入，Agent 正常执行 |

---

## 六、实施步骤

### Phase 1：基础设施搭建（预计 2-3 天）

**目标**：建立 Skill 的存储结构、基础读写接口。

1. 创建 `.agent_skills/` 目录结构
2. 实现 `skill_store.py` — Skill 文件的写入（支持版本号）
3. 实现 `skill_retriever.py` — 按 `container_type` 读取对应 Skill
4. 创建 `_registry.yaml` 初始化逻辑
5. 手动撰写 1-2 个示例 Skill（如 `conflict_detection` 的种子 Skill）

**交付物**：
- `.agent_skills/conflict_detection/_skill.md`（手工撰写的种子）
- `backend_business/services/agent/experience/skill_store.py`
- `backend_business/services/agent/experience/skill_retriever.py`

---

### Phase 2：提炼触发机制 + Review Agent + 重复检测（预计 3-4 天）

**目标**：在 Container 完成后自动触发提炼 + 评审 + 去重，将经验写入 Skill 文件。

1. 实现 `skill_compiler.py` — 接收执行轨迹，调用 LLM 提炼为 Skill 格式
2. 实现 `review_agent.py` — Review Agent 评审逻辑（含 quality_score）
3. 实现 `skill_dedup.py` — 大模型语义重复检测（独立于 hash）
4. 实现 `container_completion_hook.py` — 在 `graph_executor.py` 的 Container 完成处植入钩子
5. 实现 `registry.py` — 注册表更新逻辑（新增 Skill 后自动注册，含 quality_score）
6. 设置提炼条件（最小 tool_calls 数、重复检测、质量门槛 60 分）
7. 端到端测试：执行一个冲突检测任务 → 验证 Skill 草稿 → Review 通过 → 写入文件

**交付物**：
- `backend_business/services/agent/experience/skill_compiler.py`
- `backend_business/services/agent/experience/review_agent.py`
- `backend_business/services/agent/experience/skill_dedup.py`
- `backend_business/services/agent/experience/registry.py`
- `backend_business/services/agent/execution/container_completion_hook.py`
- 完整流程验证（提炼 → 评审 → 写入）

---

### Phase 3：检索与注入（预计 1-2 天）

**目标**：在每次任务开始时，自动加载相关 Skill 到 Prompt 中。

1. 实现 `skill_loader.py` — 将 Skill 内容格式化为 Prompt 片段
2. 修改 `SessionControllerPromptBuilder.build_system_prompt()` — 注入 Skill 片段
3. 实现意图推断逻辑（判断用户消息应该路由到哪个 Container）
4. 端到端测试：连续两次执行同类任务 → 验证第二次执行时 Skill 被加载到上下文中

**交付物**：
- `backend_business/services/agent/experience/skill_loader.py`
- 修改后的 `session_controller/prompt_builder.py`
- 完整的 Skill 注入效果验证

---

### Phase 4：优化与迭代（持续）

1. **版本管理优化**：当同一 `container_type` 下有多个版本 Skill 时，LLM 自动选择更好的版本
2. **Skill 质量反馈**：记录 Skill 的 `invocation_count` 和 `last_used_at`，长期未使用的 Skill 降级或合并
3. **扩展容器支持**：逐步为其他 Container（requirement_management、requirement_classification 等）添加 Skill 支持
4. **跨容器模式提取**（可选）：识别跨 Container 复用的 Subgraph 模式，提取为共享原子 Skill
5. **可观测性**：Skill 被加载时记录日志，便于追踪哪些经验被使用了

---

## 七、关键文件清单

|| 文件路径 | 职责 | 状态 |
|----------|------|------|
|| `.agent_skills/_registry.yaml` | Skill 索引注册表（含 quality_score） | 新增 |
|| `.agent_skills/<container_type>/_skill.md` | 各容器经验 Skill 文件 | 新增 |
|| `backend_business/services/agent/experience/__init__.py` | 模块入口 | 新增 |
|| `backend_business/services/agent/experience/skill_store.py` | Skill 写入存储 | 新增 |
|| `backend_business/services/agent/experience/skill_retriever.py` | Skill 按类型检索 | 新增 |
|| `backend_business/services/agent/experience/skill_loader.py` | Skill 注入 Prompt | 新增 |
|| `backend_business/services/agent/experience/skill_compiler.py` | 执行轨迹 → Skill 提炼 | 新增 |
|| `backend_business/services/agent/experience/review_agent.py` | Skill 草稿质量评审 + quality_score | 新增 |
|| `backend_business/services/agent/experience/skill_dedup.py` | 大模型语义重复检测 | 新增 |
|| `backend_business/services/agent/experience/registry.py` | 注册表管理（含 quality_score） | 新增 |
|| `backend_business/services/agent/execution/container_completion_hook.py` | Container 完成钩子（串联提炼→评审→写入） | 新增 |
|| `backend_business/services/agent/agents/session_controller/prompt_builder.py` | Prompt 构建（含 Skill 注入） | 修改 |

---

## 八、潜在风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| Skill 提炼质量差（LLM 幻觉） | 中 | 中 | Phase 1 先手工写种子 Skill；提炼 Prompt 强调"不要写具体数值，要写模式" |
| 同一 task_type 下多版本 Skill 堆积 | 低 | 低 | 版本号自动管理；`invocation_count` 长期低的版本可考虑合并 |
| 提炼触发过于频繁，拖慢响应速度 | 低 | 中 | 提炼为异步后台任务，不阻塞主流程 |
| Skill 内容泄露隐私信息 | 低 | 高 | 提炼 Prompt 中明确禁止记录用户私人信息；写入前增加过滤层 |
| 新增代码影响现有 Agent 稳定性 | 中 | 高 | Phase 1-3 均设计为可开关（通过配置项 `ENABLE_EXPERIENCE_SKILL`） |

---

## 九、配置项

```yaml
# backend_business/.env 或 docker-compose.yml 环境变量

# 经验技能总开关
ENABLE_EXPERIENCE_SKILL: "true"          # false = 禁用整个子系统

# 提炼相关
SKILL_COMPILER_MODEL: "gpt-4o-mini"      # 提炼用模型
SKILL_MIN_TOOL_CALLS: 2                  # 至少执行 N 次 tool_call 才触发提炼
SKILL_DEDUP_SIMILARITY_THRESHOLD: 0.8   # task_pattern 相似度超过此值不新建

# 存储相关
AGENT_SKILLS_ROOT: ".agent_skills"       # Skill 库根目录（相对项目根）
```

---

## 十、附录：相关文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| Multi-Agent 协同架构总结 | `docs/总结文档/MULTI_AGENT_SUMMARY.md` | 现有 Agent 架构全景 |
| 需求管理数据库设计 | `docs/总结文档/REQUIREMENTS_DB_DESIGN.md` | 数据库表结构参考 |
| Agent 方案 | `docs/开发文档/Agent方案_updated.md` | 详细的设计文档 |
| 新奇的思想 | `docs/新奇的思想/newidea.md` | 架构灵感参考 |
