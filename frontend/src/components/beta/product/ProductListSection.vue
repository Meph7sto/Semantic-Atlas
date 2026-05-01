<template>
  <section class="grid" data-animate style="--delay: 0.12s">
    <div class="card wide sa-card">
      <div class="card-header no-border">
        <div>
          <p class="card-kicker">Products</p>
          <h2 class="section-title">产品列表</h2>
        </div>
        <div class="header-actions">
          <input
            type="text"
            :value="searchQuery"
            @input="$emit('update:searchQuery', $event.target.value)"
            placeholder="搜索产品..."
            class="search-input sa-input"
          />
          <div class="view-toggle" role="tablist" aria-label="产品视图切换">
            <button
              type="button"
              class="toggle-btn"
              :class="{ active: viewMode === 'grid' }"
              role="tab"
              :aria-selected="viewMode === 'grid'"
              @click="$emit('update:viewMode', 'grid')"
            >块视图</button>
            <button
              type="button"
              class="toggle-btn"
              :class="{ active: viewMode === 'list' }"
              role="tab"
              :aria-selected="viewMode === 'list'"
              @click="$emit('update:viewMode', 'list')"
            >条视图</button>
            <button
              type="button"
              class="toggle-btn"
              :class="{ active: viewMode === 'table' }"
              role="tab"
              :aria-selected="viewMode === 'table'"
              @click="$emit('update:viewMode', 'table')"
            >表格</button>
          </div>
        </div>
      </div>

      <div v-if="loading" class="loading-state"><span>加载中...</span></div>

      <div v-else-if="products.length === 0" class="empty-state">
        <p>暂无产品，点击"新建产品"创建第一个产品</p>
      </div>

      <div v-else>
        <!-- Grid view -->
        <div v-if="viewMode === 'grid'" class="product-grid">
          <div
            v-for="product in products"
            :key="product.product_id"
            class="product-card"
            @click="$emit('select', product)"
          >
            <div class="product-card-header">
              <h3 class="product-name">{{ product.name }}</h3>
              <span :class="['status-pill', product.status]">
                {{ product.status === 'active' ? '活跃' : '已归档' }}
              </span>
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
            v-for="product in products"
            :key="product.product_id"
            class="product-row"
            @click="$emit('select', product)"
          >
            <div class="row-main">
              <div class="row-top">
                <strong class="row-title">{{ product.name }}</strong>
                <span :class="['status-pill', product.status]">
                  {{ product.status === 'active' ? '活跃' : '已归档' }}
                </span>
              </div>
              <div class="row-desc">{{ product.description || '暂无描述' }}</div>
              <div class="row-meta">
                <span v-if="product.version" class="meta-item">
                  <span class="meta-label">版本:</span> {{ product.version }}
                </span>
                <span class="meta-item">
                  <span class="meta-label">创建:</span> {{ formatDate(product.created_at) }}
                </span>
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
            v-for="product in products"
            :key="product.product_id"
            class="table-row"
            @click="$emit('select', product)"
            title="点击查看详情"
          >
            <span class="cell-main">
              <strong>{{ product.name }}</strong>
              <span class="cell-desc">{{ product.description || '暂无描述' }}</span>
            </span>
            <span>
              <span :class="['status-pill', product.status]">
                {{ product.status === 'active' ? '活跃' : '已归档' }}
              </span>
            </span>
            <span>{{ product.version || '-' }}</span>
            <span>{{ formatDate(product.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  products: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  viewMode: { type: String, default: 'grid' },
  searchQuery: { type: String, default: '' },
})

defineEmits(['update:searchQuery', 'update:viewMode', 'select'])

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
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

.toggle-btn:first-child { border-top-left-radius: 9px; border-bottom-left-radius: 9px; }
.toggle-btn:last-child { border-top-right-radius: 9px; border-bottom-right-radius: 9px; border-right: none; }
.toggle-btn:hover { background: var(--surface-secondary, #f9fafb); color: var(--text-primary, #1f2937); }
.toggle-btn.active { background: rgba(196, 105, 47, 0.12); color: var(--text-primary, #1f2937); }

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

.product-row:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); transform: translateY(-1px); }

.row-main { min-width: 0; flex: 1; }
.row-top { display: flex; justify-content: space-between; gap: 0.75rem; align-items: flex-start; }
.row-title { color: var(--text-primary, #1f2937); font-size: 0.95rem; line-height: 1.2; }
.row-desc { margin-top: 0.35rem; color: var(--text-secondary, #6b7280); font-size: 0.85rem; line-height: 1.45; }
.row-meta { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 0.55rem; font-size: 0.75rem; color: var(--text-muted, #9ca3af); }
.row-side { flex: 0 0 auto; max-width: 40%; }
.row-tags { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: flex-end; }

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

.product-table .table-row:hover { background: #fbf7f4; }
.product-table .table-row:last-child { border-bottom: none; }

.product-card {
  background: var(--surface-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
}

.product-card:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); transform: translateY(-2px); }

.product-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.product-name { font-size: 1.1rem; font-weight: 600; color: var(--text-primary, #1f2937); margin: 0; }
.product-desc { font-size: 0.875rem; color: var(--text-secondary, #6b7280); margin: 0 0 0.75rem 0; line-height: 1.4; }
.product-meta { display: flex; flex-wrap: wrap; gap: 1rem; font-size: 0.75rem; color: var(--text-muted, #9ca3af); }
.meta-item { display: flex; gap: 0.25rem; }
.meta-label { color: var(--text-secondary, #6b7280); }
.product-tags { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }

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

.status-pill.active { background: #d1fae5; color: #065f46; }
.status-pill.archived { background: #f3f4f6; color: #6b7280; }

.header-actions { display: flex; gap: 0.5rem; align-items: center; }

.search-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
  min-width: 200px;
}

.search-input:focus { outline: none; border-color: var(--primary-color, #c4692f); }

.loading-state,
.empty-state {
  padding: 3rem;
  text-align: center;
  color: var(--text-secondary, #6b7280);
}

.cell-desc { display: block; font-size: 0.75rem; color: var(--text-secondary, #6b7280); margin-top: 0.25rem; }

@media (max-width: 640px) {
  .header-actions { flex-wrap: wrap; justify-content: flex-end; }
  .search-input { min-width: 0; width: 100%; }
  .view-toggle { width: 100%; justify-content: space-between; }
  .toggle-btn { flex: 1; text-align: center; }
  .product-table .table-header,
  .product-table .table-row { grid-template-columns: 2fr 1fr 1fr; }
  .product-table .table-header span:nth-child(4),
  .product-table .table-row span:nth-child(4) { display: none; }
  .row-side { display: none; }
}
</style>
