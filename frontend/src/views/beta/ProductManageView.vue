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
            <button type="button" class="action-btn brown sa-button sa-button--primary" @click="showCreateModal = true">新建产品</button>
            <span class="nav-text">通知 · {{ notificationCount }}</span>
          </div>
        </section>

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

        <section v-else class="grid split-layout" data-animate style="--delay: 0.12s">
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
        </section>

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
import Sidebar from '../../components/beta/Sidebar.vue'
import ProductListSection from '../../components/beta/product/ProductListSection.vue'
import ProductDetailPanel from '../../components/beta/product/ProductDetailPanel.vue'
import ProjectListPanel from '../../components/beta/product/ProjectListPanel.vue'
import ProductFormModal from '../../components/beta/product/ProductFormModal.vue'
import ProjectFormModal from '../../components/beta/product/ProjectFormModal.vue'
import { useProducts } from '../../composables/useProducts'
import { useProductDetail } from '../../composables/useProductDetail'
import { useProjects } from '../../composables/useProjects'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('products')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

// Composables
const {
  loading, products, searchQuery, viewMode, selectedProduct,
  filteredProducts, showCreateModal, showEditModal,
  selectProduct, handleCreateProduct, handleUpdateProduct, handleDeleteProduct,
} = useProducts()

const {
  overview, aggTab, loadingAgg, aggRequirements, aggMilestones, aggBaselines,
  aggSearch, filteredAggRequirements, loadProductDetails, switchAggTab,
} = useProductDetail(selectedProduct)

const {
  projects, loadingProjects, editingProject,
  showCreateProjectModal, showEditProjectModal,
  openEditProject, handleCreateProject, handleUpdateProject, handleDeleteProject, goToProject,
} = useProjects(selectedProduct, loadProductDetails)
</script>
