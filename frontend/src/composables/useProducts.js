import { ref, computed, watch, onMounted } from 'vue'
import { productApi } from '@/api/product'

export function useProducts() {
  const loading = ref(false)
  const products = ref([])
  const searchQuery = ref('')
  const viewMode = ref(localStorage.getItem('beta-products:viewMode') || 'grid')
  const selectedProduct = ref(null)

  const showCreateModal = ref(false)
  const showEditModal = ref(false)

  const filteredProducts = computed(() => {
    if (!searchQuery.value.trim()) return products.value
    const query = searchQuery.value.toLowerCase()
    return products.value.filter(p =>
      p.name.toLowerCase().includes(query) ||
      (p.description && p.description.toLowerCase().includes(query))
    )
  })

  const loadProducts = async () => {
    loading.value = true
    try {
      const resp = await productApi.listProducts()
      products.value = resp.products || []
    } catch (err) {
      console.error('Failed to load products:', err)
    } finally {
      loading.value = false
    }
  }

  const selectProduct = (product) => {
    selectedProduct.value = product
  }

  const handleCreateProduct = async (formData) => {
    try {
      const tags = formData.tagsInput
        ? formData.tagsInput.split(',').map(t => t.trim()).filter(Boolean)
        : []
      await productApi.createProduct({
        name: formData.name.trim(),
        description: formData.description,
        version: formData.version,
        roadmap: formData.roadmap,
        tags,
      })
      showCreateModal.value = false
      await loadProducts()
    } catch (err) {
      console.error('Failed to create product:', err)
      alert('创建产品失败: ' + err.message)
    }
  }

  const handleUpdateProduct = async (formData) => {
    try {
      const tags = formData.tagsInput
        ? formData.tagsInput.split(',').map(t => t.trim()).filter(Boolean)
        : []
      const updated = await productApi.updateProduct(selectedProduct.value.product_id, {
        name: formData.name.trim(),
        description: formData.description,
        version: formData.version,
        roadmap: formData.roadmap,
        tags,
      })
      selectedProduct.value = updated
      showEditModal.value = false
      await loadProducts()
    } catch (err) {
      console.error('Failed to update product:', err)
      alert('更新产品失败: ' + err.message)
    }
  }

  const handleDeleteProduct = async () => {
    if (!confirm('确定要归档此产品吗？归档后产品将不再显示在列表中。')) return
    try {
      await productApi.deleteProduct(selectedProduct.value.product_id)
      selectedProduct.value = null
      await loadProducts()
    } catch (err) {
      console.error('Failed to delete product:', err)
      alert('归档产品失败: ' + err.message)
    }
  }

  watch(viewMode, (val) => {
    localStorage.setItem('beta-products:viewMode', val)
  })

  onMounted(() => loadProducts())

  return {
    loading,
    products,
    searchQuery,
    viewMode,
    selectedProduct,
    filteredProducts,
    showCreateModal,
    showEditModal,
    loadProducts,
    selectProduct,
    handleCreateProduct,
    handleUpdateProduct,
    handleDeleteProduct,
  }
}

