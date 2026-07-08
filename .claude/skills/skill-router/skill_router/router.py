"""Universal, auto-registering skill router (v4.0).

The router reads the *skills themselves* as its routing table. Every skill in
this repo ships a ``SKILL.md`` whose frontmatter encodes a ``[CATEGORY]`` tag,
a human summary, and quoted "Use when the user says ..." trigger phrases. That
structured metadata is all a router needs, so there is **no hand-maintained
config**: drop a new ``SKILL.md`` on disk and it registers automatically, in any
domain — Snowflow, Profit Minute, or something you invent next week.

Design contract
---------------
- **Auto-registering**: :func:`discover_skills` globs ``*/SKILL.md`` and parses
  each one. The registry is rebuilt from disk on every call — nothing is cached,
  so it can never drift from what is actually on disk.
- **Any domain**: zero brand-specific logic lives here. Skills are grouped by
  whatever ``[CATEGORY]`` tags they declare; routing works off whatever trigger
  phrases they declare.
- **Routing**: :func:`route` ranks every skill against a free-text query and
  returns the matches, best first.

Zero third-party dependencies — standard library only, matching the rest of
this repo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

def _find_repo_root() -> Path:
    """Walk up from this package to the first directory that looks like a repo
    root — one containing ``.git``, ``.claude``, or a top-level ``skills/``.

    The package is vendored across several repos at different depths
    (``src/skill_router/`` here, ``skill_router/`` at the root elsewhere), so
    the root cannot be a fixed number of ``parents[...]`` hops.
    """
    package_dir = Path(__file__).resolve().parent
    for candidate in (package_dir.parent, *package_dir.parent.parents):
        if (
            (candidate / ".git").exists()
            or (candidate / ".claude").is_dir()
            or (candidate / "skills").is_dir()
        ):
            return candidate
    return package_dir.parent


def _default_skills_dir(root: Path) -> Path:
    """Prefer ``.claude/skills`` (Claude Code's discovery path); fall back to a
    top-level ``skills/`` directory (the convention in repos that keep skills
    outside ``.claude``). When neither exists yet, point at the preferred path
    so ``discover_skills`` degrades to an empty registry rather than raising.
    """
    preferred = root / ".claude" / "skills"
    if preferred.is_dir():
        return preferred
    fallback = root / "skills"
    if fallback.is_dir():
        return fallback
    return preferred


_REPO_ROOT = _find_repo_root()
DEFAULT_SKILLS_DIR = _default_skills_dir(_REPO_ROOT)

# --- Tunable ranking knob ----------------------------------------------------
# The scorer weights every shared token by its IDF (inverse document frequency)
# across the registry, so a token common to many skills ("post", "week")
# carries little signal while a distinctive one ("canva", "invoice", "stripe")
# dominates. Trigger-phrase tokens get an extra multiplier because the skill
# author wrote those phrases to be matched.
#
# This replaced an earlier per-field-normalised blend after an eval on 34
# held-out paraphrases: the old scorer scored 50% precision@1 (it over-rewarded
# short-field skills sharing a *generic* token), a naive keyword baseline 62%,
# and this IDF scheme 76.5% (MRR 0.84). See tests/test_router_eval.py.
TRIGGER_BOOST = 0.5

# Words too common to carry routing signal. Deliberately small — domain terms
# like "post", "week", "canva", "meta" must survive so they can do the routing.
_STOPWORDS = frozenset(
    "a an the of for to this that these those and or in on at with your my our "
    "i it is are be as by from into".split()
)

_CATEGORY_RE = re.compile(r"\[([^\]]+)\]")
_QUOTED_RE = re.compile(r'"([^"]+)"')
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Skill:
    """One registered skill, parsed from its ``SKILL.md`` frontmatter."""

    name: str
    category: str
    summary: str
    triggers: tuple[str, ...] = field(default_factory=tuple)
    path: Path | None = None

    def as_dict(self) -> dict:
        """JSON-serialisable view (used by the registry dump)."""
        return {
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "triggers": list(self.triggers),
            "path": str(self.path) if self.path else None,
        }


def _tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords and 1-char noise removed."""
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS
    ]


def _split_frontmatter(text: str) -> str:
    """Return the YAML frontmatter block (between the first two ``---`` fences).

    Returns an empty string when the document has no frontmatter, so callers
    degrade gracefully rather than raising on a malformed skill file.
    """
    if not text.lstrip().startswith("---"):
        return ""
    body = text.split("---", 2)
    return body[1] if len(body) >= 3 else ""


def parse_skill_md(text: str, path: Path | None = None) -> Skill | None:
    """Parse one ``SKILL.md`` document into a :class:`Skill`.

    The frontmatter uses a YAML block scalar (``description: |``). Rather than
    pull in a YAML dependency, we extract the two fields we need by hand:
    ``name`` (a scalar) and ``description`` (an indented multi-line block).
    Returns ``None`` when there is no usable ``name``.
    """
    front = _split_frontmatter(text)
    if not front:
        return None

    name = ""
    description_lines: list[str] = []
    in_description = False
    for raw in front.splitlines():
        stripped = raw.strip()
        if not in_description:
            if stripped.startswith("name:"):
                name = stripped[len("name:") :].strip()
            elif stripped.startswith("description:"):
                inline = stripped[len("description:") :].strip()
                # "description: |" opens a block; "description: foo" is inline.
                if inline and inline != "|":
                    description_lines.append(inline)
                in_description = True
        else:
            # The block ends at the next top-level (unindented) YAML key.
            if raw and not raw[0].isspace() and stripped.endswith(":"):
                in_description = False
            elif raw and not raw[0].isspace() and ":" in stripped:
                in_description = False
            else:
                description_lines.append(stripped)

    if not name:
        return None

    description = " ".join(line for line in description_lines if line).strip()
    category_match = _CATEGORY_RE.search(description)
    category = category_match.group(1).strip() if category_match else "UNCATEGORIZED"

    # Summary = description minus the [CATEGORY] tag, trimmed before the
    # "Use when ..." trigger sentence so the registry stays scannable.
    summary = _CATEGORY_RE.sub("", description, count=1).strip()
    cut = re.search(r"\buse when(?:ever)?\b", summary, flags=re.IGNORECASE)
    if cut:
        summary = summary[: cut.start()].strip()
    summary = summary.rstrip(". ").strip()

    triggers = tuple(dict.fromkeys(_QUOTED_RE.findall(description)))

    return Skill(
        name=name,
        category=category,
        summary=summary,
        triggers=triggers,
        path=path,
    )


def discover_skills(skills_dir: Path | str = DEFAULT_SKILLS_DIR) -> list[Skill]:
    """Scan ``skills_dir`` for ``*/SKILL.md`` and return registered skills.

    This is the "auto-registering" step: it reads the live filesystem every
    call, so the registry always reflects exactly what is on disk. Results are
    sorted by name for stable output.
    """
    root = Path(skills_dir)
    skills: list[Skill] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        skill = parse_skill_md(skill_md.read_text(encoding="utf-8"), path=skill_md)
        if skill is not None:
            skills.append(skill)
    return skills


def _skill_tokens(skill: Skill) -> set[str]:
    """The skill's full distinctive vocabulary — name, summary, triggers,
    category — pooled into one bag (the routing 'document')."""
    text = " ".join(
        (
            skill.name.replace("-", " "),
            skill.summary,
            " ".join(skill.triggers),
            skill.category,
        )
    )
    return set(_tokens(text))


def _trigger_tokens(skill: Skill) -> set[str]:
    tokens: set[str] = set()
    for phrase in skill.triggers:
        tokens |= set(_tokens(phrase))
    return tokens


def build_idf(skills: Iterable[Skill]) -> dict[str, float]:
    """Inverse document frequency of every token across the registry.

    Each skill is one document (its pooled vocabulary). A token in many skills
    gets a low weight; a rare, distinctive one gets a high weight. Returned as a
    plain dict; unseen tokens fall back to the max weight via
    :func:`_idf_lookup`.
    """
    docs = [_skill_tokens(s) for s in skills]
    n = len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for tok in doc:
            df[tok] = df.get(tok, 0) + 1
    # +0.5 smoothing keeps weights finite and positive for all df in [1, n].
    return {tok: math.log((n + 1) / (count + 0.5)) for tok, count in df.items()}


def _idf_lookup(idf: dict[str, float] | None, token: str) -> float:
    """IDF weight for ``token``; 1.0 for every token when no IDF map is given
    (so a bare ``score_skill(query, skill)`` still ranks by pooled overlap)."""
    if idf is None:
        return 1.0
    if not idf:
        return 1.0
    # An unseen token is maximally distinctive → the largest weight in the map.
    return idf.get(token, max(idf.values()))


def score_skill(
    query: str, skill: Skill, idf: dict[str, float] | None = None
) -> float:
    """Rank how well ``skill`` answers ``query`` (higher is better, 0 = no match).

    IDF-weighted pooled overlap: sum the IDF weight of every query token the
    skill's vocabulary contains, then add ``TRIGGER_BOOST`` × the IDF weight of
    the query tokens that appear specifically in an authored trigger phrase.
    Weighting by IDF is what stops a shared *generic* token ("post", "week")
    from outranking the skill that shares a *distinctive* one.

    ``idf`` is normally supplied by :func:`route` (built from the whole
    registry). Called without it, every token weighs 1.0 and this degrades to
    plain pooled-overlap — still monotonic, just less discriminating.
    """
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0.0

    base = sum(
        _idf_lookup(idf, tok) for tok in query_tokens & _skill_tokens(skill)
    )
    boost = TRIGGER_BOOST * sum(
        _idf_lookup(idf, tok) for tok in query_tokens & _trigger_tokens(skill)
    )
    # Cohesion: reward query tokens that co-occur in a SINGLE authored trigger
    # phrase, so "queue this post" (one whole add-to-feed trigger) beats a rival
    # that only matches the same tokens scattered across two separate triggers.
    cohesion = 0.0
    for phrase in skill.triggers:
        shared = query_tokens & set(_tokens(phrase))
        cohesion = max(cohesion, sum(_idf_lookup(idf, tok) for tok in shared))
    return base + boost + TRIGGER_BOOST * cohesion


def route(
    query: str,
    skills: Iterable[Skill] | None = None,
    *,
    top: int | None = None,
    skills_dir: Path | str = DEFAULT_SKILLS_DIR,
) -> list[tuple[Skill, float]]:
    """Return ``(skill, score)`` pairs for ``query``, best match first.

    When ``skills`` is omitted the registry is auto-discovered from
    ``skills_dir`` (so a bare ``route("...")`` call "just works"). Only positive
    scores are returned; ``top`` optionally caps the list length.
    """
    registry = list(skills) if skills is not None else discover_skills(skills_dir)
    idf = build_idf(registry)
    ranked = [
        (skill, score_skill(query, skill, idf)) for skill in registry
    ]
    ranked = [pair for pair in ranked if pair[1] > 0]
    ranked.sort(key=lambda pair: (-pair[1], pair[0].name))
    return ranked[:top] if top is not None else ranked
