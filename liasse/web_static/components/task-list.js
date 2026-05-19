import { LucideIcon } from "./icons.js";
import { t, i18n, fmtDurI18n } from "../i18n.js";

const STATUS_KEY = {
  queued: "list.statusQueued",
  running: "list.statusRunning",
  done: "list.statusDone",
  failed: "list.statusFailed",
  stopping: "list.statusStopping",
  stopped: "list.statusStopped",
};
const STATUS_CLS = {
  queued: "chip-queued",
  running: "chip-running",
  done: "chip-done",
  failed: "chip-failed",
  stopping: "chip-stopped",
  stopped: "chip-stopped",
};

const FILTER_PREDICATES = {
  all: () => true,
  active: (t) => t.status === "queued" || t.status === "running" || t.status === "stopping",
  done: (t) => t.status === "done",
  failed: (t) => t.status === "failed" || t.status === "stopped",
};

export const TaskList = {
  name: "TaskList",
  components: { LucideIcon },
  props: {
    tasks: { type: Array, default: () => [] },
    now: { type: Number, default: () => Date.now() },
  },
  emits: ["open", "stop", "delete", "clear-completed", "show-error", "retry"],
  data() {
    return { filter: "all" };
  },
  computed: {
    queuedTasks() { return this.tasks.filter((t) => t.status === "queued"); },
    filteredTasks() {
      const pred = FILTER_PREDICATES[this.filter] || FILTER_PREDICATES.all;
      return this.tasks.filter(pred);
    },
    counts() {
      const c = { all: this.tasks.length, active: 0, done: 0, failed: 0 };
      for (const task of this.tasks) {
        if (FILTER_PREDICATES.active(task)) c.active += 1;
        else if (task.status === "done") c.done += 1;
        else if (task.status === "failed" || task.status === "stopped") c.failed += 1;
      }
      return c;
    },
    hasCompleted() {
      return this.tasks.some((t) => ["done", "failed", "stopped"].includes(t.status));
    },
    filters() {
      return [
        { key: "all", label: t("list.filterAll"), count: this.counts.all },
        { key: "active", label: t("list.filterActive"), count: this.counts.active },
        { key: "done", label: t("list.filterDone"), count: this.counts.done },
        { key: "failed", label: t("list.filterFailed"), count: this.counts.failed },
      ];
    },
    isFilteredEmpty() {
      return this.tasks.length > 0 && this.filteredTasks.length === 0;
    },
  },
  methods: {
    t,
    setFilter(key) { this.filter = key; },
    chipLabel(task) { return t(STATUS_KEY[task.status] || "list.statusQueued"); },
    chipCls(task) { return STATUS_CLS[task.status] || "chip-queued"; },
    queuePosition(task) {
      const idx = this.queuedTasks.findIndex((q) => q.id === task.id);
      if (idx < 0) return "";
      return t("list.queuePosition", { n: idx + 1 });
    },
    paramSummary(task) {
      const cfg = task.config || {};
      const parts = [];
      const mode = cfg.speakerMode || (cfg.diarize ? "pyannote" : "fast");
      if (!cfg.autoSegment || mode === "fast") {
        parts.push(t("list.paramSpeakerModeFast"));
      } else if (mode === "llm") {
        parts.push(t("list.paramSpeakerModeLLM"));
      } else if (mode === "pyannote") {
        parts.push(t("list.paramSpeakerModePyannote"));
      }
      if (cfg.autoSegment && mode !== "fast") {
        if (cfg.numSpeakers) parts.push(t("list.paramSpeakersN", { n: cfg.numSpeakers }));
        else parts.push(t("list.paramSpeakersAuto"));
      }
      if (cfg.summarize) parts.push(t("list.paramSummary"));
      if (cfg.asrModel) parts.push(cfg.asrModel.replace("Qwen/Qwen3-ASR-", ""));
      if (cfg.language) parts.push(t(`audioLang.${cfg.language}`) || cfg.language);
      return parts.join(" · ");
    },
    formatBytes(n) {
      if (!n) return "-";
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
      return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
    },
    formatDuration(s) {
      if (s == null) return "-";
      const total = Math.round(s);
      const h = Math.floor(total / 3600);
      const m = Math.floor((total % 3600) / 60);
      const ss = total % 60;
      const pad = (n) => String(n).padStart(2, "0");
      return h > 0 ? `${pad(h)}:${pad(m)}:${pad(ss)}` : `${pad(m)}:${pad(ss)}`;
    },
    formatTime(iso) {
      if (!iso) return "-";
      const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
      const pad = (n) => String(n).padStart(2, "0");
      if (i18n.locale === "zh") return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const monthsEn = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const monthsEs = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
      const months = i18n.locale === "es" ? monthsEs : monthsEn;
      return `${months[d.getMonth()]} ${d.getDate()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
    elapsedSec(task) {
      if (!task || !task.startedAt) return 0;
      const startMs = new Date(task.startedAt + (task.startedAt.endsWith("Z") ? "" : "Z")).getTime();
      return Math.max(0, (this.now - startMs) / 1000);
    },
    fmtDur(sec) { return fmtDurI18n(sec, i18n.locale); },
    elapsedText(task) {
      if (task.status !== "running") return "";
      const sec = this.elapsedSec(task);
      if (sec < 1) return "";
      return t("list.elapsedLabel", { dur: this.fmtDur(sec) });
    },
    etaText(task) {
      if (!task || task.status !== "running") return "";
      const elapsed = this.elapsedSec(task);
      if (elapsed < 3) return "";
      // 优先：基于实际本机进度外推（progress 由后端按已完成的 chunk 数推出来）
      if (task.progress && task.progress > 0.02 && task.progress < 0.999) {
        const remaining = (elapsed / task.progress) * (1 - task.progress);
        if (isFinite(remaining) && remaining > 0) {
          return t("list.etaLabel", { dur: this.fmtDur(remaining) });
        }
      }
      // 兜底：刚启动还没有真实进度时，用音频长度 × 1.5 给个粗略估计
      if (task.durationSec && task.durationSec > 0) {
        const estTotal = task.durationSec * 1.5;
        const remaining = estTotal - elapsed;
        if (remaining > 0) return t("list.etaLabel", { dur: this.fmtDur(remaining) });
        if (-remaining < estTotal * 0.5) return t("list.etaNear");
        return t("list.etaSlow");
      }
      return "";
    },
    completionStat(task) {
      if (task.status !== "done") return "";
      const segs = (task.transcript && task.transcript.segments) || [];
      if (!task.startedAt || !task.completedAt) {
        return segs.length ? t("list.completed", { dur: "", segs: segs.length }) : "";
      }
      const startMs = new Date(task.startedAt + (task.startedAt.endsWith("Z") ? "" : "Z")).getTime();
      const endMs = new Date(task.completedAt + (task.completedAt.endsWith("Z") ? "" : "Z")).getTime();
      const sec = Math.max(0, (endMs - startMs) / 1000);
      const dur = this.fmtDur(sec);
      if (segs.length) return t("list.completed", { dur, segs: segs.length });
      return t("list.completedNoSegs", { dur });
    },
    isDone(t) { return t.status === "done"; },
    isRunning(t) { return t.status === "running"; },
    isFailed(t) { return t.status === "failed"; },
    isQueued(t) { return t.status === "queued"; },
    hasPartialTranscript(t) {
      const segs = (t.transcript && t.transcript.segments) || [];
      return Boolean(t.transcript && t.transcript.partial && segs.length > 0);
    },
    progressPercent(t) {
      const p = Math.min(1, Math.max(0, t.progress || 0));
      return Math.round(p * 100);
    },
    onRowClick(t) {
      if (this.isDone(t) || this.isFailed(t) || this.isRunning(t)) this.$emit("open", t);
    },
  },
  template: `
    <section class="col" style="gap:12px">
      <div class="task-list-toolbar">
        <div class="task-list-toolbar-left">
          <h2 class="section-title">{{ t('list.title') }}</h2>
          <div class="filter-chips" role="tablist" :aria-label="t('list.filterLabel') || t('list.title')">
            <button
              v-for="f in filters"
              :key="f.key"
              class="filter-chip"
              :class="{ active: filter === f.key }"
              :aria-pressed="filter === f.key"
              @click="setFilter(f.key)"
            >
              <span>{{ f.label }}</span>
              <span v-if="f.count > 0" class="filter-count">{{ f.count }}</span>
            </button>
          </div>
        </div>
        <button
          class="btn btn-sm"
          :disabled="!hasCompleted"
          @click="$emit('clear-completed')"
        >{{ t('list.clearCompleted') }}</button>
      </div>

      <div class="task-list">
        <div class="task-header">
          <div>{{ t('list.colName') }}</div>
          <div>{{ t('list.colStatus') }}</div>
          <div>{{ t('list.colProgress') }}</div>
          <div>{{ t('list.colParams') }}</div>
          <div>{{ t('list.colCreated') }}</div>
          <div style="text-align:right">{{ t('list.colActions') }}</div>
        </div>

        <div v-if="!tasks.length" class="empty-state">
          <div class="empty-state-title">{{ t('list.emptyTitle') }}</div>
          <div>{{ t('list.emptyHint') }}</div>
        </div>
        <div v-else-if="isFilteredEmpty" class="empty-state">
          <div class="empty-state-title">{{ t('list.emptyFilterTitle') }}</div>
          <div>{{ t('list.emptyFilterHint') }}</div>
        </div>

        <div
          v-for="task in filteredTasks"
          :key="task.id"
          class="task-row"
          :class="{ clickable: isDone(task) || isFailed(task) || isRunning(task) }"
          @click="onRowClick(task)"
        >
          <div class="task-file">
            <div class="task-file-icon"><lucide-icon name="file-audio" :size="18" /></div>
            <div style="min-width:0">
              <div class="task-file-name">{{ task.fileName }}</div>
              <div class="task-file-meta">{{ formatBytes(task.fileSizeBytes) }} · {{ formatDuration(task.durationSec) }}</div>
            </div>
          </div>

          <div><span class="chip" :class="chipCls(task)">{{ chipLabel(task) }}</span></div>

          <div>
            <div class="progress">
              <div
                class="progress-fill"
                :class="{ 'is-running': isRunning(task), 'is-failed': isFailed(task), 'is-stopped': task.status === 'stopped' }"
                :style="{ width: progressPercent(task) + '%' }"
              ></div>
            </div>
            <div class="progress-stage" :class="{ 'progress-running': isRunning(task) }">
              <span v-if="isQueued(task)">{{ queuePosition(task) }}</span>
              <template v-else-if="isRunning(task)">
                <span>{{ task.progressStage || task.fileName }} · {{ progressPercent(task) }}%</span>
                <span v-if="hasPartialTranscript(task)" class="chip chip-partial-ready" style="margin-left:6px" :title="t('list.partialReadyHint')">
                  <lucide-icon name="file-text" :size="11" /> {{ t('list.partialReady') }}
                </span>
                <span class="muted" style="margin-left:6px">{{ elapsedText(task) }}<span v-if="etaText(task)"> · {{ etaText(task) }}</span></span>
              </template>
              <span v-else-if="isDone(task)">{{ completionStat(task) }}</span>
              <span v-else-if="isFailed(task)">{{ t('list.clickError') }}</span>
              <span v-else>{{ task.progressStage || '—' }} · {{ progressPercent(task) }}%</span>
            </div>
          </div>

          <div class="task-params muted" :title="paramSummary(task)">{{ paramSummary(task) }}</div>

          <div class="task-time">{{ formatTime(task.createdAt) }}</div>

          <div class="task-actions" @click.stop>
            <button v-if="isRunning(task)" class="btn btn-icon btn-danger" @click="$emit('stop', task)">
              <lucide-icon name="square" :size="14" />
            </button>
            <button v-if="isDone(task) || isRunning(task)" class="btn btn-icon" @click="$emit('open', task)">
              <lucide-icon name="file-text" :size="16" />
            </button>
            <button v-if="isFailed(task) || task.status === 'stopped'" class="btn btn-icon" :title="t('upload.btnRetry')" @click="$emit('retry', task)">
              <lucide-icon name="refresh-cw" :size="14" />
            </button>
            <button v-if="isFailed(task)" class="btn btn-icon" @click="$emit('show-error', task)">
              <lucide-icon name="alert-circle" :size="16" />
            </button>
            <button class="btn btn-icon" @click="$emit('delete', task)">
              <lucide-icon name="trash-2" :size="16" />
            </button>
          </div>
        </div>
      </div>
    </section>
  `,
};
