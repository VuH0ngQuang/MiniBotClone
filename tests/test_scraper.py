import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import articleToMarkdown, contentHash, htmlBodyToMarkdown


def test_contentHash_is_deterministic():
    assert contentHash("hello") == contentHash("hello")


def test_contentHash_differs_for_different_content():
    assert contentHash("hello") != contentHash("world")


def test_htmlBodyToMarkdown_strips_script_and_nav():
    html = "<div><nav>Menu</nav><script>alert(1)</script><p>Real content</p></div>"
    md = htmlBodyToMarkdown(html)
    assert "Menu" not in md
    assert "alert" not in md
    assert "Real content" in md


def test_htmlBodyToMarkdown_drops_images():
    html = '<p>See below</p><img src="pic.png" alt="pic">'
    md = htmlBodyToMarkdown(html)
    assert "pic.png" not in md
    assert "See below" in md


def test_htmlBodyToMarkdown_preserves_links_and_headings():
    html = '<h2>Setup</h2><p>Read the <a href="/hc/en-us/articles/123">guide</a>.</p>'
    md = htmlBodyToMarkdown(html)
    assert "## Setup" in md
    assert "[guide](/hc/en-us/articles/123)" in md


def test_htmlBodyToMarkdown_collapses_blank_lines():
    html = "<p>One</p>" + "<br>" * 10 + "<p>Two</p>"
    md = htmlBodyToMarkdown(html)
    assert "\n\n\n" not in md


def test_articleToMarkdown_includes_metadata_and_body():
    article = {
        "url": "https://support.optisigns.com/hc/en-us/articles/1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-02-01T00:00:00Z",
        "title": "How to add a YouTube video",
        "body": "<p>Open the app and click add.</p>",
    }
    md = articleToMarkdown(42, article)
    assert md.startswith("# How to add a YouTube video")
    assert "- ID: 42" in md
    assert "- URL: https://support.optisigns.com/hc/en-us/articles/1" in md
    assert "Open the app and click add." in md
