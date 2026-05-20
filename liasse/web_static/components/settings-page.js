import { LucideIcon } from "./icons.js";
import { GlossaryEditor } from "./glossary-editor.js";
import { t, i18n, setLocale, LOCALES } from "../i18n.js";

const ASR_MODEL_OPTIONS = [
  { id: "Qwen/Qwen3-ASR-0.6B", labelKey: "settings.asrQuick" },
  { id: "Qwen/Qwen3-ASR-1.7B", labelKey: "settings.asrHigh" },
];

export const SettingsPage = {
  name: "SettingsPage",
  components: { LucideIcon, GlossaryEditor },
  props: {
    models: { type: Array, default: () => [] },
  },
  data() {
    return {
      settings: null,
      loading: true,
      saving: false,
      message: null,
      confirmClear: false,
      locales: LOCALES,
      i18nState: i18n,
    };
  },
  async mounted() {
    await this.load();
  },
  computed: {
    asrModelOptions() { return ASR_MODEL_OPTIONS; },
  },
  methods: {
    t,
    async load() {
      this.loading = true;
      try {
        const resp = await fetch("/api/settings");
        if (!resp.ok) throw new Error(await resp.text());
        this.settings = await resp.json();
        if (!this.settings.defaultSpeakerMode) {
          this.settings.defaultSpeakerMode = this.settings.defaultDiarize ? "llm" : "fast";
        }
      } catch (err) {
        this.message = { type: "error", text: t("settings.loadFail", { msg: err.message || err }) };
      } finally {
        this.loading = false;
      }
    },
    async save() {
      if (!this.settings) return;
      this.saving = true;
      this.message = null;
      try {
        const resp = await fetch("/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.settings),
        });
        if (!resp.ok) throw new Error(await resp.text());
        this.settings = await resp.json();
        this.message = { type: "ok", text: t("settings.saved") };
      } catch (err) {
        this.message = { type: "error", text: t("settings.saveFail", { msg: err.message || err }) };
      } finally {
        this.saving = false;
      }
    },
    async clearHistory() {
      if (!this.confirmClear) { this.confirmClear = true; return; }
      this.confirmClear = false;
      try {
        const resp = await fetch("/api/tasks", { method: "DELETE" });
        if (!resp.ok) throw new Error(await resp.text());
        this.message = { type: "ok", text: t("settings.historyCleared") };
      } catch (err) {
        this.message = { type: "error", text: t("settings.historyClearFail", { msg: err.message || err }) };
      }
    },
    changeLocale(code) { setLocale(code); },
    modelInfo(id) {
      return this.models.find((mm) => mm.id === id) || null;
    },
    modelLabel(id) {
      const m = this.modelInfo(id);
      if (!m) return `${id} (${t("settings.checking")})`;
      return m.label + (m.downloaded ? ` (${t("settings.loaded")})` : ` (${t("settings.notLoaded")})`);
    },
    modelStatusLabel(id) {
      const m = this.modelInfo(id);
      if (!m) return t("settings.checking");
      return m.downloaded ? t("settings.loaded") : t("settings.notLoaded");
    },
    asrOptionLabel(option) {
      return `${t(option.labelKey)} (${this.modelStatusLabel(option.id)})`;
    },
    isModelSelectable(id) {
      const m = this.modelInfo(id);
      return !m || m.downloaded;
    },
    statusOf(id) {
      const m = this.modelInfo(id);
      return m && m.downloaded ? "loaded" : "missing";
    },
  },
  template: `
    <div class="main-scroll">
      <div>
        <h1 class="page-title">{{ t('settings.title') }}</h1>
        <p class="page-subtitle">{{ t('settings.subtitle') }}</p>
      </div>

      <div v-if="loading" class="settings-empty-state">
        <span class="muted">Loading settings…</span>
      </div>
      <div v-else-if="!settings" class="settings-empty-state">
        <p class="muted" style="margin-bottom: 12px;">
          {{ message ? message.text : 'Settings could not be loaded.' }}
        </p>
        <button class="btn btn-sm" @click="load">Retry</button>
      </div>
      <template v-else>

        <div class="settings-card">
          <div class="section-head"><h2 class="section-title">{{ t('settings.sectionAppearance') }}</h2></div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.uiLanguage') }}</div>
              <div class="settings-row-hint">{{ t('settings.uiLanguageHint') }}</div>
            </div>
            <div class="row" style="gap:6px">
              <button
                v-for="loc in locales"
                :key="loc.code"
                class="btn btn-sm"
                :class="{ 'btn-primary': i18nState.locale === loc.code }"
                @click="changeLocale(loc.code)"
              >{{ loc.label }}</button>
            </div>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-head"><h2 class="section-title">{{ t('settings.sectionDefaults') }}</h2></div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.outputDir') }}</div>
              <div class="settings-row-hint">{{ t('settings.outputDirHint') }}</div>
            </div>
            <input type="text" v-model="settings.outputDir" />
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.asrModel') }}</div>
              <div class="settings-row-hint">{{ modelLabel(settings.defaultASRModel) }}</div>
            </div>
            <select v-model="settings.defaultASRModel">
              <option
                v-for="option in asrModelOptions"
                :key="option.id"
                :value="option.id"
                :disabled="!isModelSelectable(option.id)"
              >{{ asrOptionLabel(option) }}</option>
            </select>
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.audioLang') }}</div>
            </div>
            <select v-model="settings.defaultLanguage">
              <option value="English">{{ t('audioLang.English') }}</option>
              <option value="Chinese">{{ t('audioLang.Chinese') }}</option>
              <option value="Cantonese">{{ t('audioLang.Cantonese') }}</option>
              <option value="auto">{{ t('audioLang.auto') }}</option>
            </select>
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.speakerMode') }}</div>
              <div class="settings-row-hint">{{ t('settings.speakerModeHint') }}</div>
            </div>
            <select v-model="settings.defaultSpeakerMode">
              <option value="fast">{{ t('upload.speakerModeFast') }}</option>
              <option value="llm">{{ t('upload.speakerModeLLM') }}</option>
              <option value="pyannote">{{ t('upload.speakerModePyannote') }}</option>
            </select>
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.numSpeakers') }}</div>
              <div class="settings-row-hint">{{ t('settings.numSpeakersHint') }}</div>
            </div>
            <select v-model="settings.defaultNumSpeakers">
              <option :value="null">{{ t('upload.speakersAuto') }}</option>
              <option :value="2">2</option>
              <option :value="3">3</option>
              <option :value="4">4</option>
              <option :value="5">5+</option>
            </select>
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.summarize') }}</div>
              <div class="settings-row-hint">{{ t('settings.summarizeHint') }}</div>
            </div>
            <button class="toggle" :class="{ on: settings.defaultSummarize }" @click="settings.defaultSummarize = !settings.defaultSummarize">
              {{ settings.defaultSummarize ? t('settings.on') : t('settings.off') }}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-head"><h2 class="section-title">{{ t('settings.sectionPrivacy') }}</h2></div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.fullyOffline') }}</div>
              <div class="settings-row-hint">{{ t('settings.fullyOfflineHint') }}</div>
            </div>
            <button class="toggle" :class="{ on: settings.fullyOffline }" @click="settings.fullyOffline = !settings.fullyOffline">
              {{ settings.fullyOffline ? t('settings.on') : t('settings.off') }}
            </button>
          </div>

          <div class="settings-row">
            <div>
              <div class="settings-row-label">{{ t('settings.clearHistory') }}</div>
              <div class="settings-row-hint">{{ t('settings.clearHistoryHint') }}</div>
            </div>
            <button class="btn" :class="{ 'btn-danger': confirmClear }" @click="clearHistory">
              <lucide-icon name="trash-2" :size="14" />
              {{ confirmClear ? t('settings.clearOnce') : t('settings.clearBtn') }}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-head"><h2 class="section-title">{{ t('settings.sectionModels') }}</h2></div>
          <div v-for="m in models" :key="m.id" class="settings-row">
            <div>
              <div class="settings-row-label">{{ m.label }}</div>
              <div class="settings-row-hint">{{ m.id }}</div>
            </div>
            <div class="row">
              <span class="status-dot" :class="statusOf(m.id)"></span>
              <span class="muted">{{ m.downloaded ? t('settings.loaded') : t('settings.notLoaded') }}</span>
            </div>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-head"><h2 class="section-title">{{ t('glossary.title') }}</h2></div>
          <glossary-editor />
        </div>

        <div class="row" style="gap: 12px">
          <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? t('settings.saving') : t('settings.save') }}</button>
          <span v-if="message" :style="{ color: message.type === 'ok' ? 'var(--success)' : 'var(--danger)' }" style="font-size:13px">{{ message.text }}</span>
        </div>
      </template>
    </div>
  `,
};
