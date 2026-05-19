/**
 * Dialog 家族 — System D · Cobalt & Lavender 风格的对话框组件
 *
 * 参照 Apple HIG「Alert / Sheet / Modal」三档：
 *   • alert()    单按钮信息提示
 *   • confirm()  二选一（默认 / 破坏性 / 警告）
 *   • prompt()   一个输入框 + 确认 / 取消
 *
 * 全部走同一个 `BaseDialog` 容器，行为模仿 native dialog 但视觉/键盘交互可控：
 *   - 按 Esc 取消；按 Enter 确认（input 有焦点时也算）
 *   - 点 backdrop 关闭（除非 dismissible=false）
 *   - 自动聚焦：prompt 聚焦 input，alert/confirm 聚焦默认按钮
 *   - 队列：多个 dialog 串行显示，不重叠
 *
 * Imperative API（替换 window.prompt / alert / confirm）：
 *   import { dialog } from "./dialog.js";
 *   const ok = await dialog.confirm({ title, body, tone: "danger" });
 *   const name = await dialog.prompt({ title, defaultValue });   // 返回 string|null
 *   await dialog.alert({ title, body, tone: "success" });
 *
 * 必须先把 <dialog-host /> 挂到 app 根上才能用 imperative API。
 */
import { LucideIcon } from "./icons.js";
import { t } from "../i18n.js";

const { reactive, nextTick } = window.Vue;

// ---------- 模块级队列 + 状态 ----------
//
// queue: 等待显示的请求列表，每项 { resolve, type, options, id }
// current: 当前正在显示的请求；显示中时 active=true
const state = reactive({
  current: null,
  queue: [],
  active: false,
  inputValue: "",
  inputError: null,
});

let _idSeq = 0;
function _enqueue(type, options) {
  return new Promise((resolve) => {
    state.queue.push({ id: ++_idSeq, type, options: options || {}, resolve });
    _drain();
  });
}

function _drain() {
  if (state.active || state.queue.length === 0) return;
  const next = state.queue.shift();
  state.current = next;
  state.inputValue = (next.options.defaultValue ?? "");
  state.inputError = null;
  state.active = true;
}

function _resolve(value) {
  if (!state.current) return;
  const { resolve } = state.current;
  state.active = false;
  state.current = null;
  resolve(value);
  // queue next on next tick to let DOM unmount cleanly
  nextTick(_drain);
}

// 公开的 imperative API
export const dialog = {
  alert(options) {
    return _enqueue("alert", options);
  },
  confirm(options) {
    return _enqueue("confirm", options);
  },
  prompt(options) {
    return _enqueue("prompt", options);
  },
};


// ---------- DialogHost 组件 ----------

const TONE_TO_ICON = {
  default: "info",
  danger: "alert-octagon",
  warning: "alert-triangle",
  success: "check-circle",
  question: "help-circle",
};

export const DialogHost = {
  name: "DialogHost",
  components: { LucideIcon },
  data() {
    return { state };
  },
  computed: {
    visible() { return this.state.active && !!this.state.current; },
    type() { return this.state.current?.type || "alert"; },
    options() { return this.state.current?.options || {}; },
    tone() { return this.options.tone || (this.type === "confirm" ? "question" : "default"); },
    iconName() {
      if (this.options.icon) return this.options.icon;
      return TONE_TO_ICON[this.tone] || "info";
    },
    title() { return this.options.title || ""; },
    subtitle() { return this.options.subtitle || ""; },
    body() { return this.options.body || ""; },
    confirmLabel() {
      return this.options.confirmLabel
        || (this.type === "alert" ? t("dialog.ok") : t("dialog.confirm"));
    },
    cancelLabel() {
      return this.options.cancelLabel || t("dialog.cancel");
    },
    confirmClass() {
      // tone=danger → destructive button；其它走 primary
      if (this.tone === "danger") return "btn btn-destructive";
      return "btn btn-primary";
    },
    iconToneClass() {
      const map = {
        danger: "tone-danger",
        warning: "tone-warning",
        success: "tone-success",
      };
      return map[this.tone] || "";
    },
    dismissible() {
      // alert 默认可点 backdrop 关；confirm/prompt 默认不可（要求显式选择）
      const o = this.options;
      if (o.dismissible !== undefined) return !!o.dismissible;
      return this.type === "alert";
    },
    placeholder() { return this.options.placeholder || ""; },
    validator() { return this.options.validator || null; },
  },
  watch: {
    visible(v) {
      if (v) {
        // 自动聚焦：prompt 聚焦 input；alert/confirm 聚焦默认按钮
        nextTick(() => {
          const root = this.$refs.card;
          if (!root) return;
          const target = this.type === "prompt"
            ? root.querySelector("input.modal-input")
            : root.querySelector("button.btn-primary, button.btn-destructive");
          if (target) target.focus();
        });
      }
    },
  },
  methods: {
    onConfirm() {
      if (this.type === "prompt") {
        const value = this.state.inputValue;
        // validator 返回 null/undefined = ok，返回 string = error message
        if (typeof this.validator === "function") {
          const err = this.validator(value);
          if (err) { this.state.inputError = err; return; }
        }
        _resolve(value);
      } else if (this.type === "confirm") {
        _resolve(true);
      } else {
        _resolve(undefined);
      }
    },
    onCancel() {
      if (this.type === "prompt") _resolve(null);
      else if (this.type === "confirm") _resolve(false);
      else _resolve(undefined);
    },
    onBackdropClick() {
      if (this.dismissible) this.onCancel();
    },
    onKeydown(e) {
      if (!this.visible) return;
      if (e.key === "Escape") {
        e.preventDefault();
        this.onCancel();
      } else if (e.key === "Enter") {
        // 在 textarea 里允许换行；只在 input 或按钮上拦截
        const tag = (e.target.tagName || "").toLowerCase();
        if (tag === "textarea") return;
        e.preventDefault();
        this.onConfirm();
      }
    },
  },
  mounted() {
    document.addEventListener("keydown", this.onKeydown);
  },
  beforeUnmount() {
    document.removeEventListener("keydown", this.onKeydown);
  },
  template: `
    <transition name="dialog-fade">
      <div
        v-if="visible"
        class="modal-backdrop"
        role="presentation"
        @click.self="onBackdropClick"
      >
        <div
          ref="card"
          class="modal-card"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="'dlg-title-' + state.current.id"
        >
          <div class="modal-header">
            <div class="modal-icon" :class="iconToneClass">
              <lucide-icon :name="iconName" :size="18" />
            </div>
            <div class="modal-titles">
              <div class="modal-title" :id="'dlg-title-' + state.current.id">{{ title }}</div>
              <div class="modal-subtitle" v-if="subtitle">{{ subtitle }}</div>
            </div>
          </div>

          <div class="modal-body" v-if="body" style="white-space:pre-wrap">{{ body }}</div>

          <input
            v-if="type === 'prompt'"
            class="modal-input"
            type="text"
            v-model="state.inputValue"
            :placeholder="placeholder"
            :aria-invalid="!!state.inputError"
            autocomplete="off"
            spellcheck="false"
          />
          <div v-if="state.inputError" class="modal-error">{{ state.inputError }}</div>

          <div class="modal-actions">
            <button
              v-if="type !== 'alert'"
              class="btn btn-ghost"
              type="button"
              @click="onCancel"
            >{{ cancelLabel }}</button>
            <button
              :class="confirmClass"
              type="button"
              @click="onConfirm"
            >{{ confirmLabel }}</button>
          </div>
        </div>
      </div>
    </transition>
  `,
};
