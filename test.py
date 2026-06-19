"""Unit tests for convert.py.

Pandoc link post-processing tests reflect output from Pandoc 3.9.0.2.
"""

import mwparserfromhell
import convert
from convert import (
    clean_heading_ids,
    fix_links_from_pandoc,
    build_yaml_header,
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
