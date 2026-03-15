<script setup>
import { ref, onMounted, computed } from 'vue'
import { fileApi } from '@/api/system'
import { FolderUp, RefreshCw, Download, Trash2, Eye, FileText, Image, File, FileArchive, ChevronDown, ChevronRight, User } from 'lucide-vue-next'

const filesByUser = ref({})
const isLoading = ref(false)
const selectedFile = ref(null)
const isDeleting = ref(false)
const expandedUsers = ref(new Set())

const formatFileSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i]
}

const formatTime = (isoString) => {
    if (!isoString) return '-'
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

const getFileIcon = (ext) => {
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']
    const docExts = ['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'csv', 'json', 'xml']
    const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz']

    if (imageExts.includes(ext?.toLowerCase())) return Image
    if (docExts.includes(ext?.toLowerCase())) return FileText
    if (archiveExts.includes(ext?.toLowerCase())) return FileArchive
    return File
}

const isImageFile = (ext) => {
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
    return imageExts.includes(ext?.toLowerCase())
}

const isUserExpanded = (userId) => {
    return expandedUsers.value.has(userId)
}

const toggleUserFolder = (userId) => {
    if (expandedUsers.value.has(userId)) {
        expandedUsers.value.delete(userId)
    } else {
        expandedUsers.value.add(userId)
    }
}

const loadFiles = async () => {
    isLoading.value = true
    try {
        const result = await fileApi.listAll()
        filesByUser.value = result.files || {}
        // 默认展开第一个用户
        const userIds = Object.keys(filesByUser.value)
        if (userIds.length > 0 && expandedUsers.value.size === 0) {
            expandedUsers.value.add(userIds[0])
        }
    } catch (e) {
        console.error('Failed to load files', e)
        alert('Failed to load files: ' + (e.message || e))
    } finally {
        isLoading.value = false
    }
}

const downloadFile = (filename) => {
    fileApi.download(filename)
}

const previewFile = (file) => {
    selectedFile.value = file
}

const closePreview = () => {
    selectedFile.value = null
}

const deleteFile = async (filename) => {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return
    isDeleting.value = true
    try {
        await fileApi.delete(filename)
        await loadFiles()
        if (selectedFile.value?.filename === filename) {
            selectedFile.value = null
        }
    } catch (e) {
        console.error('Failed to delete file', e)
        alert('Failed to delete file: ' + (e.message || e))
    } finally {
        isDeleting.value = false
    }
}

const previewUrl = computed(() => {
    if (!selectedFile.value) return null
    return `/api/v2/uploads/${encodeURIComponent(selectedFile.value.filename)}`
})

const totalFiles = computed(() => {
    return Object.values(filesByUser.value).reduce((sum, files) => sum + files.length, 0)
})

const userCount = computed(() => {
    return Object.keys(filesByUser.value).length
})

onMounted(() => {
    loadFiles()
})
</script>

<template>
    <div class="h-full w-full overflow-y-auto">
        <div class="flex flex-col min-h-full max-w-6xl mx-auto px-6 py-8 gap-6">
            <div class="flex items-center justify-between">
                <div>
                    <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight flex items-center gap-2">
                        <FolderUp class="w-7 h-7" />
                        File Receive
                    </h2>
                    <p class="text-zinc-500 mt-2 text-sm">View and manage files uploaded from mobile devices (All Users).</p>
                </div>
                <button @click="loadFiles" :disabled="isLoading"
                    class="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-lg text-sm hover:bg-zinc-800 transition-colors disabled:opacity-50">
                    <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
                    Refresh
                </button>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2">
                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="flex items-center justify-between mb-4">
                            <div class="text-sm font-semibold text-zinc-700">Uploaded Files</div>
                            <div class="text-xs text-zinc-500">{{ userCount }} Users | {{ totalFiles }} Files</div>
                        </div>

                        <div v-if="isLoading" class="text-center text-zinc-400 py-12">
                            Loading files...
                        </div>
                        <div v-else-if="userCount === 0" class="text-center text-zinc-400 py-12">
                            No files uploaded yet.
                        </div>
                        <div v-else class="space-y-3 max-h-[60vh] overflow-y-auto">
                            <div v-for="(files, userId) in filesByUser" :key="userId" class="border border-zinc-200 rounded-lg overflow-hidden">
                                <!-- User Folder Header -->
                                <div @click="toggleUserFolder(userId)"
                                    class="flex items-center gap-3 px-4 py-3 bg-zinc-50 hover:bg-zinc-100 cursor-pointer transition-colors select-none">
                                    <component :is="isUserExpanded(userId) ? ChevronDown : ChevronRight"
                                        class="w-4 h-4 text-zinc-500 flex-shrink-0" />
                                    <User class="w-5 h-5 text-zinc-500 flex-shrink-0" />
                                    <div class="flex-1 min-w-0">
                                        <div class="text-sm font-medium text-zinc-800 truncate">User: {{ userId }}</div>
                                        <div class="text-xs text-zinc-500">{{ files.length }} file(s)</div>
                                    </div>
                                </div>

                                <!-- User Files -->
                                <div v-show="isUserExpanded(userId)" class="divide-y divide-zinc-200">
                                    <div v-for="file in files" :key="file.filename"
                                        class="flex items-center gap-4 px-4 py-3 hover:bg-zinc-50 transition-colors"
                                        :class="{ 'ring-2 ring-zinc-900': selectedFile?.filename === file.filename }">
                                        <component :is="getFileIcon(file.extension)" class="w-8 h-8 text-zinc-400 flex-shrink-0" />
                                        <div class="flex-1 min-w-0">
                                            <div class="text-sm font-medium text-zinc-800 truncate" :title="file.originalFilename">
                                                {{ file.originalFilename }}
                                            </div>
                                            <div class="text-xs text-zinc-500 mt-1">
                                                {{ formatFileSize(file.fileSize) }} | {{ formatTime(file.uploadTime) }}
                                            </div>
                                            <div v-if="file.description" class="text-xs text-zinc-400 mt-1 truncate">
                                                {{ file.description }}
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-2 flex-shrink-0">
                                            <button v-if="isImageFile(file.extension)" @click="previewFile(file)"
                                                class="p-2 border border-zinc-200 rounded-lg hover:bg-zinc-100 transition-colors"
                                                title="Preview">
                                                <Eye class="w-4 h-4 text-zinc-600" />
                                            </button>
                                            <button @click="downloadFile(file.filename)"
                                                class="p-2 border border-zinc-200 rounded-lg hover:bg-zinc-100 transition-colors"
                                                title="Download">
                                                <Download class="w-4 h-4 text-zinc-600" />
                                            </button>
                                            <button @click="deleteFile(file.filename)" :disabled="isDeleting"
                                                class="p-2 border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                                                title="Delete">
                                                <Trash2 class="w-4 h-4 text-red-500" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div>
                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="text-sm font-semibold text-zinc-700 mb-4">Preview</div>
                        <div v-if="!selectedFile" class="text-center text-zinc-400 py-12 text-sm">
                            Select an image file to preview
                        </div>
                        <div v-else class="space-y-4">
                            <div class="aspect-square bg-zinc-100 rounded-lg overflow-hidden flex items-center justify-center">
                                <img :src="previewUrl" :alt="selectedFile.originalFilename"
                                    class="max-w-full max-h-full object-contain" />
                            </div>
                            <div class="space-y-2">
                                <div class="text-sm font-medium text-zinc-800 truncate">
                                    {{ selectedFile.originalFilename }}
                                </div>
                                <div class="text-xs text-zinc-500">
                                    <div>User: {{ selectedFile.user_id || '-' }}</div>
                                    <div>Size: {{ formatFileSize(selectedFile.fileSize) }}</div>
                                    <div>Type: {{ selectedFile.mimeType }}</div>
                                    <div>Uploaded: {{ formatTime(selectedFile.uploadTime) }}</div>
                                </div>
                                <div class="flex items-center gap-2 pt-2">
                                    <button @click="downloadFile(selectedFile.filename)"
                                        class="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-zinc-900 text-white rounded-lg text-sm hover:bg-zinc-800 transition-colors">
                                        <Download class="w-4 h-4" />
                                        Download
                                    </button>
                                    <button @click="closePreview"
                                        class="px-3 py-2 border border-zinc-200 rounded-lg text-sm hover:bg-zinc-50 transition-colors">
                                        Close
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="mt-6 p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="text-sm font-semibold text-zinc-700 mb-4">Upload Info</div>
                        <div class="text-xs text-zinc-500 space-y-2">
                            <p>Files uploaded from mobile devices are organized by user.</p>
                            <p>Click on a user folder to expand/collapse their files.</p>
                            <p>Supported formats: images, documents, archives (max 50MB)</p>
                            <p class="font-medium text-zinc-600">Admin Only: View all users' files</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
