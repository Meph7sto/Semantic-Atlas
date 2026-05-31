<template>
  <aside ref="railRef" class="rail" :class="{ collapsed: isCollapsed }">
    <button
      type="button"
      class="sidebar-toggle"
      @click="toggleSidebar"
      aria-label="Toggle Sidebar"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="square"
        stroke-linejoin="round"
        style="width: 14px; height: 14px;"
      >
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>

    <div class="brand">
      <div class="brand-mark" v-if="!isCollapsed">Semantic</div>
      <div class="brand-mark" v-else>S</div>
      <div class="brand-sub">Atlas</div>
    </div>
    <nav class="rail-nav">
      <template v-for="item in navItems">
        <!-- 带子菜单的导航项 -->
        <div v-if="item.children && item.children.length > 0" :key="'group-' + item.key" class="nav-group">
          <button
            type="button"
            class="rail-link has-children"
            :class="{
              active: item.key === activePage || isChildActive(item),
              muted: item.disabled,
              expanded: expandedMenus[item.key]
            }"
            :disabled="item.disabled"
            @click="toggleMenu(item.key)"
            :title="isCollapsed ? item.label : ''"
          >
            <component v-if="item.icon" :is="item.icon" class="nav-icon-svg" />
            <span v-else class="nav-icon" :style="{ backgroundColor: getIconColor(item.key) }"></span>
            <span class="nav-label">{{ item.label }}</span>
            <svg
              v-if="!isCollapsed"
              class="nav-chevron"
              :class="{ rotated: expandedMenus[item.key] }"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          <!-- 子菜单 -->
          <Transition :name="isCollapsed ? '' : 'submenu-collapse'">
            <div v-if="expandedMenus[item.key] && !isCollapsed && !isSidebarTransitioning" class="nav-submenu">
              <button
                v-for="child in item.children"
                :key="child.key"
                type="button"
                class="rail-link submenu-item"
                :class="{ active: child.key === activePage }"
                @click="handleNavigateItem(child.key)"
              >
                <component v-if="child.icon" :is="child.icon" class="submenu-icon-svg" />
                <span v-else class="submenu-dot"></span>
                <span>{{ child.label }}</span>
              </button>
            </div>
          </Transition>
        </div>
        <!-- 普通导航项 -->
        <button
          v-else
          :key="'item-' + item.key"
          type="button"
          class="rail-link"
          :class="{ active: item.key === activePage, muted: item.disabled }"
          :disabled="item.disabled"
          @click="handleNavigateItem(item.key)"
          :title="isCollapsed ? item.label : ''"
        >
          <component v-if="item.icon" :is="item.icon" class="nav-icon-svg" />
          <span v-else class="nav-icon" :style="{ backgroundColor: getIconColor(item.key) }"></span>
          <span>{{ item.label }}</span>
        </button>
      </template>
    </nav>
    <div class="rail-meta">
      <button
        type="button"
        class="ghost rail-guide sa-button sa-button--secondary"
        @click="router.push('/guide')"
        :title="isCollapsed ? '返回 Guide' : ''"
      >
        <Compass class="rail-action-icon" />
        <span v-if="!isCollapsed">返回 Guide</span>
      </button>

      <!-- 账户入口（ChatGPT 风格） -->
      <button
        type="button"
        class="account-btn"
        :class="{ 'account-btn--collapsed': isCollapsed, active: props.activePage === 'account' }"
        @click="router.push({ name: 'beta-account' })"
        :title="isCollapsed ? (displayLabel || '个人账户') : ''"
      >
        <!-- 头像：优先使用图片，其次首字母 -->
        <div class="account-avatar" :style="{ backgroundColor: accountAvatarColor }">
          <img
            v-if="currentUser?.avatar_url"
            :src="currentUser.avatar_url"
            :alt="displayLabel"
            class="account-avatar-img"
            @error="onAvatarImgError"
          />
          <span v-else class="account-avatar-letter">{{ avatarLetter }}</span>
        </div>
        <div v-if="!isCollapsed" class="account-info">
          <div class="account-name">{{ displayLabel || '未登录' }}</div>
          <div class="account-role">{{ roleCaption }}</div>
        </div>
        <Settings v-if="!isCollapsed" class="account-settings-icon" />
      </button>

      <button
        type="button"
        class="ghost rail-exit sa-button sa-button--secondary"
        @click="handleLogout"
        :title="isCollapsed ? '退出登录' : ''"
      >
        <LogOut class="rail-action-icon" />
        <span v-if="!isCollapsed">退出登录</span>
      </button>
    </div>

    <div
      v-if="!isCollapsed"
      class="sidebar-resize-handle"
      :class="{ 'is-resizing': isResizing }"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize Sidebar"
      title="拖拽调整侧边栏宽度"
      @pointerdown="startResize"
    ></div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  BarChart3,
  Bug,
  GitBranch,
  FileCheck,
  FileBarChart,
  Sparkles,
  Package,
  Compass,
  LogOut,
  ClipboardList,
  CheckSquare,
  Settings,
  Users,
} from 'lucide-vue-next';

const router = useRouter();
const authStore = useAuthStore();

const props = defineProps({
  roleType: {
    type: String,
    required: false, // 改为非必需，从 localStorage 获取
    default: "",
  },
  roleLabel: {
    type: String,
    default: "",
  },
  borrowerRole: {
    type: String,
    default: "",
  },
  timestamp: {
    type: String,
    default: "",
  },
  notificationCount: {
    type: Number,
    default: 0,
  },
  activePage: {
    type: String,
    default: "dashboard",
  },
});

const emit = defineEmits(["exit", "navigate"]);

const isCollapsed = ref(false);
const isSidebarTransitioning = ref(false);
const railRef = ref(null);
const isResizing = ref(false);

const DEFAULT_SIDEBAR_WIDTH = 260;
const COLLAPSED_SIDEBAR_WIDTH = 80;
const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 420;
const SIDEBAR_WIDTH_STORAGE_KEY = "semantic-atlas.sidebar.width";

// 从 localStorage 获取当前用户信息
const currentUser = ref(null);

onMounted(() => {
  try {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      currentUser.value = JSON.parse(userStr);
    }
  } catch (e) {
    console.error('Failed to parse user data:', e);
  }

  applySidebarWidth();
});

// 导航菜单配置（根据身份动态显示）
const navItemsConfig = computed(() => {
  const identity = authStore.systemIdentity;

  // 超级管理员：全部菜单
  const adminNav = [
    { key: "dashboard", label: "概览", icon: LayoutDashboard },
    { key: "products", label: "产品管理", icon: Package },
    { key: "user-management", label: "人员管理", icon: Users },
    {
      key: "project-management",
      label: "项目管理",
      icon: FolderKanban,
      children: [
        { key: "requirements-collection", label: "需求采集", icon: Sparkles },
        { key: "multimodal-ingestion", label: "多模态采集", icon: Sparkles },
        { key: "requirements-overview", label: "需求列表", icon: FileText },
        { key: "requirements", label: "需求工作台", icon: FileText },
        { key: "requirements-analysis", label: "需求分析", icon: BarChart3 },
        { key: "requirement-graph", label: "需求图谱", icon: GitBranch },
      ]
    },
    { key: "defects", label: "缺陷与问题", icon: Bug },
    { key: "tracking", label: "追踪", icon: GitBranch },
    { key: "reviews", label: "评审", icon: FileCheck },
    { key: "reports", label: "报告", icon: FileBarChart },
  ];

  // 普通用户 (SYS_USER - member/viewer)
  const userNav = [
    { key: "dashboard", label: "概览", icon: LayoutDashboard },
    { key: "products", label: "产品管理", icon: Package },
    {
      key: "project-management",
      label: "项目管理",
      icon: FolderKanban,
      children: [
        { key: "requirements-collection", label: "需求采集", icon: Sparkles },
        { key: "multimodal-ingestion", label: "多模态采集", icon: Sparkles },
        { key: "requirements-overview", label: "需求列表", icon: FileText },
        { key: "requirements", label: "需求工作台", icon: FileText },
        { key: "requirements-analysis", label: "需求分析", icon: BarChart3 },
        { key: "requirement-graph", label: "需求图谱", icon: GitBranch },
      ]
    },
    { key: "defects", label: "缺陷与问题", icon: Bug },
    { key: "tracking", label: "追踪", icon: GitBranch },
    { key: "reviews", label: "评审", icon: FileCheck },
    { key: "reports", label: "报告", icon: FileBarChart },
  ];

  // 甲方客户 (SYS_CLIENT)：只关注已发布/已确认的需求
  const clientNav = [
    { key: "dashboard", label: "需求概览", icon: LayoutDashboard },
    {
      key: "project-management",
      label: "已发布需求",
      icon: FileCheck,
      children: [
        { key: "requirements-overview", label: "需求列表", icon: FileText },
      ]
    },
    { key: "reviews", label: "验收确认", icon: CheckSquare },
  ];

  // 外包成员 (SYS_CONTRACTOR)：聚焦分配给我的任务
  const contractorNav = [
    { key: "dashboard", label: "我的任务", icon: LayoutDashboard },
    {
      key: "project-management",
      label: "分配给我的",
      icon: ClipboardList,
      children: [
        { key: "requirements-overview", label: "需求列表", icon: FileText },
      ]
    },
    { key: "tracking", label: "提交记录", icon: GitBranch },
  ];

  switch (identity) {
    case 'SYS_ADMIN':
      return adminNav;
    case 'SYS_CLIENT':
      return clientNav;
    case 'SYS_CONTRACTOR':
      return contractorNav;
    case 'SYS_USER':
    default:
      return userNav;
  }
});
let sidebarTransitionTimer = null;
let resizeCleanup = null;

// 展开的菜单状态
const EXPANDED_MENUS_STORAGE_KEY = "semantic-atlas.sidebar.expandedMenus";

const getInitialExpandedMenus = () => {
  const defaults = {
    "project-management": false,
    "products": false,
  };

  if (typeof window === "undefined") return defaults;

  try {
    const raw = window.sessionStorage.getItem(EXPANDED_MENUS_STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return defaults;

    return {
      ...defaults,
      ...Object.fromEntries(
        Object.keys(defaults).map((k) => [k, Boolean(parsed[k])])
      ),
    };
  } catch {
    return defaults;
  }
};

const expandedMenus = ref(getInitialExpandedMenus());
const clampSidebarWidth = (value) => {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return DEFAULT_SIDEBAR_WIDTH;
  }

  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, numericValue));
};

const getInitialSidebarWidth = () => {
  if (typeof window === "undefined") return DEFAULT_SIDEBAR_WIDTH;

  try {
    const raw = window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    if (!raw) return DEFAULT_SIDEBAR_WIDTH;
    return clampSidebarWidth(raw);
  } catch {
    return DEFAULT_SIDEBAR_WIDTH;
  }
};

const sidebarWidth = ref(getInitialSidebarWidth());

const applySidebarWidth = () => {
  if (typeof document === "undefined") return;

  const targetWidth = isCollapsed.value ? COLLAPSED_SIDEBAR_WIDTH : sidebarWidth.value;
  document.documentElement.style.setProperty("--sidebar-width", `${targetWidth}px`);
  document.documentElement.style.setProperty("--sidebar-transition-duration", isResizing.value ? "0s" : "0.3s");
};

// 当 activePage 是子菜单项时，自动展开父菜单（但不会自动收缩已展开的菜单）
watch(() => props.activePage, (newPage) => {
  // 检查是否是 project-management 的子项，如果是则自动展开（不在子项时不自动收缩）
  const projectChildren = ['requirements-collection', 'multimodal-ingestion', 'requirements-overview', 'requirements', 'requirements-analysis','requirement-graph'];
  if (projectChildren.includes(newPage) && !isCollapsed.value) {
    expandedMenus.value['project-management'] = true;
  }
}, { immediate: true });

watch(isCollapsed, () => {
  applySidebarWidth();
});

watch(sidebarWidth, (value) => {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(value));
    } catch {
      // ignore storage failures
    }
  }

  if (!isCollapsed.value) {
    applySidebarWidth();
  }
});

watch(isResizing, () => {
  applySidebarWidth();
});

watch(
  expandedMenus,
  (v) => {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(EXPANDED_MENUS_STORAGE_KEY, JSON.stringify(v));
    } catch {
      // ignore storage failures
    }
  },
  { deep: true }
);

const toggleSidebar = () => {
  isCollapsed.value = !isCollapsed.value;
  isSidebarTransitioning.value = true;

  if (sidebarTransitionTimer) {
    clearTimeout(sidebarTransitionTimer);
  }

  sidebarTransitionTimer = window.setTimeout(() => {
    isSidebarTransitioning.value = false;
    sidebarTransitionTimer = null;
  }, 320);
};

const stopResize = () => {
  if (resizeCleanup) {
    resizeCleanup();
    resizeCleanup = null;
  }

  if (typeof document !== "undefined") {
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }

  isResizing.value = false;
};

const startResize = (event) => {
  if (typeof window === "undefined" || isCollapsed.value || window.innerWidth <= 1100) {
    return;
  }

  event.preventDefault();
  event.currentTarget?.setPointerCapture?.(event.pointerId);

  const handlePointerMove = (moveEvent) => {
    const railLeft = railRef.value?.getBoundingClientRect().left ?? 0;
    sidebarWidth.value = clampSidebarWidth(moveEvent.clientX - railLeft);
  };

  const handlePointerUp = () => {
    stopResize();
  };

  resizeCleanup = () => {
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", handlePointerUp);
    window.removeEventListener("pointercancel", handlePointerUp);
  };

  isResizing.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";

  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", handlePointerUp);
  window.addEventListener("pointercancel", handlePointerUp);
};

onBeforeUnmount(() => {
  if (sidebarTransitionTimer) {
    clearTimeout(sidebarTransitionTimer);
  }

  stopResize();
});

const navItems = computed(() => navItemsConfig.value);

const getIconColor = (key) => {
  const colors = {
    dashboard: "#2f8f89",
    products: "#7c3aed",
    "user-management": "#64748b",
    "project-management": "#c4692f",
    defects: "#c45b60",
    tracking: "#5d6b76",
    reviews: "#a85424",
    reports: "#1b2730",
    "requirements-collection": "#8b5cf6",
    "multimodal-ingestion": "#0f766e",
    "requirements-overview": "#2f8f89",
    requirements: "#c4692f",
    "requirements-session": "#5d6b76",
    "requirements-analysis": "#c4692f",
    "requirement-graph": "#0f766e",
    "requirement-replay": "#5d6b76",
  };
  return colors[key] || "#9eabb4";
};

const handleNavigateItem = (key) => {
  emit('navigate', key);
};

// 切换菜单展开状态
const toggleMenu = (key) => {
  expandedMenus.value[key] = !expandedMenus.value[key];
};

// 检查子菜单是否有激活项
const isChildActive = (item) => {
  if (!item.children) return false;
  return item.children.some(child => child.key === props.activePage);
};

// 头像首字母
const avatarLetter = computed(() => {
  const name = currentUser.value?.display_name || currentUser.value?.username || '?'
  return name.charAt(0).toUpperCase()
})

// 头像背景色（基于用户名哈希）
const accountAvatarColor = computed(() => {
  const colors = [
    '#2f8f89', '#7c3aed', '#c4692f', '#c45b60',
    '#5d6b76', '#a85424', '#1b2730', '#8b5cf6',
  ]
  const name = currentUser.value?.username || ''
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})

// 头像加载失败时清除 URL
const onAvatarImgError = () => {
  if (currentUser.value) {
    currentUser.value = { ...currentUser.value, avatar_url: null }
  }
}

// 计算显示的用户名或显示名
const displayLabel = computed(() => {
  if (currentUser.value?.display_name) {
    return currentUser.value.display_name;
  }
  if (currentUser.value?.username) {
    return currentUser.value.username;
  }
  return props.roleLabel;
});

// 计算当前用户的角色说明
const roleCaption = computed(() => {
  // 优先使用 authStore 中的 identityLabel
  if (authStore.identityLabel) {
    return authStore.identityLabel;
  }
  // 兼容旧逻辑
  const role = currentUser.value?.role || props.roleType;
  if (role === "admin") return "管理员";
  if (role === "member") return "项目成员";
  if (role === "viewer") return "访客";
  return "项目成员";
});

// 处理退出登录
const handleLogout = async () => {
  try {
    await authStore.logout();
  } catch (e) {
    console.error('Failed to clear auth data:', e);
  }
  router.push({ name: 'beta-login' });
};
</script>

<style scoped>
.nav-icon-svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke-width: 2;
}

.submenu-icon-svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  stroke-width: 2;
  opacity: 0.7;
}

.rail-link.active .nav-icon-svg,
.submenu-item.active .submenu-icon-svg {
  opacity: 1;
}

.submenu-collapse-enter-active,
.submenu-collapse-leave-active {
  overflow: hidden;
  transition: max-height 0.3s ease, opacity 0.24s ease, transform 0.3s ease;
}

.submenu-collapse-enter-from,
.submenu-collapse-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-6px);
}

.submenu-collapse-enter-to,
.submenu-collapse-leave-from {
  max-height: 220px;
  opacity: 1;
  transform: translateY(0);
}

.rail-action-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* ---- 账户入口按钮（ChatGPT 风格） ---- */
.account-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
  color: inherit;
}

.account-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}

.account-btn.active {
  background: rgba(47, 143, 137, 0.15);
  border-color: rgba(47, 143, 137, 0.25);
}

.account-btn--collapsed {
  justify-content: center;
  padding: 8px;
}

.account-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.account-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.account-avatar-letter {
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  line-height: 1;
}

.account-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.account-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--sidebar-text, var(--ink-950, #1b2730));
}

.account-role {
  font-size: 11px;
  color: var(--sidebar-muted, var(--ink-500, #5d6b76));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-settings-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  opacity: 0.5;
  color: var(--sidebar-muted, var(--ink-500, #5d6b76));
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 12px;
  height: 100%;
  cursor: col-resize;
  touch-action: none;
  z-index: 12;
  opacity: 0;
  transition: opacity 0.2s ease;
  background: linear-gradient(
    90deg,
    transparent 0,
    transparent calc(100% - 2px),
    rgba(28, 40, 52, 0.16) calc(100% - 2px),
    rgba(28, 40, 52, 0.16) 100%
  );
}

.rail:hover .sidebar-resize-handle,
.sidebar-resize-handle.is-resizing {
  opacity: 1;
}
</style>
