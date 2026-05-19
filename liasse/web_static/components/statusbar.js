import { LucideIcon } from "./icons.js";
import { toast } from "./toast.js";
import { t, i18n, fmtDurI18n } from "../i18n.js";

const { computed, ref } = window.Vue;

function progressLabel(progress) {
  const pct = Math.min(100, Math.max(0, (progress || 0) * 100));
  if (pct > 0 && pct < 99.95) return pct.toFixed(1);
  return String(Math.round(pct));
}

export const StatusBar = {
  name: "StatusBar",
  components: { LucideIcon },
  props: {
    tasks: { type: Array, default: () => [] },
    health: { type: Object, default: () => ({ checks: {} }) },
    now: { type: Number, default: () => Date.now() },
  },
  emits: ["health-refresh"],
  setup(props, { emit }) {
    const startingOllama = ref(false);

    const runningTask = computed(() => props.tasks.find((task) => task.status === "running"));
    const queuedCount = computed(() => props.tasks.filter((task) => task.status === "queued").length);

    const etaText = computed(() => {
      const task = runningTask.value;
      if (!task || !task.startedAt) return "";
      const startMs = new Date(task.startedAt + (task.startedAt.endsWith("Z") ? "" : "Z")).getTime();
      const elapsed = (props.now - startMs) / 1000;
      if (elapsed < 3) return "";
      // 优先：基于实际本机进度外推（progress 由后端按已完成的 chunk 数推出来）
      if (task.progress && task.progress > 0.02 && task.progress < 0.999) {
        const remaining = (elapsed / task.progress) * (1 - task.progress);
        if (isFinite(remaining) && remaining > 0) {
          return t("status.etaLabel", { dur: fmtDurI18n(remaining, i18n.locale) });
        }
      }
      // 兜底：刚启动还没有真实进度时，用音频长度 × 1.5 给个粗略估计
      if (task.durationSec && task.durationSec > 0) {
        const estTotal = task.durationSec * 1.5;
        const remaining = estTotal - elapsed;
        if (remaining > 0) return t("status.etaLabel", { dur: fmtDurI18n(remaining, i18n.locale) });
        if (-remaining < estTotal * 0.5) return t("status.etaNear");
        return t("status.etaSlow");
      }
      return "";
    });

    const elapsedText = computed(() => {
      const task = runningTask.value;
      if (!task || !task.startedAt) return "";
      const startMs = new Date(task.startedAt + (task.startedAt.endsWith("Z") ? "" : "Z")).getTime();
      const elapsed = (props.now - startMs) / 1000;
      if (elapsed < 1) return "";
      return t("status.elapsedLabel", { dur: fmtDurI18n(elapsed, i18n.locale) });
    });

    const statusText = computed(() => {
      const task = runningTask.value;
      if (task) {
        const pct = progressLabel(task.progress);
        const stage = task.progressStage || "";
        let str = t("status.processing", { file: task.fileName });
        if (stage) str += ` · ${stage}`;
        str += ` · ${pct}%`;
        if (queuedCount.value > 0) str += t("status.queueSuffix", { n: queuedCount.value });
        return str;
      }
      if (queuedCount.value > 0) return t("status.queueOnly", { n: queuedCount.value });
      return t("status.idle");
    });

    const ollamaOnline = computed(() => !!(props.health.checks && props.health.checks.ollama));

    async function startOllama() {
      if (startingOllama.value) return;
      startingOllama.value = true;
      const tid = toast.info(t("status.ollamaStartingToast"), t("status.ollamaStartingBody"), { persist: true });
      try {
        const resp = await fetch("/api/ollama/start", { method: "POST" });
        toast.dismiss(tid);
        if (resp.ok) {
          const data = await resp.json();
          toast.success(t("status.ollamaStartedTitle"), data.alreadyRunning ? t("status.ollamaAlreadyRunning") : "");
          emit("health-refresh");
        } else {
          const txt = await resp.text();
          toast.error(t("status.ollamaFailedTitle"), txt);
        }
      } catch (err) {
        toast.dismiss(tid);
        toast.error(t("status.ollamaFailedTitle"), err.message || String(err));
      } finally {
        startingOllama.value = false;
      }
    }

    async function openLog() {
      try {
        const resp = await fetch("/api/open-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: "outputs" }),
        });
        if (!resp.ok) {
          const txt = await resp.text();
          toast.warning(t("status.cantOpenLogs"), txt);
        }
      } catch (err) {
        toast.warning(t("status.cantOpenLogs"), err.message || String(err));
      }
    }

    return { t, runningTask, queuedCount, elapsedText, etaText, statusText, ollamaOnline, startingOllama, startOllama, openLog };
  },
  template: `
    <div class="statusbar">
      <div class="statusbar-left">
        <lucide-icon name="activity" :size="14" />
        <span class="statusbar-text">{{ statusText }}</span>
        <span v-if="elapsedText" class="muted" style="font-size:12px;margin-left:8px">{{ elapsedText }}<span v-if="etaText"> · {{ etaText }}</span></span>
      </div>
      <div class="statusbar-right">
        <span class="ollama-pill" :class="ollamaOnline ? 'is-online' : 'is-offline'">
          <span class="ollama-dot"></span>
          {{ ollamaOnline ? t('status.ollamaRunning') : t('status.ollamaStopped') }}
          <button
            v-if="!ollamaOnline"
            class="btn btn-ghost btn-sm"
            style="margin-left:6px"
            :disabled="startingOllama"
            @click="startOllama"
          >
            {{ startingOllama ? t('status.ollamaStarting') : t('status.ollamaStart') }}
          </button>
        </span>
        <button class="btn btn-ghost btn-sm" @click="openLog">
          <lucide-icon name="folder-open" :size="14" /> {{ t('status.openLogs') }}
        </button>
      </div>
    </div>
  `,
};
