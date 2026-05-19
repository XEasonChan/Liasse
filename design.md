# Liasse 本地访谈转录工具 · 设计规范

文件名：`design.md`  
版本：v0.2 · System D · Cobalt &amp; Lavender  
状态：可交给 Claude Code / Cursor / 前端 agent 执行  
设计基准：2026-05-19 品牌咨询结论（见 `outputs/brand_consulting_report.html`、`outputs/design_system_review.html`）  
目标风格：欧洲学术出版物 + 现代桌面 app 的混合——黑 / 白 / 米色骨架，cobalt 蓝管"机构与状态"，lavender 渐变管"声音与内容"，全 serif 字体。低噪音、克制、可信。

> **品牌**：Liasse（法语，意为"一束被妥善收束起来的档案材料"）。  
> **副标题**：Private local transcription for interviews and case files.  
> **目标用户**：欧洲学术 PI、IRB/DPO、口述史研究者、美国诉讼律师、paralegal、西语/拉美研究项目负责人。

---

## 1. 产品定位

这是一个本地优先的 Electron 桌面应用，用于上传录音文件或选择包含多个音频文件的文件夹，然后在后台自动执行转录任务。

核心能力：

1. 上传单个或多个音频文件。
2. 选择包含多个音频文件的文件夹。
3. 后台任务队列自动转录。
4. 支持发言人识别。
5. 支持自动分段。
6. 支持总结。
7. 支持 AI Chat 对话。
8. ASR、发言人识别、自动分段默认依赖本地 `Qwen-ASR-1.7B`。
9. 总结和 AI Chat 额外依赖本地 `Qwen-8B`。
10. 不上传音频到云端，不接入云 ASR。

---

## 2. 设计原则

### 2.1 视觉原则

整体界面像一份"印刷品 + 现代 app"的混合体——欧陆学术出版的克制，加上桌面工具的可用性：

- 背景使用偏暖的 off-white（`#fbf8f3`），不是冷蓝白。
- 卡片使用纯白或极浅米色，边框用 cream 色细线（`#d6cfbf`），避免强分割。
- **配色分工严格**：
  - **黑 / 白 / 米色（cream）** = 骨架，承载 90% 的视觉面积。
  - **Cobalt 蓝（`#1a3a78`）** = 机构性 accent——offline / local 状态、规则线、年份/卷号标签、合规副标题、机构性强调。
  - **Lavender 渐变（`#7d6db0 → #9285c0 → #aea3d6`）** = 内容性 accent——波形、进度条、说话人标记、回放高亮、引言强调。
  - 两个 accent **永远不混用**——一旦混用会立刻"软掉"，失去机构感。
- 字体使用衬线字体（DM Serif Display + DM Serif Text），CJK 字符 fallback 到苹方 / 思源宋体。**不使用 Inter / 系统 sans-serif 作为主字体。**
- 圆角整体收紧（2-3px 为主），更像印刷物，少用 18-22px 的圆角。
- 阴影几乎不用——靠 1px hairline 和留白制造层级。
- 图标使用统一线性 SVG（Lucide），线宽 1.5（比之前的 1.75 更细，与衬线字体协调）。
- 不使用 emoji。
- 状态反馈用 hairline 边框 + 小字 + 小标签，不用大面积彩色背景。

### 2.2 交互原则

- 首屏重点只做一件事：让用户上传文件或选择文件夹。
- 转录应当是后台队列，不阻塞用户继续添加任务。
- 发言人识别、自动分段、总结、AI Chat 必须是显式可见的功能开关。
- 总结和 AI Chat 在 `Qwen-8B` 未加载时不可用或显示警告状态。
- 用户需要随时看到当前模型加载状态、任务进度和后台运行状态。
- 所有危险操作，例如删除任务、清空 completed 任务，需要有清晰的按钮样式和二次确认或撤销机制。

---

## 3. 信息架构

应用采用典型桌面工具布局：

```text
┌─────────────────────────────────────────────────────────────────────┐
│ App Window                                                          │
│ ┌───────────────────────┐ ┌───────────────────────────────────────┐ │
│ │ Sidebar               │ │ Main Workspace                         │ │
│ │ - Logo/App Name       │ │ - Page Title                           │ │
│ │ - Navigation          │ │ - Upload Zone                          │ │
│ │ - Model Info Card     │ │ - Feature Toggles                      │ │
│ │                       │ │ - Task List                            │ │
│ │                       │ │ - Background Process Status Bar         │ │
│ └───────────────────────┘ └───────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 Sidebar

Sidebar 包含：

- 应用 logo 与版本号。
- 导航菜单：
  - 转录
  - AI Chat
  - 设置
- 模型信息卡片：
  - ASR 模型：`Qwen-ASR-0.6 B`
  - 总结模型：`Qwen-4B`
  - Chat 模型：`Qwen-4B`
  - 本地运行状态提示

### 3.2 Main Workspace

主工作区包含：

- 页面标题：`转录`
- 页面说明文案
- 文件上传区域
- 功能开关区域
- 任务列表
- 后台转录进程状态条

---

## 4. 首屏布局规范

参考设计稿的桌面窗口尺寸为宽屏布局，建议最小尺寸：

```text
min-width: 1180px
min-height: 760px
preferred-width: 1536px
preferred-height: 864px
```

### 4.1 Sidebar 尺寸

```css
--sidebar-width: 360px;
--sidebar-padding-x: 30px;
--sidebar-padding-y: 28px;
```

Sidebar 使用固定宽度，右侧有一条极浅分割线。

### 4.2 Main Workspace 尺寸

```css
--main-padding-x: 32px;
--main-padding-y: 40px;
--content-max-width: none;
```

主区域不需要居中窄容器，保持桌面工具的宽屏工作区感。

---

## 5. 颜色系统 — System D · Cobalt &amp; Lavender

完整 token 表定义为 CSS variables。

```css
:root {
  /* ============ paper / surfaces ============ */
  --paper:            #fbf8f3;   /* 主背景 off-white */
  --paper-2:          #ffffff;   /* 卡片背景 */
  --paper-3:          #f4ede0;   /* 暖米色 surface */
  --cream:            #e4ddcb;   /* 强调 cream 色块 */
  --cream-soft:       #efe9d8;   /* 柔 cream — 例如非激活区底色 */

  --bg-app:           var(--paper);
  --bg-sidebar:       rgba(255, 255, 255, 0.78);
  --bg-surface:       var(--paper-2);
  --bg-surface-soft:  #faf5ec;
  --bg-surface-hover: #f4ede0;

  /* ============ ink (text) ============ */
  --ink:              #0a0807;   /* 主文本 */
  --ink-soft:         #2a241f;   /* 次文本 / 段落 */
  --muted:            #6a6158;   /* 三级文字 / 元信息 */
  --muted-2:          #8a8175;   /* 占位 / 辅助 */
  --text-primary:     var(--ink);
  --text-secondary:   var(--ink-soft);
  --text-tertiary:    var(--muted);
  --text-quaternary:  var(--muted-2);
  --text-inverse:     var(--paper);

  /* ============ lines ============ */
  --line:             #d6cfbf;   /* 默认 hairline */
  --line-soft:        #e6dfcc;   /* 极浅分割 */
  --rule:             #b8a98e;   /* 强分隔线（章节） */
  --border-subtle:    var(--line-soft);
  --border-strong:    var(--line);

  /* ============ cobalt — institutional accent ============ */
  --cobalt:           #1a3a78;   /* 主 cobalt */
  --cobalt-hover:     #15305f;
  --cobalt-soft:      #e4eaf3;   /* cobalt 浅底 */
  --cobalt-border:    #c7d2e3;

  /* ============ lavender — content accent ============ */
  --lavender-1:       #7d6db0;   /* 渐变起点 — 较深 */
  --lavender-2:       #9285c0;   /* 渐变中点 — 主 lavender */
  --lavender-3:       #aea3d6;   /* 渐变终点 — 较浅 */
  --lavender-soft:    #ece8f5;   /* lavender 极浅底 */
  --lavender-border:  #d8d0ea;
  --lavender-deep:    #6b5d96;   /* hover / 强调 */

  /* ============ semantic（仍用低饱和） ============ */
  --success:          #4a6650;   /* archive green，不是亮绿 */
  --success-soft:     #e7eee9;
  --success-border:   #c8d4ca;

  --warning:          #94703a;   /* brass，不是亮黄 */
  --warning-soft:     #f0e7d5;
  --warning-border:   #dccba6;

  --danger:           #762a2a;   /* oxblood，不是亮红 */
  --danger-soft:      #f0dcdc;
  --danger-border:    #d9b8b8;

  --progress-track:   #ece5d4;

  /* ============ accent legacy alias（兼容旧代码） ============ */
  --accent:           var(--lavender-2);
  --accent-hover:     var(--lavender-deep);
  --accent-soft:      var(--lavender-soft);
  --accent-border:    var(--lavender-border);

  /* ============ shadows — 极少用 ============ */
  --shadow-card:      0 1px 0 rgba(31, 27, 22, 0.04);
  --shadow-card-lg:   0 10px 28px rgba(31, 27, 22, 0.06);
  --shadow-button:    none;     /* 按钮靠边框，不靠阴影 */
}
```

### 5.1 背景

应用背景纯净，不使用径向渐变彩色光晕。可以加一层极淡的纸面纹理：

```css
body {
  background: var(--bg-app);
}

/* 可选：极淡纸纹 — 像 brand_consulting_report.html 里那个 */
body::before {
  content: "";
  position: fixed; inset: 0;
  pointer-events: none;
  background-image: radial-gradient(rgba(60, 46, 28, 0.025) 1px, transparent 1px);
  background-size: 3px 3px;
  mix-blend-mode: multiply;
  z-index: 1;
}
```

### 5.2 主按钮 — Cobalt 实心

主操作按钮使用 cobalt 实心，不用渐变。这是"机构性"动作。

```css
.btn-primary {
  background: var(--cobalt);
  color: var(--paper);
  border: 1px solid var(--cobalt);
  border-radius: 3px;
  padding: 10px 18px;
  font-family: var(--font-display);
  font-style: italic;
  font-size: 16px;
  font-weight: 400;
  letter-spacing: 0;
  transition: background .12s;
}
.btn-primary:hover { background: var(--cobalt-hover); }
```

### 5.3 Lavender 渐变 — 进度条 / 波形 / 内容高亮

```css
.progress-fill,
.waveform-bar,
.content-highlight {
  background: linear-gradient(90deg,
    var(--lavender-1) 0%,
    var(--lavender-2) 50%,
    var(--lavender-3) 100%);
}

/* 垂直版本 — 波形单根柱 */
.wave-bar {
  background: linear-gradient(180deg, var(--lavender-3) 0%, var(--lavender-1) 100%);
}
```

### 5.4 配色使用规则（强约束）

| 元素 | 颜色 | 不要用 |
| --- | --- | --- |
| 主按钮、机构状态 chip、规则线、章节编号、年份/卷号 | **Cobalt** | lavender |
| 波形、进度条、说话人色块、回放游标、引言强调 | **Lavender 渐变** | cobalt |
| 正文、标题 | **Ink** | cobalt 蓝色文字 |
| 卡片背景 | **Paper / cream** | cobalt soft 或 lavender soft（除 hover/active 状态） |
| Hover / 激活背景 | **极浅 cobalt soft 或 lavender soft** | 高饱和填充 |
| 错误 | **Oxblood `#762a2a`** | 亮红 `#ef4444` |
| 警告 | **Brass `#94703a`** | 亮黄 `#f59e0b` |
| 成功 | **Archive green `#4a6650`** | 亮绿 `#22c55e` |

---

## 6. 字体系统 — Serif first

**主显示字体（display）**：DM Serif Display — 现代衬线，slab-edged，用于标题、wordmark、强调引言。  
**主正文字体（text）**：DM Serif Text — DM 系列的工作版本，长文段不刺眼。  
**辅助字体（meta / 元信息）**：Source Serif 4 — 给小字标签、letterspacing 大写小字。  
**CJK fallback**：苹方 / 思源宋体（macOS / Windows 系统衬线优先）。

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Serif+Text:ital@0;1&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap');

:root {
  --font-display:
    'DM Serif Display',
    'EB Garamond',
    'Source Han Serif SC',
    '思源宋体',
    Georgia,
    'Times New Roman',
    serif;

  --font-text:
    'DM Serif Text',
    'EB Garamond',
    'Source Han Serif SC',
    '思源宋体',
    Georgia,
    'Times New Roman',
    serif;

  --font-meta:
    'Source Serif 4',
    'DM Serif Text',
    Georgia,
    serif;

  /* tabular numerals — for time codes, file sizes, durations */
  --font-numeric: 'DM Serif Text', Georgia, serif;
}

html, body {
  font-family: var(--font-text);
  font-feature-settings: "kern" 1, "liga" 1, "onum" 1, "calt" 1;
  -webkit-font-smoothing: antialiased;
}

.display, h1, h2, .page-title, .brand-name {
  font-family: var(--font-display);
  font-weight: 400;
  letter-spacing: -0.012em;
}

.meta, .eyebrow, .label, .nav-item, .pill, th, .status-chip {
  font-family: var(--font-meta);
  letter-spacing: 0.04em;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--muted);
}

/* italic 是 lavender 强调的默认形态 */
em, .italic, .accent-italic {
  font-style: italic;
  color: var(--lavender-deep);
}
```

字号规范：

```css
:root {
  --font-display-xl: 48px;   /* hero */
  --font-display-lg: 36px;   /* page title */
  --font-display-md: 26px;   /* section title */
  --font-display-sm: 20px;   /* card title */
  --font-body:       16px;
  --font-small:      14px;
  --font-meta:       12px;
  --font-micro:      11px;   /* eyebrow / label，搭配 0.22em letterspacing */

  --leading-tight:   1.12;
  --leading-snug:    1.35;
  --leading-body:    1.55;
  --leading-loose:   1.7;
}
```

字重规范（serif 字体字重普遍较少）：

```css
--weight-regular:  400;
--weight-medium:   500;
--weight-italic:   400 italic;
```

> **注意**：DM Serif Display 和 DM Serif Text 都只有 400 重量。需要"加粗"的视觉强调一律用斜体 italic 而不是 weight。这是欧洲学术出版物里典型的强调系统。

---

## 7. 圆角与阴影

```css
--radius-xs: 6px;
--radius-sm: 10px;
--radius-md: 14px;
--radius-lg: 18px;
--radius-xl: 22px;
--radius-full: 999px;
```

使用建议：

- Sidebar nav item：`12px`
- Upload zone：`16px`
- Task list card：`14px`
- Buttons：`10px`
- Model info card：`12px`
- Bottom status bar：`12px`

阴影保持轻：

```css
.card {
  box-shadow: 0 16px 40px rgba(31, 35, 62, 0.045);
}
```

---

## 8. 图标与素材规范

### 8.1 绝对约束

- 不允许使用 emoji 作为 UI 图标。
- 不允许使用系统 emoji、Twemoji 或彩色 emoji 替代功能 icon。
- 所有图标必须来自统一的 SVG 图标库，或由 SVG 组件固化到项目中。
- 运行时不依赖线上图标 API，避免本地应用离线时失效。
- 线上素材库只用于检索和选择，最终图标应通过 npm 包、本地 SVG 或项目内 icon registry 固化。

### 8.2 推荐素材库优先级

第一优先级：Lucide

- 用途：主 UI 图标。
- 风格：线性、轻量、现代、干净。
- React 包：`lucide-react`
- 安装：`npm install lucide-react`
- 官方文档：[https://lucide.dev/guide/react/](https://lucide.dev/guide/react/)
- npm：[https://www.npmjs.com/package/lucide-react](https://www.npmjs.com/package/lucide-react)

第二优先级：Tabler Icons

- 用途：Lucide 找不到合适语义图标时补充。
- 风格：线性、工程感强，适合桌面工具。
- React 包：`@tabler/icons-react`
- 官方文档：[https://docs.tabler.io/icons/libraries/react](https://docs.tabler.io/icons/libraries/react)
- npm：[https://www.npmjs.com/package/@tabler/icons-react](https://www.npmjs.com/package/@tabler/icons-react)

第三优先级：Phosphor Icons

- 用途：需要更柔和、更有亲和力的图标时使用。
- React 包：`@phosphor-icons/react`
- npm：[https://www.npmjs.com/package/@phosphor-icons/react](https://www.npmjs.com/package/@phosphor-icons/react)
- GitHub：[https://github.com/phosphor-icons/react](https://github.com/phosphor-icons/react)

第四优先级：Iconify

- 用途：给 agent 做线上检索，快速搜索不同开源图标集。
- 注意：不要在生产运行时依赖 Iconify 远程 API。
- React 文档：[https://iconify.design/docs/icon-components/react/](https://iconify.design/docs/icon-components/react/)

第五优先级：Untitled UI Icons

- 用途：如果项目允许引入额外设计资产，可作为更偏高级 SaaS 风格的备选。
- 说明：优先使用免费 SVG 或 React 组件，使用付费 Pro 资源前必须确认授权。
- 官方资源：[https://www.untitledui.com/resources/icons](https://www.untitledui.com/resources/icons)

### 8.3 图标样式参数

默认图标规范：

```tsx
const iconProps = {
  size: 18,
  strokeWidth: 1.5,           // System D: 1.5 harmonizes with serif body
  absoluteStrokeWidth: true,
};
```

不同场景：


| 场景          | 尺寸   | 线宽   | 颜色                                               |
| ----------- | ---- | ---- | ------------------------------------------------ |
| Sidebar nav | 18px | 1.5  | inactive: `--text-secondary`; active: `--cobalt` |
| 主按钮         | 18px | 1.5  | `--text-inverse`                                 |
| 次按钮         | 18px | 1.5  | `--text-primary`                                 |
| 上传区主图标      | 42px | 1.5  | `--cobalt` on `--cream` square container         |
| 表格文件图标      | 20px | 1.5  | `--lavender-deep`                                |
| 操作按钮        | 18px | 1.5  | `--text-secondary` 或状态色                          |
| 模型状态        | 14px | 1.5  | archive-green / brass / oxblood 状态色             |


### 8.4 图标映射

优先使用 Lucide 图标。若某个名称在实际包版本中不存在，agent 应使用同语义的 Lucide 图标替代，或者从 Tabler 中选择风格相近的线性图标。


| UI 位置           | 语义     | 推荐 Lucide 图标              | 备注              |
| --------------- | ------ | ------------------------- | --------------- |
| App logo        | 本地语音助手 | `AudioLines` + 自定义圆形容器    | 不使用品牌 logo，避免侵权 |
| Sidebar：转录      | 音频转录主页 | `Home` 或 `AudioLines`     | 设计稿中当前页高亮       |
| Sidebar：发言人识别   | 多说话人   | `Users`                   | 线性人群图标          |
| Sidebar：自动分段    | 章节与段落  | `ListTree` 或 `ListChecks` | 表示结构化分段         |
| Sidebar：总结      | 文档总结   | `FileText`                | 与总结文档语义一致       |
| Sidebar：AI Chat | 对话     | `MessageCircle`           | 不使用机器人 emoji    |
| Sidebar：设置      | 设置     | `Settings`                | 常规齿轮线性图标        |
| 上传区             | 上传     | `Upload` 或 `FolderUp`     | 主视觉可放在紫色渐变方块内   |
| 选择文件            | 音频文件   | `FileAudio`               | 按钮左侧图标          |
| 选择文件夹           | 文件夹    | `FolderOpen`              | 按钮左侧图标          |
| 任务文件            | 音频文件   | `FileAudio`               | 可置于淡紫色圆角方块内     |
| 停止任务            | 停止     | `Square`                  | 红色描边按钮          |
| 删除任务            | 删除     | `Trash2`                  | 危险操作            |
| 打开输出            | 打开文件夹  | `FolderOpen`              | 表格操作区           |
| 任务完成            | 成功     | `CheckCircle2`            | 也可只用绿色 chip     |
| 任务失败            | 错误     | `AlertCircle`             | 失败 chip         |
| 模型状态            | 运行     | `Cpu`                     | 模型卡片和底部状态栏      |
| 本地运行            | 桌面设备   | `Monitor`                 | 模型信息底部          |
| 后台进程            | 活动状态   | `Activity`                | 底部状态条           |
| AI 总结           | 智能生成   | `Sparkles`                | 不使用星星 emoji     |
| AI Chat         | LLM 对话 | `Bot` 或 `MessageCircle`   | 保持线性风格          |


---

## 9. 组件规范

### 9.1 App Window

Electron 应用可以使用无边框窗口加自定义标题区，也可以保留系统标题栏。若使用自定义 macOS 风格窗口控制点，必须用 CSS 圆点绘制，不使用 emoji 或图片。

窗口控制点：

```css
.window-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
}
.window-dot.close { background: #ff5f57; }
.window-dot.minimize { background: #ffbd2e; }
.window-dot.maximize { background: #28c840; }
```

### 9.2 Sidebar Navigation

每个 nav item：

```text
height: 54px
border-radius: 12px
padding: 0 18px
gap: 12px
```

状态：

- inactive：透明背景，灰色文字。
- hover：浅灰背景。
- active：浅紫背景，紫色文字，带 1px 紫色浅边框。

CSS 示例：

```css
.nav-item.active {
  background: linear-gradient(180deg, rgba(245, 246, 255, 0.96), rgba(241, 242, 255, 0.86));
  color: var(--accent);
  border: 1px solid var(--accent-border);
}
```

### 9.3 Model Info Card

位置：Sidebar 底部。  
用途：让用户明确知道哪些能力依赖哪些本地模型。

内容结构：

```text
模型信息

ASR 模型（转录）
Qwen-ASR-1.7B
已加载

总结模型
Qwen-8B
已加载 / 未加载

Chat 模型
Qwen-8B
已加载 / 未加载

所有模型均在本地运行
```

状态点：

```css
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}
.status-dot.loaded { background: var(--success); }
.status-dot.loading { background: var(--warning); }
.status-dot.missing { background: var(--danger); }
```

### 9.4 Upload Zone

上传区域是首屏视觉中心。

内容：

```text
拖拽文件到此处，或点击选择
支持音频文件和包含音频文件的文件夹

[选择文件] [选择文件夹]

支持格式：mp3, wav, m4a, flac, aac, ogg, wma 等
```

布局：

```css
.upload-zone {
  min-height: 320px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.72);
}
```

Drag over 状态：

```css
.upload-zone.is-drag-over {
  border-color: var(--accent);
  background: linear-gradient(180deg, rgba(248, 249, 255, 0.96), rgba(255, 255, 255, 0.88));
  box-shadow: 0 20px 50px rgba(91, 92, 246, 0.12);
}
```

### 9.5 Feature Toggles

功能开关可以放在上传区下方或任务列表上方，也可以在设置页复用。首屏建议以轻量按钮组形式展示。

功能：

1. 发言人识别
2. 自动分段
3. 总结
4. AI Chat

其中：

- 发言人识别：依赖 `Qwen-ASR-1.7B`
- 自动分段：依赖 `Qwen-ASR-1.7B`
- 总结：依赖 `Qwen-8B`
- AI Chat：依赖 `Qwen-8B`

按钮状态：


| 状态       | 视觉                |
| -------- | ----------------- |
| off      | 白底、灰边、灰字          |
| on       | 浅紫背景、紫色边框、紫色文字    |
| disabled | 低透明度、不可点击、显示说明    |
| warning  | 淡黄背景、黄色边框，提示模型未加载 |


总结和 AI Chat 的 disabled 文案：

```text
需要加载 Qwen-8B 后使用
```

### 9.6 Task List

任务列表是核心工作台区域。

标题区：

```text
任务列表                                      [清空 completed]
```

表头：

```text
任务名称 | 进度 | 状态 | 创建时间 | 操作
```

任务行内容：

```text
会议记录_2024-05-20.mp3
25.4 MB     00:45:12

progress bar     65%

转录中

2024-05-20 14:30:25

[停止] [打开输出]
```

任务状态枚举：

```ts
type TaskStatus =
  | 'queued'
  | 'transcribing'
  | 'diarizing'
  | 'segmenting'
  | 'summarizing'
  | 'completed'
  | 'failed'
  | 'cancelled';
```

状态中文映射：

```ts
const taskStatusLabel = {
  queued: '排队中',
  transcribing: '转录中',
  diarizing: '识别发言人',
  segmenting: '自动分段',
  summarizing: '总结中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};
```

状态 chip 视觉：


| 状态    | 背景                  | 文字                 |
| ----- | ------------------- | ------------------ |
| 排队中   | `--bg-surface-soft` | `--text-secondary` |
| 转录中   | `--accent-soft`     | `--accent`         |
| 识别发言人 | `--accent-soft`     | `--accent`         |
| 自动分段  | `--accent-soft`     | `--accent`         |
| 总结中   | `--warning-soft`    | `--warning`        |
| 已完成   | `--success-soft`    | `--success`        |
| 失败    | `--danger-soft`     | `--danger`         |
| 已取消   | `--bg-surface-soft` | `--text-tertiary`  |


### 9.7 Progress Bar — Lavender gradient

```css
.progress {
  height: 6px;
  border-radius: 3px;
  background: var(--progress-track);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg,
    var(--lavender-1) 0%,
    var(--lavender-2) 50%,
    var(--lavender-3) 100%);
}
```

### 9.8 Waveform — Lavender vertical-gradient bars

波形是 lavender 的"主场"。每根柱使用垂直渐变（深→浅，从上到下），柱间距 1.5px，柱宽 2px。

```css
.waveform {
  display: flex;
  align-items: center;
  gap: 1.5px;
  height: 56px;
}
.waveform > i {
  display: block;
  width: 2px;
  border-radius: 1px;
  background: linear-gradient(180deg,
    var(--lavender-3) 0%,
    var(--lavender-1) 100%);
}
/* 当前播放位置之前的柱 — 提高饱和度 */
.waveform > i.played {
  background: linear-gradient(180deg,
    var(--lavender-2) 0%,
    var(--lavender-deep) 100%);
}
/* 当前播放位置之后的柱 — 降低饱和度 */
.waveform > i.upcoming {
  opacity: 0.55;
}
/* 说话人 A / B / C 区分 — 用语义色板而不是 hue-rotate（小尺寸上更可区分） */
.waveform > i.speaker-a {
  background: linear-gradient(180deg, var(--lavender-3) 0%, var(--lavender-1) 100%);
}
.waveform > i.speaker-b {
  background: linear-gradient(180deg, #8ba391 0%, var(--success) 100%);
}
.waveform > i.speaker-c {
  background: linear-gradient(180deg, #c4a06b 0%, var(--warning) 100%);
}
/* 超过 3 个说话人时，fallback 到深浅 ink 灰阶 */
.waveform > i.speaker-d {
  background: linear-gradient(180deg, var(--muted-2) 0%, var(--ink-soft) 100%);
}
```

### 9.8 Bottom Background Process Bar

底部状态条用于显示后台进程和系统资源占位：

```text
后台转录进程
使用 Qwen-ASR-1.7B 模型进行转录和发言人识别

CPU 23%    RAM 6.2/16 GB    GPU 18%       [打开日志]
```

资源曲线可以先用小型 SVG sparkline 或 CSS 简化，不要使用 emoji 或第三方位图。

---

## 10. 页面与功能状态

### 10.1 初始状态

用户尚未添加任务。

主区域展示：

- 上传区
- 功能开关
- 空任务列表提示

空状态文案：

```text
还没有转录任务
上传音频文件或选择文件夹后，任务会自动加入后台队列。
```

### 10.2 添加文件状态

用户选择文件或拖拽文件后：

1. Electron 主进程校验扩展名。
2. 支持的音频加入任务队列。
3. 不支持的文件显示轻量错误提示。
4. 任务状态初始为 `排队中`。
5. 后台队列自动开始处理。

### 10.3 选择文件夹状态

用户选择文件夹后：

1. Electron 主进程扫描文件夹。
2. 只提取音频文件。
3. 按文件名或创建时间排序。
4. 批量加入任务队列。
5. 如果文件夹内没有音频，显示空提示。

### 10.4 Qwen-8B 未加载状态

当 `Qwen-8B` 未加载：

- 总结按钮 disabled 或 warning。
- AI Chat 按钮 disabled 或 warning。
- 总结相关任务不应进入队列。
- 已完成转录任务的总结入口显示 tooltip：`需要加载 Qwen-8B 后使用`。
- AI Chat 入口显示 tooltip：`需要加载 Qwen-8B 后使用`。

### 10.5 转录完成状态

任务完成后可以展示：

- 打开输出目录
- 查看转录文本
- 查看分段
- 查看发言人结果
- 生成总结
- 进入 AI Chat

这些二级能力可以在后续版本中进入详情页或右侧抽屉。

---

## 11. 推荐主界面文案

### 11.1 Sidebar

```text
Liasse
Private local transcription · v1.0.0

转录
发言人识别
自动分段
总结（Qwen 8B）
AI Chat（Qwen 8B）
设置
```

> **Wordmark 排版规则**：`Liasse` 一词在 sidebar 顶部、登录页、关于页一律使用 DM Serif Display italic，斜体本身就是它的强调形态。  
> **副标题**：英文用 `Private local transcription`；中文产品语境用 `本地访谈转录工具`。

### 11.2 Main Header

```text
转录
上传访谈或庭审录音，本地完成转录、说话人识别与分段。音频、转录、总结、日志——任何一项都不离开本机。
```

### 11.3 Upload Zone

```text
拖拽文件到此处，或点击选择
支持音频文件和包含音频文件的文件夹

选择文件
选择文件夹

支持格式：mp3, wav, m4a, flac, aac, ogg, wma 等
```

### 11.4 Task List

```text
任务列表
清空 completed
任务名称
进度
状态
创建时间
操作
```

### 11.5 Model Info

```text
模型信息

ASR 模型（转录）
Qwen-ASR-1.7B
已加载

总结模型
Qwen-8B
已加载

Chat 模型
Qwen-8B
已加载

所有模型均在本地运行
```

### 11.6 Bottom Status

```text
后台转录进程
使用 Qwen-ASR-1.7B 模型进行转录和发言人识别

打开日志
```

---

## 12. Electron IPC 设计建议

Renderer 不应直接访问 Node.js 文件系统能力。文件选择、文件夹扫描、后台任务应通过 preload 暴露安全 API。

### 12.1 Preload API

```ts
declare global {
  interface Window {
    localAsr: {
      selectAudioFiles: () => Promise<SelectedAudioFile[]>;
      selectAudioFolder: () => Promise<SelectedAudioFile[]>;
      createTranscriptionTasks: (
        files: SelectedAudioFile[],
        options: TranscriptionOptions
      ) => Promise<TranscriptionTask[]>;
      getTasks: () => Promise<TranscriptionTask[]>;
      cancelTask: (taskId: string) => Promise<void>;
      openTaskOutput: (taskId: string) => Promise<void>;
      clearCompletedTasks: () => Promise<void>;
      getModelStatus: () => Promise<ModelStatus>;
      loadModel: (model: 'asr' | 'llm') => Promise<void>;
      onTaskProgress: (
        callback: (event: TaskProgressEvent) => void
      ) => () => void;
    };
  }
}
```

### 12.2 数据类型

```ts
export type SelectedAudioFile = {
  id: string;
  name: string;
  path: string;
  extension: string;
  sizeBytes?: number;
  durationSeconds?: number;
};

export type TranscriptionOptions = {
  diarization: boolean;
  autoSegmentation: boolean;
  summary: boolean;
  aiChat: boolean;
};

export type TranscriptionTask = {
  id: string;
  file: SelectedAudioFile;
  status:
    | 'queued'
    | 'transcribing'
    | 'diarizing'
    | 'segmenting'
    | 'summarizing'
    | 'completed'
    | 'failed'
    | 'cancelled';
  progress: number;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
  outputDir?: string;
};

export type ModelStatus = {
  asr: {
    name: 'Qwen-ASR-1.7B';
    loaded: boolean;
    loading: boolean;
    localPath?: string;
  };
  llm: {
    name: 'Qwen-8B';
    loaded: boolean;
    loading: boolean;
    localPath?: string;
  };
};

export type TaskProgressEvent = {
  taskId: string;
  status: TranscriptionTask['status'];
  progress: number;
  message?: string;
};
```

---

## 13. Agent 执行约束

给 Claude Code / Cursor agent 的实现约束：

1. 不使用 emoji 作为任何按钮、导航、状态或空状态图标。
2. 默认安装并使用 `lucide-react`。
3. 如果 Lucide 图标无法满足语义，可以添加 `@tabler/icons-react`，但不要混用过多图标风格。
4. 不要在生产代码中依赖 Iconify 远程 API。
5. 不要使用随机 PNG 图标或无授权素材。
6. 所有图标统一封装到 `src/components/icons.tsx` 或 `src/design/icons.tsx`。
7. 所有颜色、圆角、阴影、间距沉淀到 CSS variables 或 Tailwind tokens。
8. Renderer 只处理 UI，不直接读写文件系统。
9. Main process 负责文件选择、文件夹扫描、任务队列和模型进程管理。
10. Preload 使用 `contextBridge` 暴露白名单 API。
11. 总结和 AI Chat 必须检查 `Qwen-8B` 状态。
12. 未接入真实模型前允许使用 mock 后台进度，但 UI 结构和 IPC 设计要为真实模型保留接口。
13. 所有 UI 文案使用中文。
14. 不上传音频，不接入云端 ASR，不调用第三方转录 API。

---

## 14. 推荐文件结构

```text
src/
  main/
    index.ts
    ipc/
      dialog.ts
      tasks.ts
      models.ts
    services/
      audioScanner.ts
      transcriptionQueue.ts
      modelManager.ts
  preload/
    index.ts
  renderer/
    App.tsx
    pages/
      TranscriptionPage.tsx
      SettingsPage.tsx
    components/
      AppShell.tsx
      Sidebar.tsx
      UploadZone.tsx
      FeatureToggles.tsx
      TaskTable.tsx
      ProgressBar.tsx
      ModelStatusCard.tsx
      BottomProcessBar.tsx
      StatusChip.tsx
    design/
      tokens.css
      icons.tsx
      copy.ts
    types/
      asr.ts
docs/
  design.md
  IMPLEMENTATION.md
```

---

## 15. 视觉验收清单

实现完成后，用以下清单验收：

```text
[ ] 页面整体是浅色、干净、低噪声的桌面应用风格。
[ ] 左侧 Sidebar 和右侧主工作区比例接近设计稿。
[ ] Sidebar 有 logo、版本号、导航、模型信息卡片。
[ ] 主区域有标题、说明、上传区、任务列表、底部进程栏。
[ ] 上传区有大号线性上传图标，且不是 emoji。
[ ] “选择文件”和“选择文件夹”两个按钮视觉层级清晰。
[ ] 功能开关包含发言人识别、自动分段、总结、AI Chat。
[ ] 总结和 AI Chat 明确依赖 Qwen-8B。
[ ] Qwen-8B 未加载时，总结和 AI Chat 有 disabled 或 warning 状态。
[ ] 任务列表有文件名、大小、时长、进度、状态、创建时间、操作。
[ ] 进度条使用紫蓝渐变。
[ ] 状态 chip 颜色克制，不刺眼。
[ ] 没有任何 emoji icon。
[ ] 所有 icon 风格统一，尺寸统一，线宽统一。
[ ] 所有模型状态都强调本地运行。
[ ] Electron renderer 没有直接访问 Node 文件系统。
[ ] 文件/文件夹选择通过 IPC 完成。
```

---

## 16. 实现验收命令

agent 完成实现后，至少运行：

```bash
npm run typecheck
npm run lint
npm run build
```

如果项目没有对应脚本，需要先检查 `package.json`，然后运行项目中实际存在的等价命令。

开发启动命令通常为：

```bash
npm run dev
```

验收时必须在输出中说明：

```text
已完成的 UI 模块
已完成的 IPC 模块
已完成的 mock 队列或真实队列模块
未完成的真实模型接入点
执行过的验证命令
验证命令是否通过
```

---

## 17. 可直接给 Claude Code 的实现 prompt

```text
请根据 docs/design.md 实现 Electron 本地 ASR 应用 UI。

硬性要求：
1. UI 必须是中文。
2. 风格参考 design.md 中的 Granola-like 浅色桌面工作台。
3. 不允许用 emoji 做图标，安装并使用 lucide-react。
4. 实现上传文件、选择文件夹、任务队列、进度状态、模型信息卡片、功能开关。
5. 发言人识别和自动分段依赖 Qwen-ASR-1.7B。
6. 总结和 AI Chat 依赖 Qwen-8B；Qwen-8B 未加载时必须禁用或显示 warning。
7. Renderer 不直接访问文件系统，通过 preload IPC 调主进程能力。
8. 未接入真实模型前可以使用 mock 队列，但要保留真实模型接入点。
9. 不上传音频到云端。
10. 完成后运行 typecheck/lint/build，并更新 docs/IMPLEMENTATION.md。
```

---

## 18. 后续版本扩展

MVP 完成后可扩展：

1. 转录详情页。
2. 分段编辑器。
3. 发言人重命名。
4. 多文件批量导出。
5. Markdown / SRT / VTT / JSON 导出。
6. AI Chat 与当前转录文件绑定上下文。
7. 摘要模板。
8. 本地模型路径配置。
9. GPU / CPU 推理模式切换。
10. 失败任务重试。

