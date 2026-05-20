import { LucideIcon } from "./icons.js";
import { toast } from "./toast.js";
import { t } from "../i18n.js";

const LANG_OPTIONS = [
  { value: "Chinese", label: "中文" },
  { value: "English", label: "English" },
  { value: "Cantonese", label: "粤语 / Cantonese" },
  { value: "Spanish", label: "Español" },
];

const NAME_RE = /^[\w一-鿿\-]+$/;

export const GlossaryEditor = {
  name: "GlossaryEditor",
  components: { LucideIcon },
  data() {
    return {
      names: [],
      current: null,         // {name, sourceLang, targetLang, entries, note}
      originalName: null,    // 用来判断当前是 PUT 还是 POST
      dirty: false,
      loading: false,
      saving: false,
    };
  },
  async mounted() {
    await this.refreshList();
  },
  watch: {
    current: {
      deep: true,
      handler() {
        if (this.current) this.dirty = true;
      },
    },
  },
  computed: {
    langOptions() { return LANG_OPTIONS; },
    isNew() { return this.originalName === null; },
    canSave() {
      return !!(this.current && this.current.name && NAME_RE.test(this.current.name));
    },
  },
  methods: {
    t,
    async refreshList() {
      try {
        const r = await fetch("/api/glossaries");
        if (!r.ok) return;
        const data = await r.json();
        this.names = data.names || [];
      } catch (e) { /* offline-tolerant */ }
    },
    async openGlossary(name) {
      if (this.dirty && !confirm(t("glossary.discard"))) return;
      this.loading = true;
      try {
        const r = await fetch(`/api/glossaries/${encodeURIComponent(name)}`);
        if (!r.ok) throw new Error(await r.text());
        const g = await r.json();
        this.current = {
          name: g.name,
          sourceLang: g.sourceLang || "Chinese",
          targetLang: g.targetLang || "English",
          entries: (g.entries || []).map(e => ({ ...e })),
          note: g.note || "",
        };
        this.originalName = g.name;
        // 重置 dirty,因 watch 会在 next tick 触发
        this.$nextTick(() => { this.dirty = false; });
      } catch (err) {
        toast.error(t("glossary.title"), err.message || String(err));
      } finally {
        this.loading = false;
      }
    },
    newGlossary() {
      if (this.dirty && !confirm(t("glossary.discard"))) return;
      this.current = {
        name: "",
        sourceLang: "Chinese",
        targetLang: "English",
        entries: [],
        note: "",
      };
      this.originalName = null;
      this.$nextTick(() => { this.dirty = false; });
    },
    addEntry() {
      if (!this.current) return;
      this.current.entries.push({ source: "", target: "", domain: "", note: "" });
    },
    removeEntry(idx) {
      this.current.entries.splice(idx, 1);
    },
    async save() {
      if (!this.canSave) {
        toast.error(t("glossary.title"), t("glossary.nameInvalid"));
        return;
      }
      this.saving = true;
      try {
        // 过滤掉空白条目,模型不喜欢 ""→""
        const payload = {
          ...this.current,
          entries: this.current.entries.filter(e => e.source && e.target),
        };
        const isUpdate = this.originalName === this.current.name;
        const url = isUpdate
          ? `/api/glossaries/${encodeURIComponent(this.current.name)}`
          : "/api/glossaries";
        const r = await fetch(url, {
          method: isUpdate ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!r.ok) throw new Error(await r.text());
        // 改名场景:先 POST 新名,再删旧名
        if (!isUpdate && this.originalName && this.originalName !== this.current.name) {
          await fetch(`/api/glossaries/${encodeURIComponent(this.originalName)}`, { method: "DELETE" });
        }
        this.originalName = this.current.name;
        this.$nextTick(() => { this.dirty = false; });
        await this.refreshList();
        toast.success(t("glossary.title"), t("glossary.saved"));
      } catch (err) {
        toast.error(t("glossary.title"), err.message || String(err));
      } finally {
        this.saving = false;
      }
    },
    async deleteCurrent() {
      if (!this.current || !this.originalName) {
        // 未保存的新词库,直接 discard
        this.current = null;
        this.originalName = null;
        this.dirty = false;
        return;
      }
      if (!confirm(t("glossary.confirmDelete", { name: this.current.name }))) return;
      try {
        const r = await fetch(
          `/api/glossaries/${encodeURIComponent(this.originalName)}`,
          { method: "DELETE" },
        );
        if (!r.ok && r.status !== 404) throw new Error(await r.text());
        this.current = null;
        this.originalName = null;
        this.dirty = false;
        await this.refreshList();
        toast.success(t("glossary.title"), t("glossary.deleted"));
      } catch (err) {
        toast.error(t("glossary.title"), err.message || String(err));
      }
    },
  },
  template: `
    <section class="glossary-editor">
      <div class="settings-row" style="border-bottom:none">
        <div>
          <div class="settings-row-label">{{ t('glossary.title') }}</div>
          <div class="settings-row-hint">{{ t('glossary.hint') }}</div>
        </div>
        <button class="btn btn-sm btn-primary" @click="newGlossary">
          <lucide-icon name="plus" :size="14" />
          {{ t('glossary.newButton') }}
        </button>
      </div>

      <div class="glossary-body">
        <aside class="glossary-list" :class="{ empty: !names.length }">
          <div v-if="!names.length" class="muted glossary-empty">{{ t('glossary.empty') }}</div>
          <ul v-else>
            <li v-for="n in names" :key="n">
              <button
                class="glossary-list-btn"
                :class="{ active: current && originalName === n }"
                @click="openGlossary(n)"
              >{{ n }}</button>
            </li>
          </ul>
        </aside>

        <main class="glossary-editor-panel" v-if="current">
          <div class="row" style="gap:12px; align-items:flex-end; flex-wrap:wrap">
            <label class="field">
              <span class="field-label">{{ t('glossary.nameLabel') }}</span>
              <input
                type="text"
                v-model="current.name"
                :placeholder="t('glossary.namePlaceholder')"
                :disabled="saving"
              />
            </label>
            <label class="field">
              <span class="field-label">{{ t('glossary.sourceLangLabel') }}</span>
              <select v-model="current.sourceLang">
                <option v-for="o in langOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">{{ t('glossary.targetLangLabel') }}</span>
              <select v-model="current.targetLang">
                <option v-for="o in langOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </label>
          </div>

          <div class="glossary-entries-head">
            <span class="field-label">{{ t('glossary.entriesLabel') }}</span>
            <button class="btn btn-sm" @click="addEntry">
              <lucide-icon name="plus" :size="13" /> {{ t('glossary.addEntry') }}
            </button>
          </div>

          <table class="glossary-table">
            <thead>
              <tr>
                <th>{{ t('glossary.colSource') }}</th>
                <th>{{ t('glossary.colTarget') }}</th>
                <th>{{ t('glossary.colDomain') }}</th>
                <th>{{ t('glossary.colNote') }}</th>
                <th class="col-x"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in current.entries" :key="i">
                <td><input v-model="e.source" /></td>
                <td><input v-model="e.target" /></td>
                <td><input v-model="e.domain" /></td>
                <td><input v-model="e.note" /></td>
                <td class="col-x">
                  <button class="btn btn-icon" @click="removeEntry(i)" :title="t('glossary.delete')">
                    <lucide-icon name="x" :size="14" />
                  </button>
                </td>
              </tr>
              <tr v-if="!current.entries.length">
                <td colspan="5" class="muted" style="text-align:center; padding:14px">
                  {{ t('glossary.empty') }}
                </td>
              </tr>
            </tbody>
          </table>

          <div class="row" style="gap:10px; margin-top:12px">
            <button class="btn btn-primary" :disabled="!canSave || saving" @click="save">
              {{ saving ? '…' : t('glossary.save') }}
            </button>
            <button class="btn btn-danger" @click="deleteCurrent">
              <lucide-icon name="trash-2" :size="14" /> {{ t('glossary.delete') }}
            </button>
            <span v-if="dirty" class="muted" style="font-size:12px">●</span>
          </div>
        </main>
        <main class="glossary-editor-panel placeholder" v-else>
          <p class="muted">{{ t('glossary.placeholder') }}</p>
        </main>
      </div>
    </section>
  `,
};
