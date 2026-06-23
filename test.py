"""Unit tests for convert.py.

Pandoc link post-processing tests reflect output from Pandoc 3.9.0.2.
"""

import sys

import mwparserfromhell

import convert
from convert import (
    build_mediawiki_page_url,
    build_source_fields,
    build_yaml_header,
    clean_heading_ids,
    create_tag_indexes,
    fix_links_from_pandoc,
    merge_tags,
    prep_wikilinks_download_files_and_get_categories,
    prepare_wikitext,
    split_front_matter,
    transform_templates_to_callouts,
)

sys.argv = ["test.py", "dummy.xml"]




# ***************
# Heading cleanup
def test_clean_heading_ids() -> None:
    md = "# Heading 1 {#heading1}\n## Heading 2 {#heading2}"
    expected = "# Heading 1\n## Heading 2"
    assert clean_heading_ids(md) == expected


# ***************
# Pandoc-style link cleanup (input reflects Pandoc 3.9.0.2 output)
def test_fix_links_from_pandoc_internal(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", False)
    md = 'This is a [Foo Bar](Foo_Bar "Foo Bar"){.wikilink} and [Alias](Target_Page "Alias"){.wikilink}.'
    expected = 'This is a [[Foo Bar]] and [[Target Page|Alias]].'
    assert fix_links_from_pandoc(md) == expected


def test_fix_links_from_pandoc_restores_underscores_with_pandoc(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", True)
    md = '[Category Main Characters](categories/Category_Main:Characters "Category Main_Characters"){.wikilink}'
    expected = '[[categories/Category Main_Characters|Category Main_Characters]]'
    assert fix_links_from_pandoc(md) == expected


def test_fix_links_from_pandoc_external(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", False)
    md = 'Visit [Google](https://google.com) or contact [me](mailto:test@example.com).'
    assert fix_links_from_pandoc(md) == md  # external links are left unchanged


# ***************
# YAML front matter
def test_build_yaml_header_basic() -> None:
    tags = ["category_one", "tag_two"]
    yaml = build_yaml_header(tags)
    assert "---" in yaml
    assert "tags:" in yaml
    assert "- category_one" in yaml
    assert "- tag_two" in yaml


# ***************
# Wiki URL extraction and page links
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


def test_config_reads_wiki_metadata(tmp_path, monkeypatch) -> None:
    xml = """<?xml version="1.0"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <siteinfo>
    <base>https://en.wikipedia.org/wiki/Main_Page</base>
    <generator>MediaWiki 1.41.0</generator>
    <sitename>Wikipedia</sitename>
  </siteinfo>
</mediawiki>"""
    xml_file = tmp_path / "wiki.xml"
    xml_file.write_text(xml, encoding="utf-8")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["test.py", str(xml_file), str(out_dir), "--pandoc-skip"],
    )

    tree = convert.config()

    assert tree is not None
    assert convert.WIKI_URL == "https://en.wikipedia.org"
    assert convert.WIKI_BASE_URL == "https://en.wikipedia.org/wiki/Main_Page"
    assert convert.WIKI_GENERATOR == "MediaWiki 1.41.0"
    assert convert.WIKI_NAME == "Wikipedia"
    assert convert.OUTPUT_DIR == str(out_dir)
    assert out_dir.is_dir()


def test_config_raises_when_base_missing(tmp_path, monkeypatch) -> None:
    xml = """<?xml version="1.0"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <siteinfo>
    <generator>MediaWiki 1.41.0</generator>
    <sitename>Wikipedia</sitename>
  </siteinfo>
</mediawiki>"""
    xml_file = tmp_path / "wiki.xml"
    xml_file.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["test.py", str(xml_file), "--pandoc-skip"])

    import pytest

    with pytest.raises(ValueError, match="Could not extract wiki domain"):
        convert.config()


# ***************
# YAML front matter with source metadata
def test_build_yaml_header_with_source() -> None:
    convert.WIKI_URL = "https://example.com"
    convert.WIKI_BASE_URL = "https://example.com/wiki/Main_Page"
    convert.WIKI_GENERATOR = "MediaWiki 1.41.0"
    convert.WIKI_NAME = "Example Wiki"
    yaml = build_yaml_header(
        ["tag"],
        extra_fields=build_source_fields("Sample Page", "2024-06-18T10:30:00Z"),
    )
    assert (
        "source/note: Imported from Example Wiki (MediaWiki 1.41.0) @ https://example.com" in yaml
    )
    assert "source/url: https://example.com/wiki/Sample_Page" in yaml
    assert "source/date: '2024-06-18T10:30:00Z'" in yaml


def test_prepare_wikitext_omits_source_fields_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(convert, "NO_SOURCE_FIELDS", True)
    yaml_header, _, _ = prepare_wikitext("Page body [[Category:Characters]]", "Sample Page")
    assert "source/" not in yaml_header


# ***************
# Template to callout conversion
def test_transform_templates_to_callouts(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", False)
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


# ***************
# Front matter and tag helpers
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


# ***************
# Category extraction and tag index pages
def test_prep_wikilinks_rewrites_category_links() -> None:
    wikicode = mwparserfromhell.parse("Article text [[Category:Characters]] end")
    wikicode, tags = prep_wikilinks_download_files_and_get_categories(wikicode)
    assert tags == ["Characters"]
    assert (
        str(wikicode) == "Article text [[categories/Category Characters|Category Characters]] end"
    )


def test_prep_wikilinks_normalizes_tag_names_without_pandoc(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", False)
    wikicode = mwparserfromhell.parse("[[Category:Main Characters]]")
    wikicode, tags = prep_wikilinks_download_files_and_get_categories(wikicode)
    assert tags == ["Main_Characters"]
    assert str(wikicode) == "[[categories/Category Main_Characters|Category Main_Characters]]"


def test_prep_wikilinks_normalizes_tag_names_with_pandoc(monkeypatch) -> None:
    monkeypatch.setattr(convert, "USE_PANDOC", True)
    wikicode = mwparserfromhell.parse("[[Category:Main Characters]]")
    wikicode, tags = prep_wikilinks_download_files_and_get_categories(wikicode)
    assert tags == ["Main_Characters"]
    assert str(wikicode) == "[[categories/Category Main:Characters|Category Main_Characters]]"


def test_create_tag_indexes_writes_new_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(convert, "OUTPUT_DIR", str(tmp_path))
    convert.tag_to_pages.clear()
    convert.tag_to_pages["Characters"] = ["Aragorn", "Legolas"]

    create_tag_indexes()

    filepath = tmp_path / "categories" / "Category Characters.md"
    assert filepath.exists()
    content = filepath.read_text(encoding="utf-8")
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
    assert "# Characters Index" in content
    assert "- [[Aragorn]]" in content


def test_create_tag_indexes_strips_source_fields_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(convert, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(convert, "NO_SOURCE_FIELDS", True)
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
    assert "source/url" not in content
    assert "Original category page content." in content
    assert "- [[Aragorn]]" in content


def test_create_tag_indexes_skips_duplicate_index_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(convert, "OUTPUT_DIR", str(tmp_path))
    category_dir = tmp_path / "categories"
    category_dir.mkdir()
    index_section = "# Characters Index\n- [[Aragorn]]"
    existing = f"""---
title: Category Characters
tags:
- existing_tag
---
Original category page content.

{index_section}
"""
    filepath = category_dir / "Category Characters.md"
    filepath.write_text(existing, encoding="utf-8")

    convert.tag_to_pages.clear()
    convert.tag_to_pages["Characters"] = ["Aragorn"]

    create_tag_indexes()

    content = filepath.read_text(encoding="utf-8")
    assert content.count("# Characters Index") == 1
    assert content.count("- [[Aragorn]]") == 1
    assert "Original category page content." in content
    assert "- Characters" in content
