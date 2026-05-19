import { LucideIcon } from "./icons.js";
import { t } from "../i18n.js";

export const ChatPanel = {
  name: "ChatPanel",
  components: { LucideIcon },
  props: {
    taskId: { type: String, required: true },
    ready: { type: Boolean, default: false },
  },
  data() {
    return {
      messages: [],
      digestStatus: "unknown",
      input: "",
      sending: false,
      error: null,
      streamingText: "",
      streamingNote: "",
    };
  },
  async mounted() {
    await this.refresh();
  },
  watch: {
    taskId() { this.refresh(); },
  },
  methods: {
    async refresh() {
      try {
        const resp = await fetch(`/api/tasks/${this.taskId}`);
        if (!resp.ok) return;
        const data = await resp.json();
        this.messages = data.chatMessages || [];
        this.digestStatus = data.chatContextDigest ? "ready" : "missing";
      } catch (_) { /* ignore */ }
    },
    onKey(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    },
    async send() {
      const text = this.input.trim();
      if (!text || this.sending) return;
      this.input = "";
      this.sending = true;
      this.error = null;
      this.messages.push({ role: "user", content: text, ts: new Date().toISOString() });
      this.streamingText = "";
      this.streamingNote = "";

      try {
        await this.streamChat(text);
        if (this.streamingText) {
          this.messages.push({ role: "assistant", content: this.streamingText, ts: new Date().toISOString() });
        }
      } catch (err) {
        this.error = err.message || String(err);
      } finally {
        this.sending = false;
        this.streamingText = "";
        this.streamingNote = "";
        await this.refresh();
        this.$nextTick(() => this.scrollBottom());
      }
    },
    async streamChat(message) {
      const resp = await fetch(`/api/tasks/${this.taskId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const ev of events) {
          const lines = ev.split("\n");
          let event = "message", data = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) event = line.slice(7).trim();
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
          if (event === "delta") {
            try { this.streamingText += JSON.parse(data); }
            catch { this.streamingText += data; }
            this.streamingNote = "";
            this.$nextTick(() => this.scrollBottom());
          } else if (event === "info") {
            try { this.streamingNote = JSON.parse(data); }
            catch { this.streamingNote = data; }
            this.$nextTick(() => this.scrollBottom());
          } else if (event === "error") {
            try { throw new Error(JSON.parse(data)); }
            catch (e) { throw e instanceof Error ? e : new Error(data); }
          } else if (event === "done") {
            return;
          }
        }
      }
    },
    scrollBottom() {
      const el = this.$refs.scroll;
      if (el) el.scrollTop = el.scrollHeight;
    },
    t,
  },
  template: `
    <aside class="detail-side">
      <div class="chat-head">
        <div class="chat-head-title">
          <lucide-icon name="message-circle" :size="16" />
          {{ t('chat.emptyTitle') }}
        </div>
        <div class="chat-head-sub">{{ t('detail.summaryByQwen') }}</div>
      </div>

      <div class="chat-scroll scroll-thin" ref="scroll">
        <div v-if="!messages.length && !streamingText" class="chat-msg system-note">
          {{ ready ? t('chat.emptyHint') : t('chat.needTranscript') }}
        </div>
        <div v-for="(m, i) in messages" :key="i" class="chat-msg" :class="m.role">{{ m.content }}</div>
        <div v-if="streamingNote && !streamingText" class="chat-msg system-note">{{ streamingNote }}</div>
        <div v-if="streamingText" class="chat-msg assistant">{{ streamingText }}<span class="muted" style="margin-left:4px">▍</span></div>
        <div v-if="error" class="chat-msg system-note error-text">{{ error }}</div>
      </div>

      <div class="chat-input">
        <textarea
          v-model="input"
          rows="2"
          :placeholder="t('chat.placeholder')"
          :disabled="!ready || sending"
          @keydown="onKey"
        ></textarea>
        <button class="btn btn-primary" :disabled="!input.trim() || sending || !ready" @click="send" style="padding:0 14px">
          <lucide-icon name="send" :size="16" />
        </button>
      </div>
    </aside>
  `,
};
