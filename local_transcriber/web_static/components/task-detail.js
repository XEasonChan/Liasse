import { LucideIcon } from "./icons.js";
import { ChatPanel } from "./chat-panel.js";
import { t, i18n, fmtDurI18n } from "../i18n.js";

export const TaskDetail = {
  name: "TaskDetail",
  components: { LucideIcon, ChatPanel },
  props: {
    taskId: { type: String, required: true },
    now: { type: Number, default: () => Date.now() },
  },
  emits: ["back", "deleted"],
  data() {
    return {
      task: null,
      loading: true,
      activeTab: "transcript",
      summaryLoading: false,
      summaryError: null,
      pollHandle: null,
      saving: false,
    };
  },
  computed: {
    segments() {
      return ((this.task && this.task.transcript && this.task.transcript.segments) || []);
    },
    speakerLabels() {
      return (this.task && this.task.edits && this.task.edits.speakerLabels) || {};
    },
    segmentOverrides() {
      return (this.task && this.task.edits && this.task.edits.segmentOverrides) || {};
    },
    transcriptWarnings() {
      return ((this.task && this.task.transcript && this.task.transcript.warnings) || []);
    },
    isRunning() { return this.task && this.task.status === "running"; },
    isQueued() { return this.task && this.task.status === "queued"; },
    isFailed() { return this.task && this.task.status === "failed"; },
    isStopped() { return this.task && (this.task.status === "stopped" || this.task.status === "stopping"); },
    progressValue() {
      const p = Math.min(1, Math.max(0, (this.task && this.task.progress) || 0));
      return p * 100;
    },
    progressPercent() {
      return Math.round(this.progressValue);
    },
    progressLabel() {
      const pct = this.progressValue;
      if (this.isRunning && pct > 0 && pct < 99.95) return pct.toFixed(1);
      return String(Math.round(pct));
    },
    elapsedSec() {
      const t = this.task;
      if (!t || !t.startedAt) return 0;
      const startMs = new Date(t.startedAt + (t.startedAt.endsWith("Z") ? "" : "Z")).getTime();
      return Math.max(0, (this.now - startMs) / 1000);
    },
    elapsedText() {
      if (!this.isRunning) return "";
      const sec = this.elapsedSec;
      if (sec < 1) return "";
      return t("detail.elapsedPrefix", { dur: fmtDurI18n(sec, i18n.locale) });
    },
    etaText() {
      const task = this.task;
      if (!task || task.status !== "running") return "";
      const elapsed = this.elapsedSec;
      if (elapsed < 3) return "";
      // 优先：基于实际本机进度外推（progress 由后端按已完成的 chunk 数推出来）
      if (task.progress && task.progress > 0.02 && task.progress < 0.999) {
        const remaining = (elapsed / task.progress) * (1 - task.progress);
        if (isFinite(remaining) && remaining > 0) {
          return t("list.etaLabel", { dur: fmtDurI18n(remaining, i18n.locale) });
        }
      }
      // 兜底：刚启动还没有真实进度时，用音频长度 × 1.5 给个粗略估计
      if (task.durationSec && task.durationSec > 0) {
        const estTotal = task.durationSec * 1.5;
        const remaining = estTotal - elapsed;
        if (remaining > 0) return t("list.etaLabel", { dur: fmtDurI18n(remaining, i18n.locale) });
        if (-remaining < estTotal * 0.5) return t("list.etaNear");
        return t("list.etaSlow");
      }
      return "";
    },
    metaLine() {
      if (!this.task) return "";
      const task = this.task;
      const parts = [];
      parts.push(this.formatBytes(task.fileSizeBytes));
      if (task.durationSec) parts.push(this.formatDuration(task.durationSec));
      const speakers = new Set(this.segments.map((s) => s.speaker));
      if (speakers.size) parts.push(t("detail.metaSpeakers", { n: speakers.size }));
      if (task.config && task.config.asrModel) parts.push(task.config.asrModel.replace("Qwen/Qwen3-ASR-", ""));
      if (task.config && task.config.language) parts.push(this.langLabel(task.config.language));
      return parts.join(" · ");
    },
    summaryReady() {
      return Boolean(this.task && this.task.summaryText);
    },
  },
  methods: {
    async load() {
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}`);
        if (!resp.ok) throw new Error(await resp.text());
        this.task = await resp.json();
      } catch (err) {
        console.error("加载任务失败", err);
      } finally {
        this.loading = false;
      }
    },
    speakerLabel(spk) {
      return this.speakerLabels[spk] || spk;
    },
    segmentText(seg) {
      return this.segmentOverrides[seg.id] != null ? this.segmentOverrides[seg.id] : seg.text;
    },
    isEdited(seg) {
      return this.segmentOverrides[seg.id] != null;
    },
    formatBytes(n) {
      if (!n) return "-";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / 1024 / 1024).toFixed(1) + " MB";
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
    formatTime(t) {
      if (t == null) return "-";
      if (typeof t === "number") {
        const m = Math.floor(t / 60);
        const s = Math.floor(t % 60);
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
      }
      return t;
    },
    t,
    langLabel(l) { return t(`audioLang.${l}`) || l; },
    async renameSpeaker(spk) {
      const current = this.speakerLabel(spk);
      const next = window.prompt(`Rename "${current}":`, current);
      if (next == null || next.trim() === "" || next === current) return;
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}/edits/speaker`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ speakerId: spk, label: next.trim() }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.task.edits = data.edits;
      } catch (err) {
        alert(err.message || err);
      }
    },
    async saveSegmentEdit(seg, ev) {
      const newText = ev.target.innerText.trim();
      if (newText === (this.segmentText(seg) || "").trim()) return;
      this.saving = true;
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}/edits/segment`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ segmentId: seg.id, text: newText }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.task.edits = data.edits;
      } catch (err) {
        alert(t("modal.saveFailed", { msg: err.message || err }));
      } finally {
        this.saving = false;
      }
    },
    async regenerateSummary() {
      this.summaryLoading = true;
      this.summaryError = null;
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}/summary`, { method: "POST" });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.task.summaryText = data.summary;
      } catch (err) {
        this.summaryError = err.message || String(err);
      } finally {
        this.summaryLoading = false;
      }
    },
    renderSummary(text) {
      if (!text) return "";
      const escape = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
      const lines = escape(text).split("\n");
      let html = "";
      let inUl = false;
      for (const line of lines) {
        if (line.startsWith("# ")) {
          if (inUl) { html += "</ul>"; inUl = false; }
          html += `<h2 style="font-size:18px;font-weight:600;margin:14px 0 8px">${line.slice(2)}</h2>`;
        } else if (line.startsWith("## ")) {
          if (inUl) { html += "</ul>"; inUl = false; }
          html += `<h3 style="font-size:15px;font-weight:600;margin:12px 0 6px">${line.slice(3)}</h3>`;
        } else if (line.startsWith("- ") || line.startsWith("* ")) {
          if (!inUl) { html += '<ul style="padding-left:20px;margin:6px 0">'; inUl = true; }
          html += `<li style="margin:4px 0">${line.slice(2)}</li>`;
        } else if (line.trim() === "") {
          if (inUl) { html += "</ul>"; inUl = false; }
          html += "<br/>";
        } else {
          if (inUl) { html += "</ul>"; inUl = false; }
          html += `<p style="margin:6px 0;line-height:1.7">${line}</p>`;
        }
      }
      if (inUl) html += "</ul>";
      return html;
    },
  },
  async mounted() {
    await this.load();
    this.pollHandle = setInterval(() => {
      if (this.task && (this.task.status === "running" || this.task.status === "queued")) {
        this.load();
      }
    }, 2000);
  },
  beforeUnmount() {
    if (this.pollHandle) clearInterval(this.pollHandle);
  },
  watch: {
    taskId() { this.load(); },
  },
  template: `
    <div class="detail">
      <div class="detail-main">
        <div v-if="loading" class="muted">…</div>
        <template v-else-if="task">
          <div class="detail-header">
            <button class="detail-back" @click="$emit('back')">
              <lucide-icon name="chevron-left" :size="14" /> {{ t('detail.back') }}
            </button>
            <h1 class="detail-title">{{ task.fileName }}</h1>
            <div class="detail-meta">{{ metaLine }}</div>
            <div class="detail-meta" v-if="task.completedAt">
              {{ t('detail.completedAt', { time: task.completedAt.replace('T',' ').slice(0,19) }) }}<span v-if="task.elapsedSec">{{ t('detail.elapsedSuffix', { dur: formatDuration(task.elapsedSec) }) }}</span>
            </div>
          </div>

          <div v-if="isRunning || isQueued" class="detail-banner banner-running">
            <lucide-icon name="loader" :size="16" class="banner-icon-spin" />
            <div style="flex:1">
              <div class="detail-banner-title">
                <span v-if="isQueued">{{ t('detail.bannerQueued') }}</span>
                <span v-else>{{ t('detail.bannerRunning', { stage: task.progressStage || task.fileName, pct: progressLabel }) }}</span>
              </div>
              <div class="detail-banner-sub muted" v-if="isRunning">
                <span>{{ elapsedText }}</span>
                <span v-if="etaText"> · {{ etaText }}</span>
              </div>
            </div>
            <div class="progress" style="width:200px">
              <div class="progress-fill is-running" :style="{ width: progressValue + '%' }"></div>
            </div>
          </div>

          <div v-if="isFailed" class="detail-banner banner-failed">
            <lucide-icon name="alert-circle" :size="16" />
            <div style="flex:1">
              <div class="detail-banner-title">{{ t('detail.bannerFailed') }}</div>
              <div class="detail-banner-sub pre-error" style="white-space:pre-wrap;background:transparent;padding:0">{{ task.errorMessage || t('detail.bannerFailedNone') }}</div>
            </div>
          </div>

          <div v-if="isStopped" class="detail-banner banner-stopped">
            <lucide-icon name="square" :size="16" />
            <div style="flex:1">
              <div class="detail-banner-title">{{ t('detail.bannerStopped') }}</div>
              <div class="detail-banner-sub muted">{{ t('detail.bannerStoppedHint', { pct: progressLabel }) }}</div>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn" :class="{ active: activeTab==='transcript' }" @click="activeTab='transcript'">{{ t('detail.tabTranscript') }}</button>
            <button class="tab-btn" :class="{ active: activeTab==='summary' }" @click="activeTab='summary'">{{ t('detail.tabSummary') }}</button>
          </div>

          <div v-if="activeTab==='transcript'">
            <div v-if="!segments.length && (isRunning || isQueued)" class="muted">
              {{ isRunning ? t('detail.waitingTranscriptRunning') : t('detail.waitingTranscriptQueued') }}
            </div>
            <div v-else-if="!segments.length" class="muted">{{ t('detail.waitingTranscript') }}</div>
            <div v-if="isRunning && segments.length" class="muted" style="font-size:12px;margin-bottom:8px">
              {{ t('detail.transcribingNote', { n: segments.length }) }}
            </div>
            <div v-if="transcriptWarnings.length" class="upload-feedback warn" style="margin-bottom:8px">
              <lucide-icon name="alert-triangle" :size="14" />
              <span>{{ transcriptWarnings.join('；') }}</span>
            </div>
            <div v-for="seg in segments" :key="seg.id" class="segment-block">
              <div class="segment-head">
                <span class="segment-speaker" :title="t('detail.speakerTooltip')" @click="renameSpeaker(seg.speaker)">
                  <lucide-icon name="users" :size="12" />
                  {{ speakerLabel(seg.speaker) }}
                </span>
                <span class="segment-time">{{ formatTime(seg.start) }} - {{ formatTime(seg.end) }}</span>
                <span v-if="isEdited(seg)" class="muted" style="font-size:11px;color:var(--accent)">{{ t('detail.edited') }}</span>
              </div>
              <div
                class="segment-text"
                contenteditable="true"
                :data-seg-id="seg.id"
                @blur="saveSegmentEdit(seg, $event)"
              >{{ segmentText(seg) }}</div>
            </div>
          </div>

          <div v-if="activeTab==='summary'">
            <div class="row" style="justify-content: space-between; margin-bottom: 12px">
              <div class="muted">{{ t('detail.summaryByQwen') }}</div>
              <button class="btn btn-sm" :disabled="summaryLoading" @click="regenerateSummary">
                <lucide-icon name="refresh-cw" :size="14" />
                {{ summaryReady ? t('detail.summaryRegen') : t('detail.summaryGen') }}
              </button>
            </div>
            <div v-if="summaryLoading" class="muted">{{ t('detail.summaryWorking') }}</div>
            <div v-else-if="summaryError" class="pre-error">{{ summaryError }}</div>
            <div v-else-if="!summaryReady" class="empty-state">
              <div class="empty-state-title">{{ t('detail.summaryEmptyTitle') }}</div>
              <div>{{ t('detail.summaryEmptyHint') }}</div>
            </div>
            <div v-else v-html="renderSummary(task.summaryText)"></div>
          </div>
        </template>
      </div>

      <chat-panel v-if="task" :task-id="task.id" :ready="!!segments.length" />
    </div>
  `,
};
