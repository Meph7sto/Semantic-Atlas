<template>
  <div class="requirement-replay h-full w-full overflow-y-auto bg-zinc-50 p-6">
    <div class="mx-auto max-w-7xl space-y-6">
      <!-- 页面标题 -->
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold text-zinc-900">需求回放</h1>
        <div v-if="store.error" class="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
          {{ store.error }}
        </div>
      </div>

      <!-- 项目和需求选择 -->
      <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <ProjectSelector
          v-model="selected"
          :event-count="store.events.length"
          @project-selected="onProjectSelected"
          @requirement-selected="onRequirementSelected"
        />
      </section>

      <!-- 主内容区 -->
      <div v-if="store.selectedRequirementId" class="space-y-6">
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- 左侧：需求状态展示 -->
          <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
            <RequirementState
              :state="store.currentState"
              :version="store.currentVersion"
              :max-version="store.maxVersion"
              :is-loading="store.isLoadingState"
            />
          </section>

          <!-- 右侧：命令编辑器 -->
          <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
            <CommandEditor
              :requirement-id="store.selectedRequirementId"
              :current-state="store.currentState"
              @command-submitted="onCommandSubmitted"
            />
          </section>
        </div>

        <!-- 下方：状态演进画布 -->
        <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <StateCanvas
            :events="store.events"
            :current-version="store.currentVersion"
            :max-version="store.maxVersion"
            :is-playing="store.isPlaying"
            @version-select="onVersionSelect"
            @play="onPlay"
            @pause="onPause"
            @step-forward="onStepForward"
            @step-backward="onStepBackward"
            @jump-start="onJumpStart"
            @jump-end="onJumpEnd"
          />
        </section>
      </div>

      <!-- 空状态提示 -->
      <div v-else class="rounded-2xl border border-zinc-200 bg-white p-12 text-center shadow-sm">
        <svg class="mx-auto h-16 w-16 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <h3 class="mt-4 text-lg font-semibold text-zinc-900">选择一个需求开始回放</h3>
        <p class="mt-2 text-sm text-zinc-600">
          从上方选择项目和需求，然后查看状态演进画布和需求状态变化
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRequirementReplayStore } from '@/stores/requirementReplay'
import ProjectSelector from './components/ProjectSelector.vue'
import RequirementState from './components/RequirementState.vue'
import CommandEditor from './components/CommandEditor.vue'
import StateCanvas from './components/StateCanvas.vue'

const store = useRequirementReplayStore()

const selected = ref({
  projectId: '',
  requirementId: ''
})

async function onProjectSelected(projectId) {
  store.selectedProjectId = projectId
  console.log('Project selected:', projectId)
}

async function onRequirementSelected(requirementId) {
  if (!requirementId) {
    store.reset()
    return
  }

  store.selectedRequirementId = requirementId
  console.log('Requirement selected:', requirementId)

  // 加载事件
  try {
    await store.loadEvents(requirementId)

    // 连接SSE（可选，用于实时更新）
    // store.connectSSE(requirementId)
  } catch (err) {
    console.error('Failed to load events:', err)
  }
}

function onVersionSelect(version) {
  store.setCurrentVersion(version)
}

function onPlay() {
  store.play()
}

function onPause() {
  store.pause()
}

function onStepForward() {
  store.stepForward()
}

function onStepBackward() {
  store.stepBackward()
}

function onJumpStart() {
  store.jumpToStart()
}

function onJumpEnd() {
  store.jumpToEnd()
}

function onCommandSubmitted(command) {
  console.log('Command submitted:', command)
  // 命令提交后，重新加载事件以获取最新状态
  if (store.selectedRequirementId) {
    store.loadEvents(store.selectedRequirementId)
  }
}

onMounted(() => {
  console.log('RequirementReplay mounted')
})

onBeforeUnmount(() => {
  // 清理资源
  store.pause()
  store.disconnectSSE()
})

// 监听store的变化
watch(() => store.error, (newError) => {
  if (newError) {
    console.error('Store error:', newError)
  }
})
</script>

<style scoped>
.requirement-replay {
  scrollbar-width: thin;
  scrollbar-color: #d4d4d8 transparent;
}

.requirement-replay::-webkit-scrollbar {
  width: 8px;
}

.requirement-replay::-webkit-scrollbar-thumb {
  background-color: #d4d4d8;
  border-radius: 4px;
}

.requirement-replay::-webkit-scrollbar-track {
  background-color: transparent;
}
</style>
