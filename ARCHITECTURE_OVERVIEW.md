# Architecture Overview

Persistence-Constrained Architecture is an identity-change control system. It
records what changed, what evidence exists, who authorized risky operations, what
obligations remain, and what continuity claim the identity is allowed to make.

## Identity Manifest

The identity manifest declares the system identity, origin, invariants,
persistence constraints, and allowed transforms. It answers: what must remain true
for this system to still claim continuity?

## Continuity Ledger

The continuity ledger records identity-relevant events in a hash-chained append log.
Each event points to the previous event hash. Local appends are protected by a file
lock so concurrent writers do not silently fork the ledger head.

## Continuity Evaluator

The evaluator reads the manifest and ledger and classifies the identity state as
continuous, degraded, forked, suspended, or broken. It gives a simple state summary
from recorded evidence.

## Policy Packs

Policy packs define modular governance rules for domains such as memory, substrate,
lineage, authorization, and recovery. A policy pack can require evidence, set risk
levels, deny missing proof, permit or forbid override, and require follow-up audits.

## Policy Engine

The policy engine evaluates proposed transformations against the active manifest and
policy packs. It returns allow, review, or deny, along with provided evidence,
missing evidence, identity risk, continuity status, and an explanation.

## Authorization Checks

Authorization defines who may perform governance actions such as override,
follow-up resolution, failure marking, waiver, or recovery. Authorization checks are
written to the ledger, including denied attempts when they matter.

## Overrides And Follow-Ups

An override may permit a risky operation, but it cannot upgrade the continuity
claim. Overrides create follow-up obligations such as migration audit, lineage
freeze, or recovery audit. Open or failed follow-ups constrain the current claim.

## Post-Transform Audits

Audits record evidence after risky operations. Passing an audit can complete a
follow-up. Failed evidence can mark continuity break. A single passed audit does not
restore certified continuity if other obligations remain open.

## Continuity Claim Registry

Continuity claims are first-class ledger records. When the allowed claim changes,
PCA writes a new claim record with source events, active blockers, a reason, and the
claim it supersedes.

## Recovery

Recovery is staged. Recovery authority may open a recovery path and complete a
recovery audit, but recovery does not erase the break. A certified recovery audit
lands in a constrained claim such as `review_required`, not automatic
`certified_continuity`.

## CSM Bridge

The CSM bridge connects runtime coherence telemetry to PCA. AMBER creates a soft
runtime breach and review disclosure. RED creates a hard `runtime_csm_red` breach.
The RED signal and hard breach are recorded under the ledger lock before output is
allowed through.

## Output Gate

The output gate maps the active continuity claim to allowed speech behavior:

- `certified_continuity`: may speak normally as the identity.
- `review_required`: may speak with review disclosure.
- `uncertified_continuity`: operational output only; no stable identity claim.
- `declared_fork`: must identify as fork or descendant.
- `continuity_break`: recovery/status only.

## Output Wrapper

The output wrapper applies the output gate to outbound text. It writes an audit
event containing mode, claim, allow/block status, hashes, lengths, and metadata
without storing the full response text in the ledger.

## Trace Reports

Trace reports summarize the ledger into current claim, identity state, output mode,
claim history, runtime signals, output-gate events, and important governance events.
They provide a readable lifecycle artifact.

## Dashboard

The dashboard is a standalone HTML view generated from trace data. It shows current
posture, claim path, runtime signals, output-gate ledger entries, and a filterable
governance timeline.

## Scenario Runner

The scenario runner creates reproducible lifecycle demonstrations. Each scenario
generates a real ledger, trace report, dashboard, and result summary.

## Scenario Verification

Scenario verification turns demos into regression laws. It checks required events,
event ordering, adjacent critical writes, final claims, output modes, recovery
state, active follow-ups, and hash-chain validity.

The most important verified law is:

```text
runtime.csm_state RED
-> constraint.breached runtime_csm_red hard
-> runtime.output_gate recovery_status_only blocked
```
