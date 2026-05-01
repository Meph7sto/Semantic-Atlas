<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <h3>{{ mode === 'create' ? '在产品下新建项目' : '编辑项目' }}</h3>
      <div class="form-group">
        <label>项目名称 *</label>
        <input type="text" v-model="form.name" placeholder="输入项目名称" />
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea v-model="form.description" placeholder="输入项目描述" rows="3"></textarea>
      </div>
      <div v-if="mode === 'create'" class="form-group">
        <label>Session ID <span class="optional-tag">可选</span></label>
        <input
          type="text"
          v-model="form.sessionId"
          placeholder="输入 Session ID，创建后自动导入该 Session 的需求"
        />
        <p v-if="form.sessionId && form.sessionId.trim()" class="field-hint success">
          ✓ 创建后将自动导入该 Session 的需求数据（L1-L4）
        </p>
      </div>
      <div class="modal-actions">
        <button type="button" class="action-btn white sa-button sa-button--secondary" @click="$emit('close')">取消</button>
        <button
          type="button"
          class="action-btn brown sa-button sa-button--primary"
          @click="handleSubmit"
          :disabled="!form.name.trim()"
        >
          {{ mode === 'create' ? '创建' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  mode: { type: String, required: true }, // 'create' | 'edit'
  initial: { type: Object, default: null },
})

const emit = defineEmits(['submit', 'close'])

const form = ref({ name: '', description: '', sessionId: '' })

watch(
  () => props.initial,
  (val) => {
    form.value = val
      ? { name: val.name || '', description: val.description || '', sessionId: '' }
      : { name: '', description: '', sessionId: '' }
  },
  { immediate: true }
)

const handleSubmit = () => {
  emit('submit', { ...form.value })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content h3 {
  margin: 0 0 1.5rem 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  margin-bottom: 0.5rem;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--primary-color, #c4692f);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.action-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.2s;
}

.action-btn.brown {
  background: var(--primary-color, #c4692f);
  color: white;
}

.action-btn.brown:hover {
  background: #b35d28;
}

.action-btn.brown:disabled {
  background: #d1d5db;
  cursor: not-allowed;
}

.action-btn.white {
  background: white;
  border-color: var(--border-color, #e5e7eb);
  color: var(--text-primary, #1f2937);
}

.action-btn.white:hover {
  background: var(--surface-secondary, #f9fafb);
}

.optional-tag {
  font-size: 0.75rem;
  font-weight: 400;
  color: #9ca3af;
  margin-left: 0.25rem;
}

.field-hint {
  margin: 0.375rem 0 0 0;
  font-size: 0.75rem;
  color: #6b7280;
}

.field-hint.success {
  color: #059669;
}
</style>
