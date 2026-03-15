# ProductManageView.vue 拆分方案

> 当前文件：`frontend/src/views/beta/ProductManageView.vue`  
> 当前行数：**1365 行**（template 459行 + script 325行 + style 580行）  
> 目标：拆分为 View / Component / Composable 三层，View 层精简到 **≤ 100 行**

---

## 一、最终目录结构

```
frontend/src/
│
├── views/beta/
│   └── ProductManageView.vue          ← 精简到 ~80 行（只做布局编排）
│
├── components/beta/product/           ← 新建此目录
│   ├── ProductListSection.vue         ← 产品列表（含搜索、三种视图切换）
│   ├── ProductDetailPanel.vue         ← 产品详情左侧（基本信息 + 统计 + 聚合tabs）
│   ├── ProjectListPanel.vue           ← 关联项目右侧列表
│   ├── ProductFormModal.vue           ← 新建/编辑产品 Modal（合并为一个，mode prop区分）
│   └── ProjectFormModal.vue           ← 新建/编辑项目 Modal（合并为一个，mode prop区分）
│
└── composables/
    ├── useProducts.js                 ← 产品列表状态 + CRUD 逻辑
    ├── useProductDetail.js            ← 选中产品详情 + 聚合统计逻辑
    └── useProjects.js                 ← 项目列表状态 + CRUD 逻辑
```

---

## 二、各文件职责与接口定义

### 📄 View 层：`ProductManageView.vue`（目标 ~80 行）

**职责**：页面骨架，组合 Sidebar + 各区块组件，不含任何业务逻辑。

```vue
<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar ... />
      <main class="canvas">
        <!-- 顶部导航栏 -->
        <section class="page-header nav-style" ...>
          <span class="nav-title">产品管理 · 产品线与项目概览</span>
          <button @click="showCreateModal = true">新建产品</button>
        </section>

        <!-- 产品列表 视图 -->
        <ProductListSection
          v-if="!selectedProduct"
          :products="filteredProducts"
          :loading="loading"
          :viewMode="viewMode"
          :searchQuery="searchQuery"
          @update:searchQuery="searchQuery = $event"
          @update:viewMode="viewMode = $event"
          @select="selectProduct"
        />

        <!-- 产品详情 视图（左+右 split layout） -->
        <template v-else>
          <ProductDetailPanel
            :product="selectedProduct"
            :overview="overview"
            :aggTab="aggTab"
            :loadingAgg="loadingAgg"
            :aggRequirements="filteredAggRequirements"
            :aggMilestones="aggMilestones"
            :aggBaselines="aggBaselines"
            :aggSearch="aggSearch"
            @back="selectedProduct = null"
            @edit="showEditModal = true"
            @delete="handleDeleteProduct"
            @switchTab="switchAggTab"
            @update:aggSearch="aggSearch = $event"
          />
          <ProjectListPanel
            :projects="projects"
            :loading="loadingProjects"
            @create="showCreateProjectModal = true"
            @edit="openEditProject"
            @delete="handleDeleteProject"
            @goto="goToProject"
          />
        </template>

        <!-- Modals -->
        <ProductFormModal
          v-if="showCreateModal"
          mode="create"
          @submit="handleCreateProduct"
          @close="showCreateModal = false"
        />
        <ProductFormModal
          v-if="showEditModal"
          mode="edit"
          :initial="selectedProduct"
          @submit="handleUpdateProduct"
          @close="showEditModal = false"
        />
        <ProjectFormModal
          v-if="showCreateProjectModal"
          mode="create"
          @submit="handleCreateProject"
          @close="showCreateProjectModal = false"
        />
        <ProjectFormModal
          v-if="showEditProjectModal"
          mode="edit"
          :initial="editingProject"
          @submit="handleUpdateProject"
          @close="showEditProjectModal = false"
        />
      </main>
    </div>
  </div>
</template>

<script setup>
import { useProducts }       from '../../composables/useProducts'
import { useProductDetail }  from '../../composables/useProductDetail'
import { useProjects }       from '../../composables/useProjects'
// ... 组件 import
// ... Sidebar 路由逻辑（handleNavigate / handleExit）
// ... 解构三个 composable 的返回值
</script>
```

---

### 📦 Component 层

#### `ProductListSection.vue`（约 130 行）

**来自原文件**：第 28-158 行（产品列表 template）+ 对应 CSS

| Props | 类型 | 说明 |
|---|---|---|
| `products` | `Array` | 过滤后的产品列表 |
| `loading` | `Boolean` | 加载状态 |
| `viewMode` | `String` | `'grid'` / `'list'` / `'table'` |
| `searchQuery` | `String` | 搜索关键词 |

| Emits | 说明 |
|---|---|
| `update:searchQuery` | 搜索框变化 |
| `update:viewMode` | 视图切换 |
| `select(product)` | 点击某产品 |

**包含的 CSS**：`.product-grid`, `.product-card`, `.product-list`, `.product-row`, `.product-table`, `.toggle-btn`, `.view-toggle` 等

---

#### `ProductDetailPanel.vue`（约 160 行）

**来自原文件**：第 162-296 行（左侧面板：基本信息 + 统计 + 聚合 tabs）+ 对应 CSS

| Props | 类型 | 说明 |
|---|---|---|
| `product` | `Object` | 当前选中产品 |
| `overview` | `Object\|null` | 产品概览统计数据 |
| `aggTab` | `String` | 当前聚合 tab |
| `loadingAgg` | `Boolean` | 聚合数据加载中 |
| `aggRequirements` | `Array` | 过滤后需求列表 |
| `aggMilestones` | `Array` | 里程碑列表 |
| `aggBaselines` | `Array` | 基线列表 |
| `aggSearch` | `String` | 需求搜索词 |

| Emits | 说明 |
|---|---|
| `back` | 返回列表 |
| `edit` | 打开编辑 modal |
| `delete` | 归档产品 |
| `switchTab(tab)` | 切换聚合 tab |
| `update:aggSearch` | 需求搜索词变化 |

**包含的 CSS**：`.product-info`, `.info-row`, `.info-label`, `.stats-section`, `.stats-grid`, `.stat-item`, `.agg-tabs`, `.agg-panel`, `.agg-table`, `.subsection-title` 等

---

#### `ProjectListPanel.vue`（约 80 行）

**来自原文件**：第 299-346 行（右侧关联项目列表）+ 对应 CSS

| Props | 类型 | 说明 |
|---|---|---|
| `projects` | `Array` | 关联项目列表 |
| `loading` | `Boolean` | 加载状态 |

| Emits | 说明 |
|---|---|
| `create` | 点击新建项目 |
| `edit(project)` | 点击编辑 |
| `delete(project)` | 点击归档 |
| `goto(project)` | 点击查看 |

**自带**：`formatDate` 工具函数（从 composable 引入或本地 import 一个工具函数）

---

#### `ProductFormModal.vue`（约 90 行）

**来自原文件**：第 350-413 行（新建+编辑产品 Modal 合并为一个组件）

| Props | 类型 | 说明 |
|---|---|---|
| `mode` | `'create'\|'edit'` | 区分新建/编辑 |
| `initial` | `Object\|null` | 编辑时传入初始值（product 对象） |

| Emits | 说明 |
|---|---|
| `submit(formData)` | 提交表单，交给 composable 处理 |
| `close` | 关闭 modal |

**内部状态**：`form = { name, description, version, roadmap, tagsInput }`（用 `watch(props.initial)` 初始化）

**包含的 CSS**：`.modal-overlay`, `.modal-content`, `.form-group`, `.modal-actions` 等

---

#### `ProjectFormModal.vue`（约 60 行）

**来自原文件**：第 415-455 行（新建+编辑项目 Modal 合并）

| Props | 类型 | 说明 |
|---|---|---|
| `mode` | `'create'\|'edit'` | 区分新建/编辑 |
| `initial` | `Object\|null` | 编辑时传入初始 project 对象 |

| Emits | 说明 |
|---|---|
| `submit(formData)` | 提交，返回 `{ name, description }` |
| `close` | 关闭 |

---

### 🪝 Composable 层

#### `composables/useProducts.js`（约 70 行）

**来自原文件**：第 509-599 行 + 649-706 行

```js
export function useProducts() {
  const loading = ref(false)
  const products = ref([])
  const searchQuery = ref('')
  const viewMode = ref(localStorage.getItem('beta-products:viewMode') || 'grid')
  const selectedProduct = ref(null)

  const filteredProducts = computed(...)

  async function loadProducts() { ... }
  async function selectProduct(product) { ... }
  async function handleCreateProduct(formData) { ... }
  async function handleUpdateProduct(formData) { ... }
  async function handleDeleteProduct() { ... }

  // modal 状态
  const showCreateModal = ref(false)
  const showEditModal = ref(false)

  watch(viewMode, val => localStorage.setItem('beta-products:viewMode', val))
  onMounted(() => loadProducts())

  return {
    loading, products, searchQuery, viewMode, selectedProduct,
    filteredProducts, showCreateModal, showEditModal,
    loadProducts, selectProduct,
    handleCreateProduct, handleUpdateProduct, handleDeleteProduct
  }
}
```

---

#### `composables/useProductDetail.js`（약 80 행）

**来自原文件**：第 606-647 行 + 聚合相关状态

```js
export function useProductDetail(selectedProduct) {
  const overview = ref(null)
  const loadingProjects = ref(false)

  const aggTab = ref('requirements')
  const loadingAgg = ref(false)
  const aggRequirements = ref([])
  const aggMilestones = ref([])
  const aggBaselines = ref([])
  const aggSearch = ref('')

  const filteredAggRequirements = computed(...)

  async function loadProductDetails() { ... }
  async function loadAggregations() { ... }
  function switchAggTab(tab) { ... }

  // 当 selectedProduct 变化时自动加载详情
  watch(selectedProduct, (val) => { if (val) loadProductDetails() })

  return {
    overview, loadingProjects,
    aggTab, loadingAgg, aggRequirements, aggMilestones, aggBaselines, aggSearch,
    filteredAggRequirements,
    loadProductDetails, switchAggTab
  }
}
```

---

#### `composables/useProjects.js`（约 70 行）

**来自原文件**：第 516-518 行 + 708-761 行

```js
export function useProjects(selectedProduct, loadProductDetails) {
  const projects = ref([])
  const loadingProjects = ref(false)
  const editingProject = ref(null)
  const showCreateProjectModal = ref(false)
  const showEditProjectModal = ref(false)

  function openEditProject(project) { ... }
  async function handleCreateProject(formData) { ... }
  async function handleUpdateProject(formData) { ... }
  async function handleDeleteProject(project) { ... }
  function goToProject(project) { ... }

  return {
    projects, loadingProjects, editingProject,
    showCreateProjectModal, showEditProjectModal,
    openEditProject,
    handleCreateProject, handleUpdateProject, handleDeleteProject, goToProject
  }
}
```

---

## 三、CSS 归属策略

| CSS 类 | 归属 |
|---|---|
| `.modal-overlay`, `.modal-content`, `.form-group`, `.modal-actions` | `ProductFormModal.vue` / `ProjectFormModal.vue` |
| `.product-grid`, `.product-card`, `.product-list`, `.product-row`, `.product-table`, `.toggle-btn`, `.view-toggle` | `ProductListSection.vue` |
| `.product-info`, `.info-row`, `.stats-section`, `.agg-tabs`, `.agg-panel`, `.agg-table` | `ProductDetailPanel.vue` |
| `.status-pill`, `.tag`, `.meta-item`, `.cell-desc`, `.loading-state`, `.empty-state` | 考虑提取到全局 CSS（`src/assets/common.css`）或各自组件保留 |
| `.action-btn`, `.ghost-small`, `.search-input`, `.back-btn` | 已有全局样式的不动，局部的各归各组件 |
| `@media (max-width: 640px)` 响应式 | 各组件自己管自己的部分 |

---

## 四、拆分后预估行数

| 文件 | 预估行数 |
|---|---|
| `ProductManageView.vue` | ~80 行 |
| `ProductListSection.vue` | ~130 行 |
| `ProductDetailPanel.vue` | ~160 行 |
| `ProjectListPanel.vue` | ~80 行 |
| `ProductFormModal.vue` | ~90 行 |
| `ProjectFormModal.vue` | ~60 行 |
| `useProducts.js` | ~70 行 |
| `useProductDetail.js` | ~80 行 |
| `useProjects.js` | ~70 行 |
| **合计** | **~820 行** |

> 原来 1365 行压缩分散为 9 个文件，每个文件都在 200 行以内，单一职责清晰。

---

## 五、建议执行顺序

拆分时建议**由内向外、由独立到耦合**的顺序执行，避免中途代码无法运行：

```
Step 1. 创建 composables/useProducts.js        ← 纯逻辑，不涉及 UI
Step 2. 创建 composables/useProductDetail.js   ← 纯逻辑，不涉及 UI
Step 3. 创建 composables/useProjects.js        ← 纯逻辑，不涉及 UI
Step 4. 更新 ProductManageView.vue 引用三个 composable（此时还不拆模板）
Step 5. 创建 ProductFormModal.vue              ← 最独立，无外部依赖
Step 6. 创建 ProjectFormModal.vue              ← 最独立，无外部依赖
Step 7. 创建 ProductListSection.vue
Step 8. 创建 ProductDetailPanel.vue
Step 9. 创建 ProjectListPanel.vue
Step 10. 精简 ProductManageView.vue 模板为骨架
```

每一步完成后应确认页面功能正常，再进行下一步。
