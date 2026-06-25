# Known Limits

PCA v0.1 is a local continuity-governance demo. It is intentionally small,
inspectable, and honest about what it does not yet provide.

## Local Only

PCA currently runs as a local Python project. It writes local ledger files and local
HTML artifacts. It is not yet a networked service or distributed governance system.

## Not A Production Security Boundary

The file lock protects local concurrent ledger writes, but PCA v0.1 should not be
treated as a production security boundary. It does not yet provide hardened process
isolation, access control, external authentication, tamper-resistant storage, or
distributed consensus.

## Hash Chain Is Locally Verifiable Only

The ledger hash chain detects truncation, reordering, accidental corruption, and
inconsistent appends by non-coordinated local writers. It does not stop a writer with
filesystem access from rewriting the entire log and recomputing hashes. Stronger
tamper evidence requires a head hash anchored outside the writer's control, such as
signed heads, periodic notarization, append-only storage, or WORM media.

## Not Distributed Consensus

The ledger is hash-chained and file-locked, but it is not replicated across nodes.
There is no quorum, Byzantine fault tolerance, distributed clock model, or
cross-machine conflict resolution yet.

## Not A Consciousness Detector

PCA does not determine whether a system is conscious. It governs whether claimed
continuity through change is supported by recorded evidence, policy, authorization,
audits, and recovery status.

## Not Proof Of Personhood

PCA does not establish personhood, rights, moral status, or human equivalence. It is
an identity-change control system, not a legal or metaphysical status engine.

## Demo Scenarios Are Canned But Reproducible

The scenarios are scripted demonstrations. They are not random simulations and do
not cover every possible lifecycle. They are valuable because they generate real
ledger entries, reports, dashboards, and regression checks from reproducible flows.

## CSM Integration Is A Bridge

The CSM bridge accepts Lucien-style CSM monitor outputs and hard-kill payloads. It
does not yet replace a full production runtime monitor, telemetry pipeline, or
incident response system.
PCA v0.1 does not compute RTI thresholds itself. It records the CSM verdict and
enforces the continuity-governance consequences of that verdict.

## Output Gating Is Text-Level

The output wrapper gates outbound text and records privacy-conscious audit metadata.
It does not yet integrate with every possible runtime, tool call, streaming token
path, UI channel, or external API boundary.

## Policy Packs Are Starter Packs

The current policy packs cover memory, substrate, lineage, authorization, and
recovery starter rules. They are not comprehensive governance law. They are meant to
be expanded carefully as the architecture matures.

## Pytest Requires Installation

The environment used for this milestone does not have `pytest` installed. The
project includes test files, but the verified local health path is currently:

```bash
python3 scripts/check_all.py
```

That command runs compilation, smoke checks, scenario regression verification, and
demo index generation without requiring `pytest`.
