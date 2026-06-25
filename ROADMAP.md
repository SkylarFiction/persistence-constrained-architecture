# Build Roadmap

## Phase 1: Evidence-Bearing Continuity

- Create an identity manifest schema.
- Create a hash-chained continuity ledger.
- Classify identity as continuous, degraded, forked, suspended, or broken.
- Add a CLI for local experiments.

Status: initial slice implemented.

## Phase 2: Persistence Policy Engine

- Add policy files for memory, commitments, lineage, permissions, and embodiment.
- Distinguish hard invariants from soft degradation thresholds.
- Add explicit transform validation for migration, compaction, recovery, and fork.

Status: transform policy slice implemented with decision explanations, identity
risk levels, and denial paths; dedicated domain policy files still next.

## Phase 2A: Policy Packs

- Add modular policy packs for memory, substrate, lineage, authorization, and recovery.
- Load individual packs or policy directories from the CLI.
- Merge packs conservatively when rules overlap.
- Preserve denial for unknown transforms.

Status: initial pack loader and starter packs implemented.

## Phase 2B: Authorization Model

- Add authority classes: observer, operator, steward, recovery authority, root authority.
- Load authorization thresholds from the authorization policy pack.
- Enforce override authority.
- Enforce follow-up completion and failure authority.

Status: implemented for override, complete-followup, and fail-followup.

## Phase 2C: Authorization Audit Trail

- Record allowed and denied authorization checks as ledger events.
- Include actor authority, parsed authority, required authority, action, decision,
  and reason.
- Ensure denied identity-changing actions are still visible in the ledger.

Status: implemented for override, complete-followup, and fail-followup.

## Phase 3: Recovery Protocols

- Define reconstitution rules after suspended or degraded states.
- Add repair events and evidence requirements.
- Require declared recovery instead of silent restoration.

Status: initial staged recovery path implemented.

## Phase 3A: Lineage and Fork Governance

- Create lineage records from declared forks.
- Require parent-child identity relation evidence.
- Add merge and rejoin semantics only if continuity evidence supports them.

Status: fork lineage records implemented; merge/rejoin not started.

## Phase 3B: Override Governance

- Allow emergency override records.
- Preserve original policy decision.
- Permit operation without certifying continuity.
- Require follow-up audits such as post-transform identity audit and lineage freeze.

Status: implemented for transform decisions.

## Phase 3C: Follow-Up Enforcement

- Create follow-up records from override governance.
- Query follow-ups by status.
- Complete follow-ups with required evidence.
- Fail follow-ups with a reason.
- Constrain the current continuity claim while follow-ups remain active.

Status: implemented for open, completed, overdue, and failed follow-up states.
Waiver and authority-gated resolution are intentionally not started yet.

## Phase 3D: Post-Transform Audits

- Create post-transform audit records.
- Support memory compaction, substrate migration, fork, and version update audits.
- Resolve linked follow-up obligations based on audit outcomes.
- Certify continuity only when all blocking obligations are satisfied.

Status: deterministic evidence-based audits implemented.

## Phase 3E: Continuity Claim Registry

- Record continuity claim changes as first-class ledger events.
- Track source events, active blockers, reasons, and superseded claim IDs.
- Expose current and historical claims through the CLI.
- Prevent manual claim setting.

Status: implemented for state-changing CLI flows.

## Phase 3G: Staged Recovery

- Add recovery records.
- Require recovery authority to open recovery paths.
- Create recovery audit follow-ups.
- Certify recovery records without automatically restoring certified continuity.

Status: implemented for open recovery, recovery status, and recovery audit completion.

## Phase 3F: Ledger File Locking

- Protect ledger append operations with an exclusive file lock.
- Add an append batch helper for ordered multi-event writes.
- Verify concurrent writers preserve the hash chain.

Status: implemented with POSIX file locking and concurrent smoke coverage.

## Hardening Backlog

- Expand CLI flows to use batch append where grouped event atomicity matters.

## Phase 4A: Output Gate

- Map continuity claims to allowed speech modes.
- Expose gate decisions through the CLI.
- Include output gate status in `status`.

Status: initial output gate implemented.

## Phase 4: Agent Runtime Integration

- Adapt the existing `lucien_csm_ready_project` monitor into this architecture.
- Connect RTI, strain, schema validity, tool retries, and latency to continuity events.
- Add an output gate that refuses unbroken identity claims after hard breach.

Status: initial runtime adapter and CSM bridge implemented. `PCAIdentityRuntime`
records CSM-style GREEN, AMBER, and RED signals, maps AMBER to review disclosure,
maps RED to a hard continuity break, and exposes the result through `runtime-signal`.
`CSMRuntimeBridge` can ingest monitor step results and wrap Lucien-style audit
loggers so hard-kill payloads become PCA continuity evidence before the monitor
raises.

## Phase 4B: Runtime Output Wrapper

- Apply the output gate to generated text before it leaves the agent.
- Record outbound decisions as ledger events without storing full text.
- Preserve disclosure and block behavior based on the current continuity claim.

Status: initial wrapper implemented with CLI support through `gate-output`.

## Phase 5: Dashboard and Experiments

- Build a persistence dashboard.
- Add simulations for memory loss, fork, compaction, migration, and recovery.
- Produce report artifacts from ledger traces.

Status: initial trace report and standalone dashboard implemented. `trace-report`
returns structured JSON and can write a lifecycle report. `dashboard` writes a
local HTML dashboard with current posture, claim path, runtime signals, output-gate
events, and a filterable governance timeline.

## Phase 5A: Scenario Simulations

- Add canned lifecycle scenarios for memory compaction review, substrate migration
  override, CSM AMBER degradation, CSM RED continuity break, recovery opened,
  recovery audit completed, and declared fork.
- Generate real ledger entries, output-gate events, trace reports, dashboards, and
  result summaries.
- Prove CSM RED signal and hard breach are recorded adjacently under the ledger lock
  before outbound output is gated.

Status: scenario runner and regression verification implemented with
`python3 -m pca.scenario_runner`. `verify` and `verify-all` enforce expected
governance behavior. `demo` writes `scenario_runs/index.html`, linking all scenario
dashboards, traces, and results.

`scripts/regression_check.py` runs all scenario verification laws and regenerates
the demo index as a compact project-level regression check.

`scripts/check_all.py` is the canonical local health check. It runs compilation,
smoke checks, scenario regression verification, and demo index generation.
