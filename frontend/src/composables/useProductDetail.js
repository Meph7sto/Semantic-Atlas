import { ref, computed, watch } from 'vue'
import { productApi } from '@/api/product'

export function useProductDetail(selectedProduct) {
  const overview = ref(null)
  const aggTab = ref('requirements')
  const loadingAgg = ref(false)
  const aggRequirements = ref([])
  const aggMilestones = ref([])
  const aggBaselines = ref([])
  const aggSearch = ref('')

  const filteredAggRequirements = computed(() => {
    const list = aggRequirements.value || []
    const q = aggSearch.value.trim().toLowerCase()
    if (!q) return list
    return list.filter(r =>
      String(r.title || '').toLowerCase().includes(q) ||
      String(r.project_name || '').toLowerCase().includes(q)
    )
  })

  const loadAggregations = async () => {
    if (!selectedProduct.value) return
    loadingAgg.value = true
    try {
      const [reqResp, msResp, blResp] = await Promise.all([
        productApi.listRequirementsByProduct(selectedProduct.value.product_id),
        productApi.listMilestonesByProduct(selectedProduct.value.product_id),
        productApi.listBaselinesByProduct(selectedProduct.value.product_id),
      ])
      aggRequirements.value = reqResp.requirements || []
      aggMilestones.value = msResp.milestones || []
      aggBaselines.value = blResp.baselines || []
    } catch (err) {
      console.error('Failed to load product aggregations:', err)
    } finally {
      loadingAgg.value = false
    }
  }

  const loadProductDetails = async () => {
    if (!selectedProduct.value) return
    try {
      const overviewResp = await productApi.getProductOverview(selectedProduct.value.product_id)
      overview.value = overviewResp
      await loadAggregations()
    } catch (err) {
      console.error('Failed to load product details:', err)
    }
  }

  const switchAggTab = (tab) => {
    aggTab.value = tab
    aggSearch.value = ''
  }

  watch(selectedProduct, (val) => {
    if (val) {
      overview.value = null
      aggRequirements.value = []
      aggMilestones.value = []
      aggBaselines.value = []
      loadProductDetails()
    }
  })

  return {
    overview,
    aggTab,
    loadingAgg,
    aggRequirements,
    aggMilestones,
    aggBaselines,
    aggSearch,
    filteredAggRequirements,
    loadProductDetails,
    switchAggTab,
  }
}

