<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar :activePage="activePage" @navigate="handleNavigate" />
      <main class="canvas my-files-canvas">
        <div class="my-files-page">

          <!-- 页面标题 -->
          <div class="page-header">
            <div class="page-header-left">
              <h1 class="page-title">我的文件</h1>
              <p class="page-subtitle">浏览您上传的所有文件，按文件夹归类展示</p>
            </div>
            <button
              class="btn btn-default refresh-btn"
              :disabled="isLoading"
              @click="loadTree"
            >
              <RefreshCw class="btn-icon" :class="{ 'spin': isLoading }" />
              刷新
            </button>
          </div>

          <div class="files-content">
            <!-- 左侧：文件树 -->
            <div class="tree-panel card sa-card">
              <div class="panel-header">
                <span class="panel-title">文件结构</span>
                <span class="panel-meta">{{ totalFiles }} 个文件 | {{ folderCount }} 个文件夹</span>
              </div>

              <div v-if="isLoading" class="empty-state">加载中…</div>
              <div v-else-if="totalFiles === 0" class="empty-state">暂无上传文件</div>
              <div v-else class="tree-body">

                <!-- 根目录文件 -->
                <div v-if="rootFiles.length" class="root-files-section">
                  <div class="section-label">根目录</div>
                  <div
                    v-for="file in rootFiles"
                    :key="file.relativePath"
                    class="file-row"
                    :class="{ active: selectedFile?.relativePath === file.relativePath }"
                  >
                    <component :is="getFileIcon(file.extension)" class="file-icon" />
                    <div class="file-info">
                      <div class="file-name" :title="file.originalFilename">{{ file.originalFilename }}</div>
                      <div class="file-meta">{{ formatFileSize(file.fileSize) }} · {{ formatTime(file.uploadTime) }}</div>
                    </div>
                    <div class="file-actions">
                      <button
                        v-if="isImageFile(file.extension)"
                        class="icon-btn"
                        title="预览"
                        @click="previewFile(file)"
                      >
                        <Eye class="action-icon" />
                      </button>
                      <button
                        class="icon-btn"
                        title="下载"
                        @click="downloadFile(file.relativePath)"
                      >
                        <Download class="action-icon" />
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 文件夹 -->
                <div
                  v-for="folder in folders"
                  :key="folder.path"
                  class="folder-block"
                >
                  <div class="folder-header" @click="toggleFolder(folder.path)">
                    <component
                      :is="isFolderExpanded(folder.path) ? ChevronDown : ChevronRight"
                      class="chevron-icon"
                    />
                    <Folder class="folder-icon" />
                    <div class="folder-info">
                      <span class="folder-name">{{ folder.path }}</span>
                      <span class="folder-count">{{ folder.fileCount }} 个文件</span>
                    </div>
                  </div>

                  <div v-show="isFolderExpanded(folder.path)" class="folder-files">
                    <div
                      v-for="file in folder.files"
                      :key="file.relativePath"
                      class="file-row"
                      :class="{ active: selectedFile?.relativePath === file.relativePath }"
                    >
                      <component :is="getFileIcon(file.extension)" class="file-icon" />
                      <div class="file-info">
                        <div class="file-name" :title="file.originalFilename">{{ file.originalFilename }}</div>
                        <div class="file-meta">{{ formatFileSize(file.fileSize) }} · {{ formatTime(file.uploadTime) }}</div>
                      </div>
                      <div class="file-actions">
                        <button
                          v-if="isImageFile(file.extension)"
                          class="icon-btn"
                          title="预览"
                          @click="previewFile(file)"
                        >
                          <Eye class="action-icon" />
                        </button>
                        <button
                          class="icon-btn"
                          title="下载"
                          @click="downloadFile(file.relativePath)"
                        >
                          <Download class="action-icon" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            </div>

            <!-- 右侧：预览面板 -->
            <div class="preview-panel card sa-card">
              <div class="panel-header">
                <span class="panel-title">预览</span>
                <button v-if="selectedFile" class="text-btn" @click="closePreview">关闭</button>
              </div>
              <div v-if="!selectedFile" class="empty-state">选择图片即可预览</div>
              <div v-else class="preview-body">
                <div class="preview-img-wrap">
                  <img
                    v-if="isImageFile(selectedFile.extension)"
                    :src="previewUrl"
                    :alt="selectedFile.originalFilename"
                    class="preview-img"
                  />
                  <div v-else class="preview-unsupported">仅支持图片预览</div>
                </div>
                <div class="preview-meta">
                  <div class="preview-filename">{{ selectedFile.originalFilename }}</div>
                  <div class="preview-detail">路径：{{ selectedFile.relativePath }}</div>
                  <div class="preview-detail">大小：{{ formatFileSize(selectedFile.fileSize) }}</div>
                  <div class="preview-detail">上传时间：{{ formatTime(selectedFile.uploadTime) }}</div>
                  <div v-if="selectedFile.importTime" class="preview-detail">导入时间：{{ formatTime(selectedFile.importTime) }}</div>
                  <div v-if="selectedFile.captureTime" class="preview-detail">拍摄时间：{{ formatTime(selectedFile.captureTime) }}</div>
                </div>
                <button
                  class="btn btn-primary download-btn"
                  @click="downloadFile(selectedFile.relativePath)"
                >
                  <Download class="btn-icon" />
                  下载文件
                </button>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  File,
  FileArchive,
  FileText,
  Folder,
  Image,
  RefreshCw,
} from 'lucide-vue-next'
import { fileApi } from '@/api/system'
import Sidebar from '@/components/beta/Sidebar.vue'
import { useBetaNavigation } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate } = useBetaNavigation('account')

const isLoading = ref(false)
const folders = ref([])
const rootFiles = ref([])
const folderCount = ref(0)
const totalFiles = ref(0)
const selectedFile = ref(null)
const expandedFolders = ref(new Set())

const isFolderExpanded = (path) => expandedFolders.value.has(path)

const toggleFolder = (path) => {
  const next = new Set(expandedFolders.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  expandedFolders.value = next
}

const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i]
}

const formatTime = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const date = String(value).match(/^\d+$/)
    ? new Date(Number(value))
    : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

const getFileIcon = (ext) => {
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'heic', 'heif']
  const docExts = ['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'csv', 'json', 'xml']
  const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz']
  if (imageExts.includes(ext?.toLowerCase())) return Image
  if (docExts.includes(ext?.toLowerCase())) return FileText
  if (archiveExts.includes(ext?.toLowerCase())) return FileArchive
  return File
}

const isImageFile = (ext) => {
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'heic', 'heif']
  return imageExts.includes(ext?.toLowerCase())
}

const previewUrl = computed(() => {
  if (!selectedFile.value) return null
  return fileApi.getMyPreviewUrl(selectedFile.value.relativePath)
})

const loadTree = async () => {
  isLoading.value = true
  try {
    const result = await fileApi.listMyTree()
    folders.value = result.folders || []
    rootFiles.value = result.rootFiles || []
    folderCount.value = result.folderCount || 0
    totalFiles.value = result.totalFiles || 0

    // 默认展开所有文件夹
    const expanded = new Set()
    for (const f of folders.value) {
      expanded.add(f.path)
    }
    expandedFolders.value = expanded
  } catch (e) {
    console.error('Failed to load file tree', e)
  } finally {
    isLoading.value = false
  }
}

const previewFile = (file) => {
  selectedFile.value = file
}

const closePreview = () => {
  selectedFile.value = null
}

const downloadFile = (relativePath) => {
  fileApi.downloadMy(relativePath)
}

onMounted(() => {
  loadTree()
})
</script>

<style scoped>
/* ---- 布局 ---- */
.ref-app {
  height: 100vh;
  display: flex;
  overflow: hidden;
}

.app-layout {
  display: flex;
  width: 100%;
  height: 100%;
}

.my-files-canvas {
  flex: 1;
  overflow-y: auto;
  background: var(--canvas-bg, #f4f5f7);
}

.my-files-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 28px;
}

/* ---- 页头 ---- */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header-left {
  min-width: 0;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted, #8a8a9a);
  margin: 0;
}

/* ---- 主内容 ---- */
.files-content {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

/* ---- 卡片 ---- */
.card {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
}

/* ---- 文件树面板 ---- */
.tree-panel {
  flex: 2;
  min-width: 0;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
}

.panel-meta {
  font-size: 12px;
  color: var(--text-muted, #8a8a9a);
}

.tree-body {
  padding: 12px;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}

.empty-state {
  padding: 48px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted, #8a8a9a);
}

/* ---- 根目录文件 ---- */
.root-files-section {
  margin-bottom: 8px;
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted, #8a8a9a);
  padding: 4px 8px 6px;
}

/* ---- 文件行 ---- */
.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
}

.file-row:hover {
  background: var(--surface-hover, #f4f5f7);
}

.file-row.active {
  background: rgba(47, 143, 137, 0.08);
  outline: 1px solid rgba(47, 143, 137, 0.3);
}

.file-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: var(--text-muted, #8a8a9a);
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
  margin-top: 2px;
}

.file-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s;
}

.file-row:hover .file-actions,
.file-row.active .file-actions {
  opacity: 1;
}

.icon-btn {
  padding: 4px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 5px;
  background: var(--surface, #fff);
  cursor: pointer;
  display: flex;
  align-items: center;
  color: var(--text-secondary, #4a4a5a);
  transition: background 0.12s;
}

.icon-btn:hover {
  background: var(--surface-hover, #f4f5f7);
}

.action-icon {
  width: 13px;
  height: 13px;
}

/* ---- 文件夹 ---- */
.folder-block {
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid var(--border, #e5e7eb);
  overflow: hidden;
}

.folder-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  background: var(--surface-muted, #f8f9fa);
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}

.folder-header:hover {
  background: var(--surface-hover, #f0f1f3);
}

.chevron-icon {
  width: 14px;
  height: 14px;
  color: var(--text-muted, #8a8a9a);
  flex-shrink: 0;
}

.folder-icon {
  width: 16px;
  height: 16px;
  color: #f59e0b;
  flex-shrink: 0;
}

.folder-info {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.folder-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.folder-count {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
  flex-shrink: 0;
  margin-left: 8px;
}

.folder-files {
  padding: 4px 8px;
}

/* ---- 预览面板 ---- */
.preview-panel {
  flex: 1;
  min-width: 240px;
  max-width: 320px;
}

.text-btn {
  font-size: 12px;
  color: var(--accent, #2f8f89);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

.text-btn:hover {
  text-decoration: underline;
}

.preview-body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-img-wrap {
  aspect-ratio: 1;
  background: var(--surface-muted, #f8f9fa);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.preview-unsupported {
  font-size: 12px;
  color: var(--text-muted, #8a8a9a);
  text-align: center;
  padding: 16px;
}

.preview-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview-filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  word-break: break-all;
}

.preview-detail {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
}

.download-btn {
  width: 100%;
  justify-content: center;
}

/* ---- 按钮 ---- */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent, #2f8f89);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-dark, #267a74);
}

.btn-default {
  background: var(--surface, #fff);
  color: var(--text-primary, #1a1a2e);
  border: 1px solid var(--border, #e5e7eb);
}

.btn-default:hover:not(:disabled) {
  background: var(--surface-hover, #f4f5f7);
}

.btn-icon {
  width: 14px;
  height: 14px;
}

.refresh-btn {
  flex-shrink: 0;
}

/* ---- 动画 ---- */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 1s linear infinite;
}
</style>
