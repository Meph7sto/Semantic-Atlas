<script setup>
import { computed, onMounted, ref } from 'vue'
import { fileApi } from '@/api/system'
import {
    ChevronDown,
    ChevronRight,
    Download,
    Eye,
    File,
    FileArchive,
    FileText,
    Folder,
    FolderUp,
    Image,
    RefreshCw,
    Trash2,
    User,
} from 'lucide-vue-next'

const users = ref([])
const isLoading = ref(false)
const isDeleting = ref(false)
const selectedFile = ref(null)
const expandedUsers = ref(new Set())
const expandedFolders = ref(new Set())

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

    if (Number.isNaN(date.getTime())) {
        return String(value)
    }

    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
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

const makeFolderKey = (userId, path) => `${userId}::${path}`

const isUserExpanded = (userId) => expandedUsers.value.has(userId)
const isFolderExpanded = (userId, path) => expandedFolders.value.has(makeFolderKey(userId, path))

const toggleUser = (userId) => {
    if (expandedUsers.value.has(userId)) {
        expandedUsers.value.delete(userId)
        return
    }
    expandedUsers.value.add(userId)
}

const toggleFolder = (userId, path) => {
    const key = makeFolderKey(userId, path)
    if (expandedFolders.value.has(key)) {
        expandedFolders.value.delete(key)
        return
    }
    expandedFolders.value.add(key)
}

const loadFiles = async () => {
    isLoading.value = true
    try {
        const result = await fileApi.listTree()
        users.value = result.users || []

        if (users.value.length > 0 && expandedUsers.value.size === 0) {
            expandedUsers.value.add(users.value[0].userId)
        }
    } catch (e) {
        console.error('Failed to load files', e)
        alert('Failed to load files: ' + (e.message || e))
    } finally {
        isLoading.value = false
    }
}

const previewFile = (userId, file) => {
    selectedFile.value = { ...file, userId }
}

const closePreview = () => {
    selectedFile.value = null
}

const downloadFile = (userId, relativePath) => {
    fileApi.downloadAdmin(userId, relativePath)
}

const deleteFile = async (userId, relativePath, displayName) => {
    if (!confirm(`Are you sure you want to delete "${displayName}"?`)) return
    isDeleting.value = true
    try {
        await fileApi.deleteAdmin(userId, relativePath)
        if (
            selectedFile.value &&
            selectedFile.value.userId === userId &&
            selectedFile.value.relativePath === relativePath
        ) {
            selectedFile.value = null
        }
        await loadFiles()
    } catch (e) {
        console.error('Failed to delete file', e)
        alert('Failed to delete file: ' + (e.message || e))
    } finally {
        isDeleting.value = false
    }
}

const previewUrl = computed(() => {
    if (!selectedFile.value) return null
    return fileApi.getAdminPreviewUrl(selectedFile.value.userId, selectedFile.value.relativePath)
})

const totalFiles = computed(() => {
    return users.value.reduce((sum, user) => sum + (user.totalFiles || 0), 0)
})

const userCount = computed(() => users.value.length)

onMounted(() => {
    loadFiles()
})
</script>

<template>
    <div class="h-full w-full overflow-y-auto">
        <div class="flex min-h-full max-w-7xl flex-col gap-6 px-6 py-8 mx-auto">
            <div class="flex items-center justify-between">
                <div>
                    <h2 class="flex items-center gap-2 text-3xl font-semibold tracking-tight text-zinc-800">
                        <FolderUp class="w-7 h-7" />
                        File Receive
                    </h2>
                    <p class="mt-2 text-sm text-zinc-500">
                        Browse uploaded files by user and folder. Folder structure from mobile uploads is preserved.
                    </p>
                </div>
                <button
                    @click="loadFiles"
                    :disabled="isLoading"
                    class="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white transition-colors hover:bg-zinc-800 disabled:opacity-50"
                >
                    <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': isLoading }" />
                    Refresh
                </button>
            </div>

            <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div class="lg:col-span-2">
                    <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                        <div class="mb-4 flex items-center justify-between">
                            <div class="text-sm font-semibold text-zinc-700">Cloud File Structure</div>
                            <div class="text-xs text-zinc-500">{{ userCount }} Users | {{ totalFiles }} Files</div>
                        </div>

                        <div v-if="isLoading" class="py-12 text-center text-zinc-400">
                            Loading files...
                        </div>
                        <div v-else-if="userCount === 0" class="py-12 text-center text-zinc-400">
                            No files uploaded yet.
                        </div>
                        <div v-else class="max-h-[65vh] space-y-4 overflow-y-auto">
                            <div
                                v-for="user in users"
                                :key="user.userId"
                                class="overflow-hidden rounded-lg border border-zinc-200"
                            >
                                <div
                                    class="flex cursor-pointer select-none items-center gap-3 bg-zinc-50 px-4 py-3 transition-colors hover:bg-zinc-100"
                                    @click="toggleUser(user.userId)"
                                >
                                    <component
                                        :is="isUserExpanded(user.userId) ? ChevronDown : ChevronRight"
                                        class="h-4 w-4 flex-shrink-0 text-zinc-500"
                                    />
                                    <User class="h-5 w-5 flex-shrink-0 text-zinc-500" />
                                    <div class="min-w-0 flex-1">
                                        <div class="truncate text-sm font-medium text-zinc-800">
                                            User: {{ user.userId }}
                                        </div>
                                        <div class="text-xs text-zinc-500">
                                            {{ user.folderCount }} folder(s) | {{ user.totalFiles }} file(s)
                                        </div>
                                    </div>
                                </div>

                                <div v-show="isUserExpanded(user.userId)" class="space-y-3 bg-white p-3">
                                    <div
                                        v-if="user.rootFiles?.length"
                                        class="rounded-lg border border-dashed border-zinc-200 p-3"
                                    >
                                        <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                                            Root Files
                                        </div>
                                        <div class="space-y-2">
                                            <div
                                                v-for="file in user.rootFiles"
                                                :key="`${user.userId}:${file.relativePath}`"
                                                class="flex items-center gap-4 rounded-lg px-3 py-2 transition-colors hover:bg-zinc-50"
                                                :class="{ 'ring-2 ring-zinc-900': selectedFile?.userId === user.userId && selectedFile?.relativePath === file.relativePath }"
                                            >
                                                <component :is="getFileIcon(file.extension)" class="h-8 w-8 flex-shrink-0 text-zinc-400" />
                                                <div class="min-w-0 flex-1">
                                                    <div class="truncate text-sm font-medium text-zinc-800" :title="file.originalFilename">
                                                        {{ file.originalFilename }}
                                                    </div>
                                                    <div class="mt-1 text-xs text-zinc-500">
                                                        {{ formatFileSize(file.fileSize) }} | {{ formatTime(file.uploadTime) }}
                                                    </div>
                                                </div>
                                                <div class="flex flex-shrink-0 items-center gap-2">
                                                    <button
                                                        v-if="isImageFile(file.extension)"
                                                        class="rounded-lg border border-zinc-200 p-2 transition-colors hover:bg-zinc-100"
                                                        title="Preview"
                                                        @click="previewFile(user.userId, file)"
                                                    >
                                                        <Eye class="h-4 w-4 text-zinc-600" />
                                                    </button>
                                                    <button
                                                        class="rounded-lg border border-zinc-200 p-2 transition-colors hover:bg-zinc-100"
                                                        title="Download"
                                                        @click="downloadFile(user.userId, file.relativePath)"
                                                    >
                                                        <Download class="h-4 w-4 text-zinc-600" />
                                                    </button>
                                                    <button
                                                        class="rounded-lg border border-red-200 p-2 transition-colors hover:bg-red-50 disabled:opacity-50"
                                                        title="Delete"
                                                        :disabled="isDeleting"
                                                        @click="deleteFile(user.userId, file.relativePath, file.originalFilename || file.filename)"
                                                    >
                                                        <Trash2 class="h-4 w-4 text-red-500" />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div
                                        v-for="folder in user.folders"
                                        :key="`${user.userId}:${folder.path}`"
                                        class="overflow-hidden rounded-lg border border-zinc-200"
                                    >
                                        <div
                                            class="flex cursor-pointer select-none items-center gap-3 bg-zinc-50 px-4 py-3 transition-colors hover:bg-zinc-100"
                                            @click="toggleFolder(user.userId, folder.path)"
                                        >
                                            <component
                                                :is="isFolderExpanded(user.userId, folder.path) ? ChevronDown : ChevronRight"
                                                class="h-4 w-4 flex-shrink-0 text-zinc-500"
                                            />
                                            <Folder class="h-5 w-5 flex-shrink-0 text-amber-500" />
                                            <div class="min-w-0 flex-1">
                                                <div class="truncate text-sm font-medium text-zinc-800">
                                                    {{ folder.path }}
                                                </div>
                                                <div class="text-xs text-zinc-500">
                                                    {{ folder.fileCount }} file(s)
                                                </div>
                                            </div>
                                        </div>

                                        <div v-show="isFolderExpanded(user.userId, folder.path)" class="divide-y divide-zinc-200">
                                            <div
                                                v-for="file in folder.files"
                                                :key="`${user.userId}:${file.relativePath}`"
                                                class="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-zinc-50"
                                                :class="{ 'ring-2 ring-zinc-900': selectedFile?.userId === user.userId && selectedFile?.relativePath === file.relativePath }"
                                            >
                                                <component :is="getFileIcon(file.extension)" class="h-8 w-8 flex-shrink-0 text-zinc-400" />
                                                <div class="min-w-0 flex-1">
                                                    <div class="truncate text-sm font-medium text-zinc-800" :title="file.originalFilename">
                                                        {{ file.originalFilename }}
                                                    </div>
                                                    <div class="mt-1 text-xs text-zinc-500">
                                                        {{ formatFileSize(file.fileSize) }} | {{ formatTime(file.uploadTime) }}
                                                    </div>
                                                    <div class="mt-1 truncate text-xs text-zinc-400">
                                                        {{ file.relativePath }}
                                                    </div>
                                                </div>
                                                <div class="flex flex-shrink-0 items-center gap-2">
                                                    <button
                                                        v-if="isImageFile(file.extension)"
                                                        class="rounded-lg border border-zinc-200 p-2 transition-colors hover:bg-zinc-100"
                                                        title="Preview"
                                                        @click="previewFile(user.userId, file)"
                                                    >
                                                        <Eye class="h-4 w-4 text-zinc-600" />
                                                    </button>
                                                    <button
                                                        class="rounded-lg border border-zinc-200 p-2 transition-colors hover:bg-zinc-100"
                                                        title="Download"
                                                        @click="downloadFile(user.userId, file.relativePath)"
                                                    >
                                                        <Download class="h-4 w-4 text-zinc-600" />
                                                    </button>
                                                    <button
                                                        class="rounded-lg border border-red-200 p-2 transition-colors hover:bg-red-50 disabled:opacity-50"
                                                        title="Delete"
                                                        :disabled="isDeleting"
                                                        @click="deleteFile(user.userId, file.relativePath, file.originalFilename || file.filename)"
                                                    >
                                                        <Trash2 class="h-4 w-4 text-red-500" />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div>
                    <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                        <div class="mb-4 text-sm font-semibold text-zinc-700">Preview</div>
                        <div v-if="!selectedFile" class="py-12 text-center text-sm text-zinc-400">
                            Select an image file to preview
                        </div>
                        <div v-else class="space-y-4">
                            <div class="flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-zinc-100">
                                <img
                                    v-if="isImageFile(selectedFile.extension)"
                                    :src="previewUrl"
                                    :alt="selectedFile.originalFilename"
                                    class="max-h-full max-w-full object-contain"
                                />
                                <div v-else class="px-4 text-center text-sm text-zinc-500">
                                    Preview is available for image files only.
                                </div>
                            </div>
                            <div class="space-y-2 text-xs text-zinc-500">
                                <div class="truncate text-sm font-medium text-zinc-800">
                                    {{ selectedFile.originalFilename }}
                                </div>
                                <div>User: {{ selectedFile.userId }}</div>
                                <div>Folder: {{ selectedFile.folder || '(root)' }}</div>
                                <div>Path: {{ selectedFile.relativePath }}</div>
                                <div>Size: {{ formatFileSize(selectedFile.fileSize) }}</div>
                                <div>Type: {{ selectedFile.mimeType }}</div>
                                <div>Uploaded: {{ formatTime(selectedFile.uploadTime) }}</div>
                                <div>Imported: {{ formatTime(selectedFile.importTime) }}</div>
                                <div>Captured: {{ formatTime(selectedFile.captureTime) }}</div>
                            </div>
                            <div class="flex items-center gap-2 pt-2">
                                <button
                                    class="flex flex-1 items-center justify-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white transition-colors hover:bg-zinc-800"
                                    @click="downloadFile(selectedFile.userId, selectedFile.relativePath)"
                                >
                                    <Download class="h-4 w-4" />
                                    Download
                                </button>
                                <button
                                    class="rounded-lg border border-zinc-200 px-3 py-2 text-sm transition-colors hover:bg-zinc-50"
                                    @click="closePreview"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="mt-6 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                        <div class="mb-4 text-sm font-semibold text-zinc-700">Upload Info</div>
                        <div class="space-y-2 text-xs text-zinc-500">
                            <p>Files are grouped by user and then by uploaded folder path.</p>
                            <p>Imported time and capture time are persisted with each image when the mobile app provides them.</p>
                            <p>Preview, download, and delete actions now target the exact cloud path instead of a flattened filename.</p>
                            <p class="font-medium text-zinc-600">Admin Only: View all users' uploaded folder structures</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
