import { LucideIcon } from "./icons.js";
import { t } from "../i18n.js";

export const Sidebar = {
  name: "Sidebar",
  components: { LucideIcon },
  props: {
    currentRoute: { type: String, required: true },
    models: { type: Array, default: () => [] },
  },
  emits: ["navigate"],
  computed: {
    asrModel() { return this.models.find((m) => m.id === "Qwen/Qwen3-ASR-0.6B"); },
    llmModel() { return this.models.find((m) => m.id === "qwen3:4b"); },
    diarModel() { return this.models.find((m) => m.id === "pyannote/speaker-diarization-community-1"); },
  },
  methods: {
    t,
    statusClass(m) { return m && m.downloaded ? "loaded" : "missing"; },
    statusLabel(m) { return m && m.downloaded ? t("models.loaded") : t("models.notLoaded"); },
  },
  template: `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <img src="/static/assets/app-icon-512.png" alt="" />
        </div>
        <div>
          <div class="brand-name"><em>Liasse</em></div>
          <div class="brand-version">v0.2 · {{ t('nav.tagline') }}</div>
        </div>
      </div>

      <nav class="nav">
        <button class="nav-item" :class="{ active: currentRoute === 'home' }" @click="$emit('navigate', 'home')">
          <lucide-icon name="home" />
          <span>{{ t('nav.transcribe') }}</span>
        </button>
      </nav>

      <div class="model-card">
        <div class="model-card-title"><lucide-icon name="cpu" :size="16" /> {{ t('models.cardTitle') }}</div>

        <div class="model-row">
          <div class="model-row-label">{{ t('models.asrLabel') }}</div>
          <div class="model-row-name">
            <span class="status-dot" :class="statusClass(asrModel)"></span>
            <span>Qwen3-ASR 0.6B</span>
            <span class="muted" style="font-size:11px;margin-left:auto">{{ statusLabel(asrModel) }}</span>
          </div>
        </div>

        <div class="model-row">
          <div class="model-row-label">{{ t('models.diarizeLabel') }}</div>
          <div class="model-row-name">
            <span class="status-dot" :class="statusClass(diarModel)"></span>
            <span>pyannote 4.x</span>
            <span class="muted" style="font-size:11px;margin-left:auto">{{ statusLabel(diarModel) }}</span>
          </div>
        </div>

        <div class="model-row">
          <div class="model-row-label">{{ t('models.summaryLabel') }}</div>
          <div class="model-row-name">
            <span class="status-dot" :class="statusClass(llmModel)"></span>
            <span>Qwen3 4B</span>
            <span class="muted" style="font-size:11px;margin-left:auto">{{ statusLabel(llmModel) }}</span>
          </div>
        </div>

        <div class="model-footnote">
          <lucide-icon name="monitor" :size="14" />
          <span>{{ t('models.runsLocal') }}</span>
        </div>
      </div>

      <nav class="nav sidebar-settings-nav">
        <button class="nav-item" :class="{ active: currentRoute === 'settings' }" @click="$emit('navigate', 'settings')">
          <lucide-icon name="settings" />
          <span>{{ t('nav.settings') }}</span>
        </button>
      </nav>
    </aside>
  `,
};
