<template>
  <aside class="rail" :class="{ collapsed: isCollapsed }">
    <button
      type="button"
      class="sidebar-toggle"
      @click="isCollapsed = !isCollapsed"
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
          <div v-if="expandedMenus[item.key] && !isCollapsed" class="nav-submenu">
            <button
              v-for="child in item.children"
              :key="child.key"
              type="button"
              class="rail-link submenu-item"
              :class="{ active: child.key === activePage }"
              @click="$emit('navigate', child.key)"
            >
              <component v-if="child.icon" :is="child.icon" class="submenu-icon-svg" />
              <span v-else class="submenu-dot"></span>
              <span>{{ child.label }}</span>
            </button>
          </div>
        </div>
        <!-- 普通导航项 -->
        <button
          v-else
          :key="'item-' + item.key"
          type="button"
          class="rail-link"
          :class="{ active: item.key === activePage, muted: item.disabled }"
          :disabled="item.disabled"
          @click="$emit('navigate', item.key)"
          :title="isCollapsed ? item.label : ''"
        >
          <component v-if="item.icon" :is="item.icon" class="nav-icon-svg" />
          <span v-else class="nav-icon" :style="{ backgroundColor: getIconColor(item.key) }"></span>
          <span>{{ item.label }}</span>
        </button>
      </template>
    </nav>
    <div class="rail-meta">
      <div class="meta-block">
      <div class="meta-title">当前身份</div>
      <div class="meta-value">{{ isCollapsed ? roleLabel.charAt(0) : roleLabel || "未登录" }}</div>
      <div class="meta-caption">
          {{ roleCaption }}
      </div>
    </div>
      <div class="rail-footer">
        <div class="footer-label">下次审计</div>
        <div class="footer-value">12 天</div>
      </div>
      <button type="button" class="ghost rail-guide" @click="router.push('/guide')">
        <span v-if="!isCollapsed">返回 Guide</span>
        <span v-else>Guide</span>
      </button>
      <button type="button" class="ghost rail-exit" @click="$emit('exit')">
        <span v-if="!isCollapsed">返回登录</span>
        <span v-else>Exit</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  BarChart3,
  Bug,
  GitBranch,
  FileCheck,
  FileBarChart,
  Sparkles
} from 'lucide-vue-next';

const router = useRouter();

const props = defineProps({
  roleType: {
    type: String,
    required: true,
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

defineEmits(["exit", "navigate"]);

const isCollapsed = ref(false);

// 展开的菜单状态
const expandedMenus = ref({
  "project-management": false,
});

// 当 activePage 是子菜单项时，自动展开父菜单
watch(() => props.activePage, (newPage) => {
  // 检查是否是 project-management 的子项
  const projectChildren = ['requirements-collection', 'requirements', 'requirements-analysis'];
  if (projectChildren.includes(newPage)) {
    expandedMenus.value['project-management'] = true;
  }
}, { immediate: true });

// Update global CSS variable for sidebar width
watch(isCollapsed, (v) => {
  document.documentElement.style.setProperty('--sidebar-width', v ? '80px' : '260px');
});

const commonNav = [
  { key: "dashboard", label: "概览", icon: LayoutDashboard },
  {
    key: "project-management",
    label: "项目管理",
    icon: FolderKanban,
    children: [
      { key: "requirements-collection", label: "需求采集", icon: Sparkles },
      { key: "requirements", label: "需求", icon: FileText },
      { key: "requirements-analysis", label: "需求分析", icon: BarChart3 },
    ]
  },
  { key: "defects", label: "缺陷与问题", icon: Bug },
  { key: "tracking", label: "追踪", icon: GitBranch },
  { key: "reviews", label: "评审", icon: FileCheck },
  { key: "reports", label: "报告", icon: FileBarChart },
];

const getIconColor = (key) => {
  const colors = {
    dashboard: "#2f8f89",
    "project-management": "#c4692f",
    defects: "#c45b60",
    tracking: "#5d6b76",
    reviews: "#a85424",
    reports: "#1b2730",
    "requirements-collection": "#8b5cf6",
    requirements: "#c4692f",
    "requirements-analysis": "#c4692f",
    "requirements-acquisition": "#c4692f",
  };
  return colors[key] || "#9eabb4";
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

const navItems = computed(() => commonNav);

const roleCaption = computed(() => {
  if (props.roleType === "unified_admin") return "项目管理员";
  if (props.roleType === "unified_member") return "项目成员";
  if (props.roleType === "unified_viewer") return "访客视图";
  return "项目成员";
});
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
</style>
