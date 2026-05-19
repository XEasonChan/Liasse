import { LucideIcon } from "./icons.js";
import { t } from "../i18n.js";

const { reactive, ref } = window.Vue;

const _state = reactive({
  toasts: [],
  nextId: 1,
});

function _dismiss(id) {
  const idx = _state.toasts.findIndex((t) => t.id === id);
  if (idx >= 0) _state.toasts.splice(idx, 1);
}

function push(opts) {
  const id = _state.nextId++;
  const toast = {
    id,
    kind: opts.kind || "info",
    title: opts.title || "",
    body: opts.body || "",
    actionLabel: opts.actionLabel || null,
    action: opts.action || null,
    persist: !!opts.persist,
    durationMs: opts.durationMs || (opts.kind === "error" ? 6000 : 3500),
  };
  _state.toasts.push(toast);
  if (!toast.persist) {
    setTimeout(() => _dismiss(id), toast.durationMs);
  }
  return id;
}

export const toast = {
  info(title, body, opts = {}) { return push({ kind: "info", title, body, ...opts }); },
  success(title, body, opts = {}) { return push({ kind: "success", title, body, ...opts }); },
  warning(title, body, opts = {}) { return push({ kind: "warning", title, body, ...opts }); },
  error(title, body, opts = {}) { return push({ kind: "error", title, body, ...opts }); },
  dismiss(id) { _dismiss(id); },
};

const ICON_FOR_KIND = {
  info: "info",
  success: "check-circle",
  warning: "alert-triangle",
  error: "alert-circle",
};

export const ToastStack = {
  name: "ToastStack",
  components: { LucideIcon },
  setup() {
    function close(id) { _dismiss(id); }
    function trigger(t) {
      try { t.action && t.action(); } finally { _dismiss(t.id); }
    }
    return { state: _state, close, trigger, t, iconFor: (k) => ICON_FOR_KIND[k] || "info" };
  },
  template: `
    <div class="toast-stack">
      <transition-group name="toast">
        <div
          v-for="item in state.toasts"
          :key="item.id"
          class="toast"
          :class="'toast-' + item.kind"
          @click="item.persist || close(item.id)"
        >
          <div class="toast-icon"><lucide-icon :name="iconFor(item.kind)" :size="16" /></div>
          <div class="toast-body">
            <div v-if="item.title" class="toast-title">{{ item.title }}</div>
            <div v-if="item.body" class="toast-text">{{ item.body }}</div>
          </div>
          <button v-if="item.actionLabel" class="toast-action" @click.stop="trigger(item)">{{ item.actionLabel }}</button>
          <button class="toast-close" @click.stop="close(item.id)" :title="t('modal.toastCloseTitle')">
            <lucide-icon name="x" :size="14" />
          </button>
        </div>
      </transition-group>
    </div>
  `,
};
