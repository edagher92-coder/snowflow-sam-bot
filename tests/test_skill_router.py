"""Portable tests for the vendored ``skill_router`` package.

Repo-agnostic by design: routing behaviour is exercised against synthetic
skills in ``tmp_path``, plus one sanity check that this repo's own registry
includes the ``skill-router`` skill itself. The source of truth for the
package lives in the Snow Flow monorepo (edagher92-coder/Claude-code-,
``src/skill_router/``) — fix bugs there first, then re-copy.
"""

import json
from pathlib import Path

from skill_router import (
    Skill,
    build_index,
    discover_skills,
    parse_skill_md,
    route,
    score_skill,
)


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: |\n  {description}\n---\n# {name}\n",
        encoding="utf-8",
    )


def test_own_registry_includes_skill_router():
    # The vendored router must at minimum discover its own SKILL.md wrapper.
    assert "skill-router" in {s.name for s in discover_skills()}


def test_parse_extracts_name_category_and_triggers():
    skill = parse_skill_md(
        """---
name: demo-skill
description: |
  [REVIEW] Audit a thing for correctness.
  Use when the user says "check this", "audit the thing".
---
# Demo
"""
    )
    assert skill is not None
    assert skill.name == "demo-skill"
    assert skill.category == "REVIEW"
    assert skill.summary == "Audit a thing for correctness"
    assert skill.triggers == ("check this", "audit the thing")


def test_parse_returns_none_without_frontmatter():
    assert parse_skill_md("# Just a heading, no frontmatter") is None


def test_any_domain_skill_registers_and_routes(tmp_path: Path):
    _write_skill(
        tmp_path,
        "deploy-rollback",
        '[DEVOPS] Roll back a bad production deploy. '
        'Use when the user says "rollback the deploy", "revert production".',
    )
    registered = discover_skills(tmp_path)
    assert [s.name for s in registered] == ["deploy-rollback"]

    matches = route("please rollback the deploy", skills_dir=tmp_path)
    assert matches[0][0].name == "deploy-rollback"


def test_route_scores_are_descending(tmp_path: Path):
    _write_skill(
        tmp_path,
        "invoice-chaser",
        '[FINANCE] Chase overdue invoices. '
        'Use when the user says "chase overdue invoices".',
    )
    _write_skill(
        tmp_path,
        "post-drafter",
        '[CONTENT] Draft a social post. '
        'Use when the user says "draft a post about invoices".',
    )
    matches = route("chase the overdue invoices", skills_dir=tmp_path)
    scores = [score for _, score in matches]
    assert matches[0][0].name == "invoice-chaser"
    assert scores == sorted(scores, reverse=True)
    assert all(score > 0 for score in scores)


def test_empty_query_scores_zero():
    skill = Skill(name="x", category="OPS", summary="s", triggers=("a",))
    assert score_skill("", skill) == 0.0


def test_missing_skills_dir_degrades_to_empty_registry(tmp_path: Path):
    assert discover_skills(tmp_path / "does-not-exist") == []


def test_build_index_covers_registered_skills(tmp_path: Path):
    _write_skill(
        tmp_path,
        "deploy-rollback",
        '[DEVOPS] Roll back a bad deploy. Use when the user says "rollback".',
    )
    index = build_index(tmp_path)
    assert index.startswith("# Skills index (auto-generated)")
    assert "/deploy-rollback" in index


def test_skill_as_dict_is_json_serialisable():
    skill = Skill(name="x", category="OPS", summary="s", triggers=("a", "b"))
    assert json.loads(json.dumps(skill.as_dict()))["name"] == "x"
