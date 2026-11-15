"""Response translation (pt-BR -> en) for the public API.

The engine always writes its user-facing text in Portuguese (pt-BR is the default and the reference language). When a
client asks for English, the API translates the JSON response at the edge with a catalog of templates (`en.json`):

- each key is a Portuguese template extracted from the code (`scripts/i18n_extract.py`): a string literal or an f-string
  whose `{expression}` parts became positional placeholders `{0}`, `{1}`...;
- each value is the English template with the same placeholders (in any order).

A response string is translated by the longest template that matches it entirely; the placeholder values are translated
recursively (they are often crop names or sentences themselves). Strings built by joining several sentences are split on
the usual separators when no template matches the whole. Numbers inside placeholder values switch to English separators.
JSON keys, enum values, ids and dates are never translated: the response shape is the same in both languages.
"""
from __future__ import annotations

import contextvars
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "pt-BR"
SUPPORTED_LOCALES = ("pt-BR", "en")
CATALOG_FILE = Path(__file__).with_name("en.json")
_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_SEPARATORS = (" → ", "; ", ". ", " · ", " | ", " — ", ", ", ": ", " + ", " e ")
_SPLIT = re.compile("(" + "|".join(re.escape(x) for x in _SEPARATORS) + ")")
_MAX_RUN = 15  # most pieces tried as one run
_MAX_SPLITS = 64  # ways of splitting a text among the placeholders of a template that are tried
_MIN_OPEN_PREFIX = 12  # literal chars a template starting with a placeholder needs to be used on a prefix


def normalize_locale(value: str | None) -> str | None:
    """'en', 'en-US', 'EN_gb' -> 'en'; 'pt', 'pt-BR' -> 'pt-BR'; anything else -> None."""
    if not value:
        return None
    v = value.strip().lower().replace("_", "-")
    if v == "en" or v.startswith("en-"):
        return "en"
    if v == "pt" or v.startswith("pt-"):
        return "pt-BR"
    return None


def locale_from_accept_language(header: str | None) -> str | None:
    """First supported language of an Accept-Language header, by quality (e.g. 'en-US,en;q=0.9,pt;q=0.8' -> 'en')."""
    if not header:
        return None
    langs = []
    for i, part in enumerate(header.split(",")):
        tag, _, q = part.strip().partition(";q=")
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 0.0
        langs.append((-weight, i, tag))
    for _, _, tag in sorted(langs):
        loc = normalize_locale(tag)
        if loc:
            return loc
    return None


def resolve_locale(query: str | None, accept_language: str | None) -> str:
    """Precedence: `lang` query parameter > Accept-Language header > pt-BR."""
    return normalize_locale(query) or locale_from_accept_language(accept_language) or DEFAULT_LOCALE


def _unescape(s: str) -> str:
    return s.replace("{{", "{").replace("}}", "}")


class Msg(str):
    """A user text built from a catalog template: it *is* the pt-BR string (so the pt-BR response is unchanged), and it
    remembers the template and its values, so the English is rendered piece by piece instead of guessed from the text.

        Msg("{0} em {1}: não indicado", crop, sowing)   # == f"{crop} em {sowing}: não indicado"

    Values are already formatted strings (or Msg/Join). The template is a catalog key (`scripts/i18n_extract.py` finds it)."""

    def __new__(cls, template: str, *args: str):
        obj = super().__new__(cls, template.format(*args))
        obj.template, obj.args = template, args
        return obj


class Join(str):
    """Texts joined by a separator ("; ", ", ") and optionally a different last one (" e "), translated item by item."""

    def __new__(cls, items, sep: str = ", ", last: str | None = None):
        items = list(items)
        if last is not None and len(items) > 1:
            text = sep.join(items[:-1]) + last + items[-1]
        else:
            text = sep.join(items)
        obj = super().__new__(cls, text)
        obj.items, obj.sep, obj.last = items, sep, last
        return obj


class _Template:
    __slots__ = ("pt", "en", "regex", "seq", "literal_len", "prefix", "ends_literal")

    def __init__(self, pt: str, en: str):
        self.pt, self.en = pt, en
        parts = re.split(r"(\{\d+\})", pt)
        rx, lit, self.seq = [], 0, []
        for p in parts:
            m = _PLACEHOLDER.fullmatch(p)
            if m:
                rx.append(f"(?P<p{m.group(1)}>.*?)")
                self.seq.append((True, m.group(1)))
            elif p:
                text = _unescape(p)
                lit += len(text)
                rx.append(re.escape(text))
                self.seq.append((False, text))
        self.regex = re.compile("".join(rx), re.S)
        self.literal_len = lit
        self.ends_literal = bool(parts) and not _PLACEHOLDER.fullmatch(parts[-1]) and parts[-1] != ""
        first = parts[0] if parts else ""
        self.prefix = _unescape(first)[:3] if first and not _PLACEHOLDER.fullmatch(first) else ""


    def splits(self, s: str, limit: int = _MAX_SPLITS):
        """Every way of matching all of `s` (placeholder -> value), shortest values first; at most `limit`."""
        seq, out = self.seq, []

        def walk(i: int, pos: int, acc: dict):
            if len(out) >= limit:
                return
            if i == len(seq):
                if pos == len(s):
                    out.append(dict(acc))
                return
            is_ph, x = seq[i]
            if not is_ph:
                if s.startswith(x, pos):
                    walk(i + 1, pos + len(x), acc)
                return
            if i + 1 == len(seq):
                ends = [len(s)]
            elif not seq[i + 1][0]:
                lit = seq[i + 1][1]
                ends, q = [], s.find(lit, pos)
                while q != -1:
                    ends.append(q)
                    q = s.find(lit, q + 1)
            else:
                ends = range(pos, len(s) + 1)
            for e in ends:
                acc[x] = s[pos:e]
                walk(i + 1, e, acc)
            acc.pop(x, None)

        walk(0, 0, {})
        return out


class Translator:
    def __init__(self, catalog: dict[str, str | None]):
        self.templates = {k: v for k, v in catalog.items() if v is not None}  # for Msg (exact template lookup)
        self.exact: dict[str, str] = {}
        self.by_prefix: dict[str, list[_Template]] = {}
        self.open: list[_Template] = []  # templates starting with a placeholder
        for pt, en in _with_stripped_variants(catalog):
            if not _PLACEHOLDER.search(pt):
                self.exact[_unescape(pt)] = _unescape(en)
                continue
            if not _LETTERS.search(_PLACEHOLDER.sub("", pt)):
                continue  # structural templates ("{0} ({1})") are only for Msg: as patterns they would match anything
            t = _Template(pt, en)
            (self.by_prefix.setdefault(t.prefix, []) if t.prefix else self.open).append(t)
        self.exact_lower = {k.lower(): v for k, v in self.exact.items()}
        self.exact_by_head: dict[str, list[tuple[str, str]]] = {}
        for k, v in self.exact.items():
            if len(k) >= 12:
                self.exact_by_head.setdefault(k[:12], []).append((k, v))
        for lst in [*self.by_prefix.values(), self.open]:
            lst.sort(key=lambda t: -t.literal_len)
        self.text = lru_cache(maxsize=20000)(self._text)

    def _candidates(self, s: str):
        for k in {s[:1], s[:2], s[:3]}:
            yield from self.by_prefix.get(k, ())
        yield from self.open

    def _value(self, v: str) -> str:
        out = self.text(v)
        return _english_numbers(v) if out == v else out

    def _unmatched(self, values: dict) -> int:
        """Placeholder values this split leaves in Portuguese (the split with the fewest wins)."""
        return sum(1 for v in values.values() if _WORD.search(v) and self.text(v) == v)

    def _render(self, t: _Template, raw: dict[str, str]) -> str:
        values = {k: self._value(v) for k, v in raw.items()}
        en = t.en.replace("{{", "\0").replace("}}", "\1")
        return _PLACEHOLDER.sub(lambda p: values[p.group(1)], en).replace("\0", "{").replace("\1", "}")

    def _match(self, s: str) -> str | None:
        """Whole-string match: exact text or the template with the most literal text that matches all of `s`."""
        hit = self.exact.get(s)
        if hit is not None:
            return hit
        hit = self.exact_lower.get(s.lower())
        if hit is not None:  # same text with another capitalization: keep the case of the first letter
            return (hit[:1].upper() if s[:1].isupper() else hit[:1].lower()) + hit[1:]
        best = None  # (template, values); values must keep their parentheses balanced
        for t in self._candidates(s):
            if best is not None and t.literal_len <= best[0].literal_len:
                continue
            if not t.regex.fullmatch(s):
                continue
            pool = [o for o in t.splits(s) if all(map(_balanced, o.values()))]
            if pool:
                best = (t, min(pool, key=self._unmatched) if len(pool) > 1 else pool[0])
        return None if best is None else self._render(*best)

    def _prefix(self, s: str) -> str | None:
        """`s` built by concatenation: translate the longest template matching its start, then the rest."""
        best = None
        for t in self._candidates(s):
            if not t.ends_literal or (not t.prefix and t.literal_len < _MIN_OPEN_PREFIX):
                continue
            if best is not None and t.literal_len <= best[0].literal_len:
                continue
            m = t.regex.match(s)
            if m and m.end() < len(s) and not _SPLIT.match(s, m.end()) and all(map(_balanced, m.groupdict().values())):
                best = (t, m)
        for text, en in self.exact_prefixes(s):
            if _SPLIT.match(s, len(text)):
                continue  # ends at a separator: left to the split into pieces, which may find a longer run
            if best is None or len(text) > best[0].literal_len:
                return en + self.text(s[len(text):])
        if best is None:
            return None
        t, m = best
        return self._render(t, {k[1:]: v for k, v in m.groupdict().items()}) + self.text(s[m.end():])

    def exact_prefixes(self, s: str):
        """Exact (placeholder-free) texts that start `s`, longest first (at least 12 chars to avoid fragments)."""
        hits = [(k, v) for k, v in self.exact_by_head.get(s[:12], ()) if s.startswith(k)]
        return sorted(hits, key=lambda kv: -len(kv[0]))

    def _atom(self, s: str) -> str | None:
        """Translation of `s` as one piece (no splitting on separators); None if nothing matches."""
        hit = self._match(s)
        if hit is not None:
            return hit
        stripped = s.strip()
        if stripped != s and stripped:
            inner = self._atom(stripped)
            return None if inner is None else s.replace(stripped, inner, 1)
        if s[:1].isupper():  # labels capitalized at runtime ("Milho safrinha" from "milho safrinha")
            low = self._match(s[0].lower() + s[1:])
            if low is not None:
                return low[:1].upper() + low[1:]
        hit = self._prefix(s)
        if hit is not None:
            return hit
        if len(s) > 1 and s[-1] in ".:)":
            head = self._atom(s[:-1])
            if head is not None:
                return head + s[-1]
        return None

    def _text(self, s: str) -> str:
        if not s or not re.search(r"[A-Za-zÀ-ú]", s):
            return s
        if _MONTH_RANGE.fullmatch(s) or _MONTH.fullmatch(s):
            return _english_months(s)
        hit = self._atom(s)
        if hit is not None:
            return hit
        # Joined from several texts: cover the pieces (split on the usual separators) with runs that translate, leaving
        # the fewest letters in Portuguese. A run may take the separator before it (templates starting with "; " etc.).
        tokens = _SPLIT.split(s)
        n = len(tokens)
        if n == 1:
            return s
        # best[i] = (letters left untranslated, number of runs, rendering) for the text tokens[i:] (i even = a piece)
        best: dict[int, tuple[int, int, str]] = {n + 1: (0, 0, ""), n - 1 + 2: (0, 0, "")}

        def tail(j: int) -> tuple[int, int, str]:
            return best[j + 2] if j + 2 <= n + 1 else (0, 0, "")

        for i in range(n - 1, -1, -2):
            sep_after = lambda j: _SEPARATOR_EN.get(tokens[j + 1], tokens[j + 1]) if j + 1 < n else ""  # noqa: E731
            options = []
            for j in range(i, min(n - 1, i + 2 * _MAX_RUN) + 1, 2):
                run = "".join(tokens[i:j + 1])
                rest = tail(j)
                hit = self._atom(run) if run else run
                if hit is not None:
                    options.append((rest[0], rest[1] + 1, hit + sep_after(j) + rest[2]))
                if i > 0 and j > i or i > 0 and j == i:
                    with_sep = self._atom(tokens[i - 1] + run)
                    if with_sep is not None:
                        options.append((rest[0], rest[1] + 1, "\0" + with_sep + sep_after(j) + rest[2]))
            if not options:
                rest = tail(i)
                options.append((rest[0] + len(_LETTERS.findall(tokens[i])), rest[1] + 1, tokens[i] + sep_after(i) + rest[2]))
            best[i] = min(options, key=lambda o: (o[0], o[1]))
        # "\0" marks a run that already carries the separator before it: drop that separator
        return _MARKED_SEPARATOR.sub("", best[0][2]).replace("\0", "")

    def structured(self, obj: str) -> str:
        """English of a Msg/Join, rendered from its template and values; plain strings go through `text`."""
        if isinstance(obj, Msg):
            en = self.templates.get(obj.template)
            if en is None:  # template not translated yet (test_i18n fails): keep it, still translate the values
                en = obj.template
            values = [self.structured(a) if isinstance(a, (Msg, Join)) else self._value(str(a)) for a in obj.args]
            en = en.replace("{{", "\0").replace("}}", "\1")
            return _PLACEHOLDER.sub(lambda m: values[int(m.group(1))], en).replace("\0", "{").replace("\1", "}")
        if isinstance(obj, Join):
            items = [self.structured(i) for i in obj.items]
            sep = _SEPARATOR_EN.get(obj.sep, obj.sep)
            if obj.last is not None and len(items) > 1:
                return sep.join(items[:-1]) + _SEPARATOR_EN.get(obj.last, obj.last) + items[-1]
            return sep.join(items)
        return self._value(obj) if obj else obj

    def translate(self, obj: Any) -> Any:
        if isinstance(obj, (Msg, Join)):
            return self.structured(obj)
        if isinstance(obj, str):
            return obj if _CODE.fullmatch(obj) else self.text(obj)
        if isinstance(obj, dict):
            return {k: v if k in _CODE_KEYS and isinstance(v, str) else
                    self.text(v) if k in _DISPLAY_KEYS and isinstance(v, str) else self.translate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.translate(v) for v in obj]
        return obj


_MONTHS = dict(zip("jan fev mar abr mai jun jul ago set out nov dez".split(),
                   "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()))
_MONTH = re.compile(r"(?i)(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/\d{2,4}")
_MONTH_RANGE = re.compile(rf"{_MONTH.pattern[4:]} a {_MONTH.pattern[4:]}", re.I)


def _english_months(s: str) -> str:
    """'nov/25 a out/26' -> 'Nov/25 to Oct/26'."""
    s = _MONTH.sub(lambda m: _MONTHS[m.group(1).lower()] + m.group(0)[3:], s)
    return s.replace(" a ", " to ")


_WORD = re.compile(r"[A-Za-zÀ-ú]{3}")
_LETTERS = re.compile(r"[A-Za-zÀ-ú]")
_DISPLAY_KEYS = {"cultura"}  # keys whose values are labels even when they look like codes ("soja")
# keys whose values are enums/official names even when they have spaces ("não se aplica", "muito argiloso", ZARC crop names)
_CODE_KEYS = {"nivel", "classe_embrapa", "classe_textura", "cultura_zarc", "origem", "status", "erro"}
_SEPARATOR_EN = {" e ": " and "}
_MARKED_SEPARATOR = re.compile("(?:" + "|".join(re.escape(x) for x in (*_SEPARATORS, *_SEPARATOR_EN.values())) + ")\0")
_CODE = re.compile(r"[a-z0-9_]+")  # whole values like "alto", "milho_verao", "ok": codes/enums, never translated
_EDGE = re.compile(r"^[\s;:,.)—]+")


def _balanced(v: str) -> bool:
    """Parentheses of a placeholder value open and close in order (a value never ends a parenthesis it did not open)."""
    depth = 0
    for ch in v:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _with_stripped_variants(catalog: dict[str, str | None]):
    """Catalog pairs plus, for keys that start with a separator ("; margem...", " A cobertura..."), the same pair
    without it: the text may arrive split from what preceded it. Original keys win over variants."""
    pairs = [(pt, en) for pt, en in catalog.items() if en is not None]
    keys = {pt for pt, _ in pairs}
    out = list(pairs)
    for pt, en in pairs:
        lead = _EDGE.match(pt)
        if not lead:
            continue
        pt2 = pt[lead.end():]
        en2 = en[lead.end():] if en.startswith(lead.group(0)) else _EDGE.sub("", en)
        if pt2 and pt2 not in keys:
            keys.add(pt2)
            out.append((pt2, en2))
    return out


def _english_numbers(v: str) -> str:
    """'1.234,5' -> '1,234.5'; '3,5' -> '3.5' (numbers already formatted the Brazilian way inside a value)."""
    def swap(m):
        return m.group(0).replace(".", "\0").replace(",", ".").replace("\0", ",")
    return re.sub(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\d.,]*\d)|(?<![\d.,])\d+,\d+(?![\d,]*\d)", swap, v)


@lru_cache(maxsize=1)
def translator() -> Translator:
    return Translator(json.loads(CATALOG_FILE.read_text(encoding="utf-8")))


def translate(obj: Any, locale: str) -> Any:
    """Translate the user-facing text of a JSON-like object to `locale` (pt-BR returns it untouched)."""
    if locale == DEFAULT_LOCALE:
        return obj
    return translator().translate(obj)


# Request language, set by the API middleware. The route translates the service result while its Msg/Join texts still carry
# their templates (`localize`); the middleware then only translates what did not go through a route (errors, validation).
_REQUEST: contextvars.ContextVar[dict | None] = contextvars.ContextVar("field_shift_request_locale", default=None)


def start_request(locale: str) -> dict:
    state = {"locale": locale, "localized": False}
    _REQUEST.set(state)
    return state


def localize(obj: Any) -> Any:
    """Translate a route result to the request language (no-op outside a request or in pt-BR)."""
    state = _REQUEST.get()
    if state is None:
        return obj
    state["localized"] = True
    return translate(obj, state["locale"])
