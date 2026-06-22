"""Unit tests for convert.py.

Pandoc link post-processing tests reflect output from Pandoc 3.9.0.2.
"""

import sys

sys.argv = ["test.py", "dummy.xml"]

import mwparserfromhell
import convert
from convert import (
    clean_heading_ids,
    fix_links_from_pandoc,
    build_yaml_header,
    build_mediawiki_page_url,
    build_source_fields,
    transform_templates_to_callouts,
    merge_tags,
    split_front_matter,
    process_categories,
    create_tag_indexes,
)


# Test 1: Heading cleanup
def test_clean_heading_ids() -> None:
    md = "# Heading 1 {#heading1}\n## Heading 2 {#heading2}"
    expected = "# Heading 1\n## Heading 2"
    assert clean_heading_ids(md) == expected


# Test 2: Pandoc-style link cleanup
def test_fix_links_from_pandoc_internal() -> None:
    md = 'This is a [Foo Bar](Foo_Bar "Foo Bar"){.wikilink} and [Alias](Target_Page "Alias"){.wikilink}.'
    expected = 'This is a [[Foo Bar]] and [[Target Page|Alias]].'
    assert fix_links_from_pandoc(md) == expected


def test_fix_links_from_pandoc_external() -> None:
    md = 'Visit [Google](https://google.com) or contact [me](mailto:test@example.com).'
    assert fix_links_from_pandoc(md) == md  # Should remain unchanged


# Test 3: YAML frontmatter generation
def test_build_yaml_header_basic() -> None:
    title = "Sample_Page Title"
    tags = ["category_one", "tag_two"]
    yaml = build_yaml_header(title, tags)
    assert "---" in yaml
    assert "title: Sample_Page Title" in yaml  # Spaces Shouldn't be converted into underscores
    assert "tags:" in yaml
    assert "- category_one" in yaml
    assert "- tag_two" in yaml


def test_build_mediawiki_page_url_pretty() -> None:
    convert.WIKI_BASE_URL = "https://en.wikipedia.org/wiki/Main_Page"
    assert build_mediawiki_page_url("Aragorn") == "https://en.wikipedia.org/wiki/Aragorn"
    assert (
        build_mediawiki_page_url("Template:Infobox character")
        == "https://en.wikipedia.org/wiki/Template:Infobox_character"
    )


def test_build_mediawiki_page_url_index_php() -> None:
    convert.WIKI_BASE_URL = "https://www.mediawiki.org/w/index.php?title=Main_Page"
    assert (
        build_mediawiki_page_url("Help:Contents")
        == "https://www.mediawiki.org/w/index.php?title=Help%3AContents"
    )


def test_extract_wiki_url_reads_generator() -> None:
    import xml.etree.ElementTree as ET

    xml = """<?xml version="1.0"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <siteinfo>
    <base>https://en.wikipedia.org/wiki/Main_Page</base>
    <generator>MediaWiki 1.41.0</generator>
    <sitename>Wikipedia</sitename>
  </siteinfo>
</mediawiki>"""
    tree = ET.ElementTree(ET.fromstring(xml))
    wiki_url, base_url, generator, sitename = convert.extract_wiki_url(tree)
    assert wiki_url == "https://en.wikipedia.org"
    assert base_url == "https://en.wikipedia.org/wiki/Main_Page"
    assert generator == "MediaWiki 1.41.0"
    assert sitename == "Wikipedia"


def test_build_yaml_header_with_source() -> None:
    convert.WIKI_URL = "https://example.com"
    convert.WIKI_BASE_URL = "https://example.com/wiki/Main_Page"
    convert.WIKI_GENERATOR = "MediaWiki 1.41.0"
    convert.WIKI_NAME = "Example Wiki"
    yaml = build_yaml_header(
        "Sample Page",
        ["tag"],
        extra_fields=build_source_fields("Sample Page", "2024-06-18T10:30:00Z"),
    )
    assert (
        "source/note: Imported from Example Wiki (MediaWiki 1.41.0) @ https://example.com"
        in yaml
    )
    assert "source/url: https://example.com/wiki/Sample_Page" in yaml
    assert "source/date: '2024-06-18T10:30:00Z'" in yaml


# Test 4: Template parsing and callout conversion
def test_transform_templates_to_callouts(monkeypatch) -> None:
    monkeypatch.setattr(convert, "PANDOC_SKIP", True)
    wikitext = """{{Infobox_character
| name = Aragorn
| race = [[Human]]
| weapon = [[Andúril]]
| info = More info in [[More info]]
}}
[[Category:Characters]]"""

    wikitext_with_callout = """

> [!character]
> - **name**: Aragorn
> - **race**: [[Human]]
> - **weapon**: [[Andúril]]
> - **info**: More info in [[More info]]

[[Category:Characters]]"""

    wikicode = mwparserfromhell.parse(wikitext)
    cleaned_wikicode = transform_templates_to_callouts(wikicode)

    assert str(cleaned_wikicode) == wikitext_with_callout


# Test 5: Category helpers
def test_merge_tags_expands_and_dedupes() -> None:
    assert merge_tags(["a", "b"], "c") == ["a", "b", "c"]
    assert merge_tags("solo", ["solo", "new"]) == ["solo", "new"]
    assert merge_tags(None, "tag") == ["tag"]


def test_split_front_matter() -> None:
    content = "---\ntitle: Foo\ntags:\n- bar\n---\n# Body\n"
    header, body = split_front_matter(content)
    assert header == {"title": "Foo", "tags": ["bar"]}
    assert body == "# Body\n"


def test_split_front_matter_without_yaml() -> None:
    content = "# Just markdown"
    assert split_front_matter(content) == (None, content)


def test_process_categories_rewrites_links() -> None:
    wikicode = mwparserfromhell.parse("Article text [[Category:Characters]] end")
    wikicode, tags = process_categories(wikicode)
    assert tags == ["Characters"]
    assert str(wikicode) == "Article text [[Category Characters]] end"


def test_process_categories_normalizes_tag_names() -> None:
    wikicode = mwparserfromhell.parse("[[Category:Main Characters]]")
    wikicode, tags = process_categories(wikicode)
    assert tags == ["Main_Characters"]
    assert str(wikicode) == "[[Category Main Characters]]"


def test_create_tag_indexes_writes_new_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(convert, "OUTPUT_DIR", str(tmp_path))
    convert.tag_to_pages.clear()
    convert.tag_to_pages["Characters"] = ["Aragorn", "Legolas"]

    create_tag_indexes()

    filepath = tmp_path / "categories" / "Category Characters.md"
    assert filepath.exists()
    content = filepath.read_text(encoding="utf-8")
    assert "Index: Characters" in content
    assert "- Characters" in content
    assert "- [[Aragorn]]" in content
    assert "- [[Legolas]]" in content
    assert "# Characters Index" in content


def test_create_tag_indexes_merges_existing_category_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(convert, "OUTPUT_DIR", str(tmp_path))
    category_dir = tmp_path / "categories"
    category_dir.mkdir()
    existing = """---
title: Category Characters
tags:
- existing_tag
source/url: https://example.com/wiki/Category:Characters
---
Original category page content.
"""
    filepath = category_dir / "Category Characters.md"
    filepath.write_text(existing, encoding="utf-8")

    convert.tag_to_pages.clear()
    convert.tag_to_pages["Characters"] = ["Aragorn"]

    create_tag_indexes()

    content = filepath.read_text(encoding="utf-8")
    assert "Original category page content." in content
    assert "source/url: https://example.com/wiki/Category:Characters" in content
    assert "- existing_tag" in content
    assert "- Characters" in content
    assert "title: Category Characters" in content
    assert "# Characters Index" in content
    assert "- [[Aragorn]]" in content
