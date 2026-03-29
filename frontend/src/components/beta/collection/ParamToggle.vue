<template>
  <div class="param-toggle">
    <div class="param-toggle-text">
      <span class="param-toggle-label">{{ label }}</span>
      <span v-if="desc" class="param-toggle-desc">{{ desc }}</span>
    </div>
    <label class="toggle-switch" :class="{ danger }">
      <input type="checkbox" :checked="modelValue" @change="emit('update:modelValue', $event.target.checked)" />
      <span class="toggle-slider"></span>
    </label>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  modelValue: { type: Boolean, required: true },
  desc: { type: String, default: '' },
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.param-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 0;
}

.param-toggle-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.param-toggle-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700, #334155);
}

.param-toggle-desc {
  font-size: 11px;
  color: var(--ink-400, #94a3b8);
  line-height: 1.4;
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.toggle-switch input { opacity: 0; width: 0; height: 0; }

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(28, 40, 52, 0.2);
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.toggle-switch input:checked + .toggle-slider { background-color: var(--accent, #c4692f); }
.toggle-switch.danger input:checked + .toggle-slider { background-color: #ef4444; }
.toggle-switch input:checked + .toggle-slider:before { transform: translateX(20px); }
.toggle-switch input:focus + .toggle-slider { box-shadow: 0 0 0 3px rgba(196, 105, 47, 0.1); }
</style>
