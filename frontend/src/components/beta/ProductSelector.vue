<template>
  <div class="product-selector">
    <div class="selector-trigger" @click="isOpen = !isOpen">
      <div class="selected-product" v-if="selectedProduct">
        <span class="product-icon">[ ]</span>
        <span class="product-name">{{ selectedProduct.name }}</span>
      </div>
      <div class="placeholder" v-else>
        <span class="product-icon">[ ]</span>
        <span>{{ placeholder }}</span>
      </div>
      <svg
        class="chevron"
        :class="{ rotated: isOpen }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </div>

    <div v-if="isOpen" class="dropdown" @click.stop>
      <div class="dropdown-header">
        <input
          type="text"
          v-model="searchQuery"
          placeholder="搜索产品..."
          class="search-input sa-input"
          ref="searchInput"
        />
      </div>

      <div class="dropdown-content">
        <div v-if="loading" class="loading-state">加载中...</div>

        <div v-else-if="filteredProducts.length === 0" class="empty-state">
          {{ searchQuery ? '未找到匹配产品' : '暂无产品' }}
        </div>

        <div v-else class="product-list">
          <div
            v-if="allowClear"
            class="product-item clear-item"
            @click="handleSelect(null)"
          >
            <span class="product-icon">x</span>
            <span>不选择产品</span>
          </div>

          <div
            v-for="product in filteredProducts"
            :key="product.product_id"
            class="product-item"
            :class="{ active: selectedProduct?.product_id === product.product_id }"
            @click="handleSelect(product)"
          >
            <span class="product-icon">[ ]</span>
            <div class="product-info">
              <span class="product-name">{{ product.name }}</span>
              <span class="product-meta" v-if="product.version">v{{ product.version }}</span>
            </div>
            <span v-if="selectedProduct?.product_id === product.product_id" class="check-icon">✓</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Backdrop to close dropdown -->
    <div v-if="isOpen" class="backdrop" @click="isOpen = false"></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { productApi } from "@/api/product";


const props = defineProps({
  modelValue: {
    type: Object,
    default: null,
  },
  placeholder: {
    type: String,
    default: "选择产品",
  },
  allowClear: {
    type: Boolean,
    default: true,
  },
  autoLoad: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(["update:modelValue", "change"]);

const isOpen = ref(false);
const loading = ref(false);
const products = ref([]);
const searchQuery = ref("");
const searchInput = ref(null);

const selectedProduct = computed(() => props.modelValue);

const filteredProducts = computed(() => {
  if (!searchQuery.value.trim()) return products.value;
  const query = searchQuery.value.toLowerCase();
  return products.value.filter(p =>
    p.name.toLowerCase().includes(query) ||
    (p.description && p.description.toLowerCase().includes(query))
  );
});

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

const handleSelect = (product) => {
  emit("update:modelValue", product);
  emit("change", product);
  isOpen.value = false;
  searchQuery.value = "";
};

// Focus search input when dropdown opens
watch(isOpen, (val) => {
  if (val) {
    nextTick(() => {
      searchInput.value?.focus();
    });
  }
});

onMounted(() => {
  if (props.autoLoad) {
    loadProducts();
  }
});

// Expose method to reload products
defineExpose({
  reload: loadProducts,
});
</script>

<style scoped>
.product-selector {
  position: relative;
  display: inline-block;
  min-width: 200px;
}

.selector-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  background: white;
  cursor: pointer;
  gap: 0.5rem;
  transition: border-color 0.2s;
}

.selector-trigger:hover {
  border-color: var(--primary-color, #c4692f);
}

.selected-product,
.placeholder {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.placeholder {
  color: var(--text-muted, #9ca3af);
}

.product-icon {
  font-size: 1rem;
}

.product-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary, #1f2937);
}

.chevron {
  width: 16px;
  height: 16px;
  color: var(--text-secondary, #6b7280);
  transition: transform 0.2s;
}

.chevron.rotated {
  transform: rotate(180deg);
}

.dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow: hidden;
}

.dropdown-header {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.search-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 4px;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-color, #c4692f);
}

.dropdown-content {
  max-height: 240px;
  overflow-y: auto;
}

.loading-state,
.empty-state {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary, #6b7280);
  font-size: 0.875rem;
}

.product-list {
  padding: 0.25rem 0;
}

.product-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  cursor: pointer;
  transition: background-color 0.15s;
}

.product-item:hover {
  background: var(--surface-secondary, #f9fafb);
}

.product-item.active {
  background: var(--primary-light, #fef3c7);
}

.product-item.clear-item {
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  color: var(--text-secondary, #6b7280);
}

.product-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.product-meta {
  font-size: 0.75rem;
  color: var(--text-muted, #9ca3af);
}

.check-icon {
  color: var(--primary-color, #c4692f);
  font-weight: 600;
}

.backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 99;
}
</style>

