<template>
  <div class="w-full">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div class="flex items-center gap-3">
        <h3 class="text-lg font-semibold text-zinc-900">需求管理</h3>
        <div class="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-sm">
          <Briefcase class="w-3.5 h-3.5 text-zinc-500" />
          <span class="text-zinc-500 text-xs">项目:</span>
          <select
            v-model="selectedProjectId"
            class="border-0 bg-transparent text-sm text-zinc-800 focus:outline-none cursor-pointer"
          >
            <option value="">未选择</option>
            <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
              {{ p.name }}
            </option>
          </select>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-xl bg-zinc-800 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-900 transition-colors disabled:opacity-50"
          @click="openAddRequirementModal"
          :disabled="!selectedProjectId"
        >
          <Plus class="w-4 h-4" />
          新增需求
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors disabled:opacity-50"
          @click="refreshData"
          :disabled="isLoading"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
          {{ isLoading ? '加载中' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- Add Requirement Modal -->
    <div v-if="showAddRequirementModal" class="fixed inset-0 bg-black/30 z-50 flex items-center justify-center" @click.self="closeAddRequirementModal">
      <div class="rounded-2xl border border-zinc-200 bg-white shadow-2xl w-[90%] max-w-lg max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between px-6 py-4 border-b border-zinc-200">
          <h3 class="text-base font-semibold text-zinc-900">新增需求</h3>
          <button type="button" class="p-1 text-zinc-400 hover:text-zinc-700 transition-colors" @click="closeAddRequirementModal">
            <X class="w-5 h-5" />
          </button>
        </div>
        <form class="p-6 space-y-4" @submit.prevent="submitNewRequirement">
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">需求标题 <span class="text-red-500">*</span></label>
            <input v-model="newRequirement.title" type="text" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300" placeholder="输入需求标题" required />
          </div>
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">需求描述</label>
            <textarea v-model="newRequirement.description" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 resize-y min-h-[80px]" placeholder="详细描述需求内容..." rows="4"></textarea>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">需求类型 <span class="text-red-500">*</span></label>
              <select v-model="newRequirement.requirement_type" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer" required>
                <option value="top_level">顶层需求</option>
                <option value="low_level">底层需求</option>
                <option value="task">任务</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">层级</label>
              <select v-model="newRequirement.level" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
                <option value="L1">L1 - 业务需求</option>
                <option value="L2">L2 - 利益相关者需求</option>
                <option value="L3">L3 - 系统需求</option>
                <option value="L4">L4 - 底层需求</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">优先级</label>
              <select v-model="newRequirement.priority" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">状态</label>
              <select v-model="newRequirement.status" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
                <option value="draft">草稿</option>
                <option value="under_review">审核中</option>
                <option value="confirmed">已确认</option>
                <option value="in_progress">进行中</option>
                <option value="completed">已完成</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">父需求（可选）</label>
            <select v-model="newRequirement.parent_id" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
              <option value="">无</option>
              <option v-for="req in parentRequirementOptions" :key="req.req_id" :value="req.req_id">
                {{ req.title || req.text || req.statement || req.req_id }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">标签（用逗号分隔）</label>
            <input v-model="newRequirement.tags" type="text" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300" placeholder="例如: 功能, 性能, 安全" />
          </div>
          <div class="flex justify-end gap-3 pt-4 border-t border-zinc-200">
            <button type="button" class="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors" @click="closeAddRequirementModal">取消</button>
            <button type="submit" class="inline-flex items-center gap-1.5 rounded-xl bg-zinc-800 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-900 transition-colors disabled:opacity-50" :disabled="isSubmitting">
              <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
              {{ isSubmitting ? '提交中...' : '确认添加' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Edit Requirement Modal -->
    <div v-if="showEditRequirementModal" class="fixed inset-0 bg-black/30 z-50 flex items-center justify-center" @click.self="closeEditRequirementModal">
      <div class="rounded-2xl border border-zinc-200 bg-white shadow-2xl w-[90%] max-w-lg max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between px-6 py-4 border-b border-zinc-200">
          <h3 class="text-base font-semibold text-zinc-900">编辑需求</h3>
          <button type="button" class="p-1 text-zinc-400 hover:text-zinc-700 transition-colors" @click="closeEditRequirementModal">
            <X class="w-5 h-5" />
          </button>
        </div>
        <form class="p-6 space-y-4" @submit.prevent="submitEditRequirement">
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">需求标题 <span class="text-red-500">*</span></label>
            <input v-model="editRequirement.title" type="text" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300" placeholder="输入需求标题" required />
          </div>
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">需求描述</label>
            <textarea v-model="editRequirement.description" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 resize-y min-h-[80px]" placeholder="详细描述需求内容..." rows="4"></textarea>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">优先级</label>
              <select v-model="editRequirement.priority" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-medium text-zinc-600 mb-1.5">状态</label>
              <select v-model="editRequirement.status" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer">
                <option value="draft">草稿</option>
                <option value="under_review">审核中</option>
                <option value="confirmed">已确认</option>
                <option value="in_progress">进行中</option>
                <option value="completed">已完成</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-zinc-600 mb-1.5">标签（用逗号分隔）</label>
            <input v-model="editRequirement.tags" type="text" class="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300" placeholder="例如: 功能, 性能, 安全" />
          </div>
          <div class="flex justify-end gap-3 pt-4 border-t border-zinc-200">
            <button type="button" class="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors" @click="closeEditRequirementModal">取消</button>
            <button type="submit" class="inline-flex items-center gap-1.5 rounded-xl bg-zinc-800 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-900 transition-colors disabled:opacity-50" :disabled="isEditSubmitting">
              <Loader2 v-if="isEditSubmitting" class="w-4 h-4 animate-spin" />
              {{ isEditSubmitting ? '保存中...' : '保存修改' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Toolbar: Level Filter + View Switcher -->
    <div class="flex items-center justify-between rounded-2xl border border-zinc-200 bg-white px-4 py-2.5 mb-3">
      <!-- Level tabs -->
      <div class="flex gap-1 bg-zinc-100 rounded-xl p-1">
        <button
          v-for="tab in levelTabs"
          :key="tab.key"
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg transition-all"
          :class="activeLevel === tab.key
            ? 'bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900'
            : 'text-zinc-500 hover:text-zinc-700'"
          @click="activeLevel = tab.key"
        >
          {{ tab.label }}
          <span
            class="text-[11px] px-1.5 py-0.5 rounded-full"
            :class="activeLevel === tab.key
              ? 'bg-zinc-800 text-white'
              : 'bg-zinc-200 text-zinc-500'"
          >{{ getCountByLevel(tab.key) }}</span>
        </button>
      </div>

      <!-- View switcher -->
      <div v-if="!props.tableOnly" class="flex gap-1 bg-zinc-100 rounded-xl p-1">
        <button
          v-for="v in viewOptions"
          :key="v.id"
          type="button"
          class="w-8 h-8 flex items-center justify-center rounded-lg transition-all"
          :class="activeView === v.id
            ? 'bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900'
            : 'text-zinc-400 hover:text-zinc-700'"
          :title="v.title"
          @click="activeView = v.id"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-4 h-4" v-html="v.svg"></svg>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="rounded-2xl border border-zinc-200 bg-white overflow-hidden">
      <!-- Loading -->
      <div v-if="isLoading" class="flex flex-col items-center justify-center py-20 text-zinc-400">
        <Loader2 class="w-10 h-10 animate-spin mb-3" />
        <p class="text-sm">正在加载需求数据...</p>
      </div>

      <!-- Empty -->
      <div v-else-if="filteredRequirements.length === 0" class="flex flex-col items-center justify-center py-20 text-zinc-400">
        <FileText class="w-10 h-10 mb-3 opacity-40" />
        <p v-if="!selectedProjectId" class="text-sm">未选择项目</p>
        <p v-else class="text-sm">暂无需求数据</p>
        <p class="text-xs mt-1 text-zinc-300">{{ !selectedProjectId ? '请先选择一个项目' : '当前项目下还没有导入或创建需求' }}</p>
      </div>

      <!-- Tree View -->
      <div v-else-if="activeView === 'tree'" class="relative p-5 min-h-[400px]">
        <RequirementTree
          :tree-data="filteredTreeData"
          @hover="handleNodeHover"
          @click-node="handleNodeClick"
        />
        <div v-if="hoveredNode" class="absolute top-5 right-5 w-60 p-4 rounded-xl border border-zinc-200 bg-white shadow-lg">
          <div class="text-sm font-semibold text-zinc-900 mb-3 pb-2 border-b border-zinc-100">{{ hoveredNode.title || hoveredNode.text }}</div>
          <div class="flex justify-between text-xs mb-1.5">
            <span class="text-zinc-400">类型:</span>
            <span class="text-zinc-700 font-medium">{{ getTypeLabel(hoveredNode.requirement_type) }}</span>
          </div>
          <div class="flex justify-between text-xs mb-1.5">
            <span class="text-zinc-400">状态:</span>
            <span class="text-zinc-700 font-medium">{{ hoveredNode.status || '-' }}</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-zinc-400">优先级:</span>
            <span class="text-zinc-700 font-medium">{{ hoveredNode.priority || '-' }}</span>
          </div>
        </div>
      </div>

      <!-- Table View -->
      <div v-else-if="activeView === 'table'" class="flex flex-col">
        <!-- Table toolbar -->
        <div class="flex items-center justify-between gap-4 px-4 py-2.5 border-b border-zinc-100">
          <div class="relative flex-1 max-w-sm">
            <Search class="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              v-model="tableSearchQuery"
              type="text"
              placeholder="搜索需求名称、层级、状态..."
              class="w-full rounded-xl border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
            />
          </div>
          <div class="relative">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-600 hover:bg-zinc-50 transition-colors"
              @click="showColumnSelector = !showColumnSelector"
            >
              <Filter class="w-3.5 h-3.5" />
              设置展示列
              <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="showColumnSelector ? 'rotate-180' : ''" />
            </button>
            <div v-if="showColumnSelector" class="absolute right-0 top-full mt-1.5 w-48 rounded-xl border border-zinc-200 bg-white shadow-lg z-20 py-1.5">
              <div
                v-for="col in availableTableColumns"
                :key="col.key"
                class="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer hover:bg-zinc-50"
                @click="toggleColumn(col.key)"
              >
                <div class="w-3.5 h-3.5 rounded border flex items-center justify-center" :class="tableVisibleColumns.includes(col.key) ? 'bg-zinc-800 border-zinc-800 text-white' : 'border-zinc-300'">
                  <CheckCircle2 v-if="tableVisibleColumns.includes(col.key)" class="w-2.5 h-2.5" />
                </div>
                <span class="text-zinc-700">{{ col.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Table -->
        <div class="overflow-auto">
          <table class="w-full border-collapse">
            <thead>
              <tr>
                <th
                  v-for="col in availableTableColumns.filter(c => tableVisibleColumns.includes(c.key))"
                  :key="col.key"
                  class="sticky top-0 bg-zinc-50 text-left text-[11px] uppercase tracking-wider text-zinc-500 px-3 py-2.5 border-b border-zinc-200 cursor-pointer select-none"
                  @click="toggleSort(col.key)"
                >
                  <div class="flex items-center gap-1.5">
                    {{ col.label }}
                    <div class="flex flex-col -my-1">
                      <ChevronUp class="w-2.5 h-2.5" :class="tableSortKey === col.key && tableSortOrder === 'asc' ? 'text-zinc-900' : 'text-zinc-300'" />
                      <ChevronDown class="w-2.5 h-2.5" :class="tableSortKey === col.key && tableSortOrder === 'desc' ? 'text-zinc-900' : 'text-zinc-300'" />
                    </div>
                  </div>
                </th>
                <th class="sticky top-0 bg-zinc-50 text-left text-[11px] uppercase tracking-wider text-zinc-500 px-3 py-2.5 border-b border-zinc-200 w-14">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="req in tableRequirements" :key="req.id || req.req_id" class="hover:bg-zinc-50/50 transition-colors">
                <td v-if="tableVisibleColumns.includes('name')" class="px-3 py-2.5 border-b border-zinc-100 text-sm font-semibold text-zinc-900">
                  {{ req.title || req.text || req.statement }}
                </td>
                <td v-if="tableVisibleColumns.includes('type')" class="px-3 py-2.5 border-b border-zinc-100">
                  <span class="text-[10px] px-2 py-0.5 rounded-full border" :class="req.level === 'L4' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-sky-50 text-sky-700 border-sky-200'">
                    {{ req.level === 'L4' ? '底层需求' : '顶层需求' }}
                  </span>
                </td>
                <td v-if="tableVisibleColumns.includes('level')" class="px-3 py-2.5 border-b border-zinc-100">
                  <span class="text-[10px] px-2 py-0.5 rounded-full border" :class="getLevelBadgeClass(req.level || req.category)">
                    {{ req.level || req.category || '-' }}
                  </span>
                </td>
                <td v-if="tableVisibleColumns.includes('status')" class="px-3 py-2.5 border-b border-zinc-100">
                  <select
                    :value="req.status"
                    @change="updateRequirementStatus(req.id || req.req_id, $event.target.value)"
                    class="rounded-lg border border-zinc-200 bg-white px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-zinc-300 cursor-pointer"
                    :class="getStatusColorClass(req.status, 'bg')"
                  >
                    <option v-for="s in requirementStatuses" :key="s.id" :value="s.id">{{ s.name }}</option>
                  </select>
                </td>
                <td v-if="tableVisibleColumns.includes('confidence')" class="px-3 py-2.5 border-b border-zinc-100">
                  <span v-if="req.confidence" class="text-[10px] px-2 py-0.5 rounded-full border" :class="getConfidenceClass(req.confidence)">
                    {{ (req.confidence * 100).toFixed(0) }}%
                  </span>
                  <span v-else class="text-zinc-300 text-xs">-</span>
                </td>
                <td v-if="tableVisibleColumns.includes('evidence')" class="px-3 py-2.5 border-b border-zinc-100">
                  <span class="text-xs text-zinc-500 max-w-[180px] inline-block truncate" :title="req.evidence || req.anchor_span_id">
                    {{ req.evidence || req.anchor_span_id || '-' }}
                  </span>
                </td>
                <td v-if="tableVisibleColumns.includes('rationale')" class="px-3 py-2.5 border-b border-zinc-100">
                  <span class="text-xs text-zinc-500 max-w-[180px] inline-block truncate" :title="req.rationale">
                    {{ req.rationale || '-' }}
                  </span>
                </td>
                <td class="px-3 py-2.5 border-b border-zinc-100">
                  <button
                    type="button"
                    class="w-7 h-7 inline-flex items-center justify-center rounded-lg border border-zinc-200 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 transition-colors"
                    title="编辑需求"
                    @click="openEditRequirementModal(req)"
                  >
                    <Pencil class="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
              <tr v-if="tableRequirements.length === 0">
                <td :colspan="tableVisibleColumns.length + 1" class="text-center py-8 text-zinc-400 text-sm">暂无需求数据</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="px-4 py-2.5 border-t border-zinc-100 text-xs text-zinc-500">
          共 {{ tableRequirements.length }} 条
        </div>
      </div>

      <!-- Card / Kanban View -->
      <div v-else-if="activeView === 'card'" class="flex flex-col">
        <div class="px-4 py-2.5 border-b border-zinc-100 text-xs text-zinc-500">
          共 {{ filteredRequirements.length }} 条需求
        </div>
        <div class="grid grid-cols-3 gap-5 p-5 min-h-[400px]">
          <!-- Backlog -->
          <div class="flex flex-col rounded-2xl border border-zinc-200 bg-zinc-50/80 overflow-hidden min-h-[350px]">
            <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-zinc-200 bg-zinc-100/80">
              <div class="flex items-center gap-2">
                <Circle class="w-4 h-4 text-zinc-400" />
                <h4 class="text-sm font-semibold text-zinc-800">待处理</h4>
              </div>
              <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-600">{{ backlogRequirements.length }}</span>
            </div>
            <draggable
              v-model="backlogRequirements"
              :group="{ name: 'requirements', pull: true, put: true }"
              item-key="id"
              :animation="200"
              class="flex-1 p-3 space-y-2 overflow-y-auto min-h-[200px]"
              ghost-class="opacity-50"
              chosen-class="shadow-lg"
              @change="onDragChange($event, 'backlog')"
            >
              <template #item="{ element }">
                <div class="flex bg-white rounded-xl border border-zinc-200 hover:border-zinc-300 hover:shadow-sm transition-all cursor-grab active:cursor-grabbing" :class="element.level === 'L4' ? 'border-l-[3px] border-l-emerald-400' : 'border-l-[3px] border-l-sky-400'">
                  <div class="flex items-center px-1.5 text-zinc-300 hover:text-zinc-500">
                    <GripVertical class="w-3.5 h-3.5" />
                  </div>
                  <div class="flex-1 p-2.5 min-w-0">
                    <div class="flex gap-1.5 mb-1.5 flex-wrap">
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium" :class="element.level === 'L4' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-sky-50 text-sky-700 border-sky-200'">
                        {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                      </span>
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-semibold" :class="getLevelBadgeClass(element.level)">{{ element.level }}</span>
                    </div>
                    <p class="text-[13px] leading-relaxed text-zinc-800 mb-2 break-words">{{ element.statement || element.text || element.title }}</p>
                    <div class="flex justify-between items-center text-[11px]">
                      <span class="text-zinc-400 font-mono truncate max-w-[60%]">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                      <span v-if="element.confidence" class="px-1.5 py-0.5 rounded-full border font-medium" :class="getConfidenceClass(element.confidence)">{{ (element.confidence * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>
            <div v-if="backlogRequirements.length === 0" class="flex-1 flex items-center justify-center text-xs text-zinc-400 border-2 border-dashed border-zinc-200 m-3 rounded-xl min-h-[80px]">
              拖拽需求到此处
            </div>
          </div>

          <!-- In Progress -->
          <div class="flex flex-col rounded-2xl border border-blue-200 bg-blue-50/30 overflow-hidden min-h-[350px]">
            <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-blue-200 bg-blue-50/60">
              <div class="flex items-center gap-2">
                <Clock class="w-4 h-4 text-blue-500" />
                <h4 class="text-sm font-semibold text-zinc-800">进行中</h4>
              </div>
              <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">{{ inProgressRequirements.length }}</span>
            </div>
            <draggable
              v-model="inProgressRequirements"
              :group="{ name: 'requirements', pull: true, put: true }"
              item-key="id"
              :animation="200"
              class="flex-1 p-3 space-y-2 overflow-y-auto min-h-[200px]"
              ghost-class="opacity-50"
              chosen-class="shadow-lg"
              @change="onDragChange($event, 'in_progress')"
            >
              <template #item="{ element }">
                <div class="flex bg-white rounded-xl border border-zinc-200 hover:border-zinc-300 hover:shadow-sm transition-all cursor-grab active:cursor-grabbing" :class="element.level === 'L4' ? 'border-l-[3px] border-l-emerald-400' : 'border-l-[3px] border-l-sky-400'">
                  <div class="flex items-center px-1.5 text-zinc-300 hover:text-zinc-500">
                    <GripVertical class="w-3.5 h-3.5" />
                  </div>
                  <div class="flex-1 p-2.5 min-w-0">
                    <div class="flex gap-1.5 mb-1.5 flex-wrap">
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium" :class="element.level === 'L4' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-sky-50 text-sky-700 border-sky-200'">
                        {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                      </span>
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-semibold" :class="getLevelBadgeClass(element.level)">{{ element.level }}</span>
                    </div>
                    <p class="text-[13px] leading-relaxed text-zinc-800 mb-2 break-words">{{ element.statement || element.text || element.title }}</p>
                    <div class="flex justify-between items-center text-[11px]">
                      <span class="text-zinc-400 font-mono truncate max-w-[60%]">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                      <span v-if="element.confidence" class="px-1.5 py-0.5 rounded-full border font-medium" :class="getConfidenceClass(element.confidence)">{{ (element.confidence * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>
            <div v-if="inProgressRequirements.length === 0" class="flex-1 flex items-center justify-center text-xs text-zinc-400 border-2 border-dashed border-blue-200 m-3 rounded-xl min-h-[80px]">
              拖拽需求到此处
            </div>
          </div>

          <!-- Completed -->
          <div class="flex flex-col rounded-2xl border border-emerald-200 bg-emerald-50/30 overflow-hidden min-h-[350px]">
            <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-emerald-200 bg-emerald-50/60">
              <div class="flex items-center gap-2">
                <CheckCircle class="w-4 h-4 text-emerald-500" />
                <h4 class="text-sm font-semibold text-zinc-800">已完成</h4>
              </div>
              <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{{ completedRequirements.length }}</span>
            </div>
            <draggable
              v-model="completedRequirements"
              :group="{ name: 'requirements', pull: true, put: true }"
              item-key="id"
              :animation="200"
              class="flex-1 p-3 space-y-2 overflow-y-auto min-h-[200px]"
              ghost-class="opacity-50"
              chosen-class="shadow-lg"
              @change="onDragChange($event, 'completed')"
            >
              <template #item="{ element }">
                <div class="flex bg-white rounded-xl border border-zinc-200 hover:border-zinc-300 hover:shadow-sm transition-all cursor-grab active:cursor-grabbing" :class="element.level === 'L4' ? 'border-l-[3px] border-l-emerald-400' : 'border-l-[3px] border-l-sky-400'">
                  <div class="flex items-center px-1.5 text-zinc-300 hover:text-zinc-500">
                    <GripVertical class="w-3.5 h-3.5" />
                  </div>
                  <div class="flex-1 p-2.5 min-w-0">
                    <div class="flex gap-1.5 mb-1.5 flex-wrap">
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium" :class="element.level === 'L4' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-sky-50 text-sky-700 border-sky-200'">
                        {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                      </span>
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-semibold" :class="getLevelBadgeClass(element.level)">{{ element.level }}</span>
                    </div>
                    <p class="text-[13px] leading-relaxed text-zinc-800 mb-2 break-words">{{ element.statement || element.text || element.title }}</p>
                    <div class="flex justify-between items-center text-[11px]">
                      <span class="text-zinc-400 font-mono truncate max-w-[60%]">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                      <span v-if="element.confidence" class="px-1.5 py-0.5 rounded-full border font-medium" :class="getConfidenceClass(element.confidence)">{{ (element.confidence * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>
            <div v-if="completedRequirements.length === 0" class="flex-1 flex items-center justify-center text-xs text-zinc-400 border-2 border-dashed border-emerald-200 m-3 rounded-xl min-h-[80px]">
              拖拽需求到此处
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import RequirementTree from '../charts/RequirementTree.vue'
import { manageApi } from '@/api/project'
import {
  Loader2, FileText, RefreshCw, Briefcase, Circle, Clock, CheckCircle,
  GripVertical, Search, Filter, ChevronDown, ChevronUp, CheckCircle2,
  Plus, X, Pencil
} from 'lucide-vue-next'

const props = defineProps({
  projectId: {
    type: String,
    default: ''
  },
  tableOnly: {
    type: Boolean,
    default: false
  },
})

// Data
const isLoading = ref(false)
const highLevelRequirements = ref([])
const lowLevelRequirements = ref([])
const requirementTree = ref([])
const selectedProjectId = ref(props.projectId || localStorage.getItem('lastProjectId') || '')
const manageReqIdMap = ref(new Map())
const manageStatusMap = ref(new Map())
const managePriorityMap = ref(new Map())
const projects = ref([])

// View state
const activeLevel = ref('all')
const activeView = ref(props.tableOnly ? 'table' : 'tree')
const hoveredNode = ref(null)

const viewOptions = [
  { id: 'tree', title: '树状视图', svg: '<path d="M12 3v18M3 9l9-6 9 6M3 15l9 6 9-6" />' },
  { id: 'table', title: '表格视图', svg: '<rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="3" y1="15" x2="21" y2="15" /><line x1="9" y1="3" x2="9" y2="21" />' },
  { id: 'card', title: '卡片视图', svg: '<rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />' },
]

// Add requirement modal
const showAddRequirementModal = ref(false)
const isSubmitting = ref(false)
const newRequirement = ref({
  title: '', description: '', requirement_type: 'top_level',
  level: 'L1', priority: 'medium', status: 'draft', parent_id: '', tags: ''
})

// Edit requirement modal
const showEditRequirementModal = ref(false)
const isEditSubmitting = ref(false)
const editRequirementId = ref('')
const editRequirement = ref({
  title: '', description: '', priority: 'medium', status: 'draft', tags: ''
})

// Status management
const requirementStatuses = [
  { id: 'draft', name: '待处理', color: 'zinc' },
  { id: 'under_review', name: '审核中', color: 'amber' },
  { id: 'confirmed', name: '已确认', color: 'sky' },
  { id: 'in_progress', name: '进行中', color: 'blue' },
  { id: 'completed', name: '已完成', color: 'emerald' },
  { id: 'archived', name: '已归档', color: 'slate' },
]
const requirementStatusMap = ref({})
const backlogRequirements = ref([])
const inProgressRequirements = ref([])
const completedRequirements = ref([])

// Table config
const tableSearchQuery = ref('')
const tableVisibleColumns = ref(['name', 'type', 'level', 'status', 'confidence', 'evidence'])
const tableSortKey = ref('name')
const tableSortOrder = ref('asc')
const showColumnSelector = ref(false)

const availableTableColumns = [
  { key: 'name', label: '需求名称' },
  { key: 'type', label: '类型' },
  { key: 'level', label: '层级' },
  { key: 'status', label: '状态' },
  { key: 'confidence', label: '置信度' },
  { key: 'evidence', label: '证据' },
  { key: 'rationale', label: '原因' }
]

const levelTabs = [
  { key: 'all', label: '全部' },
  { key: 'L1', label: 'L1' },
  { key: 'L2', label: 'L2' },
  { key: 'L3', label: 'L3' },
  { key: 'L4', label: 'L4' },
]

// Parent requirement options
const parentRequirementOptions = computed(() => {
  const all = [
    ...highLevelRequirements.value.map(r => ({
      req_id: r.req_id || r.id,
      title: r.text || r.statement || r.title,
      level: normalizeLevel(r.level || r.category)
    })),
    ...lowLevelRequirements.value.map(r => ({
      req_id: r.req_id || r.id,
      title: r.text || r.statement || r.shall_statement,
      level: 'L4'
    }))
  ]
  return all.filter(r => r.req_id)
})

// Filtered requirements
const filteredRequirements = computed(() => {
  let all = [
    ...highLevelRequirements.value.map(r => {
      const id = r.req_id || r.id
      return {
        ...r, id,
        level: normalizeLevel(r.level || r.category),
        statement: r.text || r.statement || r.title || '',
        status: requirementStatusMap.value[id] || r.status || 'draft',
      }
    }),
    ...lowLevelRequirements.value.map(r => {
      const id = r.req_id || r.id
      return {
        ...r, id, level: 'L4',
        statement: r.text || r.statement || r.shall_statement || '',
        status: requirementStatusMap.value[id] || r.status || 'draft',
      }
    }),
  ]
  if (activeLevel.value !== 'all') {
    return all.filter(r => r.level === activeLevel.value)
  }
  return all
})

// Table filtered + sorted
const tableRequirements = computed(() => {
  let result = [...filteredRequirements.value]
  if (tableSearchQuery.value.trim()) {
    const query = tableSearchQuery.value.toLowerCase()
    result = result.filter(r =>
      (r.statement || r.text || r.title || '').toLowerCase().includes(query) ||
      (r.level || r.category || '').toLowerCase().includes(query) ||
      (getStatusName(r.status) || '').toLowerCase().includes(query)
    )
  }
  result.sort((a, b) => {
    let aVal = a[tableSortKey.value] || ''
    let bVal = b[tableSortKey.value] || ''
    if (tableSortKey.value === 'name') {
      aVal = a.statement || a.text || a.title || ''
      bVal = b.statement || b.text || b.title || ''
    }
    return tableSortOrder.value === 'asc'
      ? String(aVal).localeCompare(String(bVal))
      : String(bVal).localeCompare(String(aVal))
  })
  return result
})

// Tree data
const filteredTreeData = computed(() => {
  if (activeLevel.value === 'all') return requirementTree.value
  return filterTreeByLevel(requirementTree.value, activeLevel.value)
})

// Helpers
function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

function normalizePriority(raw, fallback = 'medium') {
  const text = String(raw ?? '').trim().toLowerCase()
  if (!text) return fallback
  return ['low', 'medium', 'high'].includes(text) ? text : fallback
}

function filterTreeByLevel(nodes, level) {
  if (!nodes || !nodes.length) return []
  return nodes.map(node => {
    const req = node.requirement || {}
    const nodeLevel = normalizeLevel(req.requirement_type || req.level || req.category)
    const children = filterTreeByLevel(node.children || [], level)
    if (nodeLevel === level || children.length > 0) return { ...node, children }
    return null
  }).filter(Boolean)
}

function getCountByLevel(level) {
  if (level === 'all') return highLevelRequirements.value.length + lowLevelRequirements.value.length
  if (level === 'L4') return lowLevelRequirements.value.length
  return highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === level).length
}

function getTypeLabel(type) {
  return { 'top_level': '顶层需求', 'low_level': '底层需求', 'task': '任务' }[type] || type || '-'
}

function getStatusName(statusId) {
  return requirementStatuses.find(s => s.id === statusId)?.name || '待处理'
}

function getStatusColorClass(statusId, variant = 'bg') {
  const color = requirementStatuses.find(s => s.id === statusId)?.color || 'zinc'
  const colorMap = {
    zinc: { bg: 'bg-zinc-100', text: 'text-zinc-700' },
    amber: { bg: 'bg-amber-100', text: 'text-amber-700' },
    sky: { bg: 'bg-sky-100', text: 'text-sky-700' },
    blue: { bg: 'bg-blue-100', text: 'text-blue-700' },
    emerald: { bg: 'bg-emerald-100', text: 'text-emerald-700' },
    slate: { bg: 'bg-slate-100', text: 'text-slate-700' },
  }
  return colorMap[color]?.[variant] || colorMap.zinc[variant]
}

function getConfidenceClass(conf) {
  if (conf >= 0.8) return 'bg-green-50 text-green-700 border-green-200'
  if (conf >= 0.5) return 'bg-amber-50 text-amber-700 border-amber-200'
  return 'bg-red-50 text-red-700 border-red-200'
}

function getLevelBadgeClass(level) {
  return {
    L1: 'bg-sky-100 text-sky-700 border-sky-200',
    L2: 'bg-violet-100 text-violet-700 border-violet-200',
    L3: 'bg-amber-100 text-amber-700 border-amber-200',
    L4: 'bg-emerald-100 text-emerald-700 border-emerald-200'
  }[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function getKanbanBucket(status) {
  if (status === 'completed' || status === 'archived') return 'completed'
  if (status === 'in_progress') return 'in_progress'
  return 'backlog'
}

function mapKanbanBucketToManage(status) {
  switch (status) {
    case 'completed': return 'completed'
    case 'in_progress': return 'in_progress'
    default: return 'draft'
  }
}

// Actions
function toggleSort(key) {
  if (tableSortKey.value === key) {
    tableSortOrder.value = tableSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    tableSortKey.value = key
    tableSortOrder.value = 'asc'
  }
}

function toggleColumn(key) {
  const idx = tableVisibleColumns.value.indexOf(key)
  if (idx >= 0) tableVisibleColumns.value.splice(idx, 1)
  else tableVisibleColumns.value.push(key)
}

async function updateRequirementStatus(reqId, newStatus) {
  const previousStatus = requirementStatusMap.value[reqId] || 'draft'
  if (previousStatus === newStatus) return
  try {
    const updated = await manageApi.updateRequirement(reqId, { status: newStatus })
    requirementStatusMap.value[reqId] = updated?.status || newStatus
    await loadRequirements()
  } catch (err) {
    requirementStatusMap.value[reqId] = previousStatus
    alert('更新需求状态失败: ' + (err?.response?.data?.detail || err?.message || '未知错误'))
  }
}

function handleNodeHover(req) { hoveredNode.value = req }
function handleNodeClick(req) { console.log('Clicked:', req) }
async function refreshData() { await loadRequirements() }

// Modal actions
function openAddRequirementModal() {
  if (!selectedProjectId.value) { alert('请先选择项目'); return }
  newRequirement.value = { title: '', description: '', requirement_type: 'top_level', level: 'L1', priority: 'medium', status: 'draft', parent_id: '', tags: '' }
  showAddRequirementModal.value = true
}

function closeAddRequirementModal() { showAddRequirementModal.value = false }

async function submitNewRequirement() {
  if (!selectedProjectId.value) { alert('请先选择项目'); return }
  if (!newRequirement.value.title.trim()) { alert('请输入需求标题'); return }
  isSubmitting.value = true
  try {
    const payload = {
      title: newRequirement.value.title.trim(),
      description: newRequirement.value.description.trim(),
      requirement_type: newRequirement.value.requirement_type,
      status: newRequirement.value.status,
      priority: normalizePriority(newRequirement.value.priority, 'medium'),
    }
    if (newRequirement.value.parent_id) payload.parent_id = newRequirement.value.parent_id
    if (newRequirement.value.tags.trim()) payload.tags = newRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean)
    await manageApi.createRequirement(selectedProjectId.value, payload)
    closeAddRequirementModal()
    await loadRequirements()
    await loadManageRequirementMap()
  } catch (err) {
    console.error('新增需求失败:', err)
    alert('新增需求失败: ' + (err.message || '未知错误'))
  } finally {
    isSubmitting.value = false
  }
}

function openEditRequirementModal(req) {
  if (!selectedProjectId.value) { alert('请先选择项目'); return }
  const reqId = resolveManageReqId(req)
  if (!reqId) { alert('无法关联到项目需求，请刷新后重试'); return }
  editRequirementId.value = reqId
  const sourceKey = req.req_id || req.id
  const mappedPriority = managePriorityMap.value.get(sourceKey) || managePriorityMap.value.get(reqId)
  editRequirement.value = {
    title: req.title || req.text || req.statement || '',
    description: req.description || '',
    priority: normalizePriority(mappedPriority ?? req.priority, 'medium'),
    status: req.status || 'draft',
    tags: Array.isArray(req.tags) ? req.tags.join(', ') : (req.tags || '')
  }
  showEditRequirementModal.value = true
}

function closeEditRequirementModal() { showEditRequirementModal.value = false; editRequirementId.value = '' }

async function submitEditRequirement() {
  if (!editRequirementId.value) { alert('需求 ID 丢失'); return }
  if (!editRequirement.value.title.trim()) { alert('请输入需求标题'); return }
  isEditSubmitting.value = true
  try {
    const payload = {
      title: editRequirement.value.title.trim(),
      description: editRequirement.value.description.trim(),
      priority: normalizePriority(editRequirement.value.priority, 'medium'),
      status: editRequirement.value.status,
    }
    payload.tags = editRequirement.value.tags.trim()
      ? editRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean)
      : []
    await manageApi.updateRequirement(editRequirementId.value, payload)
    closeEditRequirementModal()
    await loadRequirements()
    await loadManageRequirementMap()
  } catch (err) {
    console.error('编辑需求失败:', err)
    alert('编辑需求失败: ' + (err.message || '未知错误'))
  } finally {
    isEditSubmitting.value = false
  }
}

// Kanban drag
function syncRequirementLists() {
  const all = filteredRequirements.value
  backlogRequirements.value = all.filter(r => getKanbanBucket(r.status) === 'backlog')
  inProgressRequirements.value = all.filter(r => r.status === 'in_progress')
  completedRequirements.value = all.filter(r => getKanbanBucket(r.status) === 'completed')
}

function onDragChange(evt, targetStatus) {
  if (evt.added) {
    const item = evt.added.element
    if (item && item.id) {
      requirementStatusMap.value[item.id] = targetStatus
      persistStatusToDb(item, targetStatus)
    }
  }
}

function resolveManageReqId(item) {
  const candidates = [item.manage_req_id, item.req_id, item.id, item.source_req_id, item.source_top_id].filter(Boolean)
  for (const key of candidates) {
    if (manageReqIdMap.value.has(key)) return manageReqIdMap.value.get(key)
  }
  return candidates[0] || ''
}

async function persistStatusToDb(item, targetStatus) {
  const manageReqId = resolveManageReqId(item)
  if (!manageReqId) return
  try {
    const updated = await manageApi.updateRequirement(manageReqId, { status: mapKanbanBucketToManage(targetStatus) })
    requirementStatusMap.value[manageReqId] = updated?.status || mapKanbanBucketToManage(targetStatus)
    await loadRequirements()
  } catch (err) {
    console.warn('同步状态到数据库失败', err)
    alert('同步需求状态失败: ' + (err?.response?.data?.detail || err?.message || '未知错误'))
    await loadRequirements()
  }
}

// Data loading
async function loadProjects() {
  try {
    const data = await manageApi.listProjects()
    projects.value = data?.projects || []
  } catch (err) {
    console.warn('加载项目列表失败', err)
    projects.value = []
  }
}

async function loadManageRequirementMap() {
  if (!selectedProjectId.value) return
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    const reqs = data?.requirements || []
    const idMap = new Map()
    const statusMap = new Map()
    const priorityMap = new Map()
    reqs.forEach((req) => {
      if (req.req_id) {
        idMap.set(req.req_id, req.req_id)
        statusMap.set(req.req_id, req.status)
        priorityMap.set(req.req_id, normalizePriority(req.priority, null))
      }
      if (req.source_req_id) {
        idMap.set(req.source_req_id, req.req_id)
        statusMap.set(req.source_req_id, req.status)
        priorityMap.set(req.source_req_id, normalizePriority(req.priority, null))
      }
    })
    manageReqIdMap.value = idMap
    manageStatusMap.value = statusMap
    managePriorityMap.value = priorityMap
    statusMap.forEach((status, key) => {
      requirementStatusMap.value[key] = status || 'draft'
    })
  } catch (err) {
    console.warn('加载管理需求映射失败', err)
  }
}

async function loadRequirements() {
  if (!selectedProjectId.value) {
    highLevelRequirements.value = []
    lowLevelRequirements.value = []
    requirementTree.value = []
    return
  }
  isLoading.value = true
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    const reqs = data?.requirements || []
    const toLevel = (req) => {
      const sourceLevel = normalizeLevel(req.source_level || req.level || req.category)
      if (['L1', 'L2', 'L3'].includes(sourceLevel)) return sourceLevel
      if (req.requirement_type === 'low_level' || sourceLevel === 'L4') return 'L4'
      if (req.requirement_type === 'task') return 'L4'
      return 'L3'
    }
    highLevelRequirements.value = reqs
      .filter(r => r.requirement_type !== 'low_level')
      .map(r => ({ ...r, id: r.req_id, text: r.title || r.description || '', statement: r.description || r.title || '', priority: normalizePriority(r.priority, null), level: toLevel(r), category: toLevel(r) }))
    lowLevelRequirements.value = reqs
      .filter(r => r.requirement_type === 'low_level')
      .map(r => ({ ...r, id: r.req_id, text: r.title || r.description || '', statement: r.description || r.title || '', shall_statement: r.title || '', source_top_id: r.parent_id || null, priority: normalizePriority(r.priority, null), level: 'L4' }))
    requirementTree.value = buildTreeWithRelations(highLevelRequirements.value, lowLevelRequirements.value)
    await loadManageRequirementMap()
  } catch (err) {
    console.error('加载需求失败:', err)
  } finally {
    isLoading.value = false
  }
}

function buildTreeWithRelations(highReqs, lowReqs) {
  const allReqMap = new Map()
  highReqs.forEach((req, idx) => {
    const id = req.req_id || req.id || `high_${idx}`
    allReqMap.set(id, {
      id, name: req.text || req.statement || req.title || `需求 ${idx + 1}`,
      requirement: { ...req, requirement_type: 'top_level' },
      requirement_type: 'top_level', level: normalizeLevel(req.level || req.category),
      parent_id: req.parent_id || null, children: []
    })
  })
  lowReqs.forEach((req, idx) => {
    const id = req.req_id || req.id || `low_${idx}`
    allReqMap.set(id, {
      id, name: req.text || req.statement || req.shall_statement || `L4 需求 ${idx + 1}`,
      requirement: { ...req, requirement_type: 'low_level' },
      requirement_type: 'low_level', level: 'L4',
      parent_id: req.parent_id || req.source_top_id || null, children: []
    })
  })
  const roots = []
  const linkedIds = new Set()
  allReqMap.forEach((node, id) => {
    if (node.parent_id && allReqMap.has(node.parent_id)) {
      allReqMap.get(node.parent_id).children.push(node)
      linkedIds.add(id)
    }
  })
  allReqMap.forEach((node, id) => { if (!linkedIds.has(id)) roots.push(node) })
  const levelOrder = { 'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4 }
  const sortChildren = (n) => { n.children.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5)); n.children.forEach(sortChildren) }
  roots.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5))
  roots.forEach(sortChildren)
  return roots
}

// Watchers
watch(selectedProjectId, async (val) => {
  if (val) {
    localStorage.setItem('lastProjectId', val)
    window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: val } }))
    await loadRequirements()
  } else {
    window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: '' } }))
  }
})

watch(() => props.projectId, (val) => {
  if (val && val !== selectedProjectId.value) selectedProjectId.value = val
})

watch([filteredRequirements, requirementStatusMap], () => { syncRequirementLists() }, { deep: true, immediate: true })

// Init
onMounted(async () => {
  await loadProjects()
  if (selectedProjectId.value) await loadRequirements()
})
</script>
