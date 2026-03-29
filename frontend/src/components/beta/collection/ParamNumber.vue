<template>
  <div class="param-number">
    <label class="param-number-label">{{ label }}</label>
    <input
      :value="modelValue"
      type="number"
      class="param-number-input"
      :min="min"
      :max="max"
      :step="step"
      @input="handleInput"
    />
    <p v-if="hint" class="param-number-hint">{{ hint }}</p>
  </div>
</template>

<script setup>
const props = defineProps({
  label: { type: String, required: true },
  modelValue: { type: Number, required: true },
  min: { type: Number, default: undefined },
  max: { type: Number, default: undefined },
  step: { type: Number, default: 1 },
  hint: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

function handleInput(event) {
  const raw = event.target.value
  const num = Number(raw)
  if (Number.isFinite(num)) {
    emit('update:modelValue', num)
  }
}
</script>

<style scoped>
.param-number {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-number-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-600, #475569);
  letter-spacing: 0.3px;
}

.param-number-input {
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
  color: var(--ink-950, #0f172a);
  border-radius: 0;
  transition: all 0.2s ease;
}

.param-number-input:focus {
  outline: none;
  border-color: var(--accent, #c4692f);
  box-shadow: 0 0 0 3px rgba(196, 105, 47, 0.1);
}

.param-number-hint {
  font-size: 11px;
  color: var(--ink-400, #94a3b8);
  margin: 0;
}
</style>
