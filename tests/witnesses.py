"""The five control models of SPEC §8, with the bounds their real values must stay within.

Bounds are deliberately wide (roughly ×5 / ÷5 around the reference run of 2026-09-12): a
quarterly DfT release or a monthly RDW snapshot moves a stock by a few percent, while the
bugs these tests exist for moved it by orders of magnitude (Civic Type R EP3 counted as
2 vehicles instead of 4 139).
"""

from __future__ import annotations

from typing import NamedTuple


class Witness(NamedTuple):
    """One control model and what must hold for it."""

    make: str
    model_gen: str
    generation: str
    segment: str
    build_year: int  # a year inside the production window, used to place a row
    # What the rules return for a 2018 first registration with no build year. Differs from
    # ``generation`` only when the witness is resolved by year range (BMW M3); the other four
    # carry their generation in the label itself, so they are immune by construction.
    generation_without_build_year: str
    sample_labels: tuple[str, ...]  # real labels seen in the evidence bundle
    forbidden_labels: tuple[str, ...]  # real labels of the same make that must map elsewhere
    gb_stock: tuple[int, int]
    nl_stock: tuple[int, int]


WITNESSES = (
    Witness(
        make="BMW",
        model_gen="M3",
        generation="E46",
        segment="SPORTIVE",
        build_year=2003,
        generation_without_build_year="F80",
        sample_labels=("M3", "M3 SMG", "M3 CSL", "M3 CONVERTIBLE"),
        forbidden_labels=("320D SE", "M340I XDRIVE AUTO"),
        gb_stock=(800, 25_000),
        nl_stock=(100, 6_000),
    ),
    Witness(
        make="PEUGEOT",
        model_gen="205 GTI",
        generation="MK1",
        segment="GTI",
        build_year=1990,
        generation_without_build_year="MK1",
        sample_labels=("205 GTI", "205 GTI 1.9", "205 CTI", "205 RALLYE"),
        forbidden_labels=("205 XS", "205 JUNIOR"),
        gb_stock=(200, 8_000),
        nl_stock=(100, 6_000),
    ),
    Witness(
        make="HONDA",
        model_gen="S2000",
        generation="AP1_AP2",
        segment="ROADSTER",
        build_year=2003,
        generation_without_build_year="AP1_AP2",
        sample_labels=("S2000", "S 2000", "S2000 GT"),
        forbidden_labels=("CIVIC TYPE-R", "ACCORD TYPE R"),
        gb_stock=(600, 15_000),
        nl_stock=(100, 6_000),
    ),
    Witness(
        make="RENAULT",
        model_gen="CLIO WILLIAMS",
        generation="MK1",
        segment="GTI",
        build_year=1994,
        generation_without_build_year="MK1",
        sample_labels=("CLIO WILLIAMS", "CLIO 16V WILLIAMS"),
        forbidden_labels=("CLIO DYNAMIQUE 16V", "CLIO 16V"),
        gb_stock=(20, 1_500),
        nl_stock=(10, 1_000),
    ),
    Witness(
        make="AUDI",
        model_gen="RS2",
        generation="B4",
        segment="SPORTIVE",
        build_year=1995,
        generation_without_build_year="B4",
        sample_labels=("RS2", "RS2 AVANT"),
        forbidden_labels=("A2 SE", "RS4 AVANT"),
        gb_stock=(3, 400),
        nl_stock=(1, 200),
    ),
)


def witness_id(w: Witness) -> str:
    return f"{w.make}-{w.model_gen}-{w.generation}".replace(" ", "_")
