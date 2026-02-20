# 前端文件拆分指南

> 本文档总结自 `frontend/REFACTOR_PLAN_ProductManage.md` 的实践经验，
> 适用于所有超过 400 行的 Vue 单文件组件的拆分工作。

---

## 一、核心思想：三层分离

任何一个页面都应当由三层组成，每层只做自己分内的事：

```
View 层
  └─ 负责：页面骨架、组件编排、路由导航
  └─ 不含：业务逻辑、API 调用、复杂状态

Component 层
  └─ 负责：一块独立 UI 的渲染与局部交互
  └─ 不含：跨组件状态、直接 API 调用

Composable 层
  └─ 负责：状态管理、API 调用、业务逻辑
  └─ 不含：任何 template/HTML
```

**判断标准**：View 不该知道"怎么做"，只知道"有什么"；Component 不该知道"数据从哪来"，只知道"怎么展示"。

---

## 二、触发拆分的信号

出现以下任意一条，就应该开始拆分：

| 信号 | 说明 |
|---|---|
| 单文件超过 **400 行** | 文件已难以通读 |
| `<script setup>` 超过 **150 行** | 业务逻辑过于集中 |
| `<style>` 超过 **200 行** | CSS 与多个 UI 块强耦合 |
| 同一 template 中有超过 **3 个独立 UI 区块** | 每个区块都是潜在的子组件 |
| 多个页面共用相同的数据逻辑 | 应提取为 composable |

---

## 三、拆分步骤（由内向外）

**始终从最无依赖的部分开始**，确保每一步完成后页面仍可正常运行：

```
Step 1. 提取 Composable（纯逻辑，不涉及 UI）
Step 2. 让 View 引用 Composable（此时不动 template）
Step 3. 提取最独立的 Modal/Dialog 组件（无外部状态依赖）
Step 4. 提取列表/卡片等展示组件
Step 5. 提取详情/面板等复合组件
Step 6. 精简 View 的 template 为骨架
```

---

## 四、目录结构约定

```
frontend/src/
│
├── views/
│   └── <module>/
│       └── XxxView.vue            ← 只做骨架编排，目标 ≤ 100 行
│
├── components/
│   └── <module>/
│       └── <feature>/             ← 按功能域建子目录
│           ├── XxxListSection.vue
│           ├── XxxDetailPanel.vue
│           ├── XxxFormModal.vue
│           └── ...
│
└── composables/
    ├── useXxxList.js              ← 列表状态 + CRUD
    ├── useXxxDetail.js            ← 详情 + 聚合统计
    └── useXxxRelated.js           ← 关联实体的状态 + CRUD
```

**命名规则**：
- Composable 以 `use` 开头，名词描述管理的实体，如 `useProducts`、`useProjects`
- Component 以名词+职责后缀命名：`ListSection`、`DetailPanel`、`FormModal`、`Card`

---

## 五、各层的接口规范

### View 层

```vue
<script setup>
// 1. 路由 + 导航（≤ 20 行）
// 2. Sidebar 状态（roleType / activePage 等）
// 3. 解构三个 composable 的返回值
// 4. 不写任何 async 函数、不直接调用 API
</script>
```

### Component 层

```vue
<script setup>
// 只用 defineProps + defineEmits
// 允许：本地格式化工具函数（formatDate 等）
// 允许：纯 UI 交互状态（展开/折叠、hover）
// 不允许：ref 存储业务数据、直接调用 API
</script>
```

**Props 向下，Emits 向上**：子组件通过 `emit` 把用户意图上报，由 composable 决定如何处理。

### Composable 层

```js
export function useXxx(deps) {
  // 状态声明
  // computed 派生值
  // 异步方法（loadXxx / handleCreate / handleUpdate / handleDelete）
  // watch（监听依赖自动加载）
  // onMounted（初始化）
  return { /* 只暴露 View/Component 需要的内容 */ }
}
```

**依赖注入**：若 composable A 的操作需要刷新 composable B 的数据，把 B 的刷新函数作为参数传给 A：

```js
const { loadDetails } = useXxxDetail(selectedItem)
const { handleCreate } = useXxxRelated(selectedItem, loadDetails)
//                                                   ↑ 操作完后回调刷新
```

---

## 六、CSS 归属策略

| CSS 内容 | 归属位置 |
|---|---|
| Modal 结构样式（overlay、content、form-group） | 对应 Modal 组件内 `<style scoped>` |
| 列表/卡片样式 | 对应列表组件内 `<style scoped>` |
| 详情面板样式 | 对应详情组件内 `<style scoped>` |
| 通用工具类（status-pill、tag、empty-state） | 考虑提取到 `src/assets/common.css` |
| 全局布局（canvas、grid、split-layout） | 保留在全局样式中，不放入组件 |
| 响应式断点 | 各组件管理自己部分的响应式 |

---

## 七、行数预算参考

| 层级 | 典型行数 | 上限 |
|---|---|---|
| View | 80–120 行 | 150 行 |
| 列表/卡片组件 | 150–250 行 | 350 行 |
| 详情/面板组件 | 150–250 行 | 350 行 |
| Modal 组件 | 60–120 行 | 200 行 |
| Composable | 60–100 行 | 150 行 |

超出上限时，重复本文第三节的流程，继续向下拆分。

---

## 八、实际案例参考

`ProductManageView` 重构（1365 行 → 9 个文件）：

```
frontend/src/
├── views/beta/ProductManageView.vue              163 行  页面骨架
├── components/beta/product/
│   ├── ProductListSection.vue                    336 行  产品列表+三视图
│   ├── ProductDetailPanel.vue                    315 行  详情+聚合tabs
│   ├── ProjectListPanel.vue                      120 行  关联项目列表
│   ├── ProductFormModal.vue                      179 行  新建/编辑产品
│   └── ProjectFormModal.vue                      153 行  新建/编辑项目
└── composables/
    ├── useProducts.js                            113 行  产品CRUD+视图状态
    ├── useProductDetail.js                        80 行  概览+聚合统计
    └── useProjects.js                            102 行  项目CRUD
```

拆分前每次改动都要理解 1365 行；拆分后修改产品表单只需打开 179 行的 `ProductFormModal.vue`。
