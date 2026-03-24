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

      <main class="canvas workbench-canvas">
        <section class="workbench-header" data-animate style="--delay: 0.05s">
          <div>
            <h1>需求工程管理工作台</h1>
            <p>覆盖需求生命周期、里程碑、分支与合并历史，已迁移到 beta 正式页面。</p>
          </div>
          <button type="button" class="overview-link" @click="router.push({ name: 'beta-requirements-overview' })">
            打开需求总览
          </button>
        </section>

        <section class="workbench-body" data-animate style="--delay: 0.1s">
          <RequirementsManage class="legacy-manage" />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import Sidebar from '@/components/beta/Sidebar.vue'
import RequirementsManage from '@/views/alpha/RequirementsManage.vue'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'
import { useRouter } from 'vue-router'

const router = useRouter()
const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirements')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()
</script>

<style scoped>
.workbench-canvas {
  padding: 18px;
  overflow: hidden;
}

.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  padding: 14px 16px;
  border: 1px solid rgba(47, 143, 137, 0.2);
  border-radius: 0;
  background: linear-gradient(180deg, rgba(47, 143, 137, 0.08), rgba(47, 143, 137, 0.03));
}

.workbench-header h1 {
  margin: 0;
  font-size: 20px;
  color: var(--ink-950, #1b2730);
  font-family: "BodyWithTimesDigits", "Bodoni MT", "Didot", "Noto Serif SC", serif;
}

.workbench-header p {
  margin: 6px 0 0;
  color: rgba(28, 40, 52, 0.65);
  font-size: 13px;
}

.overview-link {
  border: 1px solid rgba(47, 143, 137, 0.3);
  background: #fff;
  color: #2f8f89;
  border-radius: 0;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.overview-link:hover {
  background: rgba(47, 143, 137, 0.08);
}

.workbench-body {
  height: calc(100vh - 170px);
  border-radius: 0;
  border: 1px solid rgba(28, 40, 52, 0.12);
  background: rgba(248, 242, 232, 0.45);
  overflow: auto;
}

.legacy-manage {
  min-height: 100%;
}

@media (max-width: 1024px) {
  .workbench-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .workbench-body {
    height: calc(100vh - 220px);
  }
}

/* =====================================================
   Alpha → Beta 样式覆盖（:deep）
   覆盖嵌入的 alpha RequirementsManage.vue 中的 Tailwind 工具类
   ===================================================== */

/* --- 全局：去除圆角 --- */
:deep(.rounded-xl),
:deep(.rounded-lg),
:deep(.rounded-md),
:deep(.rounded),
:deep([class*="rounded-"]) {
  border-radius: 0 !important;
}

/* --- 全局：去除阴影 --- */
:deep(.shadow-sm),
:deep(.shadow) {
  box-shadow: none !important;
}

/* --- 根容器背景 --- */
:deep(.bg-zinc-50) {
  background-color: rgba(248, 242, 232, 0.45) !important;
}

:deep(.bg-white) {
  background-color: rgba(255, 255, 255, 0.92) !important;
}

/* --- 页面头部 header --- */
:deep(header.bg-white) {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(47, 143, 137, 0.12)) !important;
  border-bottom-color: rgba(28, 40, 52, 0.12) !important;
}

/* --- Section 卡片 --- */
:deep(section.bg-white) {
  background: rgba(255, 255, 255, 0.92) !important;
  border-color: rgba(28, 40, 52, 0.12) !important;
}

/* --- 边框色 --- */
:deep(.border-zinc-200) {
  border-color: rgba(28, 40, 52, 0.12) !important;
}

:deep(.border-zinc-300) {
  border-color: rgba(28, 40, 52, 0.2) !important;
}

:deep(.border-zinc-100) {
  border-color: rgba(28, 40, 52, 0.06) !important;
}

/* --- 文字色 --- */
:deep(.text-zinc-900) {
  color: var(--ink-950, #1b2730) !important;
}

:deep(.text-zinc-800) {
  color: var(--ink-900, #23323d) !important;
}

:deep(.text-zinc-700) {
  color: rgba(28, 40, 52, 0.75) !important;
}

:deep(.text-zinc-600) {
  color: rgba(28, 40, 52, 0.65) !important;
}

:deep(.text-zinc-500) {
  color: rgba(28, 40, 52, 0.55) !important;
}

:deep(.text-zinc-400) {
  color: rgba(28, 40, 52, 0.4) !important;
}

/* --- 标题字体 --- */
:deep(h2.text-xl),
:deep(h3.text-sm) {
  font-family: "BodyWithTimesDigits", "Noto Sans SC", "PingFang SC", sans-serif;
}

/* --- 主操作按钮 (bg-zinc-900 → accent) --- */
:deep(.bg-zinc-900) {
  background-color: var(--accent, #c4692f) !important;
  color: #111 !important;
}

:deep(.bg-zinc-900:hover) {
  background-color: var(--accent-strong, #a85424) !important;
}

/* --- 次要按钮和边框按钮 --- */
:deep(button.border-zinc-300) {
  border-color: rgba(28, 40, 52, 0.25) !important;
  color: rgba(28, 40, 52, 0.75) !important;
}

:deep(button.border-zinc-300:hover) {
  background-color: rgba(28, 40, 52, 0.04) !important;
}

/* --- 表单控件（input/select） --- */
:deep(input.border-zinc-300),
:deep(select.border-zinc-300),
:deep(textarea.border-zinc-300) {
  border-color: rgba(28, 40, 52, 0.2) !important;
  border-radius: 0 !important;
  background: rgba(255, 255, 255, 0.9) !important;
  color: var(--ink-950, #1b2730) !important;
  font-family: "BodyWithTimesDigits", "Noto Sans SC", "PingFang SC", sans-serif;
}

:deep(input:focus),
:deep(select:focus),
:deep(textarea:focus) {
  border-color: rgba(47, 143, 137, 0.55) !important;
  box-shadow: 0 0 0 3px rgba(47, 143, 137, 0.12) !important;
  outline: none !important;
}

/* --- 错误信息 --- */
:deep(.text-red-600) {
  color: var(--signal, #c45b60) !important;
}

/* --- 链接/操作色 --- */
:deep(.text-blue-600) {
  color: var(--teal, #2f8f89) !important;
}

/* --- 状态色 (比较差异) --- */
:deep(.text-green-600) {
  color: #2f8f89 !important;
}

:deep(.text-amber-600) {
  color: var(--accent, #c4692f) !important;
}

/* --- 冲刺按钮 active 状态 (amber → accent) --- */
:deep(.bg-amber-100) {
  background-color: rgba(196, 105, 47, 0.15) !important;
}

:deep(.text-amber-700) {
  color: #a85424 !important;
}

:deep(.border-amber-300),
:deep(.border-amber-200) {
  border-color: rgba(196, 105, 47, 0.4) !important;
}

/* --- 变更差异标签 --- */
:deep(.bg-green-100) {
  background-color: rgba(47, 143, 137, 0.12) !important;
}

:deep(.text-green-700) {
  color: #2f8f89 !important;
}

:deep(.border-green-200),
:deep(.border-green-300) {
  border-color: rgba(47, 143, 137, 0.3) !important;
}

:deep(.bg-red-100) {
  background-color: rgba(196, 91, 96, 0.12) !important;
}

:deep(.text-red-700) {
  color: #c45b60 !important;
}

:deep(.border-red-200),
:deep(.border-red-300) {
  border-color: rgba(196, 91, 96, 0.3) !important;
}

:deep(.bg-amber-100.text-amber-700) {
  background-color: rgba(196, 105, 47, 0.15) !important;
  color: #a85424 !important;
}

:deep(.border-amber-300) {
  border-color: rgba(196, 105, 47, 0.4) !important;
}

:deep(.bg-blue-100) {
  background-color: rgba(47, 143, 137, 0.12) !important;
}

:deep(.text-blue-700) {
  color: #2f8f89 !important;
}

:deep(.border-blue-200),
:deep(.border-blue-300) {
  border-color: rgba(47, 143, 137, 0.3) !important;
}

:deep(.bg-purple-100) {
  background-color: rgba(196, 105, 47, 0.1) !important;
}

:deep(.text-purple-700) {
  color: #a85424 !important;
}

:deep(.border-purple-200),
:deep(.border-purple-300) {
  border-color: rgba(196, 105, 47, 0.3) !important;
}

/* --- 比较差异摘要卡片 --- */
:deep(.bg-zinc-50.border-zinc-200) {
  background: rgba(28, 40, 52, 0.04) !important;
  border-color: rgba(28, 40, 52, 0.12) !important;
}

/* --- checkbox --- */
:deep(input[type="checkbox"]) {
  border-radius: 0 !important;
}

/* --- 表格 hover --- */
:deep(.hover\:bg-zinc-50:hover) {
  background-color: rgba(28, 40, 52, 0.04) !important;
}

/* --- 表格头部 sticky --- */
:deep(thead.bg-zinc-50),
:deep(.bg-zinc-50.sticky) {
  background-color: rgba(248, 242, 232, 0.9) !important;
}

/* --- 冲刺规划按钮不可用 --- */
:deep(.bg-zinc-100) {
  background-color: rgba(28, 40, 52, 0.06) !important;
}

:deep(.cursor-not-allowed) {
  cursor: not-allowed;
}

/* --- scrollbar --- */
:deep(::-webkit-scrollbar) {
  width: 6px;
}

:deep(::-webkit-scrollbar-track) {
  background: transparent;
}

:deep(::-webkit-scrollbar-thumb) {
  background-color: rgba(28, 40, 52, 0.15);
}

:deep(::-webkit-scrollbar-thumb:hover) {
  background-color: rgba(28, 40, 52, 0.25);
}
</style>
