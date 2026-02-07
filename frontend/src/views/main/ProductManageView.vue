<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="roleType"
        :roleLabel="roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">产品管理 · 产品线与项目概览</span>
          </div>
          <div class="nav-center">
            <span class="jama-pill">产品→项目归属关系</span>
          </div>
          <div class="page-actions">
            <button type="button" class="action-btn brown" @click="showCreateModal = true">新建产品</button>
            <span class="nav-text">通知 · {{ notificationCount }}</span>
          </div>
        </section>

        <!-- 产品列表 -->
        <section v-if="!selectedProduct" class="grid" data-animate style="--delay: 0.12s">
          <div class="card wide">
            <div class="card-header no-border">
              <div>
                <p class="card-kicker">Products</p>
                <h2 class="section-title">产品列表</h2>
              </div>
              <div class="header-actions">
                <input type="text" v-model="searchQuery" placeholder="搜索产品..." class="search-input" />
                <div class="view-toggle" role="tablist" aria-label="产品视图切换">
                  <button
                    type="button"
                    class="toggle-btn"
                    :class="{ active: viewMode === 'grid' }"
                    role="tab"
                    :aria-selected="viewMode === 'grid'"
                    @click="viewMode = 'grid'"
                  >
                    块视图
                  </button>
                  <button
                    type="button"
                    class="toggle-btn"
                    :class="{ active: viewMode === 'list' }"
                    role="tab"
                    :aria-selected="viewMode === 'list'"
                    @click="viewMode = 'list'"
                  >
                    条视图
                  </button>
                  <button
                    type="button"
                    class="toggle-btn"
                    :class="{ active: viewMode === 'table' }"
                    role="tab"
                    :aria-selected="viewMode === 'table'"
                    @click="viewMode = 'table'"
                  >
                    表格
                  </button>
                </div>
              </div>
            </div>

            <div v-if="loading" class="loading-state">
              <span>加载中...</span>
            </div>

            <div v-else-if="filteredProducts.length === 0" class="empty-state">
              <p>暂无产品，点击"新建产品"创建第一个产品</p>
            </div>

            <div v-else>
              <!-- Grid view (default) -->
              <div v-if="viewMode === 'grid'" class="product-grid">
                <div
                  v-for="product in filteredProducts"
                  :key="product.product_id"
                  class="product-card"
                  @click="selectProduct(product)"
                >
                  <div class="product-card-header">
                    <h3 class="product-name">{{ product.name }}</h3>
                    <span :class="['status-pill', product.status]">{{ product.status === 'active' ? '活跃' : '已归档' }}</span>
                  </div>
                  <p class="product-desc">{{ product.description || '暂无描述' }}</p>
                  <div class="product-meta">
                    <span v-if="product.version" class="meta-item">
                      <span class="meta-label">版本:</span> {{ product.version }}
                    </span>
                    <span class="meta-item">
                      <span class="meta-label">创建:</span> {{ formatDate(product.created_at) }}
                    </span>
                  </div>
                  <div class="product-tags" v-if="product.tags && product.tags.length">
                    <span v-for="tag in product.tags" :key="tag" class="tag">{{ tag }}</span>
                  </div>
                </div>
              </div>

              <!-- List view -->
              <div v-else-if="viewMode === 'list'" class="product-list">
                <div
                  v-for="product in filteredProducts"
                  :key="product.product_id"
                  class="product-row"
                  @click="selectProduct(product)"
                >
                  <div class="row-main">
                    <div class="row-top">
                      <strong class="row-title">{{ product.name }}</strong>
                      <span :class="['status-pill', product.status]">{{ product.status === 'active' ? '活跃' : '已归档' }}</span>
                    </div>
                    <div class="row-desc">{{ product.description || '暂无描述' }}</div>
                    <div class="row-meta">
                      <span v-if="product.version" class="meta-item"><span class="meta-label">版本:</span> {{ product.version }}</span>
                      <span class="meta-item"><span class="meta-label">创建:</span> {{ formatDate(product.created_at) }}</span>
                    </div>
                  </div>
                  <div class="row-side">
                    <div class="row-tags" v-if="product.tags && product.tags.length">
                      <span v-for="tag in product.tags" :key="tag" class="tag">{{ tag }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Table view -->
              <div v-else class="product-table">
                <div class="table-header">
                  <span>产品名称</span>
                  <span>状态</span>
                  <span>版本</span>
                  <span>创建时间</span>
                </div>
                <div
                  v-for="product in filteredProducts"
                  :key="product.product_id"
                  class="table-row"
                  @click="selectProduct(product)"
                  title="点击查看详情"
                >
                  <span class="cell-main"><strong>{{ product.name }}</strong><span class="cell-desc">{{ product.description || '暂无描述' }}</span></span>
                  <span><span :class="['status-pill', product.status]">{{ product.status === 'active' ? '活跃' : '已归档' }}</span></span>
                  <span>{{ product.version || '-' }}</span>
                  <span>{{ formatDate(product.created_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 产品详情 -->
        <section v-else class="grid split-layout" data-animate style="--delay: 0.12s">
          <!-- Left: Product Info -->
          <div class="card">
            <div class="card-header no-border">
              <div>
                <button type="button" class="back-btn" @click="selectedProduct = null">
                  ← 返回列表
                </button>
                <h2 class="section-title">{{ selectedProduct.name }}</h2>
              </div>
              <div class="header-actions">
                <button type="button" class="ghost-small" @click="showEditModal = true">编辑</button>
                <button type="button" class="ghost-small danger" @click="handleDeleteProduct">归档</button>
              </div>
            </div>

            <div class="product-info">
              <div class="info-row">
                <span class="info-label">状态</span>
                <span :class="['status-pill', selectedProduct.status]">
                  {{ selectedProduct.status === 'active' ? '活跃' : '已归档' }}
                </span>
              </div>
              <div class="info-row" v-if="selectedProduct.version">
                <span class="info-label">版本</span>
                <span>{{ selectedProduct.version }}</span>
              </div>
              <div class="info-row" v-if="selectedProduct.roadmap">
                <span class="info-label">路线图</span>
                <span>{{ selectedProduct.roadmap }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">描述</span>
                <span>{{ selectedProduct.description || '暂无描述' }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">创建时间</span>
                <span>{{ formatDate(selectedProduct.created_at) }}</span>
              </div>
              <div class="info-row" v-if="selectedProduct.tags && selectedProduct.tags.length">
                <span class="info-label">标签</span>
                <div class="product-tags">
                  <span v-for="tag in selectedProduct.tags" :key="tag" class="tag">{{ tag }}</span>
                </div>
              </div>
            </div>

            <!-- Overview Stats -->
            <div class="stats-section" v-if="overview">
              <h3 class="subsection-title">概览统计</h3>
              <div class="stats-grid">
                <div class="stat-item">
                  <span class="stat-value">{{ overview.stats.projects.total || 0 }}</span>
                  <span class="stat-label">项目</span>
                </div>
                <div class="stat-item">
                  <span class="stat-value">{{ overview.stats.requirements.total || 0 }}</span>
                  <span class="stat-label">需求</span>
                </div>
                <div class="stat-item">
                  <span class="stat-value">{{ overview.stats.milestones.total || 0 }}</span>
                  <span class="stat-label">里程碑</span>
                </div>
                <div class="stat-item">
                  <span class="stat-value">{{ overview.stats.milestones.baselines || 0 }}</span>
                  <span class="stat-label">基线</span>
                </div>
              </div>

              <div class="agg-tabs">
                <button type="button" class="tab" :class="{ active: aggTab === 'requirements' }" @click="switchAggTab('requirements')">需求</button>
                <button type="button" class="tab" :class="{ active: aggTab === 'milestones' }" @click="switchAggTab('milestones')">里程碑</button>
                <button type="button" class="tab" :class="{ active: aggTab === 'baselines' }" @click="switchAggTab('baselines')">基线</button>
              </div>

              <div class="agg-panel">
                <div v-if="loadingAgg" class="loading-state">加载中...</div>
                <div v-else-if="aggTab === 'requirements'">
                  <div class="mini-search">
                    <input type="text" v-model="aggSearch" placeholder="搜索需求标题/项目..." class="search-input full-width" />
                  </div>
                  <div v-if="filteredAggRequirements.length === 0" class="empty-state">暂无需求</div>
                  <div v-else class="agg-table">
                    <div class="table-header">
                      <span>项目</span>
                      <span>标题</span>
                      <span>类型</span>
                      <span>状态</span>
                    </div>
                    <div v-for="r in filteredAggRequirements" :key="r.req_id" class="table-row">
                      <span>{{ r.project_name }}</span>
                      <span class="cell-main"><strong>{{ r.title }}</strong></span>
                      <span>{{ r.requirement_type }}</span>
                      <span>{{ r.status }}</span>
                    </div>
                  </div>
                </div>

                <div v-else-if="aggTab === 'milestones'">
                  <div v-if="aggMilestones.length === 0" class="empty-state">暂无里程碑</div>
                  <div v-else class="agg-table">
                    <div class="table-header">
                      <span>项目</span>
                      <span>名称</span>
                      <span>类型</span>
                      <span>版本</span>
                    </div>
                    <div v-for="m in aggMilestones" :key="m.milestone_id" class="table-row">
                      <span>{{ m.project_name }}</span>
                      <span class="cell-main"><strong>{{ m.name }}</strong></span>
                      <span>{{ m.milestone_type }}</span>
                      <span>{{ m.version || '-' }}</span>
                    </div>
                  </div>
                </div>

                <div v-else>
                  <div v-if="aggBaselines.length === 0" class="empty-state">暂无基线</div>
                  <div v-else class="agg-table">
                    <div class="table-header">
                      <span>项目</span>
                      <span>名称</span>
                      <span>版本</span>
                      <span>创建时间</span>
                    </div>
                    <div v-for="b in aggBaselines" :key="b.milestone_id" class="table-row">
                      <span>{{ b.project_name }}</span>
                      <span class="cell-main"><strong>{{ b.name }}</strong></span>
                      <span>{{ b.version || '-' }}</span>
                      <span>{{ formatDate(b.created_at) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Right: Projects List -->
          <div class="card">
            <div class="card-header no-border">
              <div>
                <p class="card-kicker">Projects</p>
                <h2 class="section-title">关联项目</h2>
              </div>
              <button type="button" class="action-btn brown small" @click="showCreateProjectModal = true">
                新建项目
              </button>
            </div>

            <div v-if="loadingProjects" class="loading-state">
              <span>加载中...</span>
            </div>

            <div v-else-if="projects.length === 0" class="empty-state">
              <p>暂无关联项目</p>
              <button type="button" class="action-btn brown" @click="showCreateProjectModal = true">
                创建第一个项目
              </button>
            </div>

            <div v-else class="data-table">
              <div class="table-header">
                <span>项目名称</span>
                <span>状态</span>
                <span>创建时间</span>
                <span>操作</span>
              </div>
              <div v-for="project in projects" :key="project.project_id" class="table-row">
                <div class="cell-main">
                  <strong>{{ project.name }}</strong>
                  <span class="cell-desc">{{ project.description }}</span>
                </div>
                <span>
                  <span :class="['status-pill', project.status]">
                    {{ project.status === 'active' ? '活跃' : '已归档' }}
                  </span>
                </span>
                <span>{{ formatDate(project.created_at) }}</span>
                <span>
                  <button type="button" class="ghost-small" @click="goToProject(project)">查看</button>
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- Create Product Modal -->
        <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
          <div class="modal-content">
            <h3>新建产品</h3>
            <div class="form-group">
              <label>产品名称 *</label>
              <input type="text" v-model="newProduct.name" placeholder="输入产品名称" />
            </div>
            <div class="form-group">
              <label>描述</label>
              <textarea v-model="newProduct.description" placeholder="输入产品描述" rows="3"></textarea>
            </div>
            <div class="form-group">
              <label>版本</label>
              <input type="text" v-model="newProduct.version" placeholder="如: v1.0.0" />
            </div>
            <div class="form-group">
              <label>路线图</label>
              <input type="text" v-model="newProduct.roadmap" placeholder="产品路线图说明" />
            </div>
            <div class="form-group">
              <label>标签 (逗号分隔)</label>
              <input type="text" v-model="newProduct.tagsInput" placeholder="tag1, tag2, tag3" />
            </div>
            <div class="modal-actions">
              <button type="button" class="action-btn white" @click="showCreateModal = false">取消</button>
              <button type="button" class="action-btn brown" @click="handleCreateProduct" :disabled="!newProduct.name.trim()">
                创建
              </button>
            </div>
          </div>
        </div>

        <!-- Edit Product Modal -->
        <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
          <div class="modal-content">
            <h3>编辑产品</h3>
            <div class="form-group">
              <label>产品名称 *</label>
              <input type="text" v-model="editProduct.name" placeholder="输入产品名称" />
            </div>
            <div class="form-group">
              <label>描述</label>
              <textarea v-model="editProduct.description" placeholder="输入产品描述" rows="3"></textarea>
            </div>
            <div class="form-group">
              <label>版本</label>
              <input type="text" v-model="editProduct.version" placeholder="如: v1.0.0" />
            </div>
            <div class="form-group">
              <label>路线图</label>
              <input type="text" v-model="editProduct.roadmap" placeholder="产品路线图说明" />
            </div>
            <div class="form-group">
              <label>标签 (逗号分隔)</label>
              <input type="text" v-model="editProduct.tagsInput" placeholder="tag1, tag2, tag3" />
            </div>
            <div class="modal-actions">
              <button type="button" class="action-btn white" @click="showEditModal = false">取消</button>
              <button type="button" class="action-btn brown" @click="handleUpdateProduct" :disabled="!editProduct.name.trim()">
                保存
              </button>
            </div>
          </div>
        </div>

        <!-- Create Project Modal -->
        <div v-if="showCreateProjectModal" class="modal-overlay" @click.self="showCreateProjectModal = false">
          <div class="modal-content">
            <h3>在产品下新建项目</h3>
            <div class="form-group">
              <label>项目名称 *</label>
              <input type="text" v-model="newProject.name" placeholder="输入项目名称" />
            </div>
            <div class="form-group">
              <label>描述</label>
              <textarea v-model="newProject.description" placeholder="输入项目描述" rows="3"></textarea>
            </div>
            <div class="modal-actions">
              <button type="button" class="action-btn white" @click="showCreateProjectModal = false">取消</button>
              <button type="button" class="action-btn brown" @click="handleCreateProject" :disabled="!newProject.name.trim()">
                创建
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import Sidebar from "../../components/main/Sidebar.vue";
import { productApi } from "../../utils/api";

const router = useRouter();
const route = useRoute();

// Sidebar state
const roleType = ref("unified_admin");
const roleLabel = ref("管理员");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);

const routeNameToPageKey = {
  "main-dashboard": "dashboard",
  "main-project": "project-management",
  "main-requirements": "requirements",
  "main-requirements-analysis": "requirements-analysis",
  "main-requirements-collection": "requirements-collection",
  "main-products": "products",
};

const pageKeyToRouteName = {
  "dashboard": "main-dashboard",
  "project-management": "main-project",
  "requirements": "main-requirements",
  "requirements-analysis": "main-requirements-analysis",
  "requirements-collection": "main-requirements-collection",
  "products": "main-products",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "products");

const handleNavigate = (page) => {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
};

const handleExit = () => {
  router.push({ name: "main-login" });
};

// Products state
const loading = ref(false);
const products = ref([]);
const searchQuery = ref("");
const selectedProduct = ref(null);
const viewMode = ref(localStorage.getItem("main-products:viewMode") || "grid");

// Projects state
const loadingProjects = ref(false);
const projects = ref([]);
const overview = ref(null);

// Aggregation state
const aggTab = ref("requirements");
const loadingAgg = ref(false);
const aggRequirements = ref([]);
const aggMilestones = ref([]);
const aggBaselines = ref([]);
const aggSearch = ref("");

// Modals
const showCreateModal = ref(false);
const showEditModal = ref(false);
const showCreateProjectModal = ref(false);

const newProduct = ref({
  name: "",
  description: "",
  version: "",
  roadmap: "",
  tagsInput: "",
});

const editProduct = ref({
  name: "",
  description: "",
  version: "",
  roadmap: "",
  tagsInput: "",
});

const newProject = ref({
  name: "",
  description: "",
});

// Computed
const filteredProducts = computed(() => {
  if (!searchQuery.value.trim()) return products.value;
  const query = searchQuery.value.toLowerCase();
  return products.value.filter(p =>
    p.name.toLowerCase().includes(query) ||
    (p.description && p.description.toLowerCase().includes(query))
  );
});

const filteredAggRequirements = computed(() => {
  const list = aggRequirements.value || [];
  const q = aggSearch.value.trim().toLowerCase();
  if (!q) return list;
  return list.filter((r) => {
    return (
      String(r.title || "").toLowerCase().includes(q) ||
      String(r.project_name || "").toLowerCase().includes(q)
    );
  });
});

// Methods
const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  return date.toLocaleDateString("zh-CN");
};

const loadProducts = async () => {
  loading.value = true;
  try {
    const resp = await productApi.listProducts();
    products.value = resp.products || [];
  } catch (err) {
    console.error("Failed to load products:", err);
  } finally {
    loading.value = false;
  }
};

const selectProduct = async (product) => {
  selectedProduct.value = product;
  await loadProductDetails();
};

const loadProductDetails = async () => {
  if (!selectedProduct.value) return;

  loadingProjects.value = true;
  try {
    const [projectsResp, overviewResp] = await Promise.all([
      productApi.listProjectsByProduct(selectedProduct.value.product_id),
      productApi.getProductOverview(selectedProduct.value.product_id),
    ]);
    projects.value = projectsResp.projects || [];
    overview.value = overviewResp;
    await loadAggregations();
  } catch (err) {
    console.error("Failed to load product details:", err);
  } finally {
    loadingProjects.value = false;
  }
};

const loadAggregations = async () => {
  if (!selectedProduct.value) return;
  loadingAgg.value = true;
  try {
    const [reqResp, msResp, blResp] = await Promise.all([
      productApi.listRequirementsByProduct(selectedProduct.value.product_id),
      productApi.listMilestonesByProduct(selectedProduct.value.product_id),
      productApi.listBaselinesByProduct(selectedProduct.value.product_id),
    ]);
    aggRequirements.value = reqResp.requirements || [];
    aggMilestones.value = msResp.milestones || [];
    aggBaselines.value = blResp.baselines || [];
  } catch (err) {
    console.error("Failed to load product aggregations:", err);
  } finally {
    loadingAgg.value = false;
  }
};

const switchAggTab = (tab) => {
  aggTab.value = tab;
  aggSearch.value = "";
};

const handleCreateProduct = async () => {
  try {
    const tags = newProduct.value.tagsInput
      ? newProduct.value.tagsInput.split(",").map(t => t.trim()).filter(Boolean)
      : [];

    await productApi.createProduct({
      name: newProduct.value.name.trim(),
      description: newProduct.value.description,
      version: newProduct.value.version,
      roadmap: newProduct.value.roadmap,
      tags,
    });

    showCreateModal.value = false;
    newProduct.value = { name: "", description: "", version: "", roadmap: "", tagsInput: "" };
    await loadProducts();
  } catch (err) {
    console.error("Failed to create product:", err);
    alert("创建产品失败: " + err.message);
  }
};

const handleUpdateProduct = async () => {
  try {
    const tags = editProduct.value.tagsInput
      ? editProduct.value.tagsInput.split(",").map(t => t.trim()).filter(Boolean)
      : [];

    const updated = await productApi.updateProduct(selectedProduct.value.product_id, {
      name: editProduct.value.name.trim(),
      description: editProduct.value.description,
      version: editProduct.value.version,
      roadmap: editProduct.value.roadmap,
      tags,
    });

    selectedProduct.value = updated;
    showEditModal.value = false;
    await loadProducts();
  } catch (err) {
    console.error("Failed to update product:", err);
    alert("更新产品失败: " + err.message);
  }
};

const handleDeleteProduct = async () => {
  if (!confirm("确定要归档此产品吗？归档后产品将不再显示在列表中。")) return;

  try {
    await productApi.deleteProduct(selectedProduct.value.product_id);
    selectedProduct.value = null;
    await loadProducts();
  } catch (err) {
    console.error("Failed to delete product:", err);
    alert("归档产品失败: " + err.message);
  }
};

const handleCreateProject = async () => {
  try {
    await productApi.createProjectUnderProduct(selectedProduct.value.product_id, {
      name: newProject.value.name.trim(),
      description: newProject.value.description,
    });

    showCreateProjectModal.value = false;
    newProject.value = { name: "", description: "" };
    await loadProductDetails();
  } catch (err) {
    console.error("Failed to create project:", err);
    alert("创建项目失败: " + err.message);
  }
};

const goToProject = (project) => {
  // 兼容现有项目工作流：写入 lastProjectId，跳转到需求页
  localStorage.setItem("lastProjectId", project.project_id);
  router.push({ name: "main-requirements" });
};

// Watch for edit modal open
watch(showEditModal, (val) => {
  if (val && selectedProduct.value) {
    editProduct.value = {
      name: selectedProduct.value.name,
      description: selectedProduct.value.description || "",
      version: selectedProduct.value.version || "",
      roadmap: selectedProduct.value.roadmap || "",
      tagsInput: (selectedProduct.value.tags || []).join(", "),
    };
  }
});

watch(viewMode, (val) => {
  localStorage.setItem("main-products:viewMode", val);
});

onMounted(() => {
  loadProducts();
});
</script>

<style scoped>
.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  padding: 1rem 0;
}

.view-toggle {
  display: inline-flex;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: white;
}

.toggle-btn {
  border: none;
  background: transparent;
  padding: 0.45rem 0.65rem;
  font-size: 0.8125rem;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  border-right: 1px solid var(--border-color, #e5e7eb);
  white-space: nowrap;
}

.toggle-btn:last-child {
  border-right: none;
}

.toggle-btn:hover {
  background: var(--surface-secondary, #f9fafb);
  color: var(--text-primary, #1f2937);
}

.toggle-btn.active {
  background: rgba(196, 105, 47, 0.12);
  color: var(--text-primary, #1f2937);
}

.product-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 0;
}

.product-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  background: white;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
}

.product-row:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.row-main {
  min-width: 0;
  flex: 1;
}

.row-top {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
}

.row-title {
  color: var(--text-primary, #1f2937);
  font-size: 0.95rem;
  line-height: 1.2;
}

.row-desc {
  margin-top: 0.35rem;
  color: var(--text-secondary, #6b7280);
  font-size: 0.85rem;
  line-height: 1.45;
}

.row-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 0.55rem;
  font-size: 0.75rem;
  color: var(--text-muted, #9ca3af);
}

.row-side {
  flex: 0 0 auto;
  max-width: 40%;
}

.row-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: flex-end;
}

.product-table {
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: white;
  margin-top: 1rem;
}

.product-table .table-header,
.product-table .table-row {
  display: grid;
  grid-template-columns: 2fr 0.75fr 0.75fr 1fr;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem 1rem;
}

.product-table .table-header {
  background: var(--surface-secondary, #f9fafb);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.product-table .table-row {
  font-size: 0.875rem;
  color: var(--text-primary, #1f2937);
  border-bottom: 1px solid var(--border-color, #f3f4f6);
  cursor: pointer;
}

.product-table .table-row:hover {
  background: #fbf7f4;
}

.product-table .table-row:last-child {
  border-bottom: none;
}

.agg-table {
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: white;
}

.agg-table .table-header,
.agg-table .table-row {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr 1fr;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem 1rem;
}

.agg-table .table-header {
  background: var(--surface-secondary, #f9fafb);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.agg-table .table-row {
  font-size: 0.875rem;
  color: var(--text-primary, #1f2937);
  border-bottom: 1px solid var(--border-color, #f3f4f6);
}

.agg-table .table-row:last-child {
  border-bottom: none;
}

.agg-table .cell-main {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-card {
  background: var(--surface-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
}

.product-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.product-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.product-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
  margin: 0;
}

.product-desc {
  font-size: 0.875rem;
  color: var(--text-secondary, #6b7280);
  margin: 0 0 0.75rem 0;
  line-height: 1.4;
}

.product-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  font-size: 0.75rem;
  color: var(--text-muted, #9ca3af);
}

.meta-item {
  display: flex;
  gap: 0.25rem;
}

.meta-label {
  color: var(--text-secondary, #6b7280);
}

.product-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.tag {
  background: var(--surface-secondary, #f3f4f6);
  color: var(--text-secondary, #6b7280);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.status-pill {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-pill.active {
  background: #d1fae5;
  color: #065f46;
}

.status-pill.archived {
  background: #f3f4f6;
  color: #6b7280;
}

.back-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}

.back-btn:hover {
  color: var(--text-primary, #1f2937);
}

.product-info {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.info-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}

.info-label {
  min-width: 80px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  font-size: 0.875rem;
}

.stats-section {
  padding: 1rem 0;
}

.agg-tabs {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.agg-tabs .tab {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 999px;
  background: white;
  color: var(--text-secondary, #6b7280);
  font-size: 0.875rem;
  cursor: pointer;
}

.agg-tabs .tab.active {
  border-color: var(--primary-color, #c4692f);
  color: var(--text-primary, #1f2937);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
}

.agg-panel {
  margin-top: 0.75rem;
}

.mini-search {
  margin-bottom: 0.5rem;
}

.subsection-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  margin: 0 0 1rem 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.stat-item {
  text-align: center;
  padding: 0.75rem;
  background: var(--surface-secondary, #f9fafb);
  border-radius: 8px;
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary, #1f2937);
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  margin-top: 0.25rem;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.ghost-small.danger {
  color: #dc2626;
}

.ghost-small.danger:hover {
  background: #fef2f2;
}

.cell-desc {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  margin-top: 0.25rem;
}

.action-btn.small {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
}

.loading-state,
.empty-state {
  padding: 3rem;
  text-align: center;
  color: var(--text-secondary, #6b7280);
}

.empty-state button {
  margin-top: 1rem;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content h3 {
  margin: 0 0 1.5rem 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  margin-bottom: 0.5rem;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--primary-color, #c4692f);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.action-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.2s;
}

.action-btn.brown {
  background: var(--primary-color, #c4692f);
  color: white;
}

.action-btn.brown:hover {
  background: #b35d28;
}

.action-btn.brown:disabled {
  background: #d1d5db;
  cursor: not-allowed;
}

.action-btn.white {
  background: white;
  border-color: var(--border-color, #e5e7eb);
  color: var(--text-primary, #1f2937);
}

.action-btn.white:hover {
  background: var(--surface-secondary, #f9fafb);
}

.search-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
  min-width: 200px;
}

@media (max-width: 640px) {
  .header-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .search-input {
    min-width: 0;
    width: 100%;
  }

  .view-toggle {
    width: 100%;
    justify-content: space-between;
  }

  .toggle-btn {
    flex: 1;
    text-align: center;
  }

  .product-table .table-header,
  .product-table .table-row {
    grid-template-columns: 2fr 1fr 1fr;
  }

  .product-table .table-header span:nth-child(4),
  .product-table .table-row span:nth-child(4) {
    display: none;
  }

  .row-side {
    display: none;
  }
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-color, #c4692f);
}
</style>
