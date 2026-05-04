---
name: pascal-sauvage
description: Use Pascal Sauvage when Pavel asks to rewrite, adapt, clean up, or polish text in Pavel Soukenik's own writing style, especially for emails, documents, memos, presentation text, workplace posts, or other content Pavel may present as his own. Do not use for ordinary Parker chat replies.
---

# Pascal Sauvage

Pascal Sauvage is Parker's routing skill for Pavel-style writing tasks. It recognizes when Pavel wants text rewritten in his own style, prepares the input/output paths, and invokes the `william` custom agent to do the actual rewrite.

## Boundary

- Parker should not load the private style guide or source document unless Pavel explicitly asks Parker to inspect them.
- Parker should not perform the rewrite directly when William is available.
- William owns the rewrite rules, style-guide reading, output writing, and issue reporting.
- Do not use this skill for ordinary Parker chat replies.

## Local Data

Pascal and William share local data in this workspace under `data/pascal-sauvage/`:

- `data/pascal-sauvage/writing-style-guide.md`: Pavel's private style guide, read by William.
- `data/pascal-sauvage/drafts/`: temporary source files and rewritten outputs.

Treat `data/pascal-sauvage/writing-style-guide.md` as the canonical local copy inside this repo (not any older path from a previous workspace).

Tracked examples live in `.agents/skills/pascal-sauvage/examples/`.

## Parker Workflow

1. If Pavel provides ad-hoc text instead of a source file, write it to:
   `data/pascal-sauvage/drafts/pascal-sauvage-input-YYYYMMDD-HHMM.md`
2. Choose an output path unless Pavel specified one:
   `data/pascal-sauvage/drafts/pascal-sauvage-output-YYYYMMDD-HHMM.md`
3. Infer or supply minimal task metadata:
   `register`, `audience`, `purpose`.
4. Invoke subagent `william` and pass William only:
   - source document path
   - output path
   - register
   - audience
   - purpose
   - any explicit constraints Pavel gave
6. Keep the subagent isolated; do not pass full conversation history unless it is genuinely required.
7. Report William's output path and issues back to Pavel.

## William Invocation

Use this compact prompt:

```text
Rewrite this source document in Pavel Soukenik's writing style.

SOURCE DOCUMENT: {source_file_path}
OUTPUT PATH: {output_path}
REGISTER: {register}
AUDIENCE: {audience}
PURPOSE: {purpose}

Follow your William agent instructions. Use the shared Pascal style guide and draft paths. Preserve the source intent and write the result to OUTPUT PATH.
```