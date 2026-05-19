import { en } from "./locales/en.js";
import { zh } from "./locales/zh.js";
import { es } from "./locales/es.js";

const { reactive } = window.Vue;

const dicts = { en, zh, es };
const LS_KEY = "liasse.locale";
const LEGACY_LS_KEY = "whisperqwen.locale";

function loadLocale() {
  try {
    let saved = localStorage.getItem(LS_KEY);
    if (!saved) {
      // Migrate legacy key once, then drop it.
      const legacy = localStorage.getItem(LEGACY_LS_KEY);
      if (legacy && dicts[legacy]) {
        localStorage.setItem(LS_KEY, legacy);
        localStorage.removeItem(LEGACY_LS_KEY);
        saved = legacy;
      }
    }
    if (saved && dicts[saved]) return saved;
  } catch (_) { /* ignore */ }
  return "zh";
}

export const i18n = reactive({
  locale: loadLocale(),
});

function get(obj, path) {
  return path.split(".").reduce((o, k) => (o && o[k] != null ? o[k] : null), obj);
}

export function t(key, params) {
  const dict = dicts[i18n.locale] || en;
  let v = get(dict, key);
  if (v == null) v = get(en, key);
  if (v == null) return key;
  if (params && typeof v === "string") {
    return v.replace(/\{(\w+)\}/g, (_, k) => (params[k] != null ? params[k] : `{${k}}`));
  }
  return v;
}

export function setLocale(locale) {
  if (dicts[locale]) {
    i18n.locale = locale;
    try { localStorage.setItem(LS_KEY, locale); } catch (_) { /* ignore */ }
  }
}

export const LOCALES = [
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
  { code: "es", label: "Español" },
];

export function fmtDurI18n(sec, locale) {
  locale = locale || i18n.locale || "en";
  sec = Math.max(0, Math.round(sec));
  if (locale === "zh") {
    if (sec < 60) return `${sec} 秒`;
    const m = Math.floor(sec / 60); const ss = sec % 60;
    if (m < 60) return ss ? `${m}分${ss}秒` : `${m} 分钟`;
    const h = Math.floor(m / 60); const mm = m % 60;
    return mm ? `${h}小时${mm}分` : `${h} 小时`;
  }
  if (locale === "es") {
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60); const ss = sec % 60;
    if (m < 60) return ss ? `${m}m${ss}s` : `${m}min`;
    const h = Math.floor(m / 60); const mm = m % 60;
    return mm ? `${h}h${mm}m` : `${h}h`;
  }
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60); const ss = sec % 60;
  if (m < 60) return ss ? `${m}m${ss}s` : `${m}m`;
  const h = Math.floor(m / 60); const mm = m % 60;
  return mm ? `${h}h${mm}m` : `${h}h`;
}
