# MediaWiki to Markdown Vault Converter 🧭

This script converts a MediaWiki XML dump into a clean, tag-driven Markdown vault — including images, categories, Obsidian callouts from wiki templates, YAML frontmatter for tags, and provenance fields linking each page back to the original wiki.

## ✨ Features

- ✅ Converts MediaWiki pages to Obsidian-compatible Markdown
- 🏷️ Extracts and normalizes categories as `tags`, rewriting category wikilinks to `[[categories/Category …|Category …]]` pages
- 📋 Adds YAML `source/*` fields on each page — wiki generator, site URL, page URL, and revision date (optional; pass `--no-source-fields` to omit)
- 📦 Converts all `{{templates}}` into Obsidian callout blocks in place (infoboxes, navboxes, etc.)
- ⏭️ Skips `Template:` namespace pages by default (pass `--include-templates` to export them, with original wikitext preserved in a reference source block)
- 📂 Writes `Category:` namespace pages under `categories/` (e.g. `Category Characters.md`)
- 📁 Writes `File:` namespace description pages under `files_metadata/` (e.g. `File Example.jpg.md`), with an embedded preview of the upload and the wiki's file metadata
- 🖼️ Downloads and embeds images as `![[images/Filename]]` (supports `File:`, `Image:`, and `Media:` links)
- 🔗 Converts internal links to Obsidian-safe `[[Wikilinks]]` via Pandoc post-processing
- 📚 Automatically generates tag-based category index files under `categories/` (e.g. `Category Characters.md`), merging with exported category pages when both exist
- 🐢 Uses Pandoc for wikitext-to-Markdown conversion when available (recommended; falls back to raw wikitext on failure)
- ⏭️ Optional `--pandoc-skip` flag to bypass Pandoc conversion entirely and keep raw wikitext
- 📝 Optional `--pandoc-plain-markdown` flag to preserve raw HTML via Pandoc's `raw_attribute` writer (see below)
- 🔐 Optional `--cookies` flag for authenticated wikis (private wikis, login-required image downloads)
- 🔍 Verbose mode for detailed output and easier troubleshooting

## Support

...

---

## 📦 Requirements

> **⚠️ Tested Pandoc version: 3.9.0.2**
>
> Pandoc integration (including wikilink post-processing) is tested against **Pandoc 3.9.0.2**. Other versions may work, but Pandoc's Markdown output can change between releases — if your version differs, conversion results may not match what was tested here.

- Python 3.8+ (already installed — see **Installation** below for the rest)
- [Pandoc](https://pandoc.org/installing.html) CLI on your `PATH` — **optional but recommended** for proper Markdown and wikilink conversion (or pass `--pandoc-skip` to skip it). Install **3.9.0.2** when possible (see callout above).

Python dependencies are listed in `requirements.txt`. All packages use pinned versions (`~=`) for compatibility across environments. You are free to remove the version constraints and try the latest (or older) releases if you prefer — just keep in mind that unpinned installs may introduce breaking changes.

| Package            | Purpose                                |
| ------------------ | -------------------------------------- |
| `mwparserfromhell` | Parse and manipulate wikitext          |
| `requests`         | Download images from the wiki API      |
| `pyyaml`           | Generate YAML frontmatter (tags, source) |
| `tqdm`             | Progress bar during conversion         |

## 🛠️ Installation

These steps assume **Python 3.8+ is already installed**. Clone or download this repository, then open a terminal in the project folder (`mediawiki-to-markdown`).

### 1. Install the Pandoc CLI (optional but recommended)

`convert.py` uses Pandoc when available for wikitext-to-Markdown conversion and wikilink cleanup. Without it, the script still runs but leaves raw wikitext in place. You can also pass `--pandoc-skip` at runtime to bypass conversion even when Pandoc is installed.

**Use Pandoc 3.9.0.2** — the version this project is tested against (see **Requirements**). Package managers often ship older releases; download the matching build from the [Pandoc install page](https://pandoc.org/installing.html) if needed.

Install the CLI once for your operating system:

> **Using Conda?** You can install Pandoc with `conda install -c conda-forge pandoc` inside your environment — see **Option B — Conda** below and skip this step.

<details>
<summary><strong>macOS</strong></summary>

With [Homebrew](https://brew.sh/):

```bash
brew install pandoc
```

Or download the macOS package from the [Pandoc install page](https://pandoc.org/installing.html).

Verify:

```bash
pandoc --version
```

</details>

<details>
<summary><strong>Linux</strong></summary>

**Debian / Ubuntu:**

```bash
sudo apt update
sudo apt install pandoc
```

**Fedora:**

```bash
sudo dnf install pandoc
```

**Arch Linux:**

```bash
sudo pacman -S pandoc
```

Or use your distribution's package manager, or the [official Linux tarball](https://pandoc.org/installing.html).

Verify:

```bash
pandoc --version
```

</details>

<details>
<summary><strong>Windows</strong></summary>

Pick one of these options:

**winget** (Windows 10/11):

```powershell
winget install JohnMacFarlane.Pandoc
```

**Chocolatey:**

```powershell
choco install pandoc
```

**Installer:** download the `.msi` from the [Pandoc install page](https://pandoc.org/installing.html) and run it. Restart your terminal afterward so `PATH` updates.

Verify in **Command Prompt** or **PowerShell**:

```powershell
pandoc --version
```

</details>

### 2. Install Python dependencies

Choose **venv** (built into Python) or **Conda** (if you already use it).

#### Option A — venv (recommended)

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
cd mediawiki-to-markdown

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

To deactivate later: `deactivate`

</details>

<details>
<summary><strong>Windows (Command Prompt)</strong></summary>

```bat
cd mediawiki-to-markdown

python -m venv .venv
.venv\Scripts\activate.bat

pip install -r requirements.txt
```

To deactivate later: `deactivate`

</details>

<details>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
cd mediawiki-to-markdown

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

If activation is blocked by execution policy, run once (as Administrator):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

To deactivate later: `deactivate`

</details>

#### Option B — Conda

Works the same on macOS, Linux, and Windows. Conda can install Pandoc alongside your Python dependencies in one environment:

```bash
cd mediawiki-to-markdown

conda create -n mediawiki-md python=3.8
conda activate mediawiki-md

conda install -c conda-forge pandoc

pip install -r requirements.txt
```

To deactivate later: `conda deactivate`

> **Tip:** If you install Pandoc here, you can skip step 1 above.

### 3. Verify the setup

With your environment activated:

```bash
python convert.py --help
```

You should see the script's help text. If you installed Pandoc, confirm the version matches **3.9.0.2** (the tested version):

```bash
pandoc --version
# Expected first line: pandoc 3.9.0.2
```

---

## 📥 Creating the input XML file

`convert.py` expects a MediaWiki XML export — the same format produced by [Special:Export](https://www.mediawiki.org/wiki/Special:Export) or `dumpBackup.php`. The file must include `<siteinfo>` with a `<base>` URL (for image downloads and page links) and a `<generator>` tag (for the source note in frontmatter).

### CLI (preferred)

If you have shell access to the MediaWiki server, use the maintenance script. This is the simplest and most reliable option for full or partial exports.

From the wiki root directory:

```bash
# Current revision of every page
php maintenance/run.php dumpBackup --current > wiki-dump.xml

# Full revision history
php maintenance/run.php dumpBackup --full > wiki-dump-full.xml

# Specific namespaces only (0 = main, 6 = File, 10 = Template, 14 = Category, etc.)
php maintenance/run.php dumpBackup --current --namespaces 0,6,10,14 > partial-dump.xml

# Pages listed in a text file (one title per line)
php maintenance/run.php dumpBackup --current --pagelist pages.txt > selected.xml
```

On older MediaWiki installations you may need to run the script directly from the `maintenance/` folder:

```bash
cd maintenance
php dumpBackup.php --current > ../wiki-dump.xml
```

See the [dumpBackup.php manual](https://www.mediawiki.org/wiki/Manual:DumpBackup.php) for all options.

### Web (Special:Export)

Use this when you do not have server access, or only need a small set of pages.

1. Open `Special:Export` on your wiki (e.g. `https://your-wiki.example/wiki/Special:Export`).
2. Enter page titles — one per line — in the text box. For a single page you can also visit `Special:Export/Page_Title` directly.
3. Optionally check **Include templates** so transcluded templates are exported too.
4. Optionally check **Export all revisions** to include full history (limited to 100 revisions per page via the web UI).
5. Click **Export** and save the downloaded XML file.

For scripted exports over HTTP, you can POST to `Special:Export` with curl:

```bash
curl -d "pages=Main_Page&pages=Another_Page&action=submit" \
  "https://your-wiki.example/wiki/Special:Export" \
  -o wiki-export.xml
```

See [Help:Export](https://www.mediawiki.org/wiki/Help:Export) and [Parameters to Special:Export](https://www.mediawiki.org/wiki/Manual:Parameters_to_Special:Export) for details.

> **Tip:** If your export does not include templates, pages that rely on them may not render correctly after conversion. Include templates in the export when possible.

---

## 🚀 Usage

```bash
python convert.py INPUT_XML [OUTPUT_DIR] [--skip-redirects] [--include-templates] [--no-source-fields] [--pandoc-skip] [--pandoc-plain-markdown] [--verbose] [--cookies COOKIES]
```

| Argument                  | Description                                                                 |
| ------------------------- | --------------------------------------------------------------------------- |
| `INPUT_XML`               | Path to your MediaWiki XML dump                                             |
| `OUTPUT_DIR`              | Optional output folder (default: `obsidian_vault/`)                          |
| `--skip-redirects`        | Ignore redirect pages                                                       |
| `--include-templates`     | Export `Template:` namespace pages (skipped by default)                     |
| `--no-source-fields`      | Omit YAML `source/*` provenance fields from frontmatter                     |
| `--pandoc-skip`           | Skip Pandoc conversion and wikilink cleanup, even if Pandoc is installed     |
| `--pandoc-plain-markdown` | Use Pandoc `--to=markdown` instead of the default `--to=markdown-raw_attribute` |
| `--verbose`               | Enable verbose logging (disables progress bar)                              |
| `--cookies`               | Cookie header for authenticated API/image requests (see below)              |

### Template namespace pages (`--include-templates`)

`Template:` namespace pages are documentation for wiki templates — they are not the same as `{{template}}` invocations in article bodies. Inline templates are always converted to Obsidian callouts regardless of this flag.

By default, `Template:` pages are **not** written to the vault. This keeps the output focused on readable content and avoids hundreds of boilerplate template-definition files. Pass `--include-templates` when you need those pages (for example, to satisfy `[[Template:…]]` wikilinks or to keep the raw template source alongside converted articles):

```bash
python convert.py wiki-dump.xml --include-templates
```

When included, each `Template:` page is written at the vault root (e.g. `Template_Infobox character.md`) with the original MediaWiki wikitext preserved in a `<source>` reference block.

### Skipping Pandoc (`--pandoc-skip`)

Use this when you do not have Pandoc installed, or when you prefer to keep the original wikitext (e.g. for manual cleanup later). Categories, template callouts, images, YAML frontmatter (tags and source fields), and image downloads are still processed — only the Pandoc Markdown conversion and post-processing step is skipped.

```bash
python convert.py wiki-dump.xml --pandoc-skip
```

### Pandoc output format (`--pandoc-plain-markdown`)

By default, the script calls Pandoc with `--to=markdown-raw_attribute`. In Pandoc's format syntax, the `-raw_attribute` suffix **disables** the [`raw_attribute` extension](https://pandoc.org/MANUAL.html#extension-raw_attribute) on the Markdown writer. That produces cleaner output for most Obsidian vaults — wikilinks, headings, and standard Markdown structures convert normally, and you avoid `{=html}` fenced code blocks in your notes.

However, disabling `raw_attribute` can drop or reshape HTML that MediaWiki pages often rely on. Pandoc only has limited native Markdown syntax for complex markup (styled tables, nested `<div>`/`<span>` wrappers, figures with captions, inline HTML with attributes, etc.). When `raw_attribute` is off, Pandoc tends to:

- **Convert** HTML it understands into Markdown or Pandoc fenced divs (`::: {.class}`), which can strip classes, inline styles, and other attributes ([discussion #9318](https://github.com/jgm/pandoc/discussions/9318))
- **Emit bare HTML** only where the [`raw_html`](https://pandoc.org/MANUAL.html#extension-raw_html) extension still allows it, rather than wrapping content in explicit `{=html}` passthrough blocks
- **Lose content** that has no Markdown equivalent and cannot be represented as plain HTML — for example, HTML comments and some block structures disappear when both `raw_attribute` and `raw_html` are disabled ([discussion #9324](https://github.com/jgm/pandoc/discussions/9324))

Since Pandoc 3.2, the Markdown writer also prefers bare HTML over `{=html}` raw-attribute syntax when `raw_html` is enabled, because the two forms are equivalent in Pandoc's internal representation ([issue #10213](https://github.com/jgm/pandoc/issues/10213)). That makes round-tripping through Pandoc again less predictable, but it does not change the core trade-off: **without `raw_attribute`, you get tidier Markdown at the cost of less faithful HTML preservation.**

Pass `--pandoc-plain-markdown` to use `--to=markdown` instead (with `raw_attribute` enabled). Pandoc will then wrap unrepresentable HTML in explicit `{=html}` fenced blocks and inline spans, preserving the original markup for manual cleanup or downstream tools that understand Pandoc's raw-attribute syntax. This is useful when your wiki dump contains heavy HTML formatting, custom templates rendered as HTML, or structures you need to keep intact even if Obsidian will not render them perfectly out of the box.

```bash
# Default — cleaner Markdown, may simplify or remove some HTML
python convert.py wiki-dump.xml

# Preserve raw HTML in Pandoc {=html} blocks
python convert.py wiki-dump.xml --pandoc-plain-markdown
```

> **Tip:** If converted pages look fine in Obsidian, stick with the default. If you notice missing tables, stripped inline styles, or lost template HTML, try `--pandoc-plain-markdown` and review the output — you may need to clean up `{=html}` blocks manually afterward.

### Authenticated wikis (`--cookies`)

Some wikis only allow logged-in users to download images or use the API. If you see a permission error during conversion, pass the `Cookie` header from an authenticated browser session:

1. Log in to the wiki in your browser.
2. Open Developer Tools → **Network**, reload a page, and copy the `Cookie` value from any request's headers.
3. Run the script with `--cookies`:

```bash
python convert.py wiki-dump.xml --cookies "sessionid=abc123; csrftoken=xyz789"
```

### Troubleshooting

> **Pandoc failed for a page:** If you see `⚠️ Pandoc failed for '{title}'. Using raw text (--verbose for more info).`, the script falls back to raw wikitext for that page. This is often caused by malformed markup in the original MediaWiki source — for example, an HTML tag that is not closed. Run with `--verbose` to see Pandoc's stderr and the wikitext that was passed to it.

---

## 🗂️ Output Structure

```text
obsidian_vault/
├── categories/
│   ├── Category Characters.md
│   ├── Category Locations.md
│   └── ...
├── files_metadata/
│   ├── File Example.jpg.md
│   └── ...
├── images/
│   ├── Example.jpg
│   └── ...
├── Page_Title_1.md
├── Page_Title_2.md
└── ...
```

Main article pages live at the vault root. Exported `Category:` namespace pages and auto-generated tag indexes both live under `categories/`. When a wiki category page and a generated index target the same filename, the converter keeps the category page content, merges the index tag into the existing YAML `tags`, and appends a member list to the body.

Exported `File:` namespace pages live under `files_metadata/`. Each page includes a **File** section with an Obsidian embed of the uploaded file (`![[images/...]]`) and a **Metadata** section with the original file description from the wiki. Include namespace `6` in your XML export when you want these description pages alongside the downloaded binaries in `images/`.

Each converted page includes YAML frontmatter with `tags` and source provenance read from the XML export (omit provenance with `--no-source-fields`):

```yaml
---
tags:
  - Characters
source/note: Imported from MediaWiki 1.41.0 website @ https://your-wiki.example
source/url: https://your-wiki.example/wiki/Aragorn
source/date: '2024-06-18T10:30:00Z'
---
```

| Field         | Source in XML export | Description |
| ------------- | -------------------- | ----------- |
| `source/note` | `<generator>` + `<base>` | Human-readable import note (e.g. `Imported from MediaWiki 1.41.0 website @ https://…`) |
| `source/url`  | `<base>` + page title | Direct link to that page on the wiki |
| `source/date` | `<timestamp>` on the revision used | UTC date of the exported revision (ISO 8601) |

Index pages under `categories/` include `tags` in YAML frontmatter. If the file already exists (from an exported `Category:` page), existing `tags` are expanded rather than replaced, and the index section is appended below the page content. Standalone indexes only include `tags` — they are generated locally, not imported from the wiki.

Wiki templates render as Obsidian callouts in place — wherever the template appeared in the original wikitext:

```markdown
> [!character]
> - **name**: Aragorn
> - **race**: [[Human]]
> - **image**: ![[images/Aragorn.jpg]]
```

Category wikilinks in the body become piped links to the matching category page (e.g. `[[Category:Characters]]` → `[[categories/Category Characters|Category Characters]]` → `categories/Category Characters.md`). Exported `Category:` pages are written to the same `categories/` folder with the `Category:` prefix renamed to `Category ` in the filename (e.g. `Category:Characters` → `categories/Category Characters.md`). Exported `File:` pages follow the same pattern under `files_metadata/` (e.g. `File:Example.jpg` → `files_metadata/File Example.jpg.md`). `Template:` namespace pages are omitted unless you pass `--include-templates`; when included, each page also preserves the original MediaWiki source in a reference block.

## 👤 Author

Felipe Caballero ([Original idea by Michael Kirkland](https://github.com/mak-kirkland/mediawiki-to-markdown)).
