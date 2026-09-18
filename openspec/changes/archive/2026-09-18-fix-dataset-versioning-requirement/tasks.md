## 1. Amend the requirement

- [x] 1.1 Replace the *Expectations are versioned against system capability* requirement with the delta's version; verify the other seven requirements in `agent-evaluation` and the spec's Purpose are untouched
- [x] 1.2 Verify the amended requirement is satisfiable by the implementation as it stands — the version is recorded in `DATASET_DESCRIPTION` and in the run name, and no code change is needed to conform

## 2. Confirm the capability is self-consistent

- [x] 2.1 Verify no requirement in `agent-evaluation` now demands a versioned dataset identity, so the capability no longer contradicts the platform it runs on
- [x] 2.2 Verify the immutability consequence appears in the requirement itself rather than only in `agent_evaluation/dataset.py`, so someone quoting a superseded score meets it in the spec
- [x] 2.3 Run `openspec validate --specs --strict` and confirm `agent-evaluation` passes with 8 requirements
