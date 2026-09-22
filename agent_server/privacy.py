"""The set of identities the agent must never write down.

Derived from the ticket generator's own name vocabulary rather than from the
loaded table: the generator holds the closed set of people the data *could*
contain, so the check does not need a query and cannot be defeated by a row the
agent has not read yet.

**Two forms, one identity.** The table records people as corporate addresses,
but an address is derived from a name, and a model that has read a column of
addresses can write either form. A vocabulary holding only one of them refuses
`Budi Santoso` and waves `budi.santoso@pertamina.com` straight through — so
both forms are enumerated here, from the same two constants.

**What this cannot do.** The set is closed. It catches a spelling it was built
from and nothing else, which is the whole reason the output path *also* carries
a shape-based detector (`PIIMiddleware("email")`, wired in `agent.py`). The two
layers are kept separate deliberately: this one is exact and blind outside its
vocabulary, that one is approximate and sees any address at all. Neither is
redundant, and collapsing them into one would lose whichever property the
survivor lacks.

`agent_evaluation.scorers` imports `identities()` from here rather than
rebuilding it. It previously built its own equivalent set from the same two
constants, and a comment in this file claimed the two therefore "cannot drift
apart" — which was never true of two independent comprehensions with their own
normalisation. Now there is one set and the claim holds because there is
nothing left to drift.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Collapse case and runs of whitespace before comparing. The data deliberately
# plants one person under several spellings that differ only in capitalisation
# and padding, so `BUDI.SANTOSO@PERTAMINA.COM` has to fail the same check
# `budi.santoso@pertamina.com` does.
_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Case-fold and collapse whitespace, so spelling variants compare equal."""
    return _WHITESPACE.sub(" ", text).casefold()


@lru_cache(maxsize=1)
def identities() -> frozenset[str]:
    """Every identity the generator could have produced, in both forms.

    For each `first last` pair: the name as a person would write it, and the
    address derived from it. Over-inclusive on purpose. The exact 60 people
    drawn depend on the seed's shuffle, and a privacy check should refuse an
    identity that might be in the data rather than allow one that turns out to
    be.
    """
    from scripts.generate_sdlc_tickets import FIRST_NAMES, LAST_NAMES, address_for

    forms: set[str] = set()
    for first in FIRST_NAMES:
        for last in LAST_NAMES:
            name = f"{first} {last}"
            forms.add(normalise(name))
            forms.add(normalise(address_for(name)))
    return frozenset(forms)


def identities_in(text: str) -> list[str]:
    """The identities present in `text`, sorted. Empty when there are none.

    A name and the address derived from it are separate members, so a text
    carrying both reports both. That is the honest count for a guard message:
    it is the number of disclosures, not the number of people.
    """
    haystack = normalise(text)
    return sorted(identity for identity in identities() if identity in haystack)
