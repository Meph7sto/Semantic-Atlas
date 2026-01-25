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
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="rail-link"
        :class="{ active: item.key === activePage, muted: item.disabled }"
        :disabled="item.disabled"
        @click="$emit('navigate', item.key)"
        :title="isCollapsed ? item.label : ''"
      >
        <span class="nav-icon" :style="{ backgroundColor: getIconColor(item.key) }"></span>
        <span>{{ item.label }}</span>
      </button>
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
      <button type="button" class="ghost rail-exit" @click="$emit('exit')">
        <span v-if="!isCollapsed">返回登录</span>
        <span v-else>Exit</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";

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

// Update global CSS variable for sidebar width
watch(isCollapsed, (v) => {
  document.documentElement.style.setProperty('--sidebar-width', v ? '80px' : '260px');
});

const commonNav = [
  { key: "dashboard", label: "概览" },
  { key: "project-management", label: "项目管理" },
  { key: "defects", label: "缺陷与问题" },
  { key: "tracking", label: "追踪" },
  { key: "reviews", label: "评审" },
  { key: "reports", label: "报告" },
];

const getIconColor = (key) => {
  const colors = {
    dashboard: "#2f8f89",
    "project-management": "#c4692f",
    defects: "#c45b60",
    tracking: "#5d6b76",
    reviews: "#a85424",
    reports: "#1b2730"
  };
  return colors[key] || "#9eabb4";
};

const navItems = computed(() => commonNav);

const roleCaption = computed(() => {
  if (props.roleType === "unified_admin") return "项目管理员";
  if (props.roleType === "unified_member") return "项目成员";
  if (props.roleType === "unified_viewer") return "访客视图";
  return "项目成员";
});
</script>
