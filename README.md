# Persistence-Constrained Architecture

This project is the working implementation of a persistence-constrained architecture
for identity-bearing systems.

For a guided public walkthrough, see [PUBLIC_DEMO.md](PUBLIC_DEMO.md).
For milestone details, see [RELEASE_NOTES.md](RELEASE_NOTES.md).
For honest constraints, see [KNOWN_LIMITS.md](KNOWN_LIMITS.md).
For a system map, see [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md).

The core claim is simple: an identity-bearing system is not preserved by name alone.
It remains itself only while its declared invariants, memories, commitments, and
transformation rules remain within admissible bounds.

PCA is not an AI personality framework. It is an identity-change control system.
Any system that claims continuity through change must be able to prove what was
preserved, what was altered, what was lost, and who authorized the transformation.
PCA does not treat governance decisions as one-time events. High-risk identity
transformations create continuing obligations. Until those obligations are completed,
failed, or formally resolved, the system's continuity claim remains constrained.
Post-transform audits are how PCA converts unresolved identity risk into an explicit
continuity claim. They do not assume that a risky transformation preserved identity.
They require evidence after the transformation and update the claim only when the
remaining obligations are satisfied.
PCA does not merely compute a continuity state. It records what continuity claim an
identity is allowed to make, why that claim is allowed, what evidence supports it,
and what prior claim it supersedes.
Policy Packs make PCA modular. Each pack defines the evidence, risk, denial rules,
follow-up obligations, and audit expectations for one identity-risk domain. Missing
policy does not mean permission. Missing policy means denial. Malformed policy is
also fail-closed: bad packs are carried as policy errors on the active manifest, and
identity-changing transforms are denied until the policy set is repaired.

In v0.1, PCA does not compute every persistence metric internally. Runtime measures
such as RTI are treated as monitor outputs from an external CSM-style classifier.
PCA records those verdicts, locks them into the ledger, and governs their
consequences for continuity claims and output behavior. In other words, this build
enforces the governance response to a trusted persistence verdict; it is not yet the
full monitor that computes the persistence inequality itself.

`deny` means the requested transformation is not authorized as presented. It does
not automatically mean identity continuity is broken. Missing evidence can leave the
identity `uncertified_continuity`; hard breaches and failed critical obligations are
what move the claim to `continuity_break`.

## First Build Slice

- `IdentityManifest`: declares what must persist for a system to remain itself.
  Required constraints may define `freshness_seconds`, which means old evidence can
  expire instead of counting forever.
- `ContinuityLedger`: records identity-relevant events in a hash-chained log.
  Ledger appends are protected by a file lock so concurrent writers do not silently
  fork the hash chain.
- `LedgerAnchorRecord`: exports the current ledger head into a separate hash-chained
  anchor log so later verification can detect drift from the anchored head.
- `AnchorExport`: writes a portable JSON checkpoint containing the latest anchor
  verification and export hash for review packets or external notarization.
- `ContinuityEvaluator`: classifies the current identity state from ledger evidence,
  including stale required evidence checks when freshness windows are declared.
- `PolicyEngine`: evaluates whether identity-relevant transforms are admissible.
- `PolicyPack`: defines modular governance rules for memory, substrate, lineage,
  authorization, and recovery domains.
- `AuthorizationPolicy`: defines authority classes and minimum permissions for
  overrides and follow-up resolution.
- `AuthorizationCheckRecord`: records allowed and denied authority checks for
  identity-changing actions.
- `RecoveryRecord`: opens staged recovery paths after uncertified or broken
  continuity without silently restoring certification.
- `OutputGate`: maps continuity claims to allowed identity-speech modes.
- `PCAIdentityRuntime`: gives agent runtimes a small adapter for recording CSM-style
  signals and checking whether output may speak as the identity.
- `LucienGovernedRuntime`: records Lucien turns as privacy-conscious input, memory,
  tool, CSM, and output-gate events so a running Lucien-style loop can be governed by
  PCA.
- `GrowthRecord`: lets Lucien propose, accept, reject, or review learned memories,
  commitments, skills, preferences, policies, and identity-impacting changes without
  storing raw learned text in the ledger.
- `GrowthGate`: constrains growth by current continuity claim, so broken or
  uncertified continuity cannot silently absorb identity-bearing learning.
- `GrowthReviewRecord`: records human/operator review of pending growth, including
  accept/reject decision, reviewer, continuity claim, and resulting growth status.
- `GrowthConflictRecord`: records when proposed growth may conflict with accepted
  commitments, policies, or identity markers.
- `GrowthConflictResolutionRecord`: records steward decisions to accept new growth,
  keep existing growth, or fork when a conflict is resolved.
- `SelfModel`: derives Lucien's accepted memories, commitments, skills,
  preferences, policies, and identity-impacting changes from accepted growth
  records.
- `SelfModelCompiler`: renders accepted growth into an evidence-linked review
  artifact without inventing raw memory prose.
- `MemoryCard`: derives accepted memory growth into inspectable cards with source
  growth id, summary hash, evidence refs, confidence, signal-adjusted effective
  confidence, and acceptance context.
- `MemorySignalRecord`: records reinforcement, contradiction, or staleness signals
  against memory cards so learned memory can strengthen or weaken through evidence.
- `EvidenceLocker`: stores evidence items, reviews, claims, and links so memories,
  missions, skills, and conclusions can cite governed sources instead of loose
  references.
- `ContextBuilder`: assembles the bounded working context Lucien may use before
  answering, including continuity state, accepted memory, evidence review states,
  mission state, skill suggestions, open governance tasks, and warnings.
- `ReflectionRecord`: records Lucien's own maintenance agenda by inspecting
  continuity state, pending growth, conflicts, and memory confidence pressure.
- `ReflectionTaskRecord`: turns reflection recommendations into ledger-backed
  steward queue items such as growth review, conflict resolution, memory audit,
  and recovery opening.
- `Lucien Constitution`: generates a human-readable charter from the current
  ledger-backed identity state, accepted commitments, policies, tasks, and latest
  reflection.
- `ChatSessionRecord`: records chat session start, turn, and close lifecycle events
  without storing raw conversation text.
- `LucienCockpit`: renders a focused operational view of continuity, sessions,
  memory cards, growth queue, and accepted self-model state.
- `LucienChatShell`: a tiny persistent conversational shell that loads continuity
  state, derives the self-model, classifies possible growth, sends growth through
  the Growth Gate, records simple memory reinforcement/correction signals, emits
  governed output, and refreshes a dashboard.
- `Lucien Live Chat`: serves a local three-panel chat page where messages are sent
  through PCA, responses are output-gated, ledger events are shown live, and browser
  text-to-speech can read Lucien's response.
- `ModelAdapter`: provides an Echo fallback plus optional OpenAI-compatible model
  calls through `OPENAI_API_KEY`, `LUCIEN_MODEL`, and `LUCIEN_MODEL_BASE_URL`.
- `CSMRuntimeBridge`: connects Lucien-style CSM monitor results and hard-kill audit
  logs to PCA continuity events.
- `PCAOutputWrapper`: gates outbound text and writes privacy-conscious audit events
  with hashes, lengths, claim, mode, and allow/block status.
- `TraceReport`: turns ledger history into a readable lifecycle summary and optional
  standalone HTML report.
- `Dashboard`: renders a standalone operational view with claim status, lifecycle
  timeline, runtime signals, output-gate events, event filtering, evidence freshness,
  state precedence, anchor status, blockers, recovery, lineage, authorization checks,
  and policy errors.
- `ScenarioRunner`: runs reproducible governance demonstrations that generate real
  ledgers, trace reports, dashboards, and result summaries.
- `ScenarioVerification`: checks expected scenario invariants such as required
  events, ordering, adjacency, final claim, output mode, recovery status, and chain
  validity.
- `TransformEvaluation`: explains decisions with provided evidence, missing evidence,
  identity risk, and an audit-ready reason.
- `OverrideRecord`: permits controlled exceptions without upgrading the continuity
  claim.
- `FollowUpRecord`: tracks continuing obligations created by risky transforms,
  overrides, review decisions, or continuity downgrades.
- `AuditRecord`: records post-transform evidence and resolves linked follow-up
  obligations when continuity checks pass or fail.
- `ContinuityClaimRecord`: records the public continuity claim history, including
  source events, active blockers, and superseded prior claims.
- `LineageRecord`: turns declared forks into parent-child identity records.
- `examples/minimal_identity.json`: a seed manifest for experimentation.

## Identity States

- `continuous`: invariants and required persistence constraints are intact.
- `degraded`: identity persists, but warning constraints have been breached.
- `forked`: the system has branched into a new lineage.
- `suspended`: identity cannot currently be asserted because required evidence is missing.
- `broken`: a hard invariant has been violated.

## Source Material Already Present

The workspace contains more than enough raw theory and design material to begin:

- `lucien_csm_ready_project`: existing monitor, audit logger, gate, and tests.
- `papers in limbo/new cohernce papers/Persistence Under Constraint.pdf`
- `papers in limbo/new cohernce papers/Identity Stability Under Constraint .pdf`
- `papers in limbo/new cohernce papers/The Coherence Stability Monitor (CSM).pdf`
- `papers in limbo/new cohernce papers/A Coherence Governor for Synthetic Minds.pdf`
- `finished books /lucien book fin/The_Coherence_First_Artificial_General_Intelligence_codex.pdf`
- `finished books /Cognitive Physics & AI Identity Design book/The_Geometry_of_Identity.pdf`

The first implementation should stay small and testable, then absorb these materials
as formal policies, invariants, metrics, and recovery protocols.

## Quick Start

```bash
python3 pca_cli.py demo
python3 scripts/demo_live.py
python3 scripts/check_all.py
python3 scripts/smoke_check.py
python3 scripts/regression_check.py
python3 scripts/csm_bridge_demo.py
python3 scripts/lifecycle_trace_demo.py
python3 scripts/dashboard_demo.py
python3 scripts/lucien_runtime_demo.py
python3 -m pca.scenario_runner list
python3 -m pca.scenario_runner run csm_red_continuity_break
python3 -m pca.scenario_runner run-all
python3 -m pca.scenario_runner report csm_red_continuity_break
python3 -m pca.scenario_runner verify csm_red_continuity_break
python3 -m pca.scenario_runner verify-all
python3 -m pca.scenario_runner demo
python3 pca_cli.py seed-required
python3 pca_cli.py status
python3 pca_cli.py anchor-head --authority root_authority --note release_checkpoint
python3 pca_cli.py verify-anchor
python3 pca_cli.py export-anchor --output reports/latest_anchor.json
python3 pca_cli.py --policies policies/ transform substrate_migration
python3 pca_cli.py --policy-pack policies/substrate.json transform substrate_migration
python3 pca_cli.py --policies policies/ transform substrate_migration --override emergency --authority operator
python3 pca_cli.py transform substrate_migration
python3 pca_cli.py override substrate_migration --authority human_operator --reason emergency_migration_from_failing_substrate
python3 pca_cli.py followups
python3 pca_cli.py audit substrate_migration --followup FOLLOWUP_ID --evidence continuity_proof=ok --evidence state_hash_match=ok --evidence operator_attestation=ok
python3 pca_cli.py claims --current
python3 pca_cli.py claims --history
python3 pca_cli.py open-recovery --authority recovery_authority --reason continuity_break_recovery_path
python3 pca_cli.py recovery-status
python3 pca_cli.py speak-gate
python3 pca_cli.py runtime-signal AMBER --source lucien_csm --metric strain=0.72 --reason runtime_strain_review
python3 pca_cli.py runtime-signal RED --source lucien_csm --metric strain=0.97 --reason csm_hard_kill
python3 pca_cli.py gate-output "I am stable and continuous as Lucien."
python3 pca_cli.py trace-report --html reports/latest_trace.html
python3 pca_cli.py dashboard --html reports/pca_dashboard.html
python3 pca_cli.py transform version_update --evidence change_summary=no_identity_invariant_changed
python3 pca_cli.py fork lucien-branch-a --reason sandboxed_identity_experiment
python3 pca_cli.py lineage
python3 pca_cli.py propose-growth memory --summary "User prefers governed learning" --impact low
python3 pca_cli.py growth-gate accept --impact medium
python3 pca_cli.py growth
python3 pca_cli.py growth --queue
python3 pca_cli.py conflicts
python3 pca_cli.py resolve-conflict CONFLICT_ID --keep-existing --reason "existing commitment remains active"
python3 pca_cli.py review-growth GROWTH_ID --accept --reviewer steward --reason "aligned with identity policy"
python3 pca_cli.py review-growth GROWTH_ID --reject --reviewer steward --reason "conflicts with continuity constraints"
python3 pca_cli.py self-model
python3 pca_cli.py self-model --compile --output reports/lucien_self_model.txt
python3 pca_cli.py memories
python3 pca_cli.py memory-signal MEMORY_ID --type reinforced --reason "confirmed by later turn"
python3 pca_cli.py memory-signals
python3 pca_cli.py evidence-add --type test_result --summary "Scenario verification passed." --confidence high
python3 pca_cli.py evidence-review EVIDENCE_ID --accept --confidence high --reason "source verified"
python3 pca_cli.py evidence-review EVIDENCE_ID --dispute --reason "conflicts with newer source"
python3 pca_cli.py evidence-link EVIDENCE_ID --mission MISSION_ID --reason "supports mission hypothesis"
python3 pca_cli.py evidence-claim --statement "The scenario suite passed." --evidence-id EVIDENCE_ID --confidence high
python3 pca_cli.py evidence-locker
python3 pca_cli.py evidence-for --mission MISSION_ID
python3 pca_cli.py mission-open "Reduce preventable isolation" --problem "Find evidence-backed ways to reduce local isolation without replacing human care." --value dignity --value evidence
python3 pca_cli.py mission-add MISSION_ID hypothesis --summary "Trusted weekly check-ins may surface needs before crisis." --confidence uncertain
python3 pca_cli.py mission-add MISSION_ID risk --summary "Automation could crowd out local human responsibility." --confidence medium
python3 pca_cli.py mission-status MISSION_ID completed --reason "pilot review complete"
python3 pca_cli.py missions
python3 pca_cli.py missions --open
python3 pca_cli.py mission-flow MISSION_ID
python3 pca_cli.py mission-flow --all
python3 pca_cli.py mission-advance MISSION_ID
python3 pca_cli.py mission-step-propose MISSION_ID --description "Review public data source" --risk low --tool research --expected-outcome "Evidence note"
python3 pca_cli.py mission-step-approve STEP_ID --reason "bounded action approved"
python3 pca_cli.py mission-step-start STEP_ID
python3 pca_cli.py mission-step-complete STEP_ID --actual-outcome "Step completed with recorded outcome"
python3 pca_cli.py mission-step-fail STEP_ID --failure-note "Step failed to reach target group"
python3 pca_cli.py mission-step-block STEP_ID --reason "requires unresolved evidence review"
python3 pca_cli.py mission-steps --mission MISSION_ID
python3 pca_cli.py skill-candidate STEP_ID --name "Push GitHub checkpoint" --procedure "Check tests, confirm commit, push, refresh GitHub, verify hash."
python3 pca_cli.py skill-auto-propose --minimum-repetitions 2
python3 pca_cli.py skill-candidates
python3 pca_cli.py skill-review SKILL_ID --accept --reason "repeatable and safe"
python3 pca_cli.py skill-review SKILL_ID --reject --reason "too context-dependent"
python3 pca_cli.py skills
python3 pca_cli.py skill-suggestions MISSION_ID
python3 pca_cli.py reflect
python3 pca_cli.py reflections
python3 pca_cli.py reflection-queue --open
python3 pca_cli.py reflection-task TASK_ID --resolve --reason "reviewed by steward"
python3 pca_cli.py reflection-task TASK_ID --dismiss --reason "not needed"
python3 pca_cli.py constitution
python3 pca_cli.py --ledger data/lucien_chat.log constitution --write
python3 pca_cli.py context
python3 pca_cli.py context --mission MISSION_ID
python3 pca_cli.py context --mission MISSION_ID --prompt
python3 pca_cli.py chat-once "Lucien, what changed in your state?"
python3 pca_cli.py live-chat
python3 pca_cli.py sessions
python3 pca_cli.py session-replay --latest
python3 pca_cli.py session-replay SESSION_ID --html reports/session_replay.html
python3 pca_cli.py cockpit --html reports/lucien_cockpit.html
python3 scripts/lucien_cockpit_demo.py
python3 lucien_chat.py --seed-required --message "Remember that PCA learning must be governed."
```

The live chat page includes steward controls for resolving reflection tasks,
reviewing pending growth, and resolving growth conflicts. These controls write
the same ledger-backed events as the CLI workflows.
It also exposes a live self-model panel and a manual reflection action so
Lucien can surface new steward work while the conversation is running.
The Memory Inbox and Recall panels let stewards accept or reject memory
candidates, request evidence, and mark accepted memories as reinforced,
contradicted, or stale.
The Evidence Locker grounds Lucien's work: evidence can be added, reviewed,
disputed, marked stale, rejected, linked to missions/memories/skills/claims, and
shown in the cockpit without storing raw source text in the ledger.
The Context Builder turns ledger state into bounded working context before Lucien
answers. It includes accepted memory, evidence status, mission flow, skill
suggestions, open governance work, recovery state, and warnings while keeping raw
private source text out of prompts.
The Mission Workspace lets Lucien open governed problem-solving missions and
separate hypotheses, evidence, interventions, risks, plan steps, outcomes, and
lessons into ledger-backed records. Mission text is stored by hash and length so
the audit trail can prove that work happened without turning the ledger into a
raw scratchpad.
Mission pressure is routed back into governance: risk items, unresolved evidence,
and failed outcomes create mission-review reflection tasks, while mission lessons
become governed growth candidates that still require the normal review path.
Mission flow derives a phase, blockers, and next action from the ledger, so a
mission can be in intake, evidence review, planning, intervention readiness,
outcome review, lesson review, completed, or blocked without manually declaring
false progress.
Mission steps move planning into governed action: each step is proposed,
approved when risk requires it, started, completed, failed, or blocked. Medium
and high risk steps cannot start without approval, and failed or blocked steps
route back into mission reflection pressure.
Skill memory converts successful mission work into reusable procedural
candidates without silently modifying Lucien. A completed step may propose a
skill candidate, repeated completed step patterns can auto-propose candidates,
and only steward-accepted skills become reusable suggestions for future mission
steps with matching tool and risk.

For a public walkthrough, run `python3 pca_cli.py demo`. It runs the local
checks, refreshes the cockpit and replay artifacts, prints reviewer steps, and
starts the Lucien live cockpit.

Scenario outputs are written to `scenario_runs/<scenario_id>/`:

- `continuity.log`
- `trace.html`
- `dashboard.html`
- `result.json`

`python3 -m pca.scenario_runner demo` also writes `scenario_runs/index.html`,
an index page linking every verified scenario dashboard, trace, and result.

Use `python3 scripts/check_all.py` as the top-level project health check. It runs
compilation, smoke checks, scenario regression verification, and regenerates the
scenario demo index.
