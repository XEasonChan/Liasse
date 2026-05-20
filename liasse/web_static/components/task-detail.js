import { LucideIcon } from "./icons.js";
import { ChatPanel } from "./chat-panel.js";
import { dialog } from "./dialog.js";
import { toast } from "./toast.js";
import { t, i18n, fmtDurI18n } from "../i18n.js";

export const TaskDetail = {
  name: "TaskDetail",
  components: { LucideIcon, ChatPanel },
  props: {
    taskId: { type: String, required: true },
    now: { type: Number, default: () => Date.now() },
    models: { type: Array, default: () => [] },
    llmReady: { type: Boolean, default: false },
  },
  emits: ["back", "deleted", "need-model"],
  data() {
    return {
      task: null,
      loading: true,
      activeTab: "transcript",
      summaryLoading: false,
      summaryError: null,
      pollHandle: null,
      saving: false,
      // 翻译状态
      selectedTargetLang: "English",
      selectedGlossary: "",
      availableGlossaries: [],
      translating: false,
      showTranslation: "both",   // "original" | "translation" | "both"
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
    transcriptPartial() {
      return Boolean(this.task && this.task.transcript && this.task.transcript.partial);
    },
    transcriptReady() {
      return this.segments.length > 0;
    },
    translations() {
      return (this.task && this.task.translations) || {};
    },
    activeTranslation() {
      return this.translations[this.selectedTargetLang] || null;
    },
    translationById() {
      const tr = this.activeTranslation;
      if (!tr || !Array.isArray(tr.segments)) return {};
      const out = {};
      for (const s of tr.segments) {
        out[s.id] = s.translation || "";
      }
      return out;
    },
    /** 推断当前后端在跑哪个阶段，用 progressStage 字符串匹配。
     *  返回 "asr-only" | "diarizing" | "aligning" | null。 */
    asrPhase() {
      if (!this.isRunning) return null;
      const stage = String((this.task && this.task.progressStage) || "");
      if (stage.includes("对齐") || stage.includes("alignment") || stage.includes("套到")) {
        return "aligning";
      }
      if (stage.includes("发言人") || stage.includes("pyannote") || stage.includes("声纹")
          || stage.includes("speaker") || stage.includes("Speaker")) {
        return "diarizing";
      }
      if (this.transcriptPartial && this.transcriptReady) return "asr-only";
      return null;
    },
    asrPhaseBannerText() {
      if (this.asrPhase === "diarizing") return t("detail.bannerDiarizing");
      if (this.asrPhase === "aligning") return t("detail.bannerAligning");
      if (this.asrPhase === "asr-only") return t("detail.bannerASROnly");
      return "";
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
      const next = await dialog.prompt({
        title: t("dialog.renameSpeakerTitle", { current }),
        subtitle: t("dialog.renameSpeakerSubtitle"),
        defaultValue: current,
        placeholder: t("dialog.renamePlaceholder"),
        confirmLabel: t("dialog.rename"),
        validator: (v) => (v == null || v.trim() === "") ? t("dialog.renameEmpty") : null,
      });
      if (next == null) return;                  // 用户点了取消
      const trimmed = next.trim();
      if (trimmed === current) return;           // 没改名
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}/edits/speaker`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ speakerId: spk, label: trimmed }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.task.edits = data.edits;
      } catch (err) {
        await dialog.alert({
          title: t("dialog.renameSpeakerFailedTitle"),
          body: err.message || String(err),
          tone: "danger",
        });
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
        await dialog.alert({
          title: t("dialog.saveSegmentFailedTitle"),
          body: err.message || String(err),
          tone: "danger",
        });
      } finally {
        this.saving = false;
      }
    },
    async regenerateSummary() {
      // Hide config in the core flow: if the LLM summary model is not loaded,
      // prompt download via the global model-required-modal (handled in app.js).
      // `llmReady` prop mirrors the canonical app-level check (qwen3:4b downloaded
      // AND ollama running) — same source of truth as upload-zone.
      if (!this.llmReady) {
        this.$emit("need-model", "summary");
        return;
      }
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
    segmentTranslation(seg) {
      return this.translationById[seg.id] || "";
    },
    async loadGlossaries() {
      try {
        const r = await fetch("/api/glossaries");
        if (!r.ok) return;
        const data = await r.json();
        this.availableGlossaries = data.names || [];
      } catch (e) { /* offline-tolerant */ }
    },
    async runTranslate() {
      if (this.translating || !this.task) return;
      this.translating = true;
      try {
        const body = { target: this.selectedTargetLang };
        if (this.selectedGlossary) body.glossaryName = this.selectedGlossary;
        const r = await fetch(`/api/tasks/${this.task.id}/translate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) {
          const txt = await r.text();
          throw new Error(txt || `HTTP ${r.status}`);
        }
        const data = await r.json();
        // 写回本地以便重新渲染 (避免等下次 poll)
        if (!this.task.translations) this.task.translations = {};
        this.task.translations[this.selectedTargetLang] = data;
        this.showTranslation = "both";
        toast.success(t("translate.action"), t("translate.done"));
      } catch (err) {
        toast.error(t("translate.action"), t("translate.failed", { msg: err.message || String(err) }));
      } finally {
        this.translating = false;
      }
    },
    exportBilingual() {
      if (!this.task || !this.activeTranslation) return;
      const url = `/api/tasks/${this.task.id}/export-bilingual?target=${encodeURIComponent(this.selectedTargetLang)}`;
      window.location.href = url;
    },
  },
  async mounted() {
    await this.load();
    await this.loadGlossaries();
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

          <div
            v-if="isRunning && transcriptReady && transcriptPartial"
            class="detail-banner banner-partial-ready"
          >
            <lucide-icon name="check-circle" :size="16" />
            <div style="flex:1">
              <div class="detail-banner-title">
                {{ t('detail.bannerPartialReady', { n: segments.length }) }}
              </div>
              <div class="detail-banner-sub muted">
                {{ asrPhaseBannerText || t('detail.bannerPartialReadyHint') }}
              </div>
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

            <!-- 翻译 toolbar：done 任务才显示 -->
            <div v-if="segments.length && task && task.status === 'done'" class="translate-toolbar">
              <label class="muted" style="font-size:12px">{{ t('translate.targetLang') }}</label>
              <select v-model="selectedTargetLang" :disabled="translating">
                <option value="English">English</option>
                <option value="Chinese">中文</option>
                <option value="Cantonese">粤语</option>
                <option value="Spanish">Español</option>
              </select>
              <label class="muted" style="font-size:12px">{{ t('translate.glossary') }}</label>
              <select v-model="selectedGlossary" :disabled="translating">
                <option value="">{{ t('translate.none') }}</option>
                <option v-for="g in availableGlossaries" :key="g" :value="g">{{ g }}</option>
              </select>
              <button class="btn btn-sm btn-primary" :disabled="translating" @click="runTranslate">
                <lucide-icon name="languages" :size="14" />
                {{ translating ? t('translate.translating') : t('translate.action') }}
              </button>
              <div v-if="activeTranslation" class="view-toggle">
                <button :class="{ on: showTranslation === 'original' }" @click="showTranslation = 'original'">{{ t('translate.showOriginal') }}</button>
                <button :class="{ on: showTranslation === 'both' }" @click="showTranslation = 'both'">{{ t('translate.showBoth') }}</button>
                <button :class="{ on: showTranslation === 'translation' }" @click="showTranslation = 'translation'">{{ t('translate.showTranslation') }}</button>
              </div>
              <button v-if="activeTranslation" class="btn btn-sm" @click="exportBilingual">
                <lucide-icon name="download" :size="14" />
                {{ t('translate.exportBilingual') }}
              </button>
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
                v-if="showTranslation !== 'translation'"
                class="segment-text"
                contenteditable="true"
                :data-seg-id="seg.id"
                @blur="saveSegmentEdit(seg, $event)"
              >{{ segmentText(seg) }}</div>
              <div v-if="showTranslation !== 'original' && activeTranslation && segmentTranslation(seg)" class="segment-translation">
                {{ segmentTranslation(seg) }}
              </div>
              <div v-else-if="showTranslation === 'translation' && activeTranslation && !segmentTranslation(seg)" class="segment-translation faded">—</div>
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
