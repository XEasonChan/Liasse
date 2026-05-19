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

export const TaskList = {
  name: "TaskList",
  components: { LucideIcon },
  props: {
    tasks: { type: Array, default: () => [] },
    now: { type: Number, default: () => Date.now() },
  },
  emits: ["open", "stop", "delete", "clear-completed", "show-error", "retry"],
  data() {
    return {
      activeFilter: "all",
    };
  },
  computed: {
    hasCompleted() {
      return this.tasks.some((t) => ["done", "failed", "stopped"].includes(t.status));
    },
    queuedTasks() {
      return this.tasks.filter((t) => t.status === "queued");
    },
    filters() {
      return [
        { key: "all", label: t("list.filterAll"), count: this.tasks.length },
        { key: "active", label: t("list.filterActive"), count: this.tasks.filter((task) => ["queued", "running", "stopping"].includes(task.status)).length },
        { key: "done", label: t("list.filterDone"), count: this.tasks.filter((task) => task.status === "done").length },
        { key: "failed", label: t("list.filterFailed"), count: this.tasks.filter((task) => ["failed", "stopped"].includes(task.status)).length },
      ];
    },
    filteredTasks() {
      if (this.activeFilter === "active") return this.tasks.filter((task) => ["queued", "running", "stopping"].includes(task.status));
      if (this.activeFilter === "done") return this.tasks.filter((task) => task.status === "done");
      if (this.activeFilter === "failed") return this.tasks.filter((task) => ["failed", "stopped"].includes(task.status));
      return this.tasks;
    },
  },
  methods: {
    t,
    chipLabel(task) { return t(STATUS_KEY[task.status] || "list.statusQueued"); },
    chipCls(task) { return STATUS_CLS[task.status] || "chip-queued"; },
    queuePosition(task) {
      const idx = this.queuedTasks.findIndex((q) => q.id === task.id);
      if (idx < 0) return "";
      return t("list.queuePosition", { n: idx + 1 });
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
    elapsedSec(t) {
      if (!t || !t.startedAt) return 0;
      const startMs = new Date(t.startedAt + (t.startedAt.endsWith("Z") ? "" : "Z")).getTime();
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
      if (task.durationSec && task.durationSec > 0) {
        const REALTIME_FACTOR = 1.5;
        const estTotal = task.durationSec * REALTIME_FACTOR;
        const remaining = estTotal - elapsed;
        if (remaining > 0) return t("list.etaLabel", { dur: this.fmtDur(remaining) });
        if (-remaining < estTotal * 0.5) return t("list.etaNear");
        return t("list.etaSlow");
      }
      if (task.progress && task.progress > 0.02) {
        const remaining = (elapsed / task.progress) * (1 - task.progress);
        if (isFinite(remaining) && remaining > 0) return t("list.etaLabel", { dur: this.fmtDur(remaining) });
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
    progressValue(t) {
      const p = Math.min(1, Math.max(0, t.progress || 0));
      return p * 100;
    },
    progressPercent(t) {
      return Math.round(this.progressValue(t));
    },
    progressLabel(t) {
      const pct = this.progressValue(t);
      if (this.isRunning(t) && pct > 0 && pct < 99.95) return pct.toFixed(1);
      return String(Math.round(pct));
    },
    languageLabel(task) {
      const lang = task.config && task.config.language ? task.config.language : "English";
      return t(`audioLang.${lang}`);
    },
    modelLabel(task) {
      const model = task.config && task.config.asrModel ? task.config.asrModel : "Qwen/Qwen3-ASR-0.6B";
      if (model.includes("1.7B")) return "1.7B";
      return "0.6B";
    },
    speakerLabel(task) {
      const cfg = task.config || {};
      if (!cfg.autoSegment || !cfg.diarize) return t("list.paramNoSpeakers");
      if (cfg.numSpeakers == null || cfg.numSpeakers === "auto") return t("list.paramSpeakersAuto");
      return t("list.paramSpeakersN", { n: cfg.numSpeakers });
    },
    paramsText(task) {
      const cfg = task.config || {};
      const parts = [
        this.speakerLabel(task),
        cfg.summarize ? t("list.paramSummary") : t("list.paramNoSummary"),
        this.modelLabel(task),
        this.languageLabel(task),
      ];
      return parts.join(" · ");
    },
    onRowClick(t) {
      if (this.isDone(t) || this.isFailed(t) || this.isRunning(t)) this.$emit("open", t);
    },
  },
  template: `
    <section class="task-section">
      <div class="section-head">
        <div>
          <h2 class="section-title">{{ t('list.title') }}</h2>
          <p class="section-hint">{{ t('list.hint') }}</p>
        </div>
        <div class="section-actions">
          <div class="filter-chips" role="tablist" :aria-label="t('list.filterLabel')">
            <button
              v-for="filter in filters"
              :key="filter.key"
              class="filter-chip"
              :class="{ active: activeFilter === filter.key }"
              @click="activeFilter = filter.key"
            >
              {{ filter.label }}
              <span class="filter-count">{{ filter.count }}</span>
            </button>
          </div>
          <button
            class="btn btn-sm"
            :disabled="!hasCompleted"
            @click="$emit('clear-completed')"
          >{{ t('list.clearCompleted') }}</button>
        </div>
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

        <div v-if="!filteredTasks.length" class="empty-state">
          <div class="empty-state-title">{{ tasks.length ? t('list.emptyFilterTitle') : t('list.emptyTitle') }}</div>
          <div>{{ tasks.length ? t('list.emptyFilterHint') : t('list.emptyHint') }}</div>
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
                :style="{ width: progressValue(task) + '%' }"
              ></div>
            </div>
            <div class="progress-stage" :class="{ 'progress-running': isRunning(task) }">
              <span v-if="isQueued(task)">{{ queuePosition(task) }}</span>
              <template v-else-if="isRunning(task)">
                <span>{{ task.progressStage || task.fileName }} · {{ progressLabel(task) }}%</span>
                <span class="muted" style="margin-left:6px">{{ elapsedText(task) }}<span v-if="etaText(task)"> · {{ etaText(task) }}</span></span>
              </template>
              <span v-else-if="isDone(task)">{{ completionStat(task) }}</span>
              <span v-else-if="isFailed(task)">{{ t('list.clickError') }}</span>
              <span v-else>{{ task.progressStage || '—' }} · {{ progressLabel(task) }}%</span>
            </div>
          </div>

          <div class="task-params">{{ paramsText(task) }}</div>

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
