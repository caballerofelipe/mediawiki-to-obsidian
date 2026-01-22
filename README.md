# MediaWiki to Markdown Vault Converter 🧭

This script converts a MediaWiki XML dump into a clean, tag-driven Markdown vault — including images, categories, infoboxes, and structured YAML frontmatter.

🧭 If you're looking for a worldbuilding tool to connect your ideas, check out my app [Chronicler](https://chronicler.pro/) (source available [here](https://github.com/mak-kirkland/chronicler))

🗂️ If you want to organize your vault into folders based on tags, check out my [Markdown Vault Organizer](https://github.com/mak-kirkland/markdown-vault-organizer).

## ✨ Features

- ✅ Converts MediaWiki pages to Obsidian-compatible Markdown
- 🏷️ Extracts and normalizes categories as `tags`
- 📦 Converts infoboxes into YAML frontmatter (including images)
- 🔧 Infers tags from infobox types using noun inflection
- 🖼️ Downloads and embeds images as `![[images/Filename]]`
- 🔗 Converts internal links to `[[Wikilinks]]`
- 📚 Automatically generates tag-based index files under `_indexes/`
- 🐢 Supports optional Pandoc for better Markdown rendering
- 🔍 Verbose mode for detailed output and easier troubleshooting

## Support

If you find this script useful, please consider supporting me on Patreon:

❤️ [Support on Patreon](https://patreon.com/MichaelKirkland)

---

## 📦 Requirements

- Python 3.8+
- [`pandoc`](https://pandoc.org/) (optional, but recommended for better Markdown conversion)

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

## 🚀 Usage

```bash
python convert.py INPUT_XML [OUTPUT_DIR] [--skip-redirects] [--verbose]
```

| Argument           | Description                                         |
| ------------------ | --------------------------------------------------- |
| `INPUT_XML`        | Path to your MediaWiki XML dump                     |
| `OUTPUT_DIR`       | Optional output folder (default: `obsidian_vault/`) |
| `--skip-redirects` | Ignore redirect pages                               |
| `--verbose`        | Enable verbose logging (disables progress bar)      |


## 🗂️ Output Structure

```text
chronicler_vault/
├── _indexes/
│   ├── _people.md
│   ├── _locations.md
│   └── ...
├── images/
│   ├── Example.jpg
│   └── ...
├── Page_Title_1.md
├── Page_Title_2.md
└── ...
```

## 👤 Author

Created by Michael Kirkland
