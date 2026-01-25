# 需求数据存储概览

本文档总结：
- 推理阶段产出的原始需求条目如何落库；
- 需求管理阶段 `manage_requirements` 中如何统一存储这些需求。

---

## 一、推理阶段原始需求表

### 1. requirements_l123（Phase 3：L1-L3 需求）

**用途：** 存储从文本中抽取的 L1/L2/L3 级别的“顶层需求草稿”，按会话分组。

表：`requirements_l123`

| 字段名         | 类型        | 说明                                         |
| -------------- | ----------- | -------------------------------------------- |
| req_id         | TEXT (PK)   | L1-L3 需求唯一标识（由系统生成的 UUID 文本） |
| session_id     | TEXT        | 抽取会话 ID，用于区分不同分析批次            |
| level          | TEXT        | 需求层级：`L1`、`L2`、`L3`                   |
| text           | TEXT        | 原始需求文本（10~500 字符区间约束）          |
| fingerprint    | TEXT        | 文本指纹，用于去重（唯一索引）               |
| anchor_span_id | TEXT (FK)   | 关联的 spans.span_id（上下文片段）           |
| r              | INTEGER     | 预留排序/评分字段                            |
| created_at     | TIMESTAMPTZ | 创建时间                                     |

> 这些记录是“原始抽取结果”，还未归入某个具体项目，仅通过 `session_id` 关联到上游分析（transcript/context）。

---

### 2. low_level_requirements（L4 底层需求）

**用途：** 存储由模型生成的 L4 “底层需求”，通常基于某个 L1-L3 顶层需求生成。

表：`low_level_requirements`

| 字段名              | 类型        | 说明                                                   |
| ------------------- | ----------- | ------------------------------------------------------ |
| req_id              | TEXT (PK)   | L4 需求唯一标识（UUID 文本）                           |
| session_id          | TEXT        | 生成会话 ID，与 L1-L3 抽取同源的 session 对齐          |
| source_top_id       | TEXT        | 来源的顶层需求 ID（通常对应 requirements_l123.req_id） |
| source_top_text     | TEXT        | 来源顶层需求的文本快照                                 |
| text                | TEXT        | L4 底层需求描述                                        |
| component           | TEXT        | 相关组件/模块名称                                      |
| acceptance_criteria | JSONB       | 验收标准列表                                           |
| test_method         | TEXT        | 建议的测试方法                                         |
| interfaces          | JSONB       | 接口信息（输入/输出等）                                |
| data_contracts      | JSONB       | 数据契约/结构描述                                      |
| error_handling      | JSONB       | 错误处理策略                                           |
| nfr                 | JSONB       | 非功能性需求相关信息                                   |
| open_questions      | JSONB       | 仍待澄清的问题列表                                     |
| evidence_ids        | JSONB       | 关联的证据（如 span/bundle ID 列表）                   |
| confidence          | REAL        | 模型给出的置信度                                       |
| source              | TEXT        | 来源标记（例如所用模型/流程）                          |
| meta                | JSONB       | 其他元信息                                             |
| created_at          | TIMESTAMPTZ | 创建时间                                               |

> 这些记录同样是“推理阶段原始结果”，按 session 组织，还未绑定到业务项目。

---

### 3. low_level_requirement_links（L4-L1/L2/L3 映射）

**用途：** 记录 L4 底层需求与顶层需求（requirements_l123）的多对多追溯关系。

表：`low_level_requirement_links`

| 字段名     | 类型        | 说明                                               |
| ---------- | ----------- | -------------------------------------------------- |
| req_id     | TEXT (PK1)  | 关联的 L4 需求 ID（low_level_requirements.req_id） |
| session_id | TEXT        | 会话 ID，便于按批次查询                            |
| top_req_id | TEXT (PK2)  | 顶层需求 ID（requirements_l123.req_id）            |
| created_at | TIMESTAMPTZ | 创建时间                                           |

---

## 二、需求管理阶段表：manage_requirements

**用途：** 将上面推理阶段产生的各种需求条目（L1-L3 顶层、L4 底层以及任务等）统一收敛到“项目级需求库”中，用于规划、里程碑、基线和变更管理。

表：`manage_requirements`

| 字段名           | 类型        | 说明                                                                                    |
| ---------------- | ----------- | --------------------------------------------------------------------------------------- |
| req_id           | TEXT (PK)   | 管理侧需求主键；可以直接使用原始 req_id（如 L1-L4 的 req_id），也可以新生成 UUID        |
| project_id       | TEXT (FK)   | 所属项目（manage_projects.project_id），将原始需求挂到具体项目之下                      |
| requirement_type | TEXT        | 需求类型：`top_level`（顶层）、`low_level`（底层）、`task`（任务/L5）                   |
| status           | TEXT        | 状态：`draft` / `under_review` / `confirmed` / `in_progress` / `completed` / `archived` |
| title            | TEXT        | 需求标题（从原始 text 抽取或用户编辑）                                                  |
| description      | TEXT        | 详细描述                                                                                |
| priority         | TEXT        | 优先级（由用户在管理界面设置）                                                          |
| assignee         | TEXT        | 负责人                                                                                  |
| tags             | JSONB       | 标签数组（例如领域、模块、风险等）                                                      |
| due_date         | TEXT        | 计划完成日期（字符串格式）                                                              |
| parent_id        | TEXT (FK)   | 父需求 ID（自引用 manage_requirements.req_id），用于组织成树                            |
| order_index      | INTEGER     | 同一父节点下的排序序号                                                                  |
| source_req_id    | TEXT        | 源需求 ID：指向原始推理表中的 req_id（如 requirements_l123/low_level_requirements）     |
| source_level     | TEXT        | 源需求层级：例如 `L1`/`L2`/`L3`/`L4`/`L5`                                               |
| custom_fields    | JSONB       | 自定义字段（例如来源、会话 ID、链接等）                                                 |
| created_by       | TEXT        | 创建人                                                                                  |
| created_at       | TIMESTAMPTZ | 创建时间                                                                                |
| updated_by       | TEXT        | 最近更新人                                                                              |
| updated_at       | TIMESTAMPTZ | 最近更新时间                                                                            |
| deleted          | BOOLEAN     | 逻辑删除标记                                                                            |

> 该表是“管理视角”的统一需求表，前端的需求树、冲刺规划、里程碑快照等都基于此表。

---

## 三、推理阶段到 manage_requirements 的映射关系

### 1. L1-L3 顶层需求（requirements_l123 → manage_requirements）

- 导入入口：`RequirementsManageService.import_from_l123()`。
- 关键规则：
  - 对于 L1/L2/L3 记录：
    - 在 manage_requirements 中创建 `requirement_type = 'top_level'` 的记录；
    - `title` 源自 requirements_l123.text；
    - `source_req_id = requirements_l123.req_id`，`source_level = level`；
    - custom_fields 中会记录 `{ "source": "requirements_l123" }`；
    - 如同一源 `source_req_id` 已存在，则跳过，避免重复导入。

### 2. L4 底层需求（low_level_requirements → manage_requirements）

- 仍由 `import_from_l123()` 在第二阶段导入：
  - 为每条 low_level_requirements 生成 `requirement_type = 'low_level'` 的记录；
  - `title` 源自 low_level_requirements.text；
  - 通过 low_level_requirement_links 或 source_top_id 去寻找对应的顶层 manage_requirements 记录，填充 `parent_id` 形成树；
  - `source_req_id = low_level_requirements.req_id`，`source_level = 'L4'`；
  - custom_fields 中记录 `{ "source": "low_level_requirements", ... }`（包括 source_top_id 等信息）。

### 3. 里程碑回流（manage_milestone_nodes.snapshot_data → manage_requirements）

- 导入入口：`RequirementsManageService.import_from_milestone()`。
- 数据来源：`manage_milestone_nodes` 中的 `snapshot_data`（保存当时 manage_requirements 行的 JSON 快照）。
- 导入规则：
  - 使用 `nodes.requirement_id` 作为 manage_requirements.req_id（即沿用原管理表主键）；
  - snapshot_data 中的字段（requirement_type、status、title、description、priority、assignee、tags、due_date、source_req_id、source_level、custom_fields 等）回填到 manage_requirements；
  - parent_id、order_index 取自节点自身（用于还原树结构）；
  - 如果目标 req_id 已存在，则执行 `ON CONFLICT (req_id) DO UPDATE`，以快照为准更新管理库记录。

---

## 四、小结

- **推理阶段**：
  - requirements_l123：存储按会话组织的 L1-L3 文本型顶层需求；
  - low_level_requirements：存储基于 L1-L3 生成的 L4 底层需求及其设计/测试相关结构化信息；
  - low_level_requirement_links：维护 L4 与 L1-L3 的追溯关系。
- **管理阶段**：
  - manage_requirements：以项目为维度，统一承载从上述原始需求导入后的“可运营需求”，支持树结构、状态流转、标签、负责人等管理字段；
  - 源头通过 `source_req_id` + `source_level` + `custom_fields` 与推理阶段数据保持可追溯性。
