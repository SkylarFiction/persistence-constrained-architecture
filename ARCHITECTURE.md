# A Persistence-Constrained Architecture for Identity-Bearing Systems

## Definition

An identity-bearing system is any system whose continuity matters: an agent, model,
institution, account, organism, archive, or synthetic mind. Its identity is not just
a label. Identity is a claim backed by continuity evidence.

A persistence-constrained architecture defines what must persist, what may change,
how changes are recorded, and when the system must stop claiming unbroken continuity.

The system's central governance rule is:

Any system that claims continuity through change must be able to prove what was
preserved, what was altered, what was lost, and who authorized the transformation.

## Runtime Layers

1. Identity Manifest
   - Defines origin, invariants, allowed transforms, and persistence constraints.
   - Answers: what must remain true for this system to still be itself?

2. Continuity Ledger
   - Stores identity-relevant events in a hash-chained append log.
   - Uses a file lock around append operations so concurrent writers cannot read
     the same head and produce conflicting next hashes.
   - Answers: what actually happened, and can the evidence be trusted?

3. Continuity Evaluator
   - Classifies identity state from manifest plus ledger evidence.
   - Answers: is identity continuous, degraded, forked, suspended, or broken?

4. Policy Engine
   - Validates proposed transformations against declared persistence policy.
   - Answers: may this system compact memory, migrate substrate, update version,
     fork lineage, or recover without breaking identity?
   - Emits decision explanations with provided evidence, missing evidence, identity
     risk, and an audit-ready reason.

5. Policy Packs
   - Load modular governance rules by identity-risk domain.
   - Define evidence requirements, risk levels, denial rules, override follow-ups,
     and audit expectations.
   - Answers: which domain policy governs this transform?

Missing policy does not mean permission. Missing policy means denial.

6. Lineage Layer
   - Converts declared fork events into parent-child identity records.
   - Answers: when singular identity splits, what new lineage was created?

7. Override Governance
   - Permits controlled exceptions without certifying continuity.
   - Answers: may an operation proceed under emergency authority, and what weaker
     continuity claim must be recorded afterward?

The override rule is strict:

An override may permit the operation, but it cannot upgrade the continuity claim.

8. Authorization Model
   - Defines authority classes for governance actions.
   - Answers: who may override, complete follow-ups, fail follow-ups, waive
     obligations, or initiate recovery?
   - Records authorization checks for identity-changing actions.

Current authority classes:

- observer
- operator
- steward
- recovery_authority
- root_authority

9. Follow-Up Enforcement
   - Creates persistent obligations from overrides and risky governance decisions.
   - Answers: what repair, audit, freeze, or review work is still required before
     continuity claims can be strengthened?

The follow-up rule is strict:

An identity cannot claim certified continuity while required follow-ups remain open,
overdue, or failed.

10. Post-Transform Audits
   - Records evidence after memory, substrate, lineage, or version transformation.
   - Resolves linked follow-up obligations when checks certify continuity or mark
     continuity break.
   - Answers: what evidence exists after the transformation, and what continuity
     claim does that evidence support?

11. Continuity Claim Registry
   - Records the continuity claim an identity is allowed to make.
   - Stores source events, active blockers, reasons, and superseded prior claims.
   - Answers: what public continuity claim is currently justified, and how did the
     system get there?

Claims are produced by state transitions, not manual declaration.

12. Recovery and Governance Layer
   - Opens staged recovery paths after uncertified or broken continuity.
   - Requires recovery authority and follow-up audit evidence.
   - Answers: how can damage be handled without pretending it never happened?

Recovery authority may open a recovery path, but cannot simply erase a continuity
break. A certified recovery audit moves the public claim to a constrained state
such as review_required, not automatically back to certified continuity.

13. Output Gate
   - Maps continuity claims to allowed speech modes.
   - Answers: what may this identity say about itself right now?

Output gate policy:

- certified_continuity: may speak normally as the identity.
- review_required: may speak as the identity with review disclosure.
- uncertified_continuity: may answer operationally, but cannot claim stable identity.
- declared_fork: must identify as fork or descendant.
- continuity_break: recovery/status only.

14. Runtime Adapter
   - Gives agent runtimes a small integration surface for PCA governance.
   - Records CSM-style GREEN, AMBER, and RED signals as ledger events.
   - Converts AMBER into a soft runtime breach and RED into a hard runtime breach.
   - Recomputes the current continuity claim and output gate after runtime signals.
   - Answers: may this runtime speak as the identity after the latest operational
     state?

15. CSM Bridge
   - Connects Lucien-style CSM monitor outputs to the PCA runtime adapter.
   - Wraps a CSM audit logger so RED hard-kill payloads are captured before the
     monitor raises.
   - Accepts normal monitor step results for GREEN and AMBER.
   - Answers: how does operational coherence telemetry become identity-governance
     evidence?

16. Output Wrapper
   - Applies the output gate to outbound runtime text.
   - Writes an audit event for each output decision without storing full response
     text in the ledger.
   - Records hashes, lengths, claim, mode, disclosure requirement, and allow/block
     status.
   - Answers: what was the identity allowed to emit under the active continuity
     claim?

17. Trace Report
   - Summarizes the ledger into current claim, identity state, output mode, claim
     history, runtime signals, output-gate events, and important governance events.
   - Writes standalone HTML reports for inspection without running a dashboard.
   - Answers: how did this identity arrive at its current continuity claim?

18. Dashboard
   - Renders a standalone operational dashboard from trace report data.
   - Shows current claim, identity state, output mode, chain validity, claim path,
     runtime signals, output-gate decisions, and a filterable governance timeline.
   - Answers: what is the live governance posture of this identity?

19. Scenario Runner
   - Runs canned lifecycle demonstrations through real PCA engines.
   - Produces ledgers, trace reports, dashboards, and result summaries.
   - Answers: how does PCA behave under reproducible identity-governance stress?

20. Scenario Verification
   - Checks scenario invariants for required events, event ordering, adjacent
     critical writes, final claims, output modes, recovery state, active follow-ups,
     and hash-chain validity.
   - Answers: did this governed lifecycle regress?

## MVP Principle

Do not begin with consciousness claims. Begin with evidence-bearing continuity.

The first working system should be able to:

- load an identity manifest,
- append continuity events,
- verify the event chain,
- classify continuity state,
- evaluate transform admissibility,
- load modular policy packs conservatively,
- enforce authority thresholds for governance actions,
- record authorization checks in the ledger,
- explain policy decisions,
- record lineage after declared forks,
- permit emergency overrides while marking continuity uncertified,
- create, query, complete, and fail follow-up obligations,
- run post-transform audits that resolve linked obligations,
- record continuity claim history when the allowed claim changes,
- open staged recovery paths under recovery authority,
- gate identity speech from the current continuity claim,
- record runtime health signals as continuity events,
- ingest CSM monitor results and hard-kill audit logs,
- gate and audit outbound text,
- generate readable lifecycle trace reports,
- render local dashboards for continuity inspection,
- run reproducible governance scenarios,
- verify scenario regression laws,
- refuse unbroken identity claims after hard breach or undeclared fork.
