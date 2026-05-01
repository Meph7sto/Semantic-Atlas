<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-container">
      <div class="modal-header">
        <h3>编辑需求</h3>
        <button type="button" class="modal-close" @click="$emit('close')">
          <X class="w-5 h-5" />
        </button>
      </div>
      <form class="modal-body" @submit.prevent="$emit('submit')">
        <div class="form-group">
          <label class="form-label required">需求标题</label>
          <input v-model="form.title" type="text" class="form-input sa-input" placeholder="输入需求标题" required />
        </div>

        <div class="form-group">
          <label class="form-label">需求描述</label>
          <textarea v-model="form.description" class="form-textarea sa-input" placeholder="详细描述需求内容..." rows="4"></textarea>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">优先级</label>
            <select v-model="form.priority" class="form-select sa-input">
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">状态</label>
            <select v-model="form.status" class="form-select sa-input">
              <option value="draft">草稿</option>
              <option value="under_review">审核中</option>
              <option value="confirmed">已确认</option>
              <option value="in_progress">进行中</option>
              <option value="completed">已完成</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">标签（用逗号分隔）</label>
          <input v-model="form.tags" type="text" class="form-input sa-input" placeholder="例如: 功能, 性能, 安全" />
        </div>

        <div class="modal-footer">
          <button type="button" class="action-btn secondary sa-button sa-button--secondary" @click="$emit('close')">取消</button>
          <button type="submit" class="action-btn primary sa-button sa-button--primary" :disabled="isSubmitting">
            <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
            {{ isSubmitting ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { X, Loader2 } from 'lucide-vue-next'

defineProps({
  form: { type: Object, required: true },
  isSubmitting: { type: Boolean, default: false },
})

defineEmits(['close', 'submit'])
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.modal-container {
  background: #fff;
  width: 90%;
  max-width: 560px;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid rgba(28, 40, 52, 0.15);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(47, 143, 137, 0.05);
}

.modal-header h3 { margin: 0; font-size: 16px; font-weight: 600; color: var(--ink-950); }
.modal-close { background: transparent; border: none; cursor: pointer; padding: 4px; color: rgba(28, 40, 52, 0.5); }
.modal-close:hover { color: rgba(28, 40, 52, 0.9); }

.modal-body { padding: 20px; }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid rgba(28, 40, 52, 0.1);
}

.form-group { margin-bottom: 16px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: rgba(28, 40, 52, 0.7);
  margin-bottom: 6px;
}

.form-label.required::after { content: ' *'; color: #dc2626; }

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
  color: var(--ink-950);
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: rgba(47, 143, 137, 0.5);
  box-shadow: 0 0 0 3px rgba(47, 143, 137, 0.1);
}

.form-textarea { resize: vertical; min-height: 80px; }

.action-btn.primary { background: var(--accent); color: #fff; border: 1px solid var(--accent); }
.action-btn.primary:hover:not(:disabled) { background: #1c6864; }
.action-btn.primary:disabled { opacity: 0.6; cursor: not-allowed; }

.action-btn.secondary { background: #fff; color: rgba(28, 40, 52, 0.8); border: 1px solid rgba(28, 40, 52, 0.2); }
.action-btn.secondary:hover { background: rgba(28, 40, 52, 0.04); }
</style>
