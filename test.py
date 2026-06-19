"""Unit tests for convert.py.

Pandoc link post-processing tests reflect output from Pandoc 3.9.0.2.
"""

import mwparserfromhell
import convert
from convert import (
    clean_heading_ids,
    fix_links_from_pandoc,
    build_yaml_header,
    build_mediawiki_page_url,
    build_source_fields,
    transform_templates_to_callouts,
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
  </siteinfo>
</mediawiki>"""
    tree = ET.ElementTree(ET.fromstring(xml))
    wiki_url, base_url, generator = convert.extract_wiki_url(tree)
    assert wiki_url == "https://en.wikipedia.org"
    assert base_url == "https://en.wikipedia.org/wiki/Main_Page"
    assert generator == "MediaWiki 1.41.0"


def test_build_yaml_header_with_source() -> None:
    convert.WIKI_URL = "https://example.com"
    convert.WIKI_BASE_URL = "https://example.com/wiki/Main_Page"
    convert.WIKI_GENERATOR = "MediaWiki 1.41.0"
    yaml = build_yaml_header(
        "Sample Page",
        ["tag"],
        extra_fields=build_source_fields("Sample Page", "2024-06-18T10:30:00Z"),
    )
    assert "source/note: Imported from MediaWiki 1.41.0 website @ https://example.com" in yaml
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
