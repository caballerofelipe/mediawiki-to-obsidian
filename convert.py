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
import unicodedata
from typing import Any, DefaultDict, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse
import xml.etree.ElementTree as ET

import mwparserfromhell
from mwparserfromhell.nodes import Template
from mwparserfromhell.wikicode import Wikicode
import requests
from tqdm import tqdm
import yaml

# Constants
NS = "http://www.mediawiki.org/xml/export-0.11/"
IMAGE_DIR = "images"
CATEGORY_DIR = "categories"
FILE_DIR = "files_metadata"

INPUT_XML: str = None
OUTPUT_DIR: str = None
SKIP_REDIRECTS: bool = None
NO_SOURCE_FIELDS: bool = None
PANDOC_SKIP: bool = None
PANDOC_TO_FORMAT: str = None
COOKIES: Optional[str] = None
PANDOC_AVAILABLE: bool = None
USE_PANDOC: bool = None
WIKI_URL: Optional[str] = None
WIKI_BASE_URL: Optional[str] = None
WIKI_GENERATOR: Optional[str] = None
WIKI_NAME: Optional[str] = None

tag_to_pages: DefaultDict[str, List[str]] = defaultdict(list)
filename_counts: DefaultDict[str, int] = defaultdict(int)
downloaded_images_local_filename: Dict[str, Optional[str]] = {}


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments for the converter."""
    parser = argparse.ArgumentParser(description="Convert MediaWiki XML to Obsidian Vault")
    parser.add_argument("input_xml", help="Input XML file")
    parser.add_argument("output_dir", nargs="?", default="obsidian_vault", help="Output directory")
    parser.add_argument("--skip-redirects", action="store_true", help="Skip redirect pages")
    parser.add_argument(
        "--no-source-fields",
        action="store_true",
        help="Omit YAML source/* provenance fields from frontmatter",
    )
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


def config() -> Optional[ET.ElementTree]:
    """Parse CLI args, initialize globals, parse XML, and return the element tree."""
    args = parse_args()

    global INPUT_XML, OUTPUT_DIR, SKIP_REDIRECTS, NO_SOURCE_FIELDS, PANDOC_SKIP
    global PANDOC_TO_FORMAT, COOKIES, PANDOC_AVAILABLE, USE_PANDOC
    global WIKI_URL, WIKI_BASE_URL, WIKI_GENERATOR, WIKI_NAME

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Setting global variables
    INPUT_XML = args.input_xml
    OUTPUT_DIR = args.output_dir
    SKIP_REDIRECTS = args.skip_redirects
    NO_SOURCE_FIELDS = args.no_source_fields
    PANDOC_SKIP = args.pandoc_skip
    PANDOC_TO_FORMAT = "markdown" if args.pandoc_plain_markdown else "markdown-raw_attribute"
    COOKIES = args.cookies
    PANDOC_AVAILABLE = shutil.which("pandoc") is not None
    USE_PANDOC = not PANDOC_SKIP and PANDOC_AVAILABLE

    if not PANDOC_SKIP and not PANDOC_AVAILABLE:
        logging.warning(
            "⚠️ Pandoc not found on PATH. Wikitext will be kept as-is. "
            "Install Pandoc (https://pandoc.org/installing.html) or pass --pandoc-skip."
        )

    # Creating the output dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Parse XML
    logging.info("🔄 Converting MediaWiki XML to Obsidian Vault...")
    try:
        tree = ET.parse(INPUT_XML)
    except ET.ParseError as e:
        logging.error(f"‼️ Failed to parse XML: {e}")
        return

    # Obtain WIKI variables
    ns = {"ns": NS}
    siteinfo = tree.find(".//ns:siteinfo", ns)
    if siteinfo is None:
        raise ValueError("Could not find <siteinfo> in XML export.")

    generator_elem = siteinfo.find("ns:generator", ns)
    generator = "MediaWiki"
    if generator_elem is not None and generator_elem.text:
        generator = generator_elem.text.strip()

    sitename_elem = siteinfo.find("ns:sitename", ns)
    sitename = ""
    if sitename_elem is not None and sitename_elem.text:
        sitename = sitename_elem.text.strip()

    base_elem = siteinfo.find("ns:base", ns)
    if base_elem is not None and base_elem.text:
        base_url = base_elem.text.strip()
        if not sitename:
            sitename = urlparse(base_url).netloc
        match = re.match(r"(https?://[^/]+)/", base_url)
        if match:
            WIKI_URL, WIKI_BASE_URL, WIKI_GENERATOR, WIKI_NAME = (
                match.group(1),
                base_url,
                generator,
                sitename,
            )
            return tree
    raise ValueError("Could not extract wiki domain from <base> tag.")


def TAG(t: str) -> str:
    """Return the MediaWiki XML namespace-qualified tag name for element ``t``."""
    return f"{{{NS}}}{t}"


def build_mediawiki_page_url(page_title: str) -> str:
    """Build a canonical wiki URL for ``page_title`` using the export ``<base>`` URL."""
    if not WIKI_BASE_URL:
        raise ValueError("Wiki base URL not set.")

    wiki_title = page_title.replace(" ", "_")
    parsed = urlparse(WIKI_BASE_URL)

    if parsed.query and "title=" in parsed.query.lower():
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["title"] = [wiki_title]
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(query, doseq=True),
                parsed.fragment,
            )
        )

    path_dir, _, _ = parsed.path.rpartition("/")
    encoded_title = quote(wiki_title, safe=":/")
    new_path = f"{path_dir}/{encoded_title}" if path_dir else f"/{encoded_title}"
    return urlunparse(
        (parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment)
    )


def build_source_fields(original_title: str, revision_date: Optional[str] = None) -> Dict[str, Any]:
    """Build YAML front matter fields describing the original MediaWiki source."""
    fields = {
        "source/original_title": original_title,
        "source/note": f"Imported from {WIKI_NAME} ({WIKI_GENERATOR}) @ {WIKI_URL}",
        "source/url": build_mediawiki_page_url(original_title),
    }
    if revision_date:
        fields["source/date"] = revision_date
    return fields


def clean_filename(title: str, underscore_to_colon: bool = False) -> str:
    """Convert a page title to a safe filename by replacing forbidden characters with underscores.

    When ``underscore_to_colon`` is ``True``, every underscore in the result is replaced with
    ``:``. Used for wikilink paths that will pass through Pandoc and be restored afterward.
    """
    clean_title = re.compile(r'[\\/*?:"<>|{}]').sub('_', title).strip()
    if underscore_to_colon:
        clean_title = clean_title.replace('_', ':')
    return clean_title


def normalize_tag(tag: str) -> str:
    """Normalize a category/tag name for use in filenames and front matter."""
    return re.compile(r'[ \\/*?:"<>|{}]').sub('_', tag.strip())


def sort_key_without_diacritics(text: str) -> str:
    """Return a case-insensitive sort key with diacritical marks stripped."""
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.casefold()


def prep_wikilinks_download_files_and_get_categories(
    wikicode: Wikicode,
) -> Tuple[Wikicode, List[str]]:
    """Rewrite wikilinks for Obsidian, download embedded files, and extract category tags.

    Operates on a deep copy of ``wikicode`` so the input is not mutated. Recursively
    processes every wikilink (including links inside templates).

    - ``file:`` / ``image:`` / ``media:`` (case-insensitive) — download via
      ``download_image()`` and replace with ``![[images/<local_filename>]]``; on
      failure, replace with ``[[<original target>]]_(download failed)_``.
    - ``category:`` / ``:category:`` (case-insensitive) — strip the prefix, append
      the normalized name to ``categories``, and replace with
      ``[[categories/Category <normalized>|<Category <display>>]]`` where the URI
      segment uses ``clean_filename(..., underscore_to_colon=...)`` and the display
      text uses ``clean_filename(...)`` without colon substitution.
    - All other links — replace with ``[[<clean_filename(target, underscore_to_colon=...)>]]``.

    When Pandoc is available and ``--pandoc-skip`` is not set, link paths pass
    ``underscore_to_colon=True`` so underscores become colons before Pandoc runs.

    Args:
        wikicode: Parsed MediaWiki wikicode to process.

    Returns:
        A tuple of the rewritten wikicode and a list of normalized category tag
        names (duplicates preserved if the same category appears more than once).
    """
    wikicode = copy.deepcopy(wikicode)  # Copy to avoid external mutation
    categories = []
    for link in list(wikicode.ifilter_wikilinks(recursive=True)):
        target = link.title.strip()
        if target.lower().startswith(("file:", "image:", "media:")):
            image_name = target.split(":", 1)[1].strip()
            local_filename = download_image(image_name)
            if local_filename:
                wikicode.replace(link, f"![[{IMAGE_DIR}/{local_filename}]]")
            else:
                wikicode.replace(link, f'[[{target}]]_(download failed)_')
            continue
        elif re.search('^:?category:', target, re.IGNORECASE):
            category = re.sub('^:?category:', '', target, flags=re.IGNORECASE).strip()
            category_normalized = normalize_tag(category)
            categories.append(category_normalized)
            filename = f'Category {category_normalized}'
            filename_text = clean_filename(filename)
            filename_uri = clean_filename(filename, USE_PANDOC)
            cat_dir = clean_filename(CATEGORY_DIR, USE_PANDOC)
            wikilink = f'[[{cat_dir}/{filename_uri}|{filename_text}]]'
            wikicode.replace(link, wikilink)
            continue
        else:
            filename = clean_filename(target, USE_PANDOC)
            wikicode.replace(link, f'[[{filename}]]')
            continue
    return wikicode, categories


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

    Returns the local filename on success, or ``None`` on failure. Successful results are
    cached in ``downloaded_images_local_filename`` for the duration of the run; failed
    downloads are not cached and are retried on subsequent calls.
    """
    if not image_name:
        return None

    if (
        image_name in downloaded_images_local_filename
        and downloaded_images_local_filename[image_name] is not None
    ):
        return downloaded_images_local_filename[image_name]

    safe_name = clean_filename(image_name)
    filepath = os.path.join(OUTPUT_DIR, IMAGE_DIR, safe_name)
    if os.path.exists(filepath):
        logging.debug(f"🖼️ Skipping download (already exists): {safe_name}")
        local_filename: Optional[str] = safe_name
    else:
        local_filename = None
        try:
            url = get_image_url(f"File:{image_name}")
        except Exception as e:
            logging.error(f"‼️ Could not find URL for image: {image_name}: {e}")
        else:
            try:
                resp = requests.get(
                    url, stream=True, headers={"Cookie": COOKIES} if COOKIES else None
                )
                if resp.status_code == 200:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logging.debug(f"📥 Downloaded image: {safe_name}")
                    local_filename = safe_name
                else:
                    logging.error(f"‼️ Failed to download image: {image_name} ({resp.status_code})")
            except Exception as e:
                logging.error(f"‼️ Error downloading {image_name}: {e}")

    downloaded_images_local_filename[image_name] = local_filename
    return local_filename


def template_to_dict(template: Template) -> Dict[str, Any]:
    """Parse a MediaWiki template invocation into a flat dictionary."""
    template_data: Dict[str, Any] = {}

    raw_name = template.name.strip().lower()
    if raw_name.startswith("infobox_"):
        callout_type = raw_name[len("infobox_") :].replace(' ', '_')  # .title()
    else:
        callout_type = template.name

    template_data['callout_type'] = callout_type

    for param in template.params:
        key = param.name.strip().replace(":", "").lower()
        val = param.value.strip()
        template_data[key] = val

    return template_data


def template_dict_to_callout(template_data: Dict[str, Any]) -> str:
    """Format a template dictionary as an Obsidian callout block."""
    callout_info = {
        data: str(template_data[data]).replace('\n', '')
        for data in template_data
        if data not in ('callout_type', 'image')  # These are treated differently
    }

    callout = ''
    callout += (
        f'\n> [!{template_data['callout_type']}]'
        if template_data['callout_type']
        else '\n> [!NOTE]'
    )
    if image_name := template_data.get('image'):
        image_name = image_name.strip()
        local_filename = download_image(image_name)
        if local_filename:
            callout += f'\n> - **image**: ![[{IMAGE_DIR}/{local_filename}]]'
        else:
            callout += f'\n> - **image**: ![[{image_name}]]_(download failed)_'

    for data in callout_info:
        callout += f'\n> - **{data}**: {callout_info[data]}'

    return callout


def transform_templates_to_callouts(wikicode: Wikicode) -> Wikicode:
    """Replace all templates in wikitext with Obsidian callout equivalents."""
    wikicode = copy.deepcopy(wikicode)  # Copy to avoid external mutation
    if len(wikicode.filter_templates()) == 0:
        return wikicode

    while template_list := wikicode.filter_templates():
        template = template_list[0]
        template_dict = template_to_dict(template)
        callout = template_dict_to_callout(template_dict)

        callout_to_insert = '\n'
        if USE_PANDOC:
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
    tags: Union[List[str], str],
    extra_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """Build Obsidian-style YAML front matter for a page."""
    # Ensure tags are unique (if tags is a list), but preserve string if given
    tags = list(dict.fromkeys([tags] if isinstance(tags, str) else tags))
    header = {'tags': tags}
    if extra_fields:
        header.update(sanitize_for_yaml(extra_fields))

    return f"---\n{yaml.safe_dump(header, sort_keys=False)}---\n"


def split_front_matter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Split YAML front matter from markdown body. Returns (header dict or None, body)."""
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    try:
        header = yaml.safe_load(content[4:end]) or {}
    except yaml.YAMLError:
        return None, content
    if not isinstance(header, dict):
        return None, content
    return header, content[end + 5 :]


def merge_tags(existing: Union[List[str], str, None], new: Union[List[str], str]) -> List[str]:
    """Merge tag values into a deduplicated list, preserving order."""

    def as_list(tags: Union[List[str], str, None]) -> List[str]:
        if tags is None:
            return []
        if isinstance(tags, str):
            return [tags]
        return list(tags)

    return list(dict.fromkeys(as_list(existing) + as_list(new)))


def clean_heading_ids(md_text: str) -> str:
    """Strip Pandoc-generated heading anchor IDs from markdown."""
    return re.compile(r'^(#{1,6} .+?)\s*\{\#.*?\}', re.MULTILINE).sub(r'\1', md_text)


def fix_links_from_pandoc(md_text: str) -> str:
    """Convert Pandoc wikilink syntax to Obsidian wikilink syntax.

    When Pandoc is available and ``--pandoc-skip`` is not set, colons in link targets
    are converted back to underscores so they match on-disk filenames after the
    underscore-to-colon round trip in ``prep_wikilinks_download_files_and_get_categories``.
    """

    def replace_wikilinks_no_files(match: re.Match) -> str:
        filename = match.group(2).replace('_', ' ')
        if USE_PANDOC:
            filename = filename.replace(':', '_')
        text = match.group(3).strip()
        if filename == text:
            return f'[[{filename}]]'
        else:
            return f'[[{filename}|{text}]]'

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
    in the transform_templates_to_callouts function. The cleanup is only needed—and only
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


def prepare_wikitext(
    raw_text: str, original_title: str, revision_date: Optional[str] = None
) -> Tuple[str, str, List[str]]:
    """Parse MediaWiki wikitext and prepare it for Pandoc conversion.

    Processes categories and images, transforms templates to callouts, builds an Obsidian YAML
    front matter header, and records tags in the global tag index.

    Note: Tags will become a file and a property, weird characters will break linking,
    cleaning for good filenames with `clean_filename()`

    Returns (yaml_header, cleaned_wikitext, tags).
    """
    text = unescape(raw_text)
    wikicode = mwparserfromhell.parse(text)
    wikicode, tags = prep_wikilinks_download_files_and_get_categories(wikicode)

    wikicode = transform_templates_to_callouts(wikicode)

    cleaned_text = str(wikicode).strip()
    source_fields = None if NO_SOURCE_FIELDS else build_source_fields(original_title, revision_date)
    yaml_header = build_yaml_header(tags, extra_fields=source_fields)

    # Track tags for index
    for tag in tags:
        tag_to_pages[tag].append(original_title)

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
            page_subdir = ""  # Used in case we want to create the file inside a subdir

            title_elem = page.find("ns:title", ns)
            if title_elem is None or not title_elem.text:
                pbar.update(1)
                continue

            if SKIP_REDIRECTS and (page.find("ns:redirect", ns) is not None):
                logging.debug(f"⏭️ Skipping redirect: {title_elem.text.strip()}")
                pbar.update(1)
                continue

            title = original_title = title_elem.text.strip()
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
                # Because template invocations are converted to callouts in article wikitext
                raw_text += wrap_original_mediawiki_source(text_elem.text)
            if title.startswith('Category:'):
                title = re.sub('^Category:', 'Category ', title)
                page_subdir = CATEGORY_DIR
            if title.startswith('File:'):
                title = re.sub('^File:', 'File ', original_title)
                page_subdir = FILE_DIR
                # Add the file to be viewed inside this metadata file
                # The link will be processed inside prepare_wikitext like original links
                raw_text += '==File==\n'
                raw_text += f'\n[[{original_title}]]'
                raw_text += '\n\n==Metadata=='

            raw_text += text_elem.text
            timestamp_elem = latest_revision.find(TAG("timestamp"))
            revision_date = (
                timestamp_elem.text.strip()
                if timestamp_elem is not None and timestamp_elem.text
                else None
            )
            yaml_str, wikitext, tags = prepare_wikitext(raw_text, original_title, revision_date)

            if USE_PANDOC:
                wikitext = convert_with_pandoc(wikitext, original_title)
                wikitext = cleanup_markdown(wikitext)
            markdown = f"{yaml_str}\n{wikitext.strip()}\n"
            base_filename = clean_filename(title)
            count = filename_counts[base_filename]
            filename_counts[base_filename] += 1
            filename = f"{base_filename}{'_' + str(count) if count else ''}.md"
            filepath = os.path.join(OUTPUT_DIR, page_subdir, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                logging.debug(f"✍️ Writing: {filepath}")
                f.write(markdown)

            pbar.update(1)

    logging.info("✅ Main articles converted")


def create_tag_indexes() -> None:
    """Write Obsidian index pages for each collected tag.

    Uses the global tag_to_pages map populated during conversion (`prepare_wikitext()`)
    to emit one markdown file per tag under categories/, each with YAML front matter and
    wikilinks to every page in that tag. If a category file already exists (e.g. from a
    wiki Category: page), existing tags in the YAML front matter are merged with the
    index tag and the index section is appended to the body.

    Note: Tags and page titles become filenames and wikilinks; weird characters
    will break linking, so both are cleaned with `clean_filename()`.
    """
    index_dir = os.path.join(OUTPUT_DIR, CATEGORY_DIR)
    os.makedirs(index_dir, exist_ok=True)
    for tag, pages in tag_to_pages.items():
        tag_filename = ' '.join(str(tag).split())
        display_tag = tag
        index_lines = [f"# {display_tag.title()} Index"]
        for page in sorted(pages, key=sort_key_without_diacritics):
            if page.startswith('Category:'):
                page = re.sub('^Category:', 'Category ', page)
                display_page = clean_filename(page)
                index_lines.append(f"- [[{CATEGORY_DIR}/{display_page}|{display_page}]]")
            else:
                display_page = clean_filename(page)
                index_lines.append(f"- [[{display_page}]]")
        index_content = "\n".join(index_lines)
        filepath = os.path.join(index_dir, f"Category {tag_filename}.md")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()
            header, body = split_front_matter(existing_content)
            if header is not None:
                merged_tags = merge_tags(header.get("tags"), tag)
                extra_fields = {k: v for k, v in header.items() if k not in ("title", "tags")}
                if NO_SOURCE_FIELDS:
                    extra_fields = {
                        k: v for k, v in extra_fields.items() if not str(k).startswith("source/")
                    }
                yaml_header = build_yaml_header(
                    merged_tags, extra_fields=extra_fields or None
                )
            else:
                yaml_header = build_yaml_header(tag)

            text_body = body.rstrip()
            if index_content not in text_body:
                text_body += f"\n\n{index_content}\n"
            else:
                text_body += "\n"
            content = yaml_header + text_body
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            yaml_header = build_yaml_header(tag)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(yaml_header + index_content + "\n")
    logging.info(f"📚 Index pages created under {CATEGORY_DIR}/ with tag references")


def main() -> None:
    try:
        tree = config()
        if tree is None:
            raise ValueError('Tree is None.')
    except ValueError as e:
        logging.error(f"‼️ {e}")
        return

    convert_pages(tree)
    create_tag_indexes()
    logging.info(f"✅ All done! Markdown vault ready at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
