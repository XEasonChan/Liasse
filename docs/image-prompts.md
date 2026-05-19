# Liasse · README Image Prompts

EverMind-style 海报，用于 README 的 hero + 6 个 use case card + workflow 图。每张图都遵循同一套 System D 视觉语言（cream paper · cobalt · lavender · ink · 一抹 painterly texture），但 accent 不同——这样既统一又有节奏。

---

## §0 · Style anchor（所有 prompt 共用）

### 0.1 Universal style block

把这一段贴在每个 prompt 前面（生成工具会"吸"这套约束）：

```
Style: editorial product poster meets European academic publishing.
Reference register: Penguin Classics book covers, La Pléiade endpapers, EverMind use-case cards, Princeton University Press promotional inserts.
Palette: warm cream paper #FBF8F3 + ink #0A0807 + a single muted accent (specified per card).
Texture: subtle painterly landscape behind the right half — soft watercolor mountain silhouettes, brushy oil texture, faded fresco. Calm, low-contrast, slightly desaturated. NOT a photo, NOT 3D rendered, NOT glossy.
Typography on poster: DM Serif Display italic (or Caslon/Garamond italic).
Mood: archival, scholarly, contemplative, slightly cinematic, end-of-day lamp light.
NO sci-fi, NO neon, NO Tailwind purple #7B61FF, NO holographic, NO glowing edges, NO glassmorphism, NO 3D blob, NO chatbot icon, NO microphone clipart, NO emoji, NO AI vocabulary on screen.
```

### 0.2 Universal negative prompt

```
no neon, no holographic, no glassmorphism, no 3D blob, no gradient mesh background, no purple AI gradient, no bright violet #7B61FF, no SaaS dashboard aesthetic, no cyberpunk, no Instagram filter, no robot, no chatbot iconography, no microphone clipart, no emoji, no rainbow, no cartoon, no rounded bubbly style, no stock-photo people grinning at camera, no generic startup product hero.
```

### 0.3 Card layout (used by §2 use cases)

Every use case card uses **the same** 1600×1000 px (16:10) layout:

```
┌────────────────────────────────────────────────────────────┐
│                          │                                 │
│   LEFT 50% — color block │   RIGHT 50% — scene + texture   │
│                          │                                 │
│   [Eyebrow caps tag]     │   ┌──────────────────────────┐  │
│                          │   │ painterly background     │  │
│   <Title in DM Serif     │   │ (mountains / brushy oil) │  │
│    Display italic, 2     │   │                          │  │
│    lines max>            │   │ + scene mockup or photo  │  │
│                          │   │ (described per card)     │  │
│   <1-line subtitle in    │   │                          │  │
│    DM Serif Text>        │   └──────────────────────────┘  │
│                          │                                 │
│   ───────                │                                 │
│   [status tag]           │                                 │
│                          │                                 │
└────────────────────────────────────────────────────────────┘
```

The painterly texture should **bleed slightly under the left color block** at the seam, so the two halves feel like one composition rather than two pasted rectangles.

---

## §1 · Hero image — top of README

**Target file**：`docs/assets/liasse-hero.png` (replaces `qwensper-hero.svg`)  
**Aspect ratio**：16:6 (very wide, banner-like)  
**Best tool**：Midjourney v6.1 / v7 with `--style raw` or Nano Banana with `outputs/brand_report_assets/liasse-mood.png` as reference image.

```
A wide cinematic banner image, 2400×900 pixels, depicting a European academic researcher's evening desk in soft warm lamp-light. Center-left: a 14-inch MacBook open on a worn walnut surface, screen displaying the Liasse desktop app — a clean cream-paper interface showing an audio waveform in soft lavender gradient (#7D6DB0 → #9285C0 → #AEA3D6), thin cobalt-blue (#1A3A78) status text reading "Stored on this Mac · Offline", and an italic serif wordmark "Liasse" at the top-left. To the right of the laptop: a small bound bundle of cream paper sheets tied with a thin natural cord (a literal "liasse"), a fountain pen and an open black field-notebook with handwritten interview notes, a cream ceramic mug, a brass mechanical pencil, an external SSD drive in matte black, and an architect's lamp in dark bronze casting warm 2700K light. Background: through a window, an Italianate or Northern European academic building at blue-hour dusk — soft, slightly out of focus, with a few warm-lit windows. Color palette: walnut brown, cream paper #FBF8F3, deep cobalt blue accents on screen and on a single ribbon, soft lavender on screen waveform, a hint of brass. Mood: archival, scholarly, contemplative, end-of-day, slightly cinematic. Lens: 35mm prime, shallow depth of field, lamp bokeh in upper-right corner. No sci-fi, no UI mockup of AI chat, no neon, no people in frame.

--ar 16:6 --style raw --v 6.1
```

**Text overlay (rendered separately in HTML/CSS, NOT in the image)**:
- Title: *Liasse*
- Subtitle: Private local transcription for interviews and case files.

---

## §2 · Use Case Cards (6 cards, 2-column grid)

For each card I give: (a) target filename, (b) the **color accent**, (c) the **scene** to render in the right half, (d) the **on-poster text** that will be rendered onto the image, (e) the full **prompt**.

If a tool can't render text reliably (Midjourney often can't), generate the **right-half scene only**, then composite the left-half text block in Figma / Photoshop / a Pretext HTML template.

---

### Card 1 — Sensitive Interviews · EU Academic PI

**Target**：`docs/assets/use-case-1-academic.png`  
**Accent**：cobalt `#1A3A78` on cream `#FBF8F3`  
**Status tag**：`Available now`

**On-poster text** (left half, white-on-cobalt):
- Eyebrow (small caps): `For academic researchers`
- Title (italic serif): *Sensitive interviews,*
- Title cont.: *bound and offline.*
- Subtitle: GDPR-clean, IRB-bound, never uploaded.

**Right-half scene**:
> A wooden university office desk in late afternoon. A 14-inch MacBook shows Liasse transcribing a recorded interview — cream paper interface, lavender waveform draws across the screen, italic "Liasse" wordmark at top-left, cobalt "Stored on this Mac" chip lit. Beside the laptop: a stack of bound research notebooks with handwritten labels (Φ-Σ-Ω stickers), a porcelain teacup, a small ribbon-tied stack of consent forms in cream paper, a brass paperknife. Soft north-window light from upper-left.

**Full prompt** (paste with §0 style anchor):
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster for a desktop app called Liasse, designed for academic interview transcription. LEFT HALF (50%): solid deep cobalt blue block (#1A3A78). [Text rendered separately — leave this side as flat cobalt color for now.] RIGHT HALF (50%): a soft painterly landscape background — faint watercolor European hills and a distant cathedral spire in dusty cream, very low contrast, slightly faded oil texture. Centered on the right half: a photorealistic but slightly painted-looking still life of a wooden university office desk in late afternoon. A 14-inch MacBook is open, screen showing the Liasse interface: cream-paper background, a soft lavender audio waveform (#7D6DB0 → #AEA3D6) drawn across the middle, thin cobalt-blue ("#1A3A78") text reading "Stored on this Mac · Offline" near the top-right of the app, and a single italic serif word "Liasse" at the top-left. Beside the laptop: a stack of bound research notebooks with letter-coded paper stickers, a porcelain teacup with a saucer, a small ribbon-tied stack of cream consent forms, a brass paperknife. Soft north-window light from upper-left, slightly warm. Color palette overall: cream paper, walnut wood, cobalt blue accent, hint of brass. The seam between the cobalt left half and the painterly right half is softened — the painterly texture bleeds slightly under the color block's right edge.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

### Card 2 — Compliance & Audit · EU DPO / IRB

**Target**：`docs/assets/use-case-2-compliance.png`  
**Accent**：archive green `#4A6650` on bone `#E4DDCB`  
**Status tag**：`Available now`

**On-poster text**:
- Eyebrow: `For DPO & IRB`
- Title: *DMP-ready.*
- Title cont.: *Audit-friendly.*
- Subtitle: No cloud anywhere in the pipeline.

**Right-half scene**:
> A clean compliance officer's desk in a European university administration building. Liasse on screen showing a "compliance summary" panel — a list of items each preceded by a small archive-green checkmark: "Audio: local", "Transcript: local", "Summary: local", "Logs: local". Beside the laptop: a printed Data Management Plan document with a signed signature line, a manila folder labeled "GDPR · Article 89 · Research", a pair of folded reading glasses, a steel desk clip holding a single page.

**Full prompt**:
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster. LEFT HALF (50%): solid muted archive-green block (#4A6650). [Text rendered separately.] RIGHT HALF (50%): a soft painterly background of stacked archival shelving in faded watercolor — distant rows of bound annual reports, very low contrast, brushy oil texture. Centered on the right half: a still life of a clean compliance officer's desk. A 14-inch MacBook open, screen showing Liasse's compliance summary panel — clean cream interface, a list of items each preceded by a small archive-green checkmark "✓": "Audio · local", "Transcript · local", "Summary · local", "Logs · local". Italic serif "Liasse" wordmark top-left. Beside the laptop: a printed Data Management Plan document with a fountain-pen signature on it, a manila folder labeled "GDPR · Article 89 · Research", a pair of folded round reading glasses, a single steel binder clip on a loose page. Lighting: cool morning north light. Palette: cream paper, archive green, walnut, hint of black ink.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

### Card 3 — Deposition Prep · US Litigation

**Target**：`docs/assets/use-case-3-litigation.png`  
**Accent**：oxblood `#762A2A` on vellum `#F3ECDB`  
**Status tag**：`Available now`

**On-poster text**:
- Eyebrow: `For litigators`
- Title: *Privileged.*
- Title cont.: *Confidential.*
- Title cont.: *On your machine.*
- Subtitle: Deposition transcripts that never touch a vendor log.

**Right-half scene**:
> A US law firm partner's office, evening. Liasse on a MacBook screen showing a deposition transcript with timestamps and speaker labels — italic-marked "Q. / A." Q-and-A format, cobalt timestamps, lavender highlighting on a single contested phrase. Beside the laptop: a leather-bound case file tied with an oxblood ribbon, a brass desk lamp with green glass shade casting warm light, a hardcover legal treatise open to a Bates-stamped exhibit, a half-empty cut-crystal glass of whisky on a leather coaster.

**Full prompt**:
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster. LEFT HALF (50%): solid muted oxblood block (#762A2A). [Text rendered separately.] RIGHT HALF (50%): a soft painterly background of dim walnut-paneled law firm interior at dusk — distant rows of leather-bound legal volumes very faintly visible, watercolor brushwork, low contrast. Centered on the right half: a still life of a US law firm partner's office at evening. A 14-inch MacBook screen showing Liasse's deposition transcript view — italic Q. / A. format with thin cobalt timestamps, a single phrase highlighted softly in lavender, italic "Liasse" wordmark top-left. Beside the laptop: a leather-bound case file tied with a thin oxblood ribbon, a brass desk lamp with green-glass shade casting warm pool of light from upper-right, an open hardcover legal treatise face-down on a Bates-stamped exhibit page, a half-empty cut-crystal whisky glass on a leather coaster. Lighting: warm 2700K from lamp, cool blue-hour through unseen window in background. Palette: warm walnut, oxblood, vellum cream, brass, green glass.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

### Card 4 — Case Management at Scale · US Paralegal

**Target**：`docs/assets/use-case-4-paralegal.png`  
**Accent**：brass `#94703A` on cream `#FBF8F3`  
**Status tag**：`Available now`

**On-poster text**:
- Eyebrow: `For paralegals & legal ops`
- Title: *Hundreds of hours,*
- Title cont.: *batched and bound.*
- Subtitle: Queue, transcribe, export, file — all local.

**Right-half scene**:
> A paralegal workstation in an open-plan office at mid-morning. Liasse showing a task list of 12 transcripts — some running, some queued, some complete, each labeled with a matter number ("M-2026-0418" etc) and a time code. Beside the laptop: a wide brass-pull filing cabinet drawer slightly ajar, a stack of index cards bound with a paper band, a coffee mug with cream interior, a small black external SSD.

**Full prompt**:
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster. LEFT HALF (50%): solid muted brass block (#94703A). [Text rendered separately.] RIGHT HALF (50%): a soft painterly background of distant filing-cabinet rows in warm-grey watercolor, brushy oil texture, low contrast. Centered on the right half: a still life of a paralegal workstation at mid-morning. A 14-inch MacBook open, screen showing Liasse's task list — clean cream interface with 12 task rows, each labeled with a matter number ("M-2026-0418", "M-2026-0419", etc.) and a time code; some rows show a partial lavender progress bar, some show a small archive-green "complete" check, italic "Liasse" wordmark top-left. Beside the laptop: a wide brass-pulled filing cabinet drawer slightly ajar (a single manila tab visible saying "Smith v. Acme"), a stack of index cards bound with a kraft-paper band, a tall coffee mug with cream interior, a small matte-black external SSD. Lighting: bright mid-morning indirect daylight. Palette: cream paper, brass, walnut, hint of cobalt on screen.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

### Card 5 — Oral History · Humanities Researcher

**Target**：`docs/assets/use-case-5-oralhistory.png`  
**Accent**：lavender-deep `#6B5D96` on ivory `#F8F2E5`  
**Status tag**：`Available now`

**On-poster text**:
- Eyebrow: `For oral historians`
- Title: *Voices preserved.*
- Title cont.: *Pages bound.*
- Subtitle: Long-form, speaker-labeled, citable for a monograph.

**Right-half scene**:
> A humanities researcher's home study at dusk. Liasse on screen showing a long-form transcript with multiple speaker labels (Speaker A in lavender, B in archive-green, C in brass), each speaker's color marking the left margin of their lines. Beside the laptop: a vintage cassette tape (TDK SA-X 90) and a small handheld cassette player; a worn leather notebook open to a page of hand-drawn family-tree of interview subjects; an open scholarly monograph on oral history methodology with a yellow Post-it bookmark; a single dried flower pressed flat under a thick glass paperweight.

**Full prompt**:
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster. LEFT HALF (50%): solid muted lavender-deep block (#6B5D96). [Text rendered separately.] RIGHT HALF (50%): a soft painterly background of distant bookshelves and a dim window at dusk, watercolor mountains barely visible beyond, low contrast, brushy. Centered on the right half: a humanities researcher's home study at dusk. A 14-inch MacBook open, screen showing Liasse's transcript view with multiple speaker labels — Speaker A's lines have a small lavender mark in the left margin, Speaker B's have archive-green, Speaker C's have brass; italic "Liasse" wordmark top-left. Beside the laptop: a vintage TDK SA-X 90 cassette tape and a small handheld cassette player, a worn brown leather notebook open to a page of hand-drawn family-tree diagram, an open scholarly monograph on oral history methodology with a yellow Post-it bookmark, a single dried flower pressed flat under a thick clear-glass paperweight. Lighting: warm dusk lamp light from upper-right. Palette: warm ivory paper, lavender accent, walnut, leather brown.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

### Card 6 — Field Research, Bilingual · Spanish / LATAM

**Target**：`docs/assets/use-case-6-field.png`  
**Accent**：terracotta `#B0623E` on warm cream `#F4ECD8`  
**Status tag**：`Available now`

**On-poster text**:
- Eyebrow: `For field researchers`
- Title: *Bilingüe.*
- Title cont.: *Both private.*
- Subtitle: Español, English, Português — transcribed and stored locally.

**Right-half scene**:
> A wooden field-research table on a sunlit veranda. A 13-inch MacBook open, screen showing Liasse transcribing audio with Spanish text on the left half and English translation on the right half, each in serif. Beside the laptop: a battered canvas field backpack with leather straps, a small clay-tile coaster, an open Moleskine field notebook with handwritten Spanish notes and a small sketch of a town plaza, a wide-brim straw hat hanging off a chair-back, a ceramic mate gourd with a silver bombilla.

**Full prompt**:
```
{paste §0.1 style anchor}

A 1600×1000 px editorial poster. LEFT HALF (50%): solid muted terracotta block (#B0623E). [Text rendered separately.] RIGHT HALF (50%): a soft painterly background of distant Spanish/LATAM colonial-era roofline at golden hour — barely-visible tile roofs and a bell tower in dusty watercolor, brushy oil texture, low contrast. Centered on the right half: a still life of a wooden field-research table on a sunlit veranda. A 13-inch MacBook open, screen showing Liasse transcribing audio with Spanish text in the left column and English translation in the right column, both in serif; italic "Liasse" wordmark top-left. Beside the laptop: a battered canvas field backpack with leather straps slumped against the table, a small terracotta-tile coaster with a clay water cup, an open Moleskine field notebook with handwritten Spanish notes and a small ink sketch of a town plaza, a wide-brim straw hat hanging off the back of a wooden chair partially visible. Lighting: warm late-afternoon golden hour. Palette: terracotta, warm cream, sun-bleached wood, leather brown, hint of cobalt on screen.

{paste §0.2 negative prompt}

--ar 16:10 --style raw --v 6.1
```

---

## §3 · Workflow diagram — replaces `qwensper-workflow.svg`

**Target**：`docs/assets/liasse-workflow.png` or hand-built SVG  
**Aspect ratio**：16:6  
**Best approach**：hand-built SVG (not AI-generated) — diagrams need precision. Brief is for human/agent illustrator, not Midjourney.

**Spec**:
```
A horizontal infographic diagram, 2400×900 px, on a cream paper background (#FBF8F3) with subtle paper grain. Five labeled steps in a single row, connected by thin cobalt arrows. Each step is illustrated as a hand-drawn line illustration (1.5pt cobalt stroke, no fill except occasional cream wash), labeled below in DM Serif Text:

  1. "Drop audio"  — illustration: a hand placing an audio file icon (waveform inside a rounded square) onto a cream paper sheet.
  2. "Local Qwen-ASR" — illustration: a small stylized M1 chip with a soft glow, cobalt outline.
  3. "Speaker labeling" — illustration: two small circles labeled "A" and "B" with a connecting bracket below a transcript snippet.
  4. "Summary & Q&A" — illustration: a fountain pen drawing an underline beneath a marked phrase.
  5. "Export bundle" — illustration: a small bound liasse of papers tied with a cobalt ribbon.

A footnote beneath, italic: "Every step runs on this Mac. No cloud, no vendor logs."

Style: editorial line illustration meets infographic. Reminiscent of Penguin Classics endpaper diagrams or Wittgenstein's "Tractatus" diagrams. Hand-drawn quality preferred over vector-perfect.
```

If using AI: generate each of the 5 illustrations separately at 256×256 px transparent PNG, then composite in SVG with the cobalt arrows and labels in HTML/CSS.

---

## §4 · Approval checklist (run for every generated image)

```
[ ] Background is cream / vellum / paper — never pure white, never neon.
[ ] Single muted accent per card, drawn from System D palette.
[ ] Any purple in image stays within the lavender gradient range (#7D6DB0 – #AEA3D6).
[ ] No bright Tailwind violet (#7B61FF), no neon glow.
[ ] Screen mockup shows ITALIC serif "Liasse" — not sans, not roman.
[ ] No microphone clipart, no chatbot icon, no robot, no AI-bro imagery.
[ ] No grinning stock-photo person; people, if shown, only in environmental detail (a hand, partial silhouette, never face-front).
[ ] Painterly texture bleeds across the seam between left color block and right scene — they feel like ONE poster, not two halves.
[ ] Reads as Penguin Classics / La Pléiade / EverMind use-case-card, NOT as Vercel / Notion / Figma marketing.
```

---

## §5 · Asset placement after generation

After you generate / approve images, drop them at these paths:

```
docs/assets/
  ├── liasse-hero.png             ← §1 hero (replaces qwensper-hero.svg)
  ├── use-case-1-academic.png     ← §2 Card 1
  ├── use-case-2-compliance.png   ← §2 Card 2
  ├── use-case-3-litigation.png   ← §2 Card 3
  ├── use-case-4-paralegal.png    ← §2 Card 4
  ├── use-case-5-oralhistory.png  ← §2 Card 5
  ├── use-case-6-field.png        ← §2 Card 6
  └── liasse-workflow.png         ← §3 workflow diagram
```

The README references these paths — once files exist at these locations, the README renders the new visuals automatically. The old `qwensper-*.svg` files can be deleted once all replacements are in place (or kept under a `_legacy/` subdirectory for archive).
