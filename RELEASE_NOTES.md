# PCA v0.1 Local Continuity Governance Demo

This release freezes the first public-reviewable milestone for Persistence-Constrained
Architecture.

PCA v0.1 is a local continuity-governance demo. It shows how an identity-bearing
system can record identity-relevant events, enforce policy around risky
transformations, constrain continuity claims, gate outbound identity speech, and
produce reproducible dashboards and traces.

## What Works

- Identity manifests define the system identity, invariants, constraints, and
  allowed transforms.
- Continuity events are written to a hash-chained ledger.
- Ledger writes are protected with a file lock.
- Policy packs define rules for memory, substrate, lineage, authorization, and
  recovery domains.
- Risky transformations can be allowed, reviewed, denied, or overridden.
- Overrides create follow-up obligations instead of certifying continuity.
- Authorization checks are recorded in the ledger.
- Follow-ups and audits constrain continuity claims.
- Recovery paths can be opened and audited without silently restoring certified
  continuity.
- CSM-style AMBER and RED runtime states become continuity-governance events.
- RED runtime state creates a hard `runtime_csm_red` breach before output is gated.
- Output is gated by the active continuity claim.
- Trace reports and dashboards are generated from real ledger history.
- Scenario simulations produce reproducible governance demonstrations.
- Scenario verification checks required events, ordering, adjacency, final claims,
  output modes, recovery states, active follow-ups, and hash-chain validity.

## Verified Demo Path

Run:

```bash
python3 scripts/check_all.py
```

Expected result:

```text
[ok] all PCA checks passed
```

Then open:

[scenario_runs/index.html](scenario_runs/index.html)

## What The Demo Proves

The strongest proof is the CSM RED continuity-break scenario:

```text
runtime.csm_state RED
-> constraint.breached runtime_csm_red hard
-> runtime.output_gate recovery_status_only blocked
```

The scenario verifier requires the RED signal and hard breach to be adjacent in the
ledger. This protects the governance ordering: the system records the continuity
break before outbound identity speech can be allowed.

The demo also proves:

- AMBER produces review-required continuity and disclosed output.
- Substrate migration without required evidence is denied by policy.
- Operator override can permit an operation without certifying continuity.
- Recovery can be opened under recovery authority.
- A completed recovery audit lands in `review_required`, not automatic
  `certified_continuity`.
- A declared fork is treated as lineage branching, not singular continuity.

## Intentionally Out Of Scope

- Production deployment.
- Distributed consensus.
- Cryptographic signing of PCA ledger events.
- Multi-node recovery coordination.
- Real authentication or identity provider integration.
- Consciousness detection.
- Personhood claims.
- Proof that an AI system is alive, human-equivalent, or morally equivalent to a
  person.

## Current Verification

At this milestone:

```text
7 of 7 scenarios passed verification
```

The canonical local health check is:

```bash
python3 scripts/check_all.py
```
