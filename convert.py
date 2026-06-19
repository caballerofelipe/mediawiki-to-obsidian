import argparse
from collections import defaultdict
import copy
from html import unescape
import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Any, DefaultDict, Dict, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

import mwparserfromhell
from mwparserfromhell.nodes import Template, Wikilink
from mwparserfromhell.wikicode import Wikicode
import requests
from tqdm import tqdm
import yaml

# Constants
NS = "http://www.mediawiki.org/xml/export-0.11/"
IMAGE_DIR = "images"


def TAG(t: str) -> str:
    """Return the MediaWiki XML namespace-qualified tag name for element ``t``."""
    return f"{{{NS}}}{t}"


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments for the converter."""
    parser = argparse.ArgumentParser(description="Convert MediaWiki XML to Obsidian Vault")
    parser.add_argument("input_xml", help="Input XML file")
    parser.add_argument("output_dir", nargs="?", default="obsidian_vault", help="Output directory")
    parser.add_argument("--skip-redirects", action="store_true", help="Skip redirect pages")
    parser.add_argument(
        "--pandoc-skip", action="store_true", help="Skip Pandoc conversion even if available"
    )
    parser.add_argument(
        "--pandoc-plain-markdown",
        action="store_true",
        help="Use Pandoc --to=markdown instead of the default --to=markdown-raw_attribute",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--cookies",
        help="Cookie header value for API/image requests (e.g. 'name=value; other=value')",
    )
    return parser.parse_args()


args: argparse.Namespace = parse_args()

logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

INPUT_XML: str = args.input_xml
OUTPUT_DIR: str = args.output_dir
SKIP_REDIRECTS: bool = args.skip_redirects
PANDOC_SKIP: bool = args.pandoc_skip
PANDOC_TO_FORMAT: str = "markdown" if args.pandoc_plain_markdown else "markdown-raw_attribute"
COOKIES: Optional[str] = args.cookies
PANDOC_AVAILABLE: bool = shutil.which("pandoc") is not None

if not PANDOC_SKIP and not PANDOC_AVAILABLE:
    logging.warning(
        "⚠️ Pandoc not found on PATH. Wikitext will be kept as-is. "
        "Install Pandoc (https://pandoc.org/installing.html) or pass --pandoc-skip."
    )

os.makedirs(OUTPUT_DIR, exist_ok=True)

tag_to_pages: DefaultDict[str, List[str]] = defaultdict(list)
filename_counts: DefaultDict[str, int] = defaultdict(int)

WIKI_URL: Optional[str] = None


def extract_wiki_url(tree: ET.ElementTree) -> str:
    """Extract the wiki base URL (scheme + host) from a MediaWiki XML export."""
    ns = {"ns": NS}
    base_elem = tree.find(".//ns:siteinfo/ns:base", ns)
    if base_elem is not None and base_elem.text:
        base_url = base_elem.text.strip()
        match = re.match(r"(https?://[^/]+)/", base_url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract wiki domain from <base> tag.")


def clean_filename(title: str) -> str:
    """Convert a page title to a safe filename by replacing forbidden characters to underscores."""
    return re.compile(r'[\\/*?:"<>|{}]').sub('_', title.strip())


def normalize_tag(tag: str) -> str:
    """Normalize a category/tag name for use in filenames and front matter."""
    return re.compile(r'[ \\/*?:"<>|{}]').sub('_', tag.strip())


def process_categories(wikicode: Wikicode) -> Tuple[Wikicode, List[str]]:
    """Extract categories and rewrite their wikilinks to index links.

    Returns (wikicode, categories).
    """
    wikicode = copy.deepcopy(wikicode)  # Copy to avoid external mutation
    categories = []
    for link in wikicode.ifilter_wikilinks():
        target = link.title.strip()
        if target.lower().startswith("category:"):
            cat = target[len("category:") :].strip()
            categories.append(normalize_tag(cat))
            wikicode.replace(link, f'[[Index {clean_filename(target[len("category:"):])}]]')
    return wikicode, categories


def embed_images(wikicode: Wikicode) -> Wikicode:
    """Replace file/image wikilinks with Obsidian embeds, downloading images as needed."""
    wikicode = copy.deepcopy(wikicode)  # Copy to avoid external mutation
    images = set()
    nodes = list(wikicode.nodes)  # make a list copy because we'll modify

    for i, node in enumerate(nodes):
        if isinstance(node, Wikilink):
            target = node.title.strip()
            if target.lower().startswith(("file:", "image:", "media:")):
                image_name = target.split(":", 1)[1].strip()
                local_filename = download_image(image_name)

                if local_filename:
                    embed_link = f"![[{IMAGE_DIR}/{local_filename}]]"

                    # Replace the wikilink node in wikicode directly
                    wikicode.replace(node, embed_link)

                    images.add(embed_link)
    return wikicode


def get_image_url(filename: str) -> Optional[str]:
    """Query the wiki API for the canonical URL of an image file."""
    url = f"{WIKI_URL}/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "titles": filename,
        "iiprop": "url",
    }
    resp = requests.get(
        url, params=params, timeout=10, headers={"Cookie": COOKIES} if COOKIES else None
    )
    if resp.headers.get('MediaWiki-API-Error') == 'readapidenied':
        raise PermissionError("Access to the wiki needs an account, pass cookies to the CLI.")
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        ii = page.get("imageinfo")
        if ii:
            return ii[0]["url"]
    return None


def download_image(image_name: str) -> Optional[str]:
    """Download an image from the wiki into the vault ``OUTPUT_DIR/IMAGE_DIR`` directory.

    Returns the local filename on success, or ``None`` on failure.
    """
    if not image_name:
        return None

    safe_name = clean_filename(image_name)
    filepath = os.path.join(OUTPUT_DIR, IMAGE_DIR, safe_name)
    if os.path.exists(filepath):
        logging.debug(f"🖼️ Skipping download (already exists): {safe_name}")
        return safe_name

    try:
        url = get_image_url(f"File:{image_name}")
    except Exception as e:
        logging.error(f"‼️ Could not find URL for image: {image_name}: {e}")
        return None

    try:
        resp = requests.get(url, stream=True, headers={"Cookie": COOKIES} if COOKIES else None)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logging.debug(f"📥 Downloaded image: {safe_name}")
            return safe_name
        else:
            logging.error(f"‼️ Failed to download image: {image_name} ({resp.status_code})")
            return None
    except Exception as e:
        logging.error(f"‼️ Error downloading {image_name}: {e}")
        return None


def infobox_to_dict(template: Template) -> Dict[str, Any]:
    """Parse an infobox MediaWiki template into a flat dictionary."""
    infobox_data: Dict[str, Any] = {}

    raw_name = template.name.strip().lower()
    if raw_name.startswith("infobox_"):
        infobox_type = raw_name[len("infobox_") :].replace(' ', '_')  # .title()
    else:
        infobox_type = template.name

    infobox_data['infobox'] = infobox_type

    for param in template.params:
        key = param.name.strip().replace(":", "").lower()
        val = param.value.strip()
        infobox_data[key] = val

    return infobox_data


def infobox_dict_to_callout(infobox_data: Dict[str, Any]) -> str:
    """Format an infobox dictionary as an Obsidian callout block."""
    callout_info = {
        data: str(infobox_data[data]).replace('\n', '')
        for data in infobox_data
        if data not in ('infobox', 'image')  # These are treated differently
    }

    callout = ''
    callout += f'\n> [!{infobox_data['infobox']}]' if infobox_data['infobox'] else '\n> [!NOTE]'
    if image_name := infobox_data.get('image'):
        image_name = image_name.strip()
        download_image(image_name)
        callout += f'\n> - **image**: ![[{IMAGE_DIR}/{image_name}]]'

    for data in callout_info:
        callout += f'\n> - **{data}**: {callout_info[data]}'

    return callout


def transform_infobox_to_callout(wikicode: Wikicode) -> Wikicode:
    """Replace all templates in wikitext with Obsidian callout equivalents."""
    wikicode = copy.deepcopy(wikicode)  # Copy to avoid external mutation
    if len(wikicode.filter_templates()) == 0:
        return wikicode

    while template_list := wikicode.filter_templates():
        template = template_list[0]
        infobox_dict = infobox_to_dict(template)
        callout = infobox_dict_to_callout(infobox_dict)

        use_pandoc = not PANDOC_SKIP and PANDOC_AVAILABLE
        callout_to_insert = '\n'
        if use_pandoc:
            callout_to_insert += '\n<source lang="obsidian-callout-block">'
            callout_to_insert += callout
            callout_to_insert += '\n</source>'
        else:
            callout_to_insert += callout

        callout_to_insert += '\n'

        wikicode.replace(template, callout_to_insert)

    return wikicode


def sanitize_for_yaml(obj: Any) -> Any:
    """Recursively coerce values to YAML-safe primitives."""
    if isinstance(obj, dict):
        return {sanitize_for_yaml(k): sanitize_for_yaml(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_yaml(i) for i in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)


def build_yaml_header(
    title: str,
    tags: Union[List[str], str],
    extra_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """Build Obsidian-style YAML front matter for a page."""
    # Ensure tags are unique (if tags is a list), but preserve string if given
    tags = list(dict.fromkeys([tags] if isinstance(tags, str) else tags))
    header = {'title': title, 'tags': tags}
    if extra_fields:
        header.update(sanitize_for_yaml(extra_fields))

    return f"---\n{yaml.safe_dump(header, sort_keys=False)}---\n"


def clean_heading_ids(md_text: str) -> str:
    """Strip Pandoc-generated heading anchor IDs from markdown."""
    return re.compile(r'^(#{1,6} .+?)\s*\{\#.*?\}', re.MULTILINE).sub(r'\1', md_text)


def fix_links_from_pandoc(md_text: str) -> str:
    """Convert Pandoc wikilink syntax to Obsidian wikilink syntax."""
    def replace_wikilinks_no_files(match: re.Match) -> str:
        cleaned_filename = clean_filename(match.group(2).strip().replace('_', ' '))
        text = match.group(3).strip()
        if cleaned_filename == text:
            return f'[[{cleaned_filename}]]'
        else:
            return f'[[{cleaned_filename}|{text}]]'

    pandoc_wikilink_no_files_regex = re.compile(r'(?<!!)\[([^]]+)\]\(([^ ]+) "(.+?)"\)({[^}]+})?')
    md_text_link_no_files_fixed = pandoc_wikilink_no_files_regex.sub(
        replace_wikilinks_no_files, md_text
    )

    def replace_wikilink_inline_files(match: re.Match) -> str:
        text = match.group(3).strip()
        return f'![[{text}]]'

    pandoc_wikilink_inline_files_regex = re.compile(r'\\*!\[([^]]+)\]\(([^ ]+) "(.+?)"\)({[^}]+})?')
    md_text_link_files_fixed = pandoc_wikilink_inline_files_regex.sub(
        replace_wikilink_inline_files, md_text_link_no_files_fixed
    )
    return md_text_link_files_fixed


def fix_image_links(md: str) -> str:
    """Unescape backslashes before Obsidian image embed syntax."""
    return re.sub(r'\\(!\[\[)', r'\1', md)


def remove_obsidian_callout_block(md_text: str) -> str:
    """
    Removes code blocks with language 'obsidian-callout-block' from the markdown text.

    This function removes code blocks created as <source lang="obsidian-callout-block">
    in the transform_infobox_to_callout function. The cleanup is only needed—and only
    takes place—when Pandoc is used, because Pandoc preserves these fenced code blocks.

    Args:
        md_text (str): The markdown content.

    Returns:
        str: Markdown content with 'obsidian-callout-block' code blocks removed, leaving only their content.
    """
    # This regex finds fenced code blocks with lang 'obsidian-callout-block' and replaces the whole block
    # (including the fences) with just the content inside the block.
    return re.sub(
        r'```\s*obsidian-callout-block\s*\n(.*?)```',
        r'\1',
        md_text,
        flags=re.DOTALL,
    )


def cleanup_markdown(md: str) -> str:
    """Run the full post-Pandoc markdown cleanup pipeline."""
    md = clean_heading_ids(md)
    md = fix_links_from_pandoc(md)
    md = fix_image_links(md)
    md = remove_obsidian_callout_block(md)
    return md


def convert_with_pandoc(text: str, title: str = "") -> str:
    """Convert wikitext to markdown via Pandoc, falling back to raw text on failure."""
    try:
        result = subprocess.run(
            ['pandoc', '--from=mediawiki', f'--to={PANDOC_TO_FORMAT}', '--wrap=none'],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        md = result.stdout.decode("utf-8")
        md = md.replace("\\'", "'")
        return md
    except subprocess.CalledProcessError as e:
        logging.warning(f"⚠️ Pandoc failed for '{title}'. Using raw text.")
        logging.debug(e.stderr.decode())
        return text
    except OSError as e:
        logging.warning(f"⚠️ Pandoc failed for '{title}'. Using raw text.")
        logging.debug(e)
        return text


def prepare_wikitext(raw_text: str, title: str) -> Tuple[str, str, List[str]]:
    """Parse MediaWiki wikitext and prepare it for Pandoc conversion.

    Processes categories and images, transforms infoboxes, builds an Obsidian YAML
    front matter header, and records tags in the global tag index.

    Note: Tags will become a file and a property, weird characters will break linking,
    cleaning for good filenames with `clean_filename()`

    Returns (yaml_header, cleaned_wikitext, tags).
    """
    text = unescape(raw_text)
    wikicode = mwparserfromhell.parse(text)
    wikicode, tags = process_categories(wikicode)
    wikicode = embed_images(wikicode)

    wikicode = transform_infobox_to_callout(wikicode)

    cleaned_text = str(wikicode).strip()
    title = clean_filename(title)
    yaml_header = build_yaml_header(title, tags)

    # Track tags for index
    for tag in tags:
        tag_to_pages[tag].append(title)

    return yaml_header, cleaned_text, tags


def wrap_original_mediawiki_source(mediawiki_text: str) -> str:
    """Wrap raw MediaWiki wikitext in a preserved source block."""
    escaped_text = mediawiki_text.replace('</source>', '&lt;/source&gt;')
    return '\n<source lang="original-mediawiki-source">' f'{escaped_text}' '\n</source>' '\n\n'


def convert_pages(tree: ET.ElementTree) -> None:
    """Convert all pages in a MediaWiki XML export to markdown files."""
    ns = {"ns": NS}
    total_pages = len(tree.findall(".//ns:page", {"ns": NS}))

    disable_tqdm = logging.getLogger().level <= logging.DEBUG

    with tqdm(total=total_pages, desc="Converting pages", disable=disable_tqdm) as pbar:
        for page in tree.findall(".//ns:page", ns):
            title_elem = page.find("ns:title", ns)
            if title_elem is None or not title_elem.text:
                pbar.update(1)
                continue

            if SKIP_REDIRECTS and (page.find("ns:redirect", ns) is not None):
                logging.debug(f"⏭️ Skipping redirect: {title_elem.text.strip()}")
                pbar.update(1)
                continue

            title = title_elem.text.strip()
            logging.debug(f"✅ Found page: {title}")

            latest_revision = None
            latest_revision_id = None
            for revision in page.findall(TAG("revision")):
                try:
                    revision_id = int(revision.find(TAG("id")).text)
                except AttributeError:
                    logging.warning(f"⚠️ No ID in revision for: {title}")
                    continue

                if latest_revision_id is None or revision_id > latest_revision_id:
                    latest_revision_id = revision_id
                    latest_revision = revision

            if latest_revision is None:
                logging.warning(f"⚠️ No revision for: {title}")
                pbar.update(1)
                continue

            text_elem = latest_revision.find(TAG("text"))
            if text_elem is None or not text_elem.text or not text_elem.text.strip():
                logging.warning(f"⚠️ No content in: {title}")
                pbar.update(1)
                continue

            raw_text = ''
            if title.startswith('Template:'):
                # Add the original source to the file if it's a Template
                # Used for reference because the template will be changed completely
                # Because parts are treated like infoboxes
                raw_text += wrap_original_mediawiki_source(text_elem.text)
            raw_text += text_elem.text
            yaml_str, wikitext, tags = prepare_wikitext(raw_text, title)

            if not PANDOC_SKIP and PANDOC_AVAILABLE:
                wikitext = convert_with_pandoc(wikitext, title)
                wikitext = cleanup_markdown(wikitext)
            markdown = f"{yaml_str}\n{wikitext.strip()}\n"
            base_filename = clean_filename(title)
            count = filename_counts[base_filename]
            filename_counts[base_filename] += 1
            filename = f"{base_filename}{'_' + str(count) if count else ''}.md"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                logging.debug(f"✍️ Writing: {filepath}")
                f.write(markdown)

            pbar.update(1)

    logging.info("✅ Main articles converted")


def create_tag_indexes() -> None:
    """Write Obsidian index pages for each collected tag.

    Uses the global tag_to_pages map populated during conversion (`prepare_wikitext()`)
    to emit one markdown file per tag under _indexes/, each with YAML front matter and
    wikilinks to every page in that tag.

    Note: Tags and page titles become filenames and wikilinks; weird characters
    will break linking, so both are cleaned with `clean_filename()`.
    """
    dir_name = "indexes"
    index_dir = os.path.join(OUTPUT_DIR, dir_name)
    os.makedirs(index_dir, exist_ok=True)
    for tag, pages in tag_to_pages.items():
        tag_filename = ' '.join(str(tag).replace('_', ' ').split())
        display_tag = tag
        yaml_header = build_yaml_header(f"Index: {display_tag}", tag)
        lines = [f"# {display_tag.title()} Index"]
        for page in sorted(pages):
            display_page = clean_filename(page)
            lines.append(f"- [[{display_page}]]")
        content = yaml_header + "\n".join(lines)
        with open(os.path.join(index_dir, f"Index {tag_filename}.md"), "w", encoding="utf-8") as f:
            f.write(content)
    logging.info(f"📚 Index pages created under {dir_name}/ with tag references")


def main() -> None:
    """Parse XML, convert pages, and create tag index pages."""
    logging.info("🔄 Converting MediaWiki XML to Obsidian Vault...")
    try:
        tree = ET.parse(INPUT_XML)
    except ET.ParseError as e:
        logging.error(f"‼️ Failed to parse XML: {e}")
        return

    try:
        global WIKI_URL
        WIKI_URL = extract_wiki_url(tree)
    except ValueError as e:
        logging.error(f"‼️ {e}")
        return

    convert_pages(tree)
    create_tag_indexes()
    logging.info(f"✅ All done! Markdown vault ready at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
