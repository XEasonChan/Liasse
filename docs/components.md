# Liasse 组件家族

按 Apple HIG 的组件分类组织，视觉/交互全部走 [`design.md`](../design.md)
的 **System D · Cobalt & Lavender** —— Cobalt 实心代表机构性主操作，
Lavender 渐变只用在内容（进度条、波形、章节高亮），不混用。

新接手的 agent 改 UI 前先读这份，避免重复造组件 / 风格漂移。

---

## 1. 按钮 Button

CSS class 在 `web_static/style.css`（"Button family" section）。

| Class | 何时用 | 视觉 |
|---|---|---|
| `.btn.btn-primary` | 主操作，**每个视图最多 1 个** | Cobalt 实心 |
| `.btn` (默认) | 次要操作 | 描边 + 透明背景 |
| `.btn.btn-destructive` | 破坏性确认（"删除这条"）| Oxblood 实心 |
| `.btn.btn-ghost` | 第三层文字按钮（"取消"）| 无边框 |
| `.btn.btn-danger` | 删除按钮 inline 版（轻量）| 透明 + oxblood 字 |
| `.btn.btn-icon` | 仅图标 32x32 | 圆角方形 |
| `.btn-sm` / `.btn-lg` | 尺寸修饰符 | 32px / 44px |

所有按钮带 `focus-visible` Cobalt 焦点环。**不要用 emoji 当 icon**——
用 `lucide-icon`（design.md §8.1）。

```html
<button class="btn btn-primary">确认</button>
<button class="btn btn-ghost">取消</button>
<button class="btn btn-destructive btn-lg">删除任务</button>
<button class="btn btn-icon"><lucide-icon name="settings" :size="16" /></button>
```

---

## 2. 对话框 Dialog

文件：`web_static/components/dialog.js`。

Imperative API，**替代 `window.prompt / alert / confirm`**：

```js
import { dialog } from "./dialog.js";

// Alert — 单按钮（消息通知）
await dialog.alert({
  title: "保存成功",
  body: "逐字稿已写入数据库。",
  tone: "success",         // default | danger | warning | success
});

// Confirm — 二选一
const ok = await dialog.confirm({
  title: "删除该任务？",
  subtitle: "音频文件、转录、摘要都会删除，不可恢复。",
  confirmLabel: "删除",
  cancelLabel: "取消",
  tone: "danger",          // tone=danger 时 confirm 按钮变 btn-destructive
});
if (!ok) return;

// Prompt — 单输入框
const name = await dialog.prompt({
  title: "重命名「SPEAKER_00」",
  subtitle: "整个逐字稿都会更新。",
  defaultValue: "采访者",
  placeholder: "新名字…",
  validator: (v) => v.trim() === "" ? "名字不能为空" : null,
});
if (name == null) return;  // 用户取消
```

行为：
- **Esc** 取消，**Enter** 确认（在 input 上焦点也算）
- alert 默认可点 backdrop 关闭；confirm/prompt 默认不能
- 多个 dialog 串行（不会重叠），从 queue 一个个弹
- 自动焦点：prompt 聚焦 input，alert/confirm 聚焦默认按钮

集成：在 root 模板挂 `<dialog-host />`（一次即可，已在 `app.js` 完成）。

---

## 3. 输入 Field

| Class | 用途 |
|---|---|
| `.modal-input` | dialog/form 里的单行输入（Cobalt focus ring） |
| `.setting-inline-select` | 行内 select（语言、人数）|
| `.setting-pill` | 切换式按钮风格（speakerMode 三档、Summary toggle）|
| `.setting-pill.on` | 激活态 — Lavender soft |
| `.setting-pill.warn` | 警告态 — Brass soft |

Toggle / Switch 还没单独做组件，目前用 `.setting-pill` 实现。

---

## 4. 反馈 Feedback

| 组件 | 文件 | 用途 |
|---|---|---|
| Toast | `components/toast.js` | 短暂消息（成功/错误/警告 / info）右上角弹起 |
| Progress bar | `.progress` + `.progress-fill` (css) | Lavender 渐变进度条 |
| Banner | `.detail-banner` + `.banner-*` (css) | 任务详情顶部状态条（running / partial-ready / failed / stopped）|
| Chip | `.chip` + `.chip-*` (css) | 状态标签（queued/running/done/failed/partial-ready）|
| Modal icon | `.modal-icon` + `.tone-*` | dialog/banner 里的 icon 容器，按 tone 着色 |

---

## 5. 容器 Container

| 组件 | 用途 |
|---|---|
| `.card` | 普通卡片，paper 背景 + 极浅阴影 |
| `.modal-card` | dialog 卡片，**比 card 强**：thin border + shadow-lg + fade-in/rise 动画 |
| `.tabs` + `.tab-btn` | 详情页 "逐字稿 / 总结" 切换 |
| `.brand-mark` | sidebar 顶部 brand icon 容器（圆角方形）|

下一轮要补：
- **Disclosure**（折叠区域，用于 "高级设置"）
- **Popover**（锚定弹出层，比 dialog 轻；适合 inline 操作如"段内重新分句"）

---

## 6. 导航 Navigation

| 组件 | 文件 |
|---|---|
| Sidebar | `components/sidebar.js` + `.sidebar` (css) |
| Tab bar | inline 在 task-detail，`.tabs` 类 |

---

## 7. 设计 token 速查（详见 design.md §5）

```css
/* 主色 */
--cobalt: #1a3a78;          --cobalt-soft: #e4eaf3;
--lavender-2: #9285c0;      --lavender-soft: #ece8f5;

/* 语义色 */
--success: #4a6650;         --warning: #94703a;
--danger:  #762a2a;

/* 圆角 */
--radius-xs: 6px;  --radius-sm: 10px;  --radius-md: 14px;
--radius-lg: 18px; --radius-xl: 22px;  --radius-full: 999px;

/* 阴影（极少用） */
--shadow-card:    0 1px 0 rgba(31,27,22,.04);
--shadow-card-lg: 0 10px 28px rgba(31,27,22,.06);
--shadow-button:  none;   /* 按钮靠边框，不靠阴影 */
```

---

## 8. 反模式

- ❌ 不要用 `window.prompt / alert / confirm` —— 走 `dialog.*`
- ❌ 不要用 emoji 当 icon —— 走 `lucide-icon`
- ❌ 不要把 Cobalt 用在波形/进度，Lavender 用在按钮 —— 看 design.md §5.4 强约束表
- ❌ 不要在按钮上加阴影 —— 阴影只给浮层（dialog/dropdown）
- ❌ 不要在新组件里写一次性 CSS —— 加到 `style.css` 的相应 section，给个类名
