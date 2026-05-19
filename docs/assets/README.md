# Liasse README Assets

放图的地方。8 个文件名锁死，README.md 和 README.en.md 都引这些路径。  
你只要把 AI 生成的图重命名成下面的文件名，丢进这个目录，`git add docs/assets/*.png && git commit` 就行。

| Filename | Used in | Aspect ratio | Recommended max size |
| --- | --- | --- | --- |
| `liasse-hero.png` | Hero banner top of README | 16:6 (e.g. 2400×900) | 600 KB |
| `use-case-1-academic.png` | Use case grid · cell 1 | 16:10 (1600×1000) | 350 KB |
| `use-case-2-compliance.png` | Use case grid · cell 2 | 16:10 (1600×1000) | 350 KB |
| `use-case-3-litigation.png` | Use case grid · cell 3 | 16:10 (1600×1000) | 350 KB |
| `use-case-4-paralegal.png` | Use case grid · cell 4 | 16:10 (1600×1000) | 350 KB |
| `use-case-5-oralhistory.png` | Use case grid · cell 5 | 16:10 (1600×1000) | 350 KB |
| `use-case-6-field.png` | Use case grid · cell 6 | 16:10 (1600×1000) | 350 KB |
| `liasse-workflow.png` | "How it works" diagram | 16:6 (2400×900) | 400 KB |

## Generation prompts

Full prompts for each image — including the EverMind-style poster layout, color
palette per card, and approval checklist — are in
[../image-prompts.md](../image-prompts.md).

## Workflow

1. Open `docs/image-prompts.md`, copy the prompt for the image you want.
2. Paste into Midjourney / Nano Banana / DALL-E / Ideogram (recommendations in
   `image-prompts.md §7`).
3. Save the output as exactly the filename above, into this directory.
4. Optional: shrink with `pngquant` or [TinyPNG](https://tinypng.com) to hit
   the size budget without visible quality loss.
5. `git add docs/assets/<name>.png && git commit -m "assets: add <use case>"`.
6. README renders automatically — no markdown changes needed.

## Partial uploads OK

GitHub falls back to alt text gracefully. You can upload one card at a time;
the rest of the grid still works.

## Legacy files

The earlier AI-looking diagrams (`qwensper-hero.svg`, `qwensper-workflow.svg`,
`qwensper-use-cases.svg`) were removed during the System D rebrand. The new
visual approach is **EverMind-style use-case poster cards** — each image is a
self-contained 16:10 poster (color block + scene), not a wireframe diagram.

## Other assets

`front_end_prototype.png` — the original 2026-05-18 UI mockup. Historical reference; not used in the current README.
