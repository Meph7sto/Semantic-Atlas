<script setup>
import AlphaRequirementsPanel from '../../components/alpha/AlphaRequirementsPanel.vue'
</script>

<template>
  <div class="h-full w-full overflow-y-auto">
    <div class="mx-auto w-full max-w-7xl p-6 md:p-8">
      <div class="rounded-3xl border border-zinc-200/70 bg-white/85 p-6 shadow-2xl backdrop-blur-sm">
        <div class="mb-4">
          <h2 class="text-2xl font-semibold tracking-tight text-zinc-900">需求管理表格调试</h2>
          <p class="mt-1 text-sm text-zinc-500">仅保留需求列表与编辑能力，便于联调。</p>
        </div>
        <AlphaRequirementsPanel table-only />
      </div>
    </div>
  </div>
</template>
