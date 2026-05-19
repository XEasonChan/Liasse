import { LucideIcon } from "./icons.js";
import { toast } from "./toast.js";
import { t } from "../i18n.js";

const ACCEPT_EXT = [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".mp4"];

function hasNativeApi() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.pick_files);
}

export const UploadZone = {
  name: "UploadZone",
  components: { LucideIcon },
  props: {
    llmReady: { type: Boolean, default: false },
    diarizeReady: { type: Boolean, default: true },
    asrReady: { type: Boolean, default: true },
    runtimeReady: { type: Boolean, default: true },
    nativeReady: { type: Boolean, default: false },
  },
  emits: ["upload", "need-model"],
  data() {
    return {
      uiState: "idle",
      isDragOver: false,
      pendingCount: 0,
      skippedCount: 0,
      lastBatchInfo: null,
      errorMessage: null,
      config: {
        asrModel: "Qwen/Qwen3-ASR-0.6B",
        language: "English",
        diarize: true,
        numSpeakers: 2,
        autoSegment: true,
        summarize: false,
        enableChat: true,
      },
    };
  },
  async mounted() {
    try {
      const resp = await fetch("/api/settings");
      if (!resp.ok) return;
      const s = await resp.json();
      if (s.defaultASRModel) this.config.asrModel = s.defaultASRModel;
      if (s.defaultLanguage) this.config.language = s.defaultLanguage;
      if (typeof s.defaultDiarize === "boolean") this.config.diarize = s.defaultDiarize;
      if (s.defaultNumSpeakers !== undefined) this.config.numSpeakers = s.defaultNumSpeakers;
      if (typeof s.defaultSummarize === "boolean") this.config.summarize = s.defaultSummarize;
    } catch (_) { /* ignore */ }
  },
  computed: {
    accept() { return ACCEPT_EXT.join(","); },
    diarizeBlocked() { return !this.config.autoSegment; },
    diarizeState() {
      if (this.diarizeBlocked) return "off";
      if (!this.diarizeReady) return "warn";
      return this.config.diarize ? "on" : "";
    },
    diarizeTooltip() {
      if (this.diarizeBlocked) return t("upload.tipDiarizeBlocked");
      if (!this.diarizeReady) return t("upload.tipDiarizeNeed");
      return t("upload.tipDiarizeOn");
    },
    summaryToggleClass() {
      if (!this.llmReady) return "warn";
      return this.config.summarize ? "on" : "";
    },
    summaryTooltip() {
      return t(this.llmReady ? "upload.tipSummaryOn" : "upload.tipSummaryNeed");
    },
    isBusy() {
      return ["dialog-opening", "validating", "creating-tasks"].includes(this.uiState);
    },
    busyText() {
      switch (this.uiState) {
        case "dialog-opening": return t("upload.titleDialogOpening");
        case "validating": return t("upload.titleValidating", { n: this.pendingCount });
        case "creating-tasks": return t("upload.titleCreating", { n: this.pendingCount });
        default: return "";
      }
    },
    speakerSummary() {
      if (this.config.autoSegment && this.config.diarize && this.diarizeReady) return t("upload.cfgSpeakers");
      if (!this.config.autoSegment || !this.config.diarize) return t("upload.summaryDiarizeOff");
      if (!this.diarizeReady) return t("upload.summaryDiarizeNeed");
      return t("upload.cfgSpeakers");
    },
    summarySummary() {
      if (!this.llmReady) return t("upload.summaryNeedQwen");
      return this.config.summarize ? t("upload.summaryOn") : t("upload.summaryOff");
    },
  },
  methods: {
    handleDiarizeClick() {
      if (this.diarizeBlocked) return;
      if (!this.diarizeReady) { this.$emit("need-model", "diarize"); return; }
      this.config.diarize = !this.config.diarize;
    },
    handleSummaryClick() {
      if (!this.llmReady) { this.$emit("need-model", "summary"); return; }
      this.config.summarize = !this.config.summarize;
    },

    onZoneClick() {
      if (this.isBusy) return;
      this.triggerFiles();
    },

    async triggerFiles() {
      if (this.isBusy) return;
      if (!this.runtimeReady) {
        toast.info("正在安装运行环境", "请等核心引擎装好后再上传文件（顶部 banner 有进度）。");
        return;
      }
      if (!this.asrReady) {
        this.$emit("need-model", "asr-required");
        return;
      }
      if (hasNativeApi()) {
        await this.pickViaNative("files");
      } else {
        this.$refs.filesInput && this.$refs.filesInput.click();
      }
    },

    async triggerFolder() {
      if (this.isBusy) return;
      if (!this.runtimeReady) {
        toast.info("正在安装运行环境", "请等核心引擎装好后再上传文件（顶部 banner 有进度）。");
        return;
      }
      if (!this.asrReady) {
        this.$emit("need-model", "asr-required");
        return;
      }
      if (hasNativeApi() && window.pywebview.api.pick_folder) {
        await this.pickViaNative("folder");
      } else {
        this.$refs.folderInput && this.$refs.folderInput.click();
      }
    },

    async pickViaNative(kind) {
      this.uiState = "dialog-opening";
      this.errorMessage = null;
      try {
        if (kind === "folder") {
          const r = await window.pywebview.api.pick_folder();
          if (r && r.cancelled) { this.uiState = "idle"; return; }
          const paths = (r && r.paths) || [];
          if (!paths.length) {
            this.uiState = "no-valid-files";
            this.errorMessage = t("upload.feedbackNoValid");
            return;
          }
          await this.processPaths(paths);
        } else {
          const paths = await window.pywebview.api.pick_files();
          if (!paths || !paths.length) { this.uiState = "idle"; return; }
          await this.processPaths(paths);
        }
      } catch (err) {
        this.uiState = "error";
        this.errorMessage = t("upload.feedbackPickFail", { msg: err.message || err });
        toast.error(t("toast.pickFailedTitle"), this.errorMessage);
      }
    },

    onDragEnter(e) { e.preventDefault(); this.isDragOver = true; },
    onDragLeave(e) { e.preventDefault(); this.isDragOver = false; },
    onDragOver(e) { e.preventDefault(); this.isDragOver = true; },
    async onDrop(e) {
      e.preventDefault();
      this.isDragOver = false;
      if (this.isBusy) return;
      if (!this.runtimeReady) {
        toast.info("正在安装运行环境", "请等核心引擎装好后再上传文件（顶部 banner 有进度）。");
        return;
      }
      if (!this.asrReady) {
        this.$emit("need-model", "asr-required");
        return;
      }
      const items = e.dataTransfer.items;
      if (items && items[0] && items[0].webkitGetAsEntry) {
        const collected = [];
        const tasks = [];
        for (let i = 0; i < items.length; i++) {
          const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
          if (entry) tasks.push(this.walkEntry(entry, collected));
        }
        await Promise.all(tasks);
        this.handleBrowserFiles(collected);
      } else {
        this.handleBrowserFiles(Array.from(e.dataTransfer.files || []));
      }
    },
    walkEntry(entry, out) {
      return new Promise((resolve) => {
        if (entry.isFile) {
          entry.file((f) => { out.push(f); resolve(); }, () => resolve());
        } else if (entry.isDirectory) {
          const reader = entry.createReader();
          const readBatch = () => {
            reader.readEntries(async (entries) => {
              if (!entries.length) return resolve();
              await Promise.all(entries.map((e) => this.walkEntry(e, out)));
              readBatch();
            }, () => resolve());
          };
          readBatch();
        } else {
          resolve();
        }
      });
    },

    onSelectFiles(e) {
      this.handleBrowserFiles(Array.from(e.target.files || []));
      e.target.value = "";
    },
    onSelectFolder(e) {
      this.handleBrowserFiles(Array.from(e.target.files || []));
      e.target.value = "";
    },

    async processPaths(paths) {
      this.uiState = "validating";
      this.pendingCount = paths.length;
      this.errorMessage = null;
      await this.$nextTick();
      const valid = paths.filter((p) => {
        const lower = p.toLowerCase();
        return ACCEPT_EXT.some((ext) => lower.endsWith(ext));
      });
      this.skippedCount = paths.length - valid.length;
      if (!valid.length) {
        this.uiState = "no-valid-files";
        this.errorMessage = t("upload.feedbackNoValid");
        return;
      }
      await this.createFromPaths(valid);
    },

    async createFromPaths(paths) {
      this.uiState = "creating-tasks";
      this.pendingCount = paths.length;
      try {
        const cfg = this.buildConfig();
        const resp = await fetch("/api/tasks/create-from-paths", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths, config: cfg }),
        });
        if (!resp.ok) {
          const txt = await resp.text();
          throw new Error(txt);
        }
        const data = await resp.json();
        const created = (data.tasks || []).length;
        const skipped = (data.skipped || []).length + this.skippedCount;
        this.lastBatchInfo = skipped
          ? t("upload.feedbackAddedWithSkipped", { n: created, skipped })
          : t("upload.feedbackAdded", { n: created });
        this.uiState = "created";
        toast.success(t("toast.addedTitle"), t("toast.addedBody", { n: created }));
        this.$emit("upload", data.tasks);
        setTimeout(() => {
          if (this.uiState === "created") this.uiState = "idle";
          this.lastBatchInfo = null;
        }, 4000);
      } catch (err) {
        this.uiState = "error";
        this.errorMessage = t("upload.feedbackQueueFail", { msg: err.message || err });
        toast.error(t("toast.queueFailedTitle"), err.message || String(err));
      }
    },

    async handleBrowserFiles(files) {
      this.uiState = "validating";
      this.errorMessage = null;
      const valid = files.filter((f) => {
        const name = (f.name || "").toLowerCase();
        return ACCEPT_EXT.some((ext) => name.endsWith(ext));
      });
      this.skippedCount = files.length - valid.length;
      this.pendingCount = valid.length;
      if (!valid.length) {
        this.uiState = "no-valid-files";
        this.errorMessage = t("upload.feedbackNoValid");
        return;
      }
      await this.uploadBrowserFiles(valid);
    },

    async uploadBrowserFiles(files) {
      this.uiState = "creating-tasks";
      this.pendingCount = files.length;
      const fd = new FormData();
      for (const f of files) fd.append("files", f, f.name);
      fd.append("config", JSON.stringify(this.buildConfig()));
      try {
        const resp = await fetch("/api/tasks/upload", { method: "POST", body: fd });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        const created = (data.tasks || []).length;
        this.lastBatchInfo = t("upload.feedbackAdded", { n: created });
        this.uiState = "created";
        toast.success(t("toast.addedTitle"), t("toast.addedBody", { n: created }));
        this.$emit("upload", data.tasks);
        setTimeout(() => {
          if (this.uiState === "created") this.uiState = "idle";
          this.lastBatchInfo = null;
        }, 4000);
      } catch (err) {
        this.uiState = "error";
        this.errorMessage = t("upload.feedbackUploadFail", { msg: err.message || err });
        toast.error(t("toast.uploadFailedTitle"), err.message || String(err));
      }
    },

    buildConfig() {
      const cfg = { ...this.config };
      if (!this.llmReady) {
        cfg.summarize = false;
        cfg.enableChat = false;
      }
      if (!cfg.autoSegment) cfg.diarize = false;
      if (cfg.numSpeakers === "auto") cfg.numSpeakers = null;
      return cfg;
    },

    resetToIdle() {
      this.uiState = "idle";
      this.errorMessage = null;
      this.lastBatchInfo = null;
      this.pendingCount = 0;
      this.skippedCount = 0;
    },
    t,
  },
  template: `
    <section class="upload-workbench">
      <div
        class="upload-zone"
        :class="{ 'is-drag-over': isDragOver, 'is-busy': isBusy }"
        @dragenter="onDragEnter"
        @dragleave="onDragLeave"
        @dragover="onDragOver"
        @drop="onDrop"
      >
        <div class="upload-main" @click="onZoneClick">
          <div class="upload-icon">
            <lucide-icon v-if="!isBusy" name="folder-up" :size="22" :stroke-width="1.7" />
            <div v-else class="spinner"></div>
          </div>

          <div class="upload-copy">
            <div class="upload-title">{{ isBusy ? busyText : t('upload.title') }}</div>
            <div v-if="!isBusy" class="upload-hint">
              {{ t('upload.formats') }}<span v-if="nativeReady"> · {{ t('upload.nativePathBadge') }}</span>
            </div>
          </div>

          <div v-if="!isBusy" class="upload-buttons" @click.stop>
            <button class="btn btn-primary" :disabled="isBusy" @click="triggerFiles">
              <lucide-icon name="file-audio" :size="16" /> {{ t('upload.chooseFiles') }}
            </button>
            <button class="btn" :disabled="isBusy" @click="triggerFolder">
              <lucide-icon name="folder-open" :size="16" /> {{ t('upload.chooseFolder') }}
            </button>
          </div>
        </div>

        <div class="config-row" @click.stop>
          <span class="config-prefix">{{ t('upload.currentSettings') }}</span>
          <div class="config-controls">
            <div class="setting-pill setting-pill-combo" :class="diarizeState">
              <button
                class="setting-pill-action"
                :disabled="diarizeBlocked"
                :title="diarizeTooltip"
                @click="handleDiarizeClick"
              >
                <lucide-icon name="users" :size="14" />
                <span>{{ speakerSummary }}</span>
              </button>
              <select v-if="config.diarize && !diarizeBlocked && diarizeReady" class="setting-inline-select" v-model="config.numSpeakers" :title="t('upload.cfgDiarize')">
                <option :value="null">{{ t('upload.speakersAuto') }}</option>
                <option :value="2">{{ t('upload.speakersN', { n: 2 }) }}</option>
                <option :value="3">{{ t('upload.speakersN', { n: 3 }) }}</option>
                <option :value="4">{{ t('upload.speakersN', { n: 4 }) }}</option>
                <option :value="5">{{ t('upload.speakersPlus', { n: 5 }) }}</option>
              </select>
            </div>

            <button
              class="setting-pill"
              :class="config.autoSegment ? 'on' : ''"
              @click="config.autoSegment = !config.autoSegment"
            >
              <lucide-icon name="list-tree" :size="14" />
              {{ t('upload.cfgAutoSegment') }}
            </button>

            <button
              class="setting-pill"
              :class="summaryToggleClass"
              :title="summaryTooltip"
              @click="handleSummaryClick"
            >
              <lucide-icon name="sparkles" :size="14" />
              {{ summarySummary }}
            </button>

            <div class="setting-pill setting-pill-radio">
              <span class="setting-label">{{ t('upload.cfgASR') }}</span>
              <div class="compact-radio">
                <label>
                  <input type="radio" value="Qwen/Qwen3-ASR-0.6B" v-model="config.asrModel" />
                  <span>{{ t('upload.cfgASRQuick') }}</span>
                </label>
                <label class="disabled">
                  <input type="radio" value="Qwen/Qwen3-ASR-1.7B" v-model="config.asrModel" disabled />
                  <span>{{ t('upload.cfgASRHigh') }}</span>
                </label>
              </div>
            </div>

            <label class="setting-pill setting-pill-select">
              <span class="setting-label">{{ t('upload.cfgLang') }}</span>
              <select class="setting-inline-select" v-model="config.language">
                <option value="English">{{ t('audioLang.English') }}</option>
                <option value="Chinese">{{ t('audioLang.Chinese') }}</option>
                <option value="Cantonese">{{ t('audioLang.Cantonese') }}</option>
                <option value="auto">{{ t('audioLang.auto') }}</option>
              </select>
            </label>
          </div>
        </div>

        <input ref="filesInput" type="file" multiple style="display:none" :accept="accept" @change="onSelectFiles" />
        <input ref="folderInput" type="file" webkitdirectory directory multiple style="display:none" @change="onSelectFolder" />
      </div>

      <div v-if="uiState === 'created' && lastBatchInfo" class="upload-feedback success">
        <lucide-icon name="check-circle" :size="14" /> {{ lastBatchInfo }}
      </div>
      <div v-else-if="errorMessage && uiState === 'no-valid-files'" class="upload-feedback warn">
        <lucide-icon name="alert-triangle" :size="14" /> {{ errorMessage }}
        <button class="btn btn-sm btn-ghost" style="margin-left:8px" @click="resetToIdle">{{ t('upload.btnReselect') }}</button>
      </div>
      <div v-else-if="errorMessage && uiState === 'error'" class="upload-feedback error">
        <lucide-icon name="alert-circle" :size="14" /> {{ errorMessage }}
        <button class="btn btn-sm btn-ghost" style="margin-left:8px" @click="resetToIdle">{{ t('upload.btnRetry') }}</button>
      </div>
      <div v-else-if="skippedCount > 0 && uiState === 'creating-tasks'" class="upload-feedback info">
        {{ t('upload.feedbackIgnored', { skipped: skippedCount, valid: pendingCount }) }}
      </div>

    </section>
  `,
};
