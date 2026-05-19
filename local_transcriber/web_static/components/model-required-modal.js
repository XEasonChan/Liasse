import { LucideIcon } from "./icons.js";
import { toast } from "./toast.js";
import { t, i18n, fmtDurI18n } from "../i18n.js";

function modelIdFor(feature) {
  switch (feature) {
    case "diarize": return "pyannote/speaker-diarization-community-1";
    case "summary":
    case "chat":
      return "qwen3:4b";
    case "asr-1.7b": return "Qwen/Qwen3-ASR-1.7B";
    case "asr-required": return "Qwen/Qwen3-ASR-0.6B";
    case "ollama-daemon": return null;
    default: return null;
  }
}

function featureKey(feature) {
  return {
    diarize: "upload.cfgDiarize",
    summary: "upload.cfgSummarize",
    chat: "upload.cfgChat",
    "asr-1.7b": "upload.cfgASRHigh",
    "asr-required": "upload.cfgASRQuick",
  }[feature] || null;
}

function fmtBytes(n) {
  if (!n) return "—";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
  return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

function fmtSec(s) {
  if (s == null) return "";
  return fmtDurI18n(s, i18n.locale);
}

export const ModelRequiredModal = {
  name: "ModelRequiredModal",
  components: { LucideIcon },
  props: {
    feature: { type: String, required: true },
    models: { type: Array, required: true },
  },
  emits: ["close", "rechecked"],
  data() {
    return {
      copied: false,
      rechecking: false,
      downloading: false,
      ollamaStarting: false,
      jobId: null,
      progress: 0,
      bytesDone: 0,
      bytesTotal: 0,
      speedBps: 0,
      etaSec: null,
      downloadError: null,
      downloadDone: false,
      logTail: "",
      eventSource: null,
    };
  },
  computed: {
    isOllamaDaemon() { return this.feature === "ollama-daemon"; },
    modelId() { return modelIdFor(this.feature); },
    modelInfo() {
      if (!this.modelId) return null;
      return this.models.find((m) => m.id === this.modelId) || null;
    },
    featureLabel() {
      const k = featureKey(this.feature);
      if (k) return t(k);
      if (this.feature === "ollama-daemon") return "Ollama";
      return this.feature;
    },
    isRequired() { return this.feature === "asr-required"; },
    sizeText() {
      if (!this.modelInfo || !this.modelInfo.sizeBytes) return null;
      return fmtBytes(this.modelInfo.sizeBytes);
    },
    progressPercent() {
      return Math.round(Math.min(1, Math.max(0, this.progress)) * 100);
    },
    speedText() {
      if (!this.speedBps) return "";
      return fmtBytes(this.speedBps) + "/s";
    },
    etaText() {
      if (this.etaSec == null) return "";
      return t("modal.eta", { dur: fmtSec(this.etaSec) });
    },
    canDownload() {
      if (this.isOllamaDaemon) return true;
      if (!this.modelInfo) return false;
      if (this.downloading) return false;
      return true;
    },
  },
  methods: {
    t,
    formatBytes: fmtBytes,
    async copyCommand() {
      const cmd = this.isOllamaDaemon
        ? "brew services start ollama"
        : (this.modelInfo && this.modelInfo.downloadCommand) || "";
      try {
        await navigator.clipboard.writeText(cmd);
        this.copied = true;
        setTimeout(() => { this.copied = false; }, 2000);
      } catch (_) { /* ignore */ }
    },
    async recheck() {
      this.rechecking = true;
      try {
        const resp = await fetch("/api/models");
        if (!resp.ok) return;
        const data = await resp.json();
        this.$emit("rechecked", data.models || []);
        const updated = (data.models || []).find((m) => m.id === this.modelId);
        if (updated && updated.downloaded) this.$emit("close");
      } finally {
        this.rechecking = false;
      }
    },
    async startOllamaDaemon() {
      if (this.ollamaStarting) return;
      this.ollamaStarting = true;
      this.downloadError = null;
      try {
        const resp = await fetch("/api/ollama/start", { method: "POST" });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        toast.success(t("toast.ollamaStartedTitle"), data.alreadyRunning ? t("status.ollamaAlreadyRunning") : (data.logPath || ""));
        this.downloadDone = true;
        setTimeout(() => this.$emit("close"), 800);
      } catch (err) {
        this.downloadError = err.message || String(err);
      } finally {
        this.ollamaStarting = false;
      }
    },
    async startDownload() {
      if (!this.canDownload || !this.modelId) return;
      this.downloading = true;
      this.downloadError = null;
      this.progress = 0;
      this.bytesDone = 0;
      this.bytesTotal = 0;
      try {
        const resp = await fetch("/api/models/download", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ modelId: this.modelId }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.jobId = data.jobId;
        this.attachStream(this.jobId);
      } catch (err) {
        this.downloadError = err.message || String(err);
        this.downloading = false;
      }
    },
    attachStream(jobId) {
      if (this.eventSource) this.eventSource.close();
      const es = new EventSource(`/api/models/download/${jobId}/stream`);
      this.eventSource = es;
      es.addEventListener("snapshot", (e) => {
        try {
          const d = JSON.parse(e.data);
          this.progress = d.progress || 0;
          this.bytesDone = d.bytesDone || 0;
          this.bytesTotal = d.bytesTotal || 0;
        } catch (_) {}
      });
      es.addEventListener("progress", (e) => {
        try {
          const d = JSON.parse(e.data);
          this.progress = d.progress || 0;
          this.bytesDone = d.bytesDone || 0;
          this.bytesTotal = d.bytesTotal || 0;
          this.speedBps = d.speedBps || 0;
          this.etaSec = d.etaSec;
        } catch (_) {}
      });
      es.addEventListener("log", (e) => {
        try {
          const d = JSON.parse(e.data);
          this.logTail = d.line || "";
        } catch (_) {}
      });
      es.addEventListener("error", (e) => {
        try {
          const d = JSON.parse(e.data);
          this.downloadError = d.message || t("modal.downloadFailed");
        } catch (_) {
          this.downloadError = t("modal.downloadDisconnected");
        }
        es.close();
        this.eventSource = null;
        this.downloading = false;
      });
      es.addEventListener("done", () => {
        this.progress = 1;
        this.downloadDone = true;
        this.downloading = false;
        es.close();
        this.eventSource = null;
        toast.success(t("toast.downloadDoneTitle"), (this.modelInfo && this.modelInfo.label) || this.modelId);
        this.recheck();
      });
    },
    async cancelDownload() {
      if (!this.jobId) return;
      await fetch(`/api/models/download/${this.jobId}/cancel`, { method: "POST" });
    },
  },
  beforeUnmount() {
    if (this.eventSource) this.eventSource.close();
  },
  template: `
    <div class="modal-backdrop" @click.self="!isRequired && !downloading && $emit('close')">
      <div class="modal-card" style="width: min(560px, 92vw)">
        <div class="row" style="justify-content: space-between; align-items: flex-start">
          <div>
            <div class="modal-title">
              <span v-if="isOllamaDaemon">{{ t('modal.titleOllama') }}</span>
              <span v-else-if="isRequired">{{ t('modal.titleRequired') }}</span>
              <span v-else>{{ t('modal.titleDownload', { label: modelInfo && modelInfo.label || modelId }) }}</span>
            </div>
            <div class="muted" style="font-size:13px;margin-top:6px">
              <template v-if="isOllamaDaemon">
                {{ t('modal.descOllama', { feature: featureLabel }) }}
              </template>
              <template v-else>
                {{ t('modal.descModel', { feature: featureLabel, modelId, size: sizeText ? t('modal.descSize', { size: sizeText }) : '' }) }}
              </template>
            </div>
          </div>
          <button v-if="!isRequired && !downloading" class="btn btn-icon btn-ghost" @click="$emit('close')">
            <lucide-icon name="x" :size="16" />
          </button>
        </div>

        <div v-if="modelInfo && modelInfo.downloadHint" class="muted" style="font-size:13px;line-height:1.6">
          {{ modelInfo.downloadHint }}
        </div>

        <div v-if="downloading || downloadDone" class="col" style="gap:6px">
          <div class="row" style="justify-content:space-between;font-size:12px">
            <span class="muted">{{ downloadDone ? t('modal.progressDone') : t('modal.progressDownloading') }}</span>
            <span class="muted">{{ progressPercent }}%</span>
          </div>
          <div class="progress"><div class="progress-fill is-running" :style="{ width: progressPercent + '%' }"></div></div>
          <div class="row" style="justify-content:space-between;font-size:11px;color:var(--text-secondary)">
            <span>{{ bytesDone ? formatBytes(bytesDone) : '' }}<span v-if="bytesTotal"> / {{ formatBytes(bytesTotal) }}</span></span>
            <span>{{ speedText }}<span v-if="etaText" style="margin-left:8px">{{ etaText }}</span></span>
          </div>
          <div v-if="logTail" class="muted" style="font-size:11px;font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ logTail }}</div>
        </div>

        <div v-if="downloadError" class="pre-error" style="font-size:12px">{{ downloadError }}</div>

        <details v-if="!isOllamaDaemon && modelInfo" style="font-size:12px">
          <summary class="muted" style="cursor:pointer">{{ t('modal.manualHeading') }}</summary>
          <div style="position: relative; margin-top:8px">
            <pre style="margin: 0; padding: 12px 50px 12px 12px; background: #1f2030; color: #f1f2f8; border-radius: 10px; font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 12px; line-height: 1.5; overflow-x: auto; white-space: pre-wrap; word-break: break-all;">{{ modelInfo.downloadCommand }}</pre>
            <button class="btn btn-icon btn-sm" style="position: absolute; top: 8px; right: 8px; background: rgba(255,255,255,.08); color: #f1f2f8; border-color: rgba(255,255,255,.18)" :title="copied ? t('modal.copied') : t('modal.copy')" @click="copyCommand">
              <lucide-icon name="copy" :size="12" />
            </button>
          </div>
          <div v-if="copied" class="muted" style="font-size:11px;color:var(--success);margin-top:4px">{{ t('modal.copied') }}</div>
        </details>

        <div class="modal-actions">
          <button v-if="!isRequired && !downloading" class="btn" @click="$emit('close')">{{ t('modal.btnLater') }}</button>
          <button v-if="isOllamaDaemon" class="btn btn-primary" :disabled="ollamaStarting" @click="startOllamaDaemon">
            <lucide-icon name="play" :size="14" />
            {{ ollamaStarting ? t('modal.btnStartBusy') : t('modal.btnStart') }}
          </button>
          <button v-else-if="!downloadDone && !downloading" class="btn btn-primary" :disabled="!canDownload" @click="startDownload">
            <lucide-icon name="download" :size="14" />
            {{ t('modal.btnDownload') }}
          </button>
          <button v-else-if="downloading" class="btn btn-danger" @click="cancelDownload">
            {{ t('modal.btnCancel') }}
          </button>
          <button v-else class="btn btn-primary" @click="$emit('close')">
            <lucide-icon name="check" :size="14" /> {{ t('modal.btnDone') }}
          </button>
        </div>
      </div>
    </div>
  `,
};
