"""What the seeder will and will not put on the Volume.

The seed is a directory on someone's laptop, so it collects what laptops leave
lying around. The tier it uploads to is one the agent lists and searches, and
the agent cannot tell an artefact from a document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_wiki import is_document


@pytest.mark.parametrize(
    "path",
    [
        "index.md",
        "policies/resolution-targets.md",
        "policies/SOP-Layanan-IT.docx",
    ],
)
def test_documents_are_uploaded(path):
    assert is_document(Path(path)) is True


@pytest.mark.parametrize(
    "path",
    [
        ".DS_Store",                 # macOS, the one that actually reached the Volume
        "policies/.DS_Store",        # and at any depth
        ".obsidian/workspace.json",  # a hidden directory, not just a hidden file
        "policies/.gitkeep",
    ],
)
def test_hidden_files_are_skipped(path):
    assert is_document(Path(path)) is False


def test_a_dot_inside_a_name_is_not_a_hidden_file():
    """`.DS_Store` is hidden because the *name* starts with a dot, not because
    the path contains one — a document with a dotted name must still upload."""
    assert is_document(Path("policies/v1.2-targets.md")) is True
