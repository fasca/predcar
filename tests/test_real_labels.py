"""Regression net over the real labels of the committed evidence bundle.

The bundle's ``silver/labels_target_makes.csv`` is the exhaustive list of raw make/model
labels the sources actually contain. These tests replay the **current** mapping rules over
all of them, in CI, without network access.

The bundle's own ``model_gen`` / ``generation`` columns are never used as an oracle: they
were produced by the rules of the day it was exported. Only ``model_raw`` is read.

The ``count`` column sums a label over every period, so it is a volume indicator, never a
stock — stocks come from ``gold/indicators.csv``.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

import polars as pl
import pytest

from predcar import normalize as n
from predcar.config import load_mapping_config
from predcar.paths import MAPPING_DIR

MIN_LABELS = 10_000

# Targets that no real label reaches today, with the reason. Keep this list short and
# documented: a target that silently becomes unreachable is a rule bug.
UNREACHABLE_TARGETS = {
    ("FORD", "RACING PUMA"),  # no distinct DfT/RDW label, folded into PUMA by the sources
}


class KeywordRule(NamedTuple):
    """One expectation over every real label of ``make`` matching ``label_regex``."""

    make: str
    label_regex: str
    kind: Literal["equals", "not_equals"]
    model_gen: str


# Every entry below encodes a bug that actually reached production (tasks/lessons.md):
# a trim level swallowed by a sport-version rule, or a sport version missed because of a
# separator. Each is checked against *all* matching real labels, not hand-picked examples.
KEYWORD_RULES = (
    KeywordRule("FORD", r"\bST[- ]?LINE\b", "not_equals", "FIESTA ST"),
    KeywordRule("FORD", r"\bST[- ]?LINE\b", "not_equals", "FOCUS ST"),
    KeywordRule("HONDA", r"^CIVIC\b.*\bTYPE[- ]?R\b", "equals", "CIVIC TYPE R"),
    KeywordRule("HONDA", r"^CIVIC\b(?!.*TYPE[- ]?R\b)", "not_equals", "CIVIC TYPE R"),
    KeywordRule("RENAULT", r"^CLIO (S )?16 ?V\b(?!.*WILLIAMS)", "equals", "CLIO 16V"),
    KeywordRule(
        "RENAULT",
        r"^CLIO\b(?! (S )?16 ?V\b)(?!.*WILLIAMS).*16 ?V\b",
        "not_equals",
        "CLIO 16V",
    ),
    KeywordRule("CITROEN", r"^SAXO\b.*\bVTR\b", "not_equals", "SAXO VTS"),
    KeywordRule("PEUGEOT", r"^306\b.*\bXSI\b", "not_equals", "306 S16"),
    KeywordRule("MITSUBISHI", r"^LANCER\b.*\bEVO(LUTION)?\b", "equals", "LANCER EVOLUTION"),
)


def test_evidence_bundle_is_present(real_labels: pl.DataFrame) -> None:
    """Guard: one clear failure instead of many obscure ones when the bundle is missing."""
    assert real_labels.height >= MIN_LABELS
    assert {"make_raw", "model_raw"} <= set(real_labels.columns)


def test_repo_rules_resolve_every_real_label_without_conflict(
    real_labels_mapped: pl.DataFrame,
) -> None:
    """No MappingError over the whole real label universe.

    ``real_labels_mapped`` calls ``normalize.apply``, which raises on conflicting rules;
    reaching this assertion already proves there is none.
    """
    assert real_labels_mapped.height > 0
    assert real_labels_mapped["model_gen"].is_not_null().any()


def test_real_coverage_stays_above_the_gate(
    real_labels: pl.DataFrame, real_labels_mapped: pl.DataFrame
) -> None:
    """Replay the production coverage gate on the real per-label volumes."""
    unknown = [u.upper() for u in load_mapping_config(None).unknown_labels]
    joined = real_labels.select(
        "country", "make_raw", "model_raw", pl.col("count").cast(pl.Int64)
    ).join(real_labels_mapped, on=["make_raw", "model_raw"], how="left")
    known = joined.filter(~pl.col("model_raw").str.to_uppercase().is_in(unknown))
    for country, group in known.group_by("country"):
        total = group["count"].sum()
        mapped = group.filter(pl.col("model_gen").is_not_null())["count"].sum()
        assert mapped / total >= 0.95, f"{country[0]}: coverage {mapped / total:.4f} below the gate"


def test_every_target_is_reachable_from_a_real_label(real_labels_mapped: pl.DataFrame) -> None:
    """A target no real label resolves to is a dead rule."""
    targets = {(t.make, t.model_gen) for t in n.load_targets(MAPPING_DIR / "target_models.csv")}
    reached = set(
        real_labels_mapped.filter(pl.col("model_gen").is_not_null())
        .select("make", "model_gen")
        .unique()
        .iter_rows()
    )
    missing = targets - reached - UNREACHABLE_TARGETS
    assert not missing, f"targets unreachable from any real label: {sorted(missing)}"
    stale = UNREACHABLE_TARGETS & reached
    assert not stale, (
        f"UNREACHABLE_TARGETS is out of date, these are reachable now: {sorted(stale)}"
    )


@pytest.mark.parametrize("rule", KEYWORD_RULES, ids=lambda r: f"{r.make}-{r.model_gen}-{r.kind}")
def test_version_keywords_never_swallow_trim_labels(
    rule: KeywordRule, real_labels_mapped: pl.DataFrame
) -> None:
    """A trim level must not land on a sport version, and vice versa.

    Does not cover the build-year vs first-registration-year bug: this file has no year
    column. See ``test_witnesses.py::test_generation_uses_build_year``.
    """
    pattern = re.compile(rule.label_regex, re.I)
    matching = real_labels_mapped.filter(
        (pl.col("make") == rule.make)
        & pl.col("model_raw").map_elements(
            lambda s: bool(pattern.search(s)), return_dtype=pl.Boolean
        )
    )
    assert matching.height > 0, f"no real label matches {rule.label_regex!r} for {rule.make}"
    got = matching.filter(pl.col("model_gen") == rule.model_gen)
    if rule.kind == "equals":
        offenders = matching.filter(
            (pl.col("model_gen") != rule.model_gen) | pl.col("model_gen").is_null()
        )
        assert offenders.is_empty(), (
            f"{offenders.height} labels should be {rule.model_gen}: "
            f"{offenders['model_raw'].head(5).to_list()}"
        )
    else:
        assert got.is_empty(), (
            f"{got.height} labels wrongly mapped to {rule.model_gen}: "
            f"{got['model_raw'].head(5).to_list()}"
        )
