"""Assainissement du HTML des sections (E3, plan L2 §6) : charges XSS connues."""

import pytest

from apps.portal.sanitizer import safe_href, sanitize_html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<p>Bonjour <strong>à tous</strong></p>", "<p>Bonjour <strong>à tous</strong></p>"),
        ("<b>gras</b> <i>italique</i>", "<strong>gras</strong> <em>italique</em>"),
        ("<p>a<br>b<br/>c</p>", "<p>a<br>b<br>c</p>"),
        ("texte & <brut>", "texte &amp;"),
        ("<p>1 &lt; 2</p>", "<p>1 &lt; 2</p>"),
        ("<div><span>gardé</span></div>", "gardé"),
        ("<ul><li>un<li>deux</ul>", "<ul><li>un</li><li>deux</li></ul>"),
        ("<p>non fermé", "<p>non fermé</p>"),
        ("</p>orphelin", "orphelin"),
        ("<!-- commentaire --><p>x</p>", "<p>x</p>"),
    ],
)
def test_allowlist(raw, expected):
    assert sanitize_html(raw) == expected


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "<SCRIPT SRC=//x.example/x.js></SCRIPT>",
        '<img src=x onerror="alert(1)">',
        "<svg><script>alert(1)</script></svg>",
        "<svg onload=alert(1)>",
        '<iframe src="javascript:alert(1)"></iframe>',
        "<style>body{display:none}</style>",
        '<p style="background:url(javascript:alert(1))" onclick="x()">t</p>',
        '<a href="javascript:alert(1)">x</a>',
        '<a href="  JaVaScRiPt:alert(1)">x</a>',
        '<a href="java&#x09;script:alert(1)">x</a>',
        '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
        '<a href="//evil.example/">x</a>',
        '<a href="/\\evil.example/">x</a>',
        "<math><mtext><img src=x onerror=alert(1)></mtext></math>",
        "<template><script>alert(1)</script></template>",
        "<object data=x></object><embed src=x>",
        '<form action="https://x.example"><input name=a></form>',
    ],
)
def test_xss_payloads_leave_no_active_content(payload):
    cleaned = sanitize_html(payload).lower()
    for needle in (
        "<script",
        "javascript:",
        "onerror",
        "onload",
        "onclick",
        "style=",
        "<svg",
        "<iframe",
        "<img",
        "<math",
        "data:",
        "//evil",
        "<form",
        "<input",
        "src=",
    ):
        assert needle not in cleaned, (payload, cleaned)


def test_links_keep_only_safe_href():
    assert sanitize_html('<a href="https://conf.example/a?b=1&c=2" target="_blank">x</a>') == (
        '<a href="https://conf.example/a?b=1&amp;c=2">x</a>'
    )
    assert sanitize_html('<a href="mailto:contact@conf.example">écrire</a>') == (
        '<a href="mailto:contact@conf.example">écrire</a>'
    )
    assert sanitize_html('<a href="/fr/appel/">appel</a>') == '<a href="/fr/appel/">appel</a>'
    assert sanitize_html('<a href="javascript:x">x</a>') == "<a>x</a>"


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://x.example", "https://x.example"),
        ("http://x.example", "http://x.example"),
        ("tel:+2250102030405", "tel:+2250102030405"),
        ("/p/infos/", "/p/infos/"),
        ("//x.example", None),
        ("javascript:alert(1)", None),
        ("java\tscript:alert(1)", None),
        ("ftp://x.example", None),
        ("", None),
    ],
)
def test_safe_href(href, expected):
    assert safe_href(href) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "<p>a &amp; b <a href='https://x.example/?a=1&amp;b=2'>l</a></p>",
        "<ul><li>un<li>deux</ul><p>fin",
        "<b>x</b><script>y</script>&lt;z&gt;",
    ],
)
def test_output_is_stable(raw):
    once = sanitize_html(raw)
    assert sanitize_html(once) == once
