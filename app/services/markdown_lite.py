"""Tiny, safe Markdown subset renderer for LLM output.

Everything is HTML-escaped FIRST, so model output can never inject markup
(OWASP LLM02: insecure output handling). Supports headings, bold/italic,
inline code, fenced code, bullet/numbered lists, pipe tables and paragraphs.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])_([^_]+)_(?!\w)", r"<em>\1</em>", text)
    return text


def _table(lines: list[str]) -> str:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c or "--") for c in r)]
    if not rows:
        return ""
    head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_markdown(source: str) -> Markup:
    lines = html.escape(source).split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append(
                f'<pre class="code" data-lang="{lang}"><code>' + "\n".join(buf) + "</code></pre>"
            )
            i += 1
            continue
        if line.strip().startswith("|"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(_table(buf))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = min(len(m.group(1)) + 2, 6)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if line.strip():
            buf = [line]
            i += 1
            while (
                i < len(lines)
                and lines[i].strip()
                and not re.match(r"^(#{1,4}\s|```|\s*\||\s*([-*]|\d+\.)\s)", lines[i])
            ):
                buf.append(lines[i])
                i += 1
            out.append("<p>" + "<br>".join(_inline(b) for b in buf) + "</p>")
            continue
        i += 1
    return Markup("\n".join(out))  # noqa: S704  # nosec B704 (escaped above)
