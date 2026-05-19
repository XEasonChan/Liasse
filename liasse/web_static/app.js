import { Sidebar } from "./components/sidebar.js";
import { UploadZone } from "./components/upload-zone.js";
import { TaskList } from "./components/task-list.js";
import { TaskDetail } from "./components/task-detail.js";
import { SettingsPage } from "./components/settings-page.js";
import { ModelRequiredModal } from "./components/model-required-modal.js";
import { LucideIcon } from "./components/icons.js";
import { StatusBar } from "./components/statusbar.js";
import { ToastStack, toast } from "./components/toast.js";
import { DialogHost } from "./components/dialog.js";
import { t } from "./i18n.js";

const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount, watch } = window.Vue;

function parseHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("/task/")) {
    return { name: "task", taskId: hash.slice("/task/".length) };
  }
  if (hash === "/settings") return { name: "settings" };
  return { name: "home" };
}

function navigateTo(target) {
  if (target === "home") window.location.hash = "/";
  else if (target === "settings") window.location.hash = "/settings";
  else if (target && target.startsWith("task:")) window.location.hash = `/task/${target.slice(5)}`;
}

const ErrorModal = {
  name: "ErrorModal",
  components: { LucideIcon },
  props: { task: { type: Object, required: true } },
  emits: ["close"],
  methods: { t },
  template: `
    <div class="modal-backdrop" @click.self="$emit('close')">
      <div class="modal-card">
        <div class="modal-title">{{ t('modal.errorTitle', { name: task.fileName }) }}</div>
        <div class="pre-error">{{ task.errorMessage || t('modal.errorNone') }}</div>
        <div class="modal-actions">
          <button class="btn" @click="$emit('close')">{{ t('modal.close') }}</button>
        </div>
      </div>
    </div>
  `,
};

const ConfirmDeleteModal = {
  name: "ConfirmDeleteModal",
  components: { LucideIcon },
  props: { task: { type: Object, required: true } },
  emits: ["confirm", "close"],
  data() { return { deleteOutputs: false }; },
  methods: { t },
  template: `
    <div class="modal-backdrop" @click.self="$emit('close')">
      <div class="modal-card">
        <div class="modal-title">{{ t('modal.deleteTitle') }}</div>
        <div v-html="t('modal.deleteBody', { name: '<strong>' + task.fileName + '</strong>' })"></div>
        <label class="row" style="font-size:13px; color: var(--text-secondary)">
          <input type="checkbox" v-model="deleteOutputs" />
          {{ t('modal.deleteAlso') }}
        </label>
        <div class="modal-actions">
          <button class="btn" @click="$emit('close')">{{ t('modal.cancel') }}</button>
          <button class="btn btn-primary" @click="$emit('confirm', deleteOutputs)">{{ t('modal.confirmDelete') }}</button>
        </div>
      </div>
    </div>
  `,
};

const App = {
  components: {
    Sidebar, UploadZone, TaskList, TaskDetail, SettingsPage,
    ErrorModal, ConfirmDeleteModal, ModelRequiredModal,
    StatusBar, ToastStack, DialogHost, LucideIcon,
  },
  setup() {
    const route = ref(parseHash());
    const tasks = ref([]);
    const models = ref([]);
    const health = ref({ checks: {} });
    const installProgress = ref(null);
    const errorModalFor = ref(null);
    const deleteModalFor = ref(null);
    const modelModalFor = ref(null);
    const pollIntervalId = ref(null);
    const modelsIntervalId = ref(null);
    const installIntervalId = ref(null);
    const nativeReady = ref(false);
    const preflightShown = ref(false);
    const now = ref(Date.now());
    const tickerId = ref(null);

    const onHashChange = () => { route.value = parseHash(); };

    const runtimeReady = computed(() => {
      // 健康未抓到时默认 true，避免一开机就闪 banner
      if (!health.value || health.value.runtime_ready === undefined) return true;
      return !!health.value.runtime_ready;
    });
    const asrReady = computed(() => !!(health.value.checks && health.value.checks.asr_model));
    const llmReady = computed(() => {
      const m = models.value.find((mm) => mm.id === "qwen3:4b");
      return !!(m && m.downloaded) && !!(health.value.checks && health.value.checks.ollama);
    });
    const diarizeReady = computed(() => {
      const m = models.value.find((mm) => mm.id === "pyannote/speaker-diarization-community-1");
      return !!(m && m.downloaded);
    });

    const previousStatuses = new Map();

    async function refreshTasks() {
      try {
        const resp = await fetch("/api/tasks");
        if (!resp.ok) return;
        const data = await resp.json();
        const newTasks = data.tasks || [];

        for (const task of newTasks) {
          const prev = previousStatuses.get(task.id);
          if (prev && prev !== task.status) {
            if (task.status === "done") {
              toast.success(
                t("toast.doneTitle"),
                task.fileName,
                { actionLabel: t("toast.view"), action: () => navigateTo(`task:${task.id}`) },
              );
            } else if (task.status === "failed") {
              toast.error(
                t("toast.failedTitle"),
                task.fileName,
                { actionLabel: t("toast.view"), action: () => { errorModalFor.value = task; } },
              );
            }
          }
          previousStatuses.set(task.id, task.status);
        }
        tasks.value = newTasks;
      } catch (_) { /* ignore */ }
    }

    async function refreshModels() {
      try {
        const [hResp, mResp] = await Promise.all([fetch("/api/health"), fetch("/api/models")]);
        if (hResp.ok) health.value = await hResp.json();
        if (mResp.ok) models.value = (await mResp.json()).models || [];
      } catch (_) { /* ignore */ }
    }

    async function refreshInstallProgress() {
      try {
        const resp = await fetch("/api/install/progress");
        if (!resp.ok) return;
        installProgress.value = await resp.json();
      } catch (_) { /* ignore */ }
    }

    async function preflight() {
      if (preflightShown.value) return;
      await refreshModels();
      const blockers = (health.value && health.value.blockers) || [];
      if (blockers.includes("asr_model")) {
        modelModalFor.value = "asr-required";
        preflightShown.value = true;
      } else if (blockers.includes("ffmpeg")) {
        toast.error(
          t("toast.blockerFfmpeg"),
          t("toast.blockerFfmpegBody"),
          { persist: true },
        );
        preflightShown.value = true;
      }
    }

    function pywebviewReady() {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_files) {
        nativeReady.value = true;
        return true;
      }
      return false;
    }

    function waitForPywebview() {
      if (pywebviewReady()) return;
      window.addEventListener("pywebviewready", () => { pywebviewReady(); }, { once: true });
      let tries = 0;
      const tid = setInterval(() => {
        tries += 1;
        if (pywebviewReady() || tries > 30) clearInterval(tid);
      }, 200);
    }

    onMounted(() => {
      window.addEventListener("hashchange", onHashChange);
      waitForPywebview();
      refreshTasks();
      refreshModels().then(() => preflight());
      refreshInstallProgress();
      pollIntervalId.value = setInterval(() => { refreshTasks(); }, 2000);
      modelsIntervalId.value = setInterval(() => refreshModels(), 15000);
      // 运行环境没就绪时每 3 秒探一次进度；就绪后切到 30 秒一次（廉价心跳）
      installIntervalId.value = setInterval(() => {
        if (!runtimeReady.value) refreshInstallProgress();
      }, 3000);
      tickerId.value = setInterval(() => { now.value = Date.now(); }, 1000);
    });
    onBeforeUnmount(() => {
      window.removeEventListener("hashchange", onHashChange);
      if (pollIntervalId.value) clearInterval(pollIntervalId.value);
      if (modelsIntervalId.value) clearInterval(modelsIntervalId.value);
      if (installIntervalId.value) clearInterval(installIntervalId.value);
      if (tickerId.value) clearInterval(tickerId.value);
    });

    function onNavigate(target) { navigateTo(target); }
    function onUpload(newTasks) {
      const merged = [...(newTasks || []), ...tasks.value];
      const seen = new Set();
      tasks.value = merged.filter((t) => {
        if (seen.has(t.id)) return false;
        seen.add(t.id);
        return true;
      });
      refreshTasks();
    }
    async function onRetry(task) {
      try {
        const resp = await fetch(`/api/tasks/${task.id}/retry`, { method: "POST" });
        if (!resp.ok) throw new Error(await resp.text());
        toast.info(t("toast.addedTitle"), task.fileName);
      } catch (err) {
        toast.error(t("toast.queueFailedTitle"), err.message || String(err));
      }
      refreshTasks();
    }
    async function onStop(task) {
      try {
        await fetch(`/api/tasks/${task.id}/stop`, { method: "POST" });
        toast.info(t("toast.stoppedTitle"), task.fileName);
      } catch (err) {
        toast.error(t("toast.stopFailedTitle"), err.message || String(err));
      }
      refreshTasks();
    }
    function onDelete(task) { deleteModalFor.value = task; }
    async function confirmDelete(deleteOutputs) {
      const target = deleteModalFor.value;
      if (!target) return;
      try {
        await fetch(`/api/tasks/${target.id}?delete_outputs=${deleteOutputs}`, { method: "DELETE" });
        toast.info(t("toast.deletedTitle"), target.fileName);
      } catch (err) {
        toast.error(t("toast.deleteFailedTitle"), err.message || String(err));
      }
      deleteModalFor.value = null;
      refreshTasks();
    }
    function onShowError(task) { errorModalFor.value = task; }
    async function clearCompleted() {
      try {
        const resp = await fetch("/api/tasks/clear-completed", { method: "POST" });
        if (resp.ok) {
          const d = await resp.json();
          toast.info(t("toast.clearedTitle"), t("toast.clearedBody", { n: d.removed || 0 }));
        }
      } catch (err) {
        toast.error(t("toast.clearFailedTitle"), err.message || String(err));
      }
      refreshTasks();
    }
    function openTask(task) { navigateTo(`task:${task.id}`); }

    function onNeedModel(feature) { modelModalFor.value = feature; }
    function onModelsRechecked(newModels) { models.value = newModels || []; }
    function onHealthRefresh() { refreshModels(); }

    return {
      t,
      route, tasks, models, health, installProgress, runtimeReady,
      asrReady, llmReady, diarizeReady, nativeReady, now,
      errorModalFor, deleteModalFor, modelModalFor,
      onNavigate, onUpload, onStop, onRetry, onDelete, confirmDelete, onShowError,
      clearCompleted, openTask, onNeedModel, onModelsRechecked, onHealthRefresh,
    };
  },
  template: `
    <sidebar :current-route="route.name" :models="models" @navigate="onNavigate" />

    <main class="main">
      <div v-if="route.name === 'home'" class="main-scroll">
        <div>
          <h1 class="page-title">{{ t('home.title') }}</h1>
          <p class="page-subtitle">{{ t('home.subtitle') }}</p>
        </div>

        <div v-if="!runtimeReady" class="runtime-install-banner">
          <div class="runtime-install-icon"><div class="spinner"></div></div>
          <div class="runtime-install-text">
            <div class="runtime-install-title">正在安装核心运行环境</div>
            <div class="runtime-install-sub">
              <template v-if="installProgress && installProgress.currently">
                正在下载 <code>{{ installProgress.currently }}</code>
                <span v-if="installProgress.installed"> · 已完成 {{ installProgress.installed }} 批</span>
              </template>
              <template v-else>
                首次启动需要下载 ASR / 发言人识别等核心依赖（约 5-10 GB，20-40 分钟）。下载完成后可以直接开始转录，无需重启。
              </template>
            </div>
          </div>
        </div>

        <upload-zone
          :llm-ready="llmReady"
          :diarize-ready="diarizeReady"
          :asr-ready="asrReady"
          :runtime-ready="runtimeReady"
          :native-ready="nativeReady"
          @upload="onUpload"
          @need-model="onNeedModel"
        />

        <task-list
          :tasks="tasks"
          :now="now"
          @open="openTask"
          @stop="onStop"
          @retry="onRetry"
          @delete="onDelete"
          @clear-completed="clearCompleted"
          @show-error="onShowError"
        />
      </div>

      <task-detail
        v-else-if="route.name === 'task'"
        :task-id="route.taskId"
        :now="now"
        @back="onNavigate('home')"
        @deleted="onNavigate('home')"
      />

      <settings-page
        v-else-if="route.name === 'settings'"
        :models="models"
      />

      <status-bar :tasks="tasks" :health="health" :now="now" @health-refresh="onHealthRefresh" />
    </main>

    <toast-stack />
    <dialog-host />

    <error-modal v-if="errorModalFor" :task="errorModalFor" @close="errorModalFor = null" />
    <confirm-delete-modal v-if="deleteModalFor" :task="deleteModalFor" @close="deleteModalFor = null" @confirm="confirmDelete" />
    <model-required-modal
      v-if="modelModalFor"
      :feature="modelModalFor"
      :models="models"
      @close="modelModalFor = null"
      @rechecked="onModelsRechecked"
    />
  `,
};

createApp(App).mount("#app");
