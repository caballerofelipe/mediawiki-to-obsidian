# # contents of test_module.py with source code and the test
# from pathlib import Path


# def getssh():
#     """Simple function to return expanded homedir ssh path."""
#     print(Path.home())
#     return Path.home() / ".ssh"


# def test_getssh(monkeypatch):
#     # mocked return function to replace Path.home
#     # always return '/abc'
#     def mockreturn():
#         return Path("/abc")

#     # Application of the monkeypatch to replace Path.home
#     # with the behavior of mockreturn defined above.
#     monkeypatch.setattr(Path, "home", lambda: '/abcX')

#     # Calling getssh() will use mockreturn in place of Path.home
#     # for this test with the monkeypatch.
#     x = getssh()
#     assert x == Path("/abc/.ssh")


"""Unit tests for convert.py.

Pandoc link post-processing tests reflect output from Pandoc 3.9.0.2.
"""

from multiprocessing import context
import pytest
import mwparserfromhell
import convert
from convert import (
    clean_heading_ids,
    fix_links_from_pandoc,
    build_yaml_header,
    transform_infobox_to_callout,
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


# def test_with_monkeypatch(monkeypatch):
#     monkeypatch.setattr('sys.argv', ['prog', '--input', 'file.txt', '--verbose'])
#     args = parse_args()
#     assert args.input == 'file.txt'
#     assert args.verbose is True


# Test 4: Infobox parsing and tag inference
def test_transform_infobox_to_callout(monkeypatch) -> None:
    # Forcing pandoc skipping
    monkeypatch.setattr(convert, 'SKIP_PANDOC', True)
    # print(convert.SKIP_PANDOC)
    # if convert.SKIP_PANDOC:
    #     print('skipping')
    # else:
    #     print('no skipping')
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
    cleaned_wikicode = transform_infobox_to_callout(wikicode)

    print(f'> wikicode: <<{wikicode}>>')
    print(f'> cleaned_wikicode: <<{cleaned_wikicode}>>')
    print(f'> wikitext_with_callout: <<{wikitext_with_callout}>>')

    assert wikitext_with_callout == cleaned_wikicode
