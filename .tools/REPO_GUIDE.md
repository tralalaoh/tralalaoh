# Tralalaoh Kodi Repository — Architecture & Push Guide

> This file is the source of truth for Claude.
> Before ANY push, read this file and follow every rule here.

---

## 1. Repository identity

| Field | Value |
|---|---|
| GitHub repo | `https://github.com/tralalaoh/tralalaoh` |
| GitHub Pages URL | `https://tralalaoh.github.io/tralalaoh/` |
| Owner / only contributor | `tralalaoh` — email `upsidedge@gmail.com` |
| Branch | `main` |

**Never** add `Co-Authored-By` lines to commits.
**Never** set git `user.name` to anything other than `tralalaoh`.

---

## 2. Directory structure

```
/ (repo root — public face, must stay clean)
├── addons.xml          ← generated, do NOT edit by hand
├── addons.xml.md5      ← generated, do NOT edit by hand
├── icon.png            ← repo icon shown in Kodi
├── index.html          ← generated, do NOT edit by hand
├── .nojekyll           ← keeps GitHub Pages from ignoring dotfiles
│
├── zips/               ← one subfolder per addon
│   ├── <addon_id>/
│   │   ├── addon.xml          ← version source of truth for that addon
│   │   ├── <addon_id>-<ver>.zip
│   │   ├── icon.png / fanart.jpg  (optional assets)
│   │   └── index.html         ← generated
│   └── ...
│
├── .tools/             ← hidden helper folder, NOT visible to Kodi users
│   ├── REPO_GUIDE.md          ← this file
│   ├── _generator.py          ← regenerates addons.xml + index.html files
│   ├── _sync_external.py      ← downloads updates from external sources
│   └── external_addons.json   ← list of external addons to mirror
│
└── .github/
    └── workflows/
        ├── update-repo.yml    ← runs generator on push to zips/**
        └── sync-external.yml  ← runs external sync daily at 06:00 UTC
```

The repo root must **only** show: `addons.xml`, `addons.xml.md5`, `icon.png`, `index.html`, `zips/`.
Do not create any new files at root level unless absolutely required.

---

## 3. Addon inventory

### 3a. Tralalaoh's own addons (in addons.xml, maintained manually)

| Addon ID | Current version | Zip file |
|---|---|---|
| `repository.tralalaoh` | 1.0.1 | `repository.tralalaoh-1.0.1.zip` |
| `plugin.video.littlefox` | 1.0.1 | `plugin.video.littlefox-1.0.1.zip` |
| `plugin.video.littleracun` | 1.0.1 | `plugin.video.littleracun-1.0.1.zip` |
| `plugin.video.littletigre` | 1.0.1 | `plugin.video.littletigre-1.0.1.zip` |
| `plugin.video.rabitewatch` | 1.0.1 | `plugin.video.rabitewatch-1.0.1.zip` |
| `skin.littleduck` | 1.0.28 | `skin.littleduck-1.0.28.zip` |
| `script.littleduck.helper` | 0.6.22 | `script.littleduck.helper-0.6.22.zip` |

### 3b. External addons (in addons.xml, auto-synced daily)

| Addon ID | Source | Current version |
|---|---|---|
| `script.module.resolveurl` | `Gujal00/smrzips` | 5.1.194 |
| `plugin.video.themoviedb.helper` | `jurialmunkey/repository.jurialmunkey` (omega) | 6.15.1 |
| `script.skinvariables` | `jurialmunkey/repository.jurialmunkey` (omega) | 2.1.35 |

### 3c. Excluded from addons.xml (stored in zips/ but hidden from Kodi repo)

| Addon ID | Reason |
|---|---|
| `repository.jurialmunkey` | Third-party repo addon — not ours |
| `repository.resolveurl` | Third-party repo addon — not ours |

Exclusion list is in `.tools/_generator.py` → `EXCLUDED_ADDONS` set.

---

## 4. Pre-push checklist — run this every time before committing

### Step 1 — Verify zip and addon.xml version match
For each own addon being updated:
- `zips/<addon_id>/addon.xml` version attribute must match the zip filename version.
- Example: if zip is `plugin.video.littlefox-1.0.2.zip` then `addon.xml` must have `version="1.0.2"`.
- There must be exactly **one** zip per addon folder. Delete the old zip.

### Step 2 — Run the generator
```bash
python3 .tools/_generator.py
```
This regenerates `addons.xml`, `addons.xml.md5`, and all `index.html` files.

### Step 3 — Verify addons.xml
- Open `addons.xml` and confirm the updated addon version appears correctly.
- Confirm `repository.jurialmunkey` and `repository.resolveurl` are **not** present.
- Confirm all own addons and external addons are present.

### Step 4 — Stage only the right files
```bash
git add addons.xml addons.xml.md5 index.html
git add zips/<addon_id>/addon.xml
git add zips/<addon_id>/<addon_id>-<newver>.zip
git add zips/<addon_id>/index.html
# if .tools/ files changed:
git add .tools/
# if workflows changed:
git add .github/
```
Do **not** `git add .` — it can accidentally include unintended files.

### Step 5 — Commit and push
```bash
git commit -m "<short description of what changed>"
git push
```
- No `Co-Authored-By` lines.
- Commit message should name what changed, e.g. `Update plugin.video.littlefox to v1.0.2`.

---

## 5. How to update an own addon

1. Put the new zip in `zips/<addon_id>/` and delete the old zip.
2. Update `zips/<addon_id>/addon.xml` — bump the `version` attribute and update `<news>`.
3. Run `python3 .tools/_generator.py`.
4. Follow the pre-push checklist above.

## 6. How to add a new own addon

1. Create folder `zips/<new_addon_id>/`.
2. Place `addon.xml`, zip file, and icon assets inside.
3. Run `python3 .tools/_generator.py` — it picks it up automatically.
4. Update section 3a of this file with the new addon and its version.
5. Follow the pre-push checklist.

## 7. How to add a new external addon to auto-sync

1. Add an entry to `.tools/external_addons.json`:
```json
{
  "id": "addon.id.here",
  "source_addons_xml": "https://.../addons.xml",
  "source_datadir": "https://.../zips/"
}
```
2. Run `python3 .tools/_sync_external.py` to do the first download.
3. Update section 3b of this file with the new addon.
4. Follow the pre-push checklist.

## 8. How to exclude an addon from addons.xml

Add its ID to `EXCLUDED_ADDONS` in `.tools/_generator.py`, then run the generator.
Update section 3c of this file.

---

## 9. GitHub Actions (automated)

| Workflow | Trigger | What it does |
|---|---|---|
| `update-repo.yml` | Push to `zips/**` | Runs generator, commits `addons.xml` + indexes |
| `sync-external.yml` | Daily 06:00 UTC + manual | Checks external sources, downloads updates, commits |

Both workflows commit as `tralalaoh <upsidedge@gmail.com>`.

---

## 10. Things that must never happen

- Do not manually edit `addons.xml` or `addons.xml.md5` — always regenerate.
- Do not leave two zip files for the same addon in the same folder.
- Do not add files at repo root (only `addons.xml`, `addons.xml.md5`, `icon.png`, `index.html` belong there).
- Do not add `Co-Authored-By` or change the git author away from `tralalaoh`.
- Do not include `repository.jurialmunkey` or `repository.resolveurl` in `addons.xml`.
- Do not commit `.tools/turkish.json` or any internal config that is not needed by GitHub Actions.
