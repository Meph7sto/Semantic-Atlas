<script setup>
import { RouterView, RouterLink } from 'vue-router'
import { LayoutDashboard, GitCompare, FileSearch } from 'lucide-vue-next'
</script>

<template>
  <div class="flex h-screen w-full bg-white">
    <!-- Sidebar -->
    <aside class="w-64 bg-zinc-900 text-zinc-300 flex flex-col border-r border-zinc-800">
      <div class="p-4 mb-4">
        <h1 class="text-white text-lg font-semibold tracking-wide">Semantic Atlas</h1>
      </div>
      
      <nav class="flex-1 px-2 space-y-1">
        <RouterLink 
          to="/conflict" 
          active-class="bg-zinc-800 text-white"
          class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors hover:bg-zinc-800 hover:text-white"
        >
          <GitCompare class="w-4 h-4" />
          <span>Requirement Conflict</span>
        </RouterLink>

        <!-- Placeholders for other views if they exist -->
        <RouterLink 
          to="/classification" 
          active-class="bg-zinc-800 text-white"
          class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors hover:bg-zinc-800 hover:text-white"
        >
          <LayoutDashboard class="w-4 h-4" />
          <span>Classification</span>
        </RouterLink>

        <RouterLink 
          to="/traceability" 
          active-class="bg-zinc-800 text-white"
          class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors hover:bg-zinc-800 hover:text-white"
        >
          <FileSearch class="w-4 h-4" />
          <span>Traceability</span>
        </RouterLink>
      </nav>

      <div class="p-4 border-t border-zinc-800">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded bg-indigo-600 flex items-center justify-center text-white text-xs font-bold">
            U
          </div>
          <div class="text-sm">
            <div class="text-white">User</div>
            <div class="text-xs text-zinc-500">Pro Plan</div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 flex flex-col h-full overflow-hidden bg-white">
      <RouterView />
    </main>
  </div>
</template>

<style>
</style>
