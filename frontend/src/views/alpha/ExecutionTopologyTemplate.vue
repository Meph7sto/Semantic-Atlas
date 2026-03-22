<script setup>
import TopologyStructureViewer from '@/components/alpha/TopologyStructureViewer.vue'
import ExecutionTopologyCanvasPanel from '@/components/alpha/execution-topology/ExecutionTopologyCanvasPanel.vue'
import ExecutionTopologyContainerFormModal from '@/components/alpha/execution-topology/ExecutionTopologyContainerFormModal.vue'
import ExecutionTopologyEdgeFormModal from '@/components/alpha/execution-topology/ExecutionTopologyEdgeFormModal.vue'
import ExecutionTopologyExecuteModal from '@/components/alpha/execution-topology/ExecutionTopologyExecuteModal.vue'
import ExecutionTopologyGraphFormModal from '@/components/alpha/execution-topology/ExecutionTopologyGraphFormModal.vue'
import ExecutionTopologyNodeFormModal from '@/components/alpha/execution-topology/ExecutionTopologyNodeFormModal.vue'
import ExecutionTopologyRightPanel from '@/components/alpha/execution-topology/ExecutionTopologyRightPanel.vue'
import ExecutionTopologySidebar from '@/components/alpha/execution-topology/ExecutionTopologySidebar.vue'
import { useExecutionTopologyTemplate } from '@/composables/useExecutionTopologyTemplate'

const {
  projects,
  selectedProjectId,
  graphs,
  selectedGraphId,
  graphDetail,
  selectedObject,
  loading,
  error,
  showNewGraphDialog,
  showNewContainerDialog,
  showNewNodeDialog,
  showNewEdgeDialog,
  showStructureViewer,
  showExecuteDialog,
  graphFormErrors,
  containerFormErrors,
  nodeFormErrors,
  edgeFormErrors,
  newGraphForm,
  newContainerForm,
  newNodeForm,
  newEdgeForm,
  structureData,
  structureLoading,
  activeRightTab,
  validationLoading,
  validationResult,
  executionLoading,
  executionResult,
  executionError,
  executeForm,
  nodeTypeOptions,
  roleTypeOptions,
  edgeTypeOptions,
  agentTypeOptions,
  currentGraph,
  selectedCanvasId,
  selectedContainerId,
  selectedInspectorObject,
  nodesByContainer,
  graphHints,
  validationSummary,
  validationItems,
  executionStatusClass,
  updateGraphForm,
  updateContainerForm,
  updateNodeForm,
  updateEdgeForm,
  updateExecuteForm,
  openNewGraphDialog,
  closeNewGraphDialog,
  openNewContainerDialog,
  closeNewContainerDialog,
  openNewNodeDialog,
  closeNewNodeDialog,
  openNewEdgeDialog,
  closeNewEdgeDialog,
  closeExecuteDialog,
  setActiveRightTab,
  selectObject,
  handleProjectChange,
  handleSelectGraph,
  handleCreateGraph,
  handleCreateContainer,
  handleCreateNode,
  handleCreateEdge,
  handleAssignNodeContainer,
  handleDeleteContainer,
  handleDeleteNode,
  handleDeleteEdge,
  handleDeleteGraph,
  handleUpdateObject,
  handleSelectGraphObject,
  handleRefresh,
  handleCanvasLayoutChange,
  handleViewStructure,
  handleCloseStructureViewer,
  handleValidateTopology,
  handleSelectValidationItem,
  handleOpenExecuteDialog,
  handleExecuteGraph,
  handleUpdateNodeContent,
  handleExportTemplate,
  handleImportTemplate
} = useExecutionTopologyTemplate()
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-100">
    <div v-if="error" class="px-4 py-2 bg-red-50 border-b border-red-200">
      <p class="text-sm text-red-600">{{ error }}</p>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <ExecutionTopologySidebar
        :projects="projects"
        :selected-project-id="selectedProjectId"
        :graphs="graphs"
        :selected-graph-id="selectedGraphId"
        :graph-detail="graphDetail"
        :selected-object="selectedObject"
        :nodes-by-container="nodesByContainer"
        @project-change="handleProjectChange"
        @create-graph="openNewGraphDialog"
        @select-graph="handleSelectGraph"
        @delete-graph="handleDeleteGraph"
        @create-container="openNewContainerDialog"
        @select-object="selectObject($event.type, $event.id)"
        @delete-container="handleDeleteContainer"
        @create-node="openNewNodeDialog"
        @assign-node-container="handleAssignNodeContainer"
        @delete-node="handleDeleteNode"
        @create-edge="openNewEdgeDialog"
        @delete-edge="handleDeleteEdge"
        @export-template="handleExportTemplate"
        @import-template="handleImportTemplate"
      />

      <ExecutionTopologyCanvasPanel
        :selected-graph-id="selectedGraphId"
        :current-graph="currentGraph"
        :loading="loading"
        :graph-hints="graphHints"
        :validation-summary="validationSummary"
        :graph-detail="graphDetail"
        :selected-canvas-id="selectedCanvasId"
        :selected-container-id="selectedContainerId"
        :structure-loading="structureLoading"
        :validation-loading="validationLoading"
        @select-graph-object="handleSelectGraphObject"
        @validate-topology="handleValidateTopology"
        @open-execute-dialog="handleOpenExecuteDialog"
        @view-structure="handleViewStructure"
        @refresh="handleRefresh"
        @select-object="selectObject($event.type, $event.id)"
        @layout-change="handleCanvasLayoutChange"
      />

      <ExecutionTopologyRightPanel
        v-if="selectedGraphId"
        :active-tab="activeRightTab"
        :inspector-object="selectedInspectorObject"
        :object-type="selectedObject.type"
        :all-nodes="graphDetail.nodes"
        :validation-loading="validationLoading"
        :validation-result="validationResult"
        :validation-items="validationItems"
        :execution-error="executionError"
        :execution-result="executionResult"
        :execution-status-class="executionStatusClass"
        @update:active-tab="setActiveRightTab"
        @update-object="handleUpdateObject"
        @validate-topology="handleValidateTopology"
        @select-validation-item="handleSelectValidationItem"
        @open-execute-dialog="handleOpenExecuteDialog"
        @update-node-content="handleUpdateNodeContent"
      />
    </div>

    <ExecutionTopologyGraphFormModal
      v-if="showNewGraphDialog"
      :form="newGraphForm"
      :errors="graphFormErrors"
      :submit-disabled="loading || !selectedProjectId"
      :agent-type-options="agentTypeOptions"
      @update:form="updateGraphForm"
      @close="closeNewGraphDialog"
      @submit="handleCreateGraph"
    />

    <ExecutionTopologyContainerFormModal
      v-if="showNewContainerDialog"
      :form="newContainerForm"
      :errors="containerFormErrors"
      :role-type-options="roleTypeOptions"
      :submit-disabled="loading"
      @update:form="updateContainerForm"
      @close="closeNewContainerDialog"
      @submit="handleCreateContainer"
    />

    <ExecutionTopologyNodeFormModal
      v-if="showNewNodeDialog"
      :form="newNodeForm"
      :errors="nodeFormErrors"
      :containers="graphDetail.containers"
      :node-type-options="nodeTypeOptions"
      :submit-disabled="loading"
      @update:form="updateNodeForm"
      @close="closeNewNodeDialog"
      @submit="handleCreateNode"
    />

    <ExecutionTopologyEdgeFormModal
      v-if="showNewEdgeDialog"
      :form="newEdgeForm"
      :errors="edgeFormErrors"
      :nodes="graphDetail.nodes"
      :edge-type-options="edgeTypeOptions"
      :submit-disabled="loading"
      @update:form="updateEdgeForm"
      @close="closeNewEdgeDialog"
      @submit="handleCreateEdge"
    />

    <ExecutionTopologyExecuteModal
      v-if="showExecuteDialog"
      :form="executeForm"
      :execution-error="executionError"
      :execution-result="executionResult"
      :execution-status-class="executionStatusClass"
      :execution-loading="executionLoading"
      @update:form="updateExecuteForm"
      @close="closeExecuteDialog"
      @submit="handleExecuteGraph"
    />

    <TopologyStructureViewer
      v-if="showStructureViewer"
      :structure="structureData"
      :loading="structureLoading"
      @close="handleCloseStructureViewer"
    />
  </div>
</template>
