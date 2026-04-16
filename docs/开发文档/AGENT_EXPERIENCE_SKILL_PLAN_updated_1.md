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
- **渐进迭代**：每次提炼对现有主 Skill 进行增量改进，旧版本自动归档备份。Skill 库中每个 container_type 维护一份当前最优主 Skill，而不是无限堆叠版本让 LLM 自行比较——后者在检索端无法可靠落实。
- **经验注入就近原则**：Skill 描述的是某个 Container 的操作经验，应注入给实际执行该任务的 Container 的 system prompt，而非会话总控。

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
│  System Prompt 中   │                         │
│  已注入相关 Skill    │                         ▼
└─────────────────────┘          ┌─────────────────────────────────┐
         ↑                       │   提炼 Prompt（后台轻量模型）     │
         │                       │   输入：user_message +           │
         │ Skill 注入             │         tool_calls 轨迹 +        │
         │ （Container 激活时）   │         conclusion               │
┌────────┴────────────────────────────────────────────────────────┐
│                    Skill 检索（语义匹配）                         │
│   SkillRetriever.retrieve(container_type, task_description)     │
└─────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                             ┌─────────────────────────────────┐
                             │   Review Agent 结构化评审        │
                             │   通过 → 迭代更新主 Skill        │
                             │   不通过 → 定向重炼（最多2次）   │
                             └──────────────┬──────────────────┘
                                            │
                                            ▼
                             ┌─────────────────────────────────┐
                             │   隐私过滤层                     │
                             │   写入 Skill 文件（主 + 归档）   │
                             └─────────────────────────────────┘
```

### 2.2 Skill 存储结构

```
Semantic-Atlas/
├── .agent_skills/                          # Agent 经验技能库（项目级）
│   ├── _registry.yaml                      # Skill 注册表（索引）
│   ├── conflict_detection/
│   │   ├── _skill.md                       # 当前最优主 Skill（唯一检索入口）
│   │   └── _archive/                       # 历史版本归档（仅用于回溯，不参与检索）
│   │       ├── _skill_20260315.md
│   │       └── _skill_20260401.md
│   ├── requirement_management/
│   │   ├── _skill.md
│   │   └── _archive/
│   ├── requirement_classification/
│   │   ├── _skill.md
│   │   └── _archive/
│   └── session_controller/
│       ├── _skill.md
│       └── _archive/
│
├── backend_business/
│   └── services/agent/
│       ├── experience/
│       │   ├── __init__.py
│       │   ├── skill_compiler.py           # 提炼：将执行轨迹 → Skill 文本（含迭代更新逻辑）
│       │   ├── skill_store.py              # 存储：写入主 Skill，归档旧版本
│       │   ├── skill_retriever.py          # 检索：语义匹配，返回最相关 Skill
│       │   ├── skill_loader.py             # 加载：将 Skill 注入目标 Container 的 Prompt
│       │   ├── skill_sanitizer.py          # 隐私过滤：写入前去除敏感内容（新增）
│       │   ├── skill_dedup.py              # 去重：大模型语义判断是否重复
│       │   ├── review_agent.py             # 评审：结构化缺失项检查
│       │   └── registry.py                # 注册表管理（_registry.yaml）
│       └── execution/
│           └── container_completion_hook.py
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
iteration: 3                               # 本主 Skill 经过多少次迭代更新
derived_from_graph_ids:                    # 最近一次迭代所依据的执行图
  - "graph_abc123"
created_at: "2026-03-15T10:30:00Z"
last_updated_at: "2026-04-01T14:22:00Z"
invocation_count: 12
last_used_at: "2026-04-01T14:22:00Z"
injection_miss_count: 0            # 注入后任务仍失败的累计次数（用于触发重炼）
---
```

### 3.2 经验正文格式

正文分为两层：**策略层（Gene）** 描述通用操作模式，**经验层（Capsule）** 记录具体成功案例快照。两者独立更新，注入时可按需选择。

```markdown
## 策略层（Gene）

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
  - 注：失败执行也会触发轻量提炼，专门更新本节，见 §4.3

### 扩展知识
- （相关的、可以进一步了解的内容）

---

## 经验层（Capsule）

> 记录过去成功执行的典型场景快照，不含具体数据值（需求 ID、数值等已脱敏）。

### 成功案例摘要
- **触发条件**：（用户表达了什么意图、提供了什么上下文）
- **关键操作**：（执行了哪些关键 tool_call，顺序如何）
- **结果特征**：（成功的标志是什么，用户反馈如何）
- **环境特征**：（任务复杂度、需求数量级等，便于判断复用适用性）
```

### 3.3 注册表 `_registry.yaml`

注册表每个 container_type 只维护一条当前主 Skill 的记录；历史版本由 `_archive/` 目录保存，不在注册表中索引。

```yaml
skills:
  conflict_detection:
    current_skill: conflict_detection/_skill.md
    iteration: 3
    task_pattern_summary: "检测两个或多个需求之间的语义冲突，输出结构化冲突报告"
    last_updated_at: "2026-04-01T14:22:00Z"
    invocation_count: 12
    last_used_at: "2026-04-01T14:22:00Z"

  requirement_management:
    current_skill: requirement_management/_skill.md
    iteration: 1
    task_pattern_summary: "将用户的需求修改意图转化为结构化变更命令并写入 Actor"
    last_updated_at: "2026-04-01T09:10:00Z"
    invocation_count: 5
    last_used_at: "2026-04-01T09:10:00Z"

  session_controller:
    current_skill: session_controller/_skill.md
    iteration: 2
    task_pattern_summary: "识别用户意图并路由到对应专项 Agent"
    ...
```

---

## 四、Skill 提炼触发机制

### 4.1 触发时机

在 `SubgraphRunner` 完成整个 Container 的执行后（`ContainerResult` 返回时），自动触发经验提炼。

触发点位于 `graph_executor.py` 中 Container 执行完成的分支。

### 4.2 提炼 Pipeline

```
Container 完成
    ↓
判断是否需要提炼（见 4.3）
    ├── failed + tool_calls >= 2
    │       ↓
    │   失败态轻量提炼（仅 Pitfall）
    │       ↓
    │   隐私过滤层（4.4）→ 去重检查 → append 到常见陷阱节 → 结束
    │
    └── succeeded
            ↓
        收集提炼素材
    ├── 原始用户消息（user_message）
    ├── Container 类型（container_type）
    ├── 执行的 tool_calls 序列
    ├── complete_phase 的 conclusion
    ├── scratchpad 内容
    └── 执行时长、任务复杂度（可选）
    ↓
读取当前主 Skill（若已存在，作为迭代基础传入提炼 Prompt）
    ↓
调用提炼 Prompt（轻量模型，如 o4-mini 或 gpt-4o-mini）
输入：执行素材 + 当前主 Skill（可选）
输出：更新后的 Skill 草稿
    ↓
隐私过滤层（见 4.4）
    ↓
Review Agent 结构化评审（见 4.5）
    ↓
通过 → 归档旧主 Skill → 写入新主 Skill → 更新注册表
    ↓
【静默完成，不打断用户】
```

### 4.3 提炼条件

| 条件 | 说明 |
|------|------|
| **任务完成度** | `succeeded` 状态（完整提炼）；`failed` 状态（轻量提炼，仅更新常见陷阱，见下） |
| **最小 tool_calls 数** | 至少执行了 2 次 tool_call（排除简单查询） |
| **用户确认度**（可选） | 用户对结果有明确的正向反馈 |
| **非重复检测** | 大模型语义判断本次 task_pattern 与现有主 Skill 是否高度重复（见 4.6） |

**失败态轻量提炼**：当任务 `failed` 且满足最小 tool_calls 条件时，跳过完整提炼流程，仅执行一次针对 `常见陷阱（Pitfall）` 的专项提炼：

```
失败提炼 Prompt（轻量）：
"这次任务执行失败了。根据以下执行轨迹，总结出一条操作模式层面的陷阱（不含具体数据值），
 用于下次执行同类任务时提前规避。禁止写"仔细分析"等泛化表述，必须是具体可操作的规避措施。"
```

提炼结果直接 append 到主 Skill 的 `常见陷阱` 节，经过隐私过滤层（4.4）后写入，不触发 Review Agent 完整评审（只做去重检查）。

### 4.4 隐私过滤层（新增）

写入 Skill 前，`skill_sanitizer.py` 对草稿执行显式过滤，不依赖提炼模型的自觉性。

过滤规则：

| 过滤目标 | 处理方式 |
|---------|---------|
| 具体需求 ID（R-1、req_xxx 等） | 替换为占位符（如 `<requirement_id>`） |
| 具体数值（版本号、数量、百分比等上下文相关数值） | 替换为 `<numeric_value>` |
| 用户名、组织名等识别性信息 | 替换为 `<actor_name>` |
| 完整需求原文片段（超过 20 字的引用） | 删除，保留模式描述 |

过滤实现为正则 + LLM 二次检查的两阶段：正则处理结构化标识符，LLM 检查是否残留语义层面的隐私内容。过滤失败时该次 Skill 不写入，记录日志。

### 4.5 Review Agent 结构化评审（修订）

#### 4.5.1 评审模式

Review Agent 不输出连续分值，改为输出**结构化缺失项清单**。通过/不通过取决于必选项是否全部满足，而非阈值比较——后者对同一份草稿的不同调用结果可能漂移 ±10 分，难以作为可靠的写入门控。

#### 4.5.2 评审维度

| 维度 | 性质 | 通过条件 |
|------|------|---------|
| **可操作性** | 必选 | 包含至少 3 个具体可执行步骤，不含"仔细分析"等泛化表述 |
| **完整性** | 必选 | 包含适用场景、关键步骤、常见陷阱三个章节，且每章节有实质内容 |
| **去隐私化** | 必选 | 已通过 4.4 过滤层（Review Agent 仅做二次确认） |
| **扩展知识** | 可选 | 有加分但不影响通过判定 |

#### 4.5.3 评审 Pipeline

```
Skill 草稿（经隐私过滤后）
    ↓
Review Agent 输出结构化评审结果：
  {
    "pass": true/false,
    "missing_required": ["缺少常见陷阱章节", "关键步骤过于抽象"],
    "optional_suggestions": ["可补充对 scope=全量模式 的处理经验"]
  }
    ↓
pass == true → 写入主 Skill，归档旧版本
pass == false → 将 missing_required 列表传回提炼 Prompt，定向重炼
    ↓
重炼后再次评审（最多 2 次）
    ↓
重炼仍不通过 → 丢弃，不写入
```

#### 4.5.4 Review Agent Prompt 示例

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是一个 Agent 经验 Skill 的评审专家。对给定 Skill 草稿逐项检查以下必选项：\n\n必选项（全部满足才算通过）：\n1. 【可操作性】关键步骤章节是否包含至少3个具体可执行步骤？泛化表述如"仔细分析"、"综合判断"不算。\n2. 【完整性】是否同时包含：适用场景、关键步骤、常见陷阱，且每项均有实质内容（非空、非占位）。\n3. 【去隐私化】是否不含具体需求ID、用户名、完整需求原文片段。\n\n输出格式（JSON，不要有额外文字）：\n{\n  \"pass\": true/false,\n  \"missing_required\": [\"具体缺失描述1\", \"具体缺失描述2\"],\n  \"optional_suggestions\": [\"可选改进建议1\"]\n}"
    },
    {
      "role": "user",
      "content": "请评审以下 Skill 草稿：\n\n{skill_draft_content}"
    }
  ]
}
```

#### 4.5.5 实施位置

- `backend_business/services/agent/experience/review_agent.py`
- 在 `container_completion_hook.py` 中，位于隐私过滤之后、`SkillStore` 写入之前

---

### 4.6 重复检测：大模型语义判断

#### 4.6.1 为什么不用 Hash

传统 hash 只能判断"表面是否相同"，无法处理：

- 用户换了表达方式，但任务本质相同
- 多个不同 Skill 描述同一类问题
- 新任务模式实际上是已有 Skill 的子集

因此改用大模型进行语义判断。

#### 4.6.2 判断 Pipeline

```
新任务完成，触发提炼条件
    ↓
提取本次 task_pattern 语义描述
    ↓
发送给判断模型：
"判断这个任务是否和已有的 {container_type} 主 Skill 高度重复？
  本次任务：{task_description}
  已有Skill的 task_pattern_summary：{existing_summary}
  输出 yes/no + 理由（限50字以内）"
    ↓
yes（高度重复）→ 跳过提炼，注册表中该 Skill 的 invocation_count + 1
no（不重复）→ 触发提炼流程（本次执行素材作为迭代输入，更新主 Skill）
```

#### 4.6.3 判断 Prompt 示例

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是一个任务相似度判断专家。给定一个新任务和已有的Skill，判断它们是否\"高度重复\"。\n\n高度重复的定义：\n- 任务类型相同（如都是\"冲突检测\"）\n- 处理流程相同\n- 使用的工具和参数模式相同\n- 只是在具体数据值上有差异（如需求ID不同）\n\n如果只是\"领域不同但模式相同\"，不算高度重复。\n\n输出格式：\n{\n  \"is_duplicate\": true/false,\n  \"reason\": \"判断理由，限50字以内\",\n  \"confidence\": 0.0-1.0\n}\n\n【重要】必须输出合法JSON，不要有额外文字。"
    },
    {
      "role": "user",
      "content": "新任务：{new_task_description}\n\n已有Skill的task_pattern_summary：{existing_skill_summary}\n\n请判断是否高度重复。"
    }
  ]
}
```

#### 4.6.4 实施位置

独立为 `skill_dedup.py`，在 `container_completion_hook` 中优先调用，重复则终止后续流程。

### 4.7 完整提炼流程图

```
Container 完成
    ↓
┌─────────────────────────────┐
│ 提炼条件检查                  │
│  - succeeded 状态？          │
│  - tool_calls >= 2？         │
│  - 非重复（4.6 大模型判断）   │
└──────────────┬──────────────┘
               ↓
        yes → 继续提炼
        no  → 丢弃，结束
               ↓
读取现有主 Skill（迭代基础，可选）
    ↓
收集提炼素材 → 提炼 Prompt → Skill 草稿
    ↓
隐私过滤层（4.4）
    ↓
Review Agent 结构化评审（4.5）
    ↓
pass == true？
    ├── yes → 归档旧主 Skill → 写入新主 Skill → 更新注册表
    └── no → 定向重炼（最多2次，传入 missing_required）
              ↓
              重炼仍不通过 → 丢弃
    ↓
【静默完成，不打断用户】
```

### 4.8 注入效果反馈闭环（新增）

Skill 注入后，现有流程不感知"注入是否起到了作用"。为此在 `container_completion_hook` 中增加以下逻辑：

```
Container 完成
    ↓
本次执行是否注入了 Skill？
    ├── 否 → 不处理
    └── 是
            ├── succeeded → skill.invocation_count + 1（已有逻辑）
            └── failed    → skill.injection_miss_count + 1
                                ↓
                            injection_miss_count / invocation_count > SKILL_MISS_THRESHOLD
                                ├── 未超过阈值 → 不处理
                                └── 超过阈值 → 强制触发完整提炼（忽略重复检测，以当前失败轨迹为迭代输入）
```

**关键参数**：`SKILL_MISS_THRESHOLD` 建议初始值 `0.4`，即注入后仍失败超过 40% 时认为 Skill 质量需要重炼。

**实施位置**：`container_completion_hook.py` 在写注册表时同步更新 `injection_miss_count`；在 `registry.py` 中加入阈值判断，超阈值时直接触发 `skill_compiler.py`。

**前提条件**：`container_completion_hook` 需要知道"本次执行是否注入了 Skill"，由 `PromptBuilder` 在构建 prompt 时写入执行上下文（`context["_injected_skill_id"]`），hook 读取即可。

---

## 五、Skill 检索与注入机制

### 5.1 注入层：就近原则

**Skill 应注入给实际执行该任务的 Container 的 system prompt，而非会话总控。**

会话总控的职责是意图理解与路由，它对领域语义保持不透明（见架构设计）；将冲突检测的操作经验注入会话总控，不仅语义不搭，还会在无关任务时引入噪声。

正确的注入时机：**各专项 Agent Container 在激活时**，由自身的 `PromptBuilder` 检索并注入本 container_type 对应的 Skill。

### 5.2 检索时机

在各专项 Agent 的 `PromptBuilder.build_system_prompt(container_type, task_description)` 中，构建 system prompt 时注入相关 Skill。`task_description` 来自 call 边传入的 payload 摘要。

### 5.3 检索流程

```
Container 激活，PromptBuilder 开始构建 system prompt
    ↓
SkillRetriever.retrieve(
    container_type=container_type,
    task_description=task_description   # 新增：用于语义匹配
)
    ↓
第一步：按 container_type 精确定位对应目录
    ↓
第二步：读取主 Skill 的 task_pattern 字段，
        与当前 task_description 做语义相似度判断（轻量模型）
        → 相关度 >= 阈值：注入该 Skill
        → 相关度 < 阈值：不注入（降级 fallback，Container 正常执行）
    ↓
将 Skill 内容格式化为 Prompt 片段
    ↓
追加到 Container system prompt 的专属区域
```

两步检索的设计意图：container_type 精确匹配保证检索范围，语义相似度判断过滤掉"类型对但任务不符"的情况（例如 conflict_detection Container 被用于概念询问时，不应注入针对具体检测任务的操作经验）。

### 5.4 Prompt 注入格式

```python
# 在各专项 Agent 的 PromptBuilder.build_system_prompt() 中
# （而非 SessionControllerPromptBuilder）

# ... base_prompt 构建逻辑 ...

# Skill 注入
skill_text, skill_meta = skill_loader.get_skill_for_container(
    container_type=container_type,
    task_description=task_description,
    similarity_threshold=SKILL_RETRIEVAL_THRESHOLD,
)
if skill_text:
    # 根据 Skill 成熟度决定注入措辞，防止早期质量差的 Skill 被过度采信
    if skill_meta.iteration <= 2:
        skill_prefix = "以下是初步积累的经验，仅供参考，不必完全照搬："
    else:
        skill_prefix = "以下是经过多次验证的经验，建议优先参考："

    base_prompt += (
        "\n\n[历史经验]\n"
        f"{skill_prefix}\n\n"
        f"{skill_text}\n"
        "—— 经验结束 ——"
    )

# scratchpad 注入（保持原有逻辑）
scratchpad_text = context.get("_scratchpad_prompt_text") or ""
if scratchpad_text:
    base_prompt += f"\n\n{scratchpad_text}"
```

### 5.5 Skill 命中逻辑

| 优先级 | 匹配方式 | 说明 |
|--------|----------|------|
| 1 | **container_type 精确匹配 + 语义相关** | 两步均通过 → 注入 |
| 2 | **container_type 精确匹配 + 语义不相关** | 类型对但任务不符 → 不注入（避免噪声） |
| 3 | **无匹配** | 无对应 container_type 目录 → 不注入 |

不设"模糊 container_type 匹配"：不同 container_type 的操作经验语义差异较大，跨类型注入收益低、风险高。

---

## 六、实施步骤

### Phase 1：基础设施搭建（预计 2-3 天）

**目标**：建立 Skill 的存储结构、基础读写接口。

1. 创建 `.agent_skills/` 目录结构（含 `_archive/` 子目录）
2. 实现 `skill_store.py` — Skill 文件写入（覆盖主文件 + 归档旧版本）
3. 实现 `skill_retriever.py` — container_type 精确匹配 + 语义相关度判断
4. 实现 `skill_sanitizer.py` — 正则 + LLM 二阶段隐私过滤
5. 创建 `_registry.yaml` 初始化逻辑
6. 手动撰写 1-2 个示例 Skill（如 `conflict_detection` 的种子 Skill）

**交付物**：
- `.agent_skills/conflict_detection/_skill.md`（手工撰写的种子）
- `skill_store.py`、`skill_retriever.py`、`skill_sanitizer.py`

---

### Phase 2：提炼触发机制 + Review Agent + 重复检测（预计 3-4 天）

**目标**：在 Container 完成后自动触发提炼 → 隐私过滤 → 结构化评审 → 迭代写入。

1. 实现 `skill_compiler.py` — 接收执行轨迹 + 现有主 Skill，调用 LLM 迭代更新
2. 实现 `review_agent.py` — 结构化缺失项评审（必选项通过判定）
3. 实现 `skill_dedup.py` — 大模型语义重复检测
4. 实现 `container_completion_hook.py` — 串联：去重 → 提炼 → 过滤 → 评审 → 写入
5. 实现 `registry.py` — 注册表更新逻辑
6. 端到端测试：执行一个冲突检测任务 → 验证提炼草稿 → 过滤 → 评审通过 → 写入文件

**交付物**：
- `skill_compiler.py`、`review_agent.py`、`skill_dedup.py`、`registry.py`
- `container_completion_hook.py`
- 完整流程验证

---

### Phase 3：检索与注入（预计 1-2 天）

**目标**：在各专项 Agent Container 激活时，自动加载相关 Skill 到 system prompt 中。

1. 实现 `skill_loader.py` — 将 Skill 内容格式化为 Prompt 片段
2. 修改各专项 Agent 的 `PromptBuilder.build_system_prompt()` — 注入 Skill 片段
3. 实现语义相关度判断（轻量 LLM 调用，判断 task_description 与 task_pattern 的匹配度）
4. 端到端测试：连续两次执行同类任务 → 验证第二次执行时目标 Container 的 system prompt 中携带 Skill

**交付物**：
- `skill_loader.py`
- 修改后的各专项 Agent `prompt_builder.py`
- 完整注入效果验证

---

### Phase 4：优化与迭代（持续）

1. **Skill 质量反馈**：记录 Skill 的 `invocation_count` 和 `last_used_at`，长期未使用的 Skill 降级或触发重新提炼
2. **扩展容器支持**：逐步为其他 Container 添加 Skill 支持
3. **跨容器模式提取**（可选）：识别跨 Container 复用的 Subgraph 模式，提取为共享原子 Skill
4. **可观测性**：Skill 被加载时记录日志，便于追踪哪些经验被使用了

---

## 七、关键文件清单

| 文件路径 | 职责 | 状态 |
|----------|------|------|
| `.agent_skills/_registry.yaml` | Skill 索引注册表 | 新增 |
| `.agent_skills/<container_type>/_skill.md` | 各容器当前最优主 Skill | 新增 |
| `.agent_skills/<container_type>/_archive/` | 历史版本归档目录 | 新增 |
| `experience/__init__.py` | 模块入口 | 新增 |
| `experience/skill_store.py` | 覆盖写入主 Skill + 归档旧版本 | 新增 |
| `experience/skill_retriever.py` | container_type 精确匹配 + 语义相关度判断 | 新增 |
| `experience/skill_loader.py` | Skill 注入目标 Container 的 Prompt | 新增 |
| `experience/skill_compiler.py` | 执行轨迹 + 现有主 Skill → 迭代更新草稿；支持失败态轻量 Pitfall 提炼模式 | 新增 |
| `experience/skill_sanitizer.py` | 正则 + LLM 二阶段隐私过滤 | 新增 |
| `experience/review_agent.py` | 结构化缺失项评审（必选项通过判定） | 新增 |
| `experience/skill_dedup.py` | 大模型语义重复检测 | 新增 |
| `experience/registry.py` | 注册表管理；包含 injection_miss_count 阈值判断与强制重炼触发 | 新增 |
| `execution/container_completion_hook.py` | 串联提炼→过滤→评审→写入；记录 injection_miss_count | 新增 |
| 各专项 Agent 的 `prompt_builder.py` | 注入 Skill 到 Container system prompt；写入 `_injected_skill_id` 到执行上下文 | 修改 |

---

## 八、潜在风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| Skill 提炼质量差（LLM 幻觉） | 中 | 中 | Phase 1 先手工写种子 Skill；提炼 Prompt 强调"不要写具体数值，要写模式" |
| 主 Skill 迭代后质量下降 | 低 | 中 | `_archive/` 保留旧版本，可手动回滚；长期可实现自动回滚机制 |
| 提炼触发过于频繁，拖慢响应速度 | 低 | 中 | 提炼为异步后台任务，不阻塞主流程 |
| Skill 内容残留隐私信息 | 低 | 高 | 4.4 隐私过滤层显式处理，不依赖模型自觉；过滤失败则不写入 |
| 语义相关度判断增加检索延迟 | 中 | 低 | 检索在 Container 激活时异步发起；相关度判断为轻量单次调用，延迟可控 |
| 新增代码影响现有 Agent 稳定性 | 中 | 高 | Phase 1-3 均通过配置项 `ENABLE_EXPERIENCE_SKILL` 可开关 |
| Skill 注入后任务仍持续失败（injection miss 积累） | 低 | 中 | 4.8 反馈闭环检测 miss 率超阈值后自动触发重炼；阈值可通过 `SKILL_MISS_THRESHOLD` 调整 |

---

## 九、配置项

```yaml
# backend_business/.env 或 docker-compose.yml 环境变量

# 经验技能总开关
ENABLE_EXPERIENCE_SKILL: "true"

# 提炼相关
SKILL_COMPILER_MODEL: "gpt-4o-mini"
SKILL_MIN_TOOL_CALLS: 2

# 去重相关
SKILL_DEDUP_MODEL: "gpt-4o-mini"

# 检索相关
SKILL_RETRIEVAL_MODEL: "gpt-4o-mini"        # 语义相关度判断用模型
SKILL_RETRIEVAL_THRESHOLD: 0.7              # 低于此值不注入 Skill

# 注入效果反馈相关
SKILL_MISS_THRESHOLD: 0.4                   # injection_miss / invocation 超过此值触发强制重炼

# 存储相关
AGENT_SKILLS_ROOT: ".agent_skills"
```

---

## 十、附录：相关文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| Multi-Agent 协同架构总结 | `docs/总结文档/MULTI_AGENT_SUMMARY.md` | 现有 Agent 架构全景 |
| 需求管理数据库设计 | `docs/总结文档/REQUIREMENTS_DB_DESIGN.md` | 数据库表结构参考 |
| Agent 方案 | `docs/开发文档/Agent方案_updated.md` | 详细的设计文档 |
| 新奇的思想 | `docs/新奇的思想/newidea.md` | 架构灵感参考 |
