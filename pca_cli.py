from __future__ import annotations

import argparse
import json
from pathlib import Path

from pca.cold_open import cold_open_report, render_cold_open_report_text
from pca import (
    mission_argument_graph,
    render_argument_graph_text,
    seed_continuity_argument_graph,
    AuditEngine,
    AuditOutcome,
    AuthorityClass,
    AuthorizationCheckRecord,
    AuthorizationPolicy,
    ContinuityEvaluator,
    ContinuityLedger,
    continuity_certification,
    FollowUpRecord,
    FollowUpStatus,
    GoalStatus,
    GrowthGate,
    GrowthGateAction,
    GrowthReviewDecision,
    GrowthStatus,
    IdentityManifest,
    MissionItemKind,
    MissionStepRisk,
    MissionStatus,
    OverrideEngine,
    OverrideRequest,
    OutputGate,
    PCAOutputWrapper,
    PCAIdentityRuntime,
    PolicyEngine,
    RecoveryRecord,
    RecoveryStatus,
    TransformRequest,
    add_evidence,
    add_evidence_claim,
    add_goal_blocker,
    append_ledger_anchor,
    apply_steward_inbox_action,
    accepted_skills_from_events,
    run_auto_daily_research_loop,
    run_coherence_paper_pipeline,
    run_research_autopilot,
    authorization_policy_from_packs,
    autonomy_queue_items_from_events,
    auto_propose_skill_candidates,
    authorize,
    build_governed_context,
    build_manifest_from_policy_results,
    build_trace_report,
    claims_from_events,
    chat_sessions_from_events,
    chat_turns_from_events,
    compile_self_model,
    seed_coherence_physics_goals,
    current_claim_record,
    current_recovery_record,
    daily_command_center,
    daily_plan,
    derive_self_model,
    derive_current_claim,
    evidence_for_target,
    evidence_locker_snapshot,
    execute_approved_autonomy_actions,
    execute_autonomy_action,
    export_latest_anchor,
    export_research_pdf,
    extract_source_notes_for_mission,
    find_followup,
    find_recovery,
    followups_from_events,
    goal_records_from_events,
    growth_records_from_events,
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    growth_review_records_from_events,
    lineage_records,
    learning_review_records_from_events,
    run_latest_session_learning_review,
    run_learning_review,
    accept_growth,
    approve_mission_step,
    block_mission_step,
    complete_mission_step,
    fail_mission_step,
    memory_cards_from_events,
    memory_signal_records_from_events,
    model_environment_diagnostic,
    mission_briefs_from_events,
    recommend_next_mission_step,
    propose_autonomous_mission_step,
    mission_flow,
    mission_flows_from_events,
    mission_onboarding_state,
    mission_step_records_from_events,
    add_mission_item,
    apply_startup_health_fix,
    create_mission_onboarding_pack,
    create_goal_record,
    create_research_output,
    index_coherence_corpus,
    index_knowledge_hub,
    knowledge_hub_snapshot,
    open_mission,
    open_tasks_from_reflection,
    propose_growth,
    propose_mission_step,
    propose_skill_candidate,
    record_memory_signal,
    record_claim_if_changed,
    recovery_records_from_events,
    record_reflection,
    reject_growth,
    resolve_growth_conflict,
    resolve_matching_reflection_tasks,
    reflection_task_records_from_events,
    reflection_records_from_events,
    review_growth,
    review_skill_candidate,
    review_evidence,
    link_evidence,
    link_goal_mission,
    safe_load_policy_directory,
    safe_load_policy_pack,
    update_mission_status,
    update_goal_status,
    update_reflection_task,
    start_mission_step,
    steward_inbox,
    startup_health,
    skill_candidates_from_events,
    skill_suggestions_for_mission,
    check_tool_permission,
    dry_run_tool_for_step,
    render_constitution_markdown,
    render_continuity_certification_text,
    render_build_review_text,
    render_autonomy_queue_text,
    render_auto_daily_research_loop_text,
    render_checkpoint_history_text,
    render_checkpoint_story_markdown,
    render_coherence_corpus_index_text,
    render_coherence_paper_pipeline_text,
    render_coherence_seed_text,
    render_commit_readiness_text,
    render_daily_command_center_text,
    render_daily_plan_text,
    render_knowledge_hub_index_text,
    render_knowledge_hub_sources_text,
    render_next_governed_build_text,
    render_project_build_brief_text,
    render_research_autopilot_text,
    render_research_review_text,
    render_research_outputs_text,
    render_source_notes_text,
    render_startup_health_text,
    run_tool_for_step,
    tool_execution_records_from_events,
    tool_permission_records_from_events,
    tool_preview_records_from_events,
    tool_specs,
    write_dashboard_html,
    write_constitution_markdown,
    write_lucien_cockpit_html,
    write_trace_report_html,
    workbench_status,
    verify_latest_anchor,
    build_session_replay,
    latest_session_id,
    write_session_replay_html,
    project_build_brief,
    build_review,
    auto_propose_checkpoint_skill_candidates,
    checkpoint_history,
    checkpoint_story,
    commit_readiness,
    link_checkpoint_to_mission,
    next_governed_build,
    propose_checkpoint_lesson,
    propose_autonomy_action,
    review_autonomy_action,
    research_outputs_from_events,
    research_review_desk,
    research_sandbox_status,
)
from pca.live_chat import chat_once, run_live_chat_server
from pca.demo_live import run_demo


def load_manifest(path: Path) -> IdentityManifest:
    return IdentityManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def apply_policy_packs(
    manifest: IdentityManifest,
    policy_pack_paths: list[str],
    policy_directories: list[str],
) -> tuple[IdentityManifest, AuthorizationPolicy]:
    results = []
    for directory in policy_directories:
        results.extend(safe_load_policy_directory(directory))
    for policy_pack_path in policy_pack_paths:
        results.append(safe_load_policy_pack(policy_pack_path))
    packs = [result.pack for result in results if result.valid and result.pack]
    authorization_policy = authorization_policy_from_packs(packs)
    if not results:
        return manifest, authorization_policy
    return build_manifest_from_policy_results(manifest, results), authorization_policy


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parse_key_values(items: list[str]) -> dict[str, str]:
    values = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator:
            raise SystemExit(f"Expected key=value, got: {item}")
        values[key] = value
    return values


def _evidence_target_from_args(args) -> tuple[str, str]:
    for target_type in ("memory", "mission", "skill", "claim"):
        target_id = getattr(args, target_type, None)
        if target_id:
            return target_type, target_id
    raise SystemExit("evidence target is required")


def create_followups_for_override(
    ledger: ContinuityLedger,
    identity_id: str,
    override_event_hash: str,
    required_followups: list[str],
) -> list[FollowUpRecord]:
    from pca import required_evidence_for

    records = []
    for followup_type in required_followups:
        record = FollowUpRecord.create(
            identity_id=identity_id,
            source_event_id=override_event_hash,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
            reason="Created by override governance.",
        )
        ledger.append("followup_created", identity_id, record.to_dict())
        records.append(record)
    return records


def _chat_ledger_path(ledger_path: str) -> str:
    if ledger_path == "data/continuity.log":
        return "data/lucien_chat.log"
    return ledger_path


def log_authorization_check(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    action: str,
    actor_authority: str,
    decision,
):
    record = AuthorizationCheckRecord.create(
        identity_id=manifest.system_id,
        action=action,
        actor_authority=actor_authority,
        decision=decision,
    )
    event = ledger.append(
        "authorization_check",
        manifest.system_id,
        record.to_dict(),
    )
    return event


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persistence-constrained identity continuity tool"
    )
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--ledger", default="data/continuity.log")
    parser.add_argument("--anchors", default="data/ledger_anchors.log")
    parser.add_argument(
        "--policy-pack",
        action="append",
        default=[],
        help="Path to a policy pack JSON file. May be repeated.",
    )
    parser.add_argument(
        "--policies",
        action="append",
        default=[],
        help="Path to a directory of policy pack JSON files. May be repeated.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    followups_parser = subparsers.add_parser("followups")
    followups_parser.add_argument("--status")

    claims_parser = subparsers.add_parser("claims")
    claims_parser.add_argument("--current", action="store_true")
    claims_parser.add_argument("--history", action="store_true")

    constitution_parser = subparsers.add_parser("constitution")
    constitution_parser.add_argument("--write", action="store_true")
    constitution_parser.add_argument("--output", default="LUCIEN_CONSTITUTION.md")

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("--mission")
    context_parser.add_argument("--prompt", action="store_true")

    subparsers.add_parser("status")
    cold_open_parser = subparsers.add_parser("cold-open")
    cold_open_parser.add_argument("--json", action="store_true")
    daily_parser = subparsers.add_parser("daily")
    daily_parser.add_argument("--json", action="store_true")
    daily_research_parser = subparsers.add_parser("daily-research-loop")
    daily_research_parser.add_argument("--json", action="store_true")
    daily_research_parser.add_argument("--force", action="store_true")
    research_autopilot_parser = subparsers.add_parser("research-autopilot")
    research_autopilot_parser.add_argument("--json", action="store_true")
    research_autopilot_parser.add_argument("--force", action="store_true")
    research_autopilot_parser.add_argument("--mission")
    coherence_corpus_parser = subparsers.add_parser("coherence-corpus-index")
    coherence_corpus_parser.add_argument("--json", action="store_true")
    coherence_corpus_parser.add_argument("--mission")
    coherence_corpus_parser.add_argument("--root", action="append", default=[])
    coherence_corpus_parser.add_argument("--limit", type=int, default=12)
    coherence_corpus_parser.add_argument("--knowledge-hub", action="store_true")
    knowledge_hub_index_parser = subparsers.add_parser("knowledge-hub-index")
    knowledge_hub_index_parser.add_argument("--json", action="store_true")
    knowledge_hub_index_parser.add_argument("--limit", type=int, default=250)
    knowledge_hub_index_parser.add_argument("--topic")
    knowledge_hub_sources_parser = subparsers.add_parser("knowledge-hub-sources")
    knowledge_hub_sources_parser.add_argument("--json", action="store_true")
    knowledge_hub_sources_parser.add_argument("--topic")
    source_notes_parser = subparsers.add_parser("coherence-source-notes")
    source_notes_parser.add_argument("--json", action="store_true")
    source_notes_parser.add_argument("--mission")
    source_notes_parser.add_argument("--limit", type=int, default=6)
    argument_graph_seed_parser = subparsers.add_parser("argument-graph-seed")
    argument_graph_seed_parser.add_argument("mission_id")
    argument_graph_seed_parser.add_argument("--json", action="store_true")
    argument_graph_show_parser = subparsers.add_parser("argument-graph-show")
    argument_graph_show_parser.add_argument("mission_id")
    argument_graph_show_parser.add_argument("--json", action="store_true")
    coherence_paper_parser = subparsers.add_parser("coherence-paper-pipeline")
    coherence_paper_parser.add_argument("--json", action="store_true")
    coherence_paper_parser.add_argument("--mission")
    coherence_paper_parser.add_argument("--root", action="append", default=[])
    coherence_paper_parser.add_argument("--limit", type=int, default=8)
    coherence_paper_parser.add_argument("--knowledge-hub", action="store_true")
    coherence_paper_parser.add_argument("--force", action="store_true")
    coherence_paper_parser.add_argument(
        "--output",
        default="reports/research_papers/coherence_physics_research_packet.pdf",
    )
    research_sandbox_parser = subparsers.add_parser("research-sandbox")
    research_sandbox_parser.add_argument("--json", action="store_true")
    research_brief_parser = subparsers.add_parser("research-brief")
    research_brief_parser.add_argument("mission_id")
    research_brief_parser.add_argument("--json", action="store_true")
    research_claim_map_parser = subparsers.add_parser("research-claim-map")
    research_claim_map_parser.add_argument("mission_id")
    research_claim_map_parser.add_argument("--json", action="store_true")
    research_paper_parser = subparsers.add_parser("research-paper-draft")
    research_paper_parser.add_argument("mission_id")
    research_paper_parser.add_argument("--json", action="store_true")
    research_outputs_parser = subparsers.add_parser("research-outputs")
    research_outputs_parser.add_argument("--mission")
    research_outputs_parser.add_argument("--json", action="store_true")
    research_pdf_parser = subparsers.add_parser("research-pdf")
    research_pdf_parser.add_argument("mission_id")
    research_pdf_parser.add_argument("--output", default="reports/lucien_research_packet.pdf")
    research_pdf_parser.add_argument("--json", action="store_true")
    research_review_parser = subparsers.add_parser("research-review")
    research_review_parser.add_argument("--mission")
    research_review_parser.add_argument("--json", action="store_true")
    certification_parser = subparsers.add_parser("continuity-certification")
    certification_parser.add_argument("--json", action="store_true")
    daily_plan_parser = subparsers.add_parser("daily-plan")
    daily_plan_parser.add_argument("--json", action="store_true")
    project_brief_parser = subparsers.add_parser("project-brief")
    project_brief_parser.add_argument("--json", action="store_true")
    build_review_parser = subparsers.add_parser("build-review")
    build_review_parser.add_argument("--json", action="store_true")
    commit_readiness_parser = subparsers.add_parser("commit-readiness")
    commit_readiness_parser.add_argument("--json", action="store_true")
    checkpoint_story_parser = subparsers.add_parser("checkpoint-story")
    checkpoint_story_parser.add_argument("--json", action="store_true")
    next_build_parser = subparsers.add_parser("next-build")
    next_build_parser.add_argument("--json", action="store_true")
    link_checkpoint_parser = subparsers.add_parser("link-checkpoint")
    link_checkpoint_parser.add_argument("--mission", required=True)
    link_checkpoint_parser.add_argument("--commit", default="HEAD")
    link_checkpoint_parser.add_argument("--step", action="append", default=[])
    link_checkpoint_parser.add_argument("--evidence", action="append", default=[])
    link_checkpoint_parser.add_argument("--check", action="append", default=[])
    link_checkpoint_parser.add_argument("--lesson", default="")
    link_checkpoint_parser.add_argument("--reason", default="")
    checkpoint_history_parser = subparsers.add_parser("checkpoint-history")
    checkpoint_history_parser.add_argument("--mission")
    checkpoint_history_parser.add_argument("--json", action="store_true")
    checkpoint_lesson_parser = subparsers.add_parser("checkpoint-lesson")
    checkpoint_lesson_parser.add_argument("link_id")
    checkpoint_lesson_parser.add_argument("--summary", required=True)
    checkpoint_lesson_parser.add_argument("--confidence", default="medium")
    checkpoint_lesson_parser.add_argument("--reason", default="")
    checkpoint_skills_parser = subparsers.add_parser("checkpoint-skills")
    checkpoint_skills_parser.add_argument("--minimum", type=int, default=2)
    autonomy_queue_parser = subparsers.add_parser("autonomy-queue")
    autonomy_queue_parser.add_argument("--status")
    autonomy_queue_parser.add_argument("--json", action="store_true")
    autonomy_propose_parser = subparsers.add_parser("autonomy-propose")
    autonomy_propose_parser.add_argument("--type", required=True)
    autonomy_propose_parser.add_argument("--reason", required=True)
    autonomy_propose_parser.add_argument("--payload", default="{}")
    autonomy_approve_parser = subparsers.add_parser("autonomy-approve")
    autonomy_approve_parser.add_argument("item_id")
    autonomy_approve_parser.add_argument("--reason", default="")
    autonomy_reject_parser = subparsers.add_parser("autonomy-reject")
    autonomy_reject_parser.add_argument("item_id")
    autonomy_reject_parser.add_argument("--reason", default="")
    autonomy_execute_parser = subparsers.add_parser("autonomy-execute")
    autonomy_execute_parser.add_argument("item_id")
    autonomy_execute_parser.add_argument("--reason", default="")
    subparsers.add_parser("autonomy-execute-approved")
    subparsers.add_parser("model-diagnostic")
    subparsers.add_parser("workbench-status")
    startup_health_parser = subparsers.add_parser("startup-health")
    startup_health_parser.add_argument("--json", action="store_true")
    startup_fix_parser = subparsers.add_parser("startup-fix")
    startup_fix_parser.add_argument(
        "action",
        choices=["refresh-required-evidence", "open-coherence-research-mission"],
    )
    startup_fix_parser.add_argument("--reason", default="")
    chat_once_parser = subparsers.add_parser("chat-once")
    chat_once_parser.add_argument("message")
    chat_once_parser.add_argument(
        "--model-mode",
        choices=["auto", "echo", "openai", "serious_only", "local_ollama", "local_first"],
        default="auto",
    )
    chat_once_parser.add_argument("--use-openai", action="store_true")

    live_chat_parser = subparsers.add_parser("live-chat")
    live_chat_parser.add_argument("--host", default="127.0.0.1")
    live_chat_parser.add_argument("--port", type=int, default=8787)

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("--host", default="127.0.0.1")
    demo_parser.add_argument("--port", type=int, default=8787)
    demo_parser.add_argument("--skip-checks", action="store_true")
    demo_parser.add_argument("--no-open", action="store_true")
    demo_parser.add_argument("--no-server", action="store_true")

    subparsers.add_parser("speak-gate")
    subparsers.add_parser("seed-required")
    subparsers.add_parser("lineage")
    subparsers.add_parser("memories")
    subparsers.add_parser("memory-signals")

    evidence_add_parser = subparsers.add_parser("evidence-add")
    evidence_add_parser.add_argument(
        "--type",
        required=True,
        choices=[
            "user_statement",
            "file",
            "web_source",
            "mission_observation",
            "tool_output",
            "chat_turn",
            "test_result",
            "code_result",
            "manual_note",
        ],
    )
    evidence_add_parser.add_argument("--summary", required=True)
    evidence_add_parser.add_argument("--source", default="")
    evidence_add_parser.add_argument("--confidence", default="unknown")
    evidence_add_parser.add_argument("--reason", default="")

    evidence_link_parser = subparsers.add_parser("evidence-link")
    evidence_link_parser.add_argument("evidence_id")
    target_group = evidence_link_parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--memory")
    target_group.add_argument("--mission")
    target_group.add_argument("--skill")
    target_group.add_argument("--claim")
    evidence_link_parser.add_argument("--reason", default="")

    evidence_review_parser = subparsers.add_parser("evidence-review")
    evidence_review_parser.add_argument("evidence_id")
    review_group = evidence_review_parser.add_mutually_exclusive_group(required=True)
    review_group.add_argument("--accept", action="store_true")
    review_group.add_argument("--dispute", action="store_true")
    review_group.add_argument("--stale", action="store_true")
    review_group.add_argument("--reject", action="store_true")
    evidence_review_parser.add_argument("--reviewer", default="steward")
    evidence_review_parser.add_argument("--confidence")
    evidence_review_parser.add_argument("--reason", required=True)

    evidence_claim_parser = subparsers.add_parser("evidence-claim")
    evidence_claim_parser.add_argument("--statement", required=True)
    evidence_claim_parser.add_argument("--evidence-id", action="append", default=[])
    evidence_claim_parser.add_argument("--confidence", default="unknown")
    evidence_claim_parser.add_argument("--status", default="proposed")
    evidence_claim_parser.add_argument("--reason", default="")

    subparsers.add_parser("evidence-locker")

    evidence_for_parser = subparsers.add_parser("evidence-for")
    target_for_group = evidence_for_parser.add_mutually_exclusive_group(required=True)
    target_for_group.add_argument("--memory")
    target_for_group.add_argument("--mission")
    target_for_group.add_argument("--skill")
    target_for_group.add_argument("--claim")

    missions_parser = subparsers.add_parser("missions")
    missions_parser.add_argument("--open", action="store_true")

    goal_create_parser = subparsers.add_parser("goal-create")
    goal_create_parser.add_argument("title")
    goal_create_parser.add_argument("--purpose", required=True)
    goal_create_parser.add_argument("--success-criteria", required=True)
    goal_create_parser.add_argument("--priority", default="medium")
    goal_create_parser.add_argument("--next-action", default="")
    goal_create_parser.add_argument("--review-state", default="pending")
    goal_create_parser.add_argument("--reason", default="")

    goals_parser = subparsers.add_parser("goals")
    goals_parser.add_argument("--active", action="store_true")
    coherence_seed_parser = subparsers.add_parser("coherence-seed")
    coherence_seed_parser.add_argument("--json", action="store_true")

    goal_status_parser = subparsers.add_parser("goal-status")
    goal_status_parser.add_argument("goal_id")

    goal_link_parser = subparsers.add_parser("goal-link-mission")
    goal_link_parser.add_argument("goal_id")
    goal_link_parser.add_argument("mission_id")
    goal_link_parser.add_argument("--reason", default="")

    goal_blocker_parser = subparsers.add_parser("goal-add-blocker")
    goal_blocker_parser.add_argument("goal_id")
    goal_blocker_parser.add_argument("text")
    goal_blocker_parser.add_argument("--reason", default="")

    goal_complete_parser = subparsers.add_parser("goal-complete")
    goal_complete_parser.add_argument("goal_id")
    goal_complete_parser.add_argument("--reason", default="")

    goal_archive_parser = subparsers.add_parser("goal-archive")
    goal_archive_parser.add_argument("goal_id")
    goal_archive_parser.add_argument("--reason", default="")

    mission_open_parser = subparsers.add_parser("mission-open")
    mission_open_parser.add_argument("title")
    mission_open_parser.add_argument("--problem", required=True)
    mission_open_parser.add_argument("--value", action="append", default=[])
    mission_open_parser.add_argument("--reason", default="")

    mission_add_parser = subparsers.add_parser("mission-add")
    mission_add_parser.add_argument("mission_id")
    mission_add_parser.add_argument(
        "kind",
        choices=[kind.value for kind in MissionItemKind],
    )
    mission_add_parser.add_argument("--summary", required=True)
    mission_add_parser.add_argument("--status", default="proposed")
    mission_add_parser.add_argument("--confidence", default="unknown")
    mission_add_parser.add_argument("--evidence-ref", action="append", default=[])
    mission_add_parser.add_argument("--reason", default="")

    mission_status_parser = subparsers.add_parser("mission-status")
    mission_status_parser.add_argument("mission_id")
    mission_status_parser.add_argument(
        "status",
        choices=[status.value for status in MissionStatus],
    )
    mission_status_parser.add_argument("--reason", default="")

    mission_flow_parser = subparsers.add_parser("mission-flow")
    mission_flow_parser.add_argument("mission_id", nargs="?")
    mission_flow_parser.add_argument("--all", action="store_true")

    mission_onboarding_parser = subparsers.add_parser("mission-onboarding")
    mission_onboarding_parser.add_argument("mission_id")

    mission_onboard_parser = subparsers.add_parser("mission-onboard")
    mission_onboard_parser.add_argument("mission_id")
    mission_onboard_parser.add_argument("--reason", default="")

    mission_advance_parser = subparsers.add_parser("mission-advance")
    mission_advance_parser.add_argument("mission_id")

    mission_next_parser = subparsers.add_parser("mission-next-step")
    mission_next_parser.add_argument("mission_id")
    mission_next_parser.add_argument("--apply", action="store_true")

    mission_steps_parser = subparsers.add_parser("mission-steps")
    mission_steps_parser.add_argument("--mission")

    step_propose_parser = subparsers.add_parser("mission-step-propose")
    step_propose_parser.add_argument("mission_id")
    step_propose_parser.add_argument("--description", required=True)
    step_propose_parser.add_argument(
        "--risk",
        required=True,
        choices=[risk.value for risk in MissionStepRisk],
    )
    step_propose_parser.add_argument("--tool", required=True)
    step_propose_parser.add_argument("--expected-outcome", default="")
    step_propose_parser.add_argument("--reason", default="")

    step_approve_parser = subparsers.add_parser("mission-step-approve")
    step_approve_parser.add_argument("step_id")
    step_approve_parser.add_argument("--reason", default="")

    step_start_parser = subparsers.add_parser("mission-step-start")
    step_start_parser.add_argument("step_id")
    step_start_parser.add_argument("--reason", default="")

    step_complete_parser = subparsers.add_parser("mission-step-complete")
    step_complete_parser.add_argument("step_id")
    step_complete_parser.add_argument("--actual-outcome", required=True)
    step_complete_parser.add_argument("--reason", default="")

    step_fail_parser = subparsers.add_parser("mission-step-fail")
    step_fail_parser.add_argument("step_id")
    step_fail_parser.add_argument("--failure-note", required=True)
    step_fail_parser.add_argument("--reason", default="")

    step_block_parser = subparsers.add_parser("mission-step-block")
    step_block_parser.add_argument("step_id")
    step_block_parser.add_argument("--reason", required=True)

    subparsers.add_parser("tools")

    tool_permission_parser = subparsers.add_parser("tool-permission")
    tool_permission_parser.add_argument("step_id")
    tool_permission_parser.add_argument("--reason", default="")

    tool_dry_run_parser = subparsers.add_parser("tool-dry-run")
    tool_dry_run_parser.add_argument("step_id")
    tool_dry_run_parser.add_argument("--arg", action="append", default=[])
    tool_dry_run_parser.add_argument("--reason", default="")

    tool_run_parser = subparsers.add_parser("tool-run")
    tool_run_parser.add_argument("step_id")
    tool_run_parser.add_argument("--arg", action="append", default=[])
    tool_run_parser.add_argument("--reason", default="")

    subparsers.add_parser("tool-history")

    subparsers.add_parser("skill-candidates")

    skill_candidate_parser = subparsers.add_parser("skill-candidate")
    skill_candidate_parser.add_argument("step_id")
    skill_candidate_parser.add_argument("--name", required=True)
    skill_candidate_parser.add_argument("--procedure", required=True)
    skill_candidate_parser.add_argument("--reason", default="")

    skill_auto_parser = subparsers.add_parser("skill-auto-propose")
    skill_auto_parser.add_argument("--minimum-repetitions", type=int, default=2)

    skill_review_parser = subparsers.add_parser("skill-review")
    skill_review_parser.add_argument("skill_id")
    skill_review_group = skill_review_parser.add_mutually_exclusive_group(required=True)
    skill_review_group.add_argument("--accept", action="store_true")
    skill_review_group.add_argument("--reject", action="store_true")
    skill_review_parser.add_argument("--reason", required=True)

    subparsers.add_parser("skills")

    skill_suggestions_parser = subparsers.add_parser("skill-suggestions")
    skill_suggestions_parser.add_argument("mission_id")

    subparsers.add_parser("sessions")
    session_replay_parser = subparsers.add_parser("session-replay")
    session_replay_parser.add_argument("session_id", nargs="?")
    session_replay_parser.add_argument("--latest", action="store_true")
    session_replay_parser.add_argument("--html")
    learning_review_parser = subparsers.add_parser("learning-review")
    learning_scope = learning_review_parser.add_mutually_exclusive_group(required=False)
    learning_scope.add_argument("--latest-session", action="store_true")
    learning_scope.add_argument("--mission")
    learning_scope.add_argument("--step")
    learning_review_parser.add_argument("--apply", action="store_true")
    learning_review_parser.add_argument("--reason", default="")
    subparsers.add_parser("learning-reviews")
    subparsers.add_parser("reflect")
    subparsers.add_parser("reflections")
    reflection_queue_parser = subparsers.add_parser("reflection-queue")
    reflection_queue_parser.add_argument("--open", action="store_true")

    reflection_task_parser = subparsers.add_parser("reflection-task")
    reflection_task_parser.add_argument("task_id")
    task_decision_group = reflection_task_parser.add_mutually_exclusive_group(
        required=True
    )
    task_decision_group.add_argument("--resolve", action="store_true")
    task_decision_group.add_argument("--dismiss", action="store_true")
    reflection_task_parser.add_argument("--reason", default="")

    steward_inbox_parser = subparsers.add_parser("steward-inbox")
    steward_inbox_parser.add_argument("--type")
    steward_inbox_parser.add_argument("--high", action="store_true")

    steward_action_parser = subparsers.add_parser("steward-action")
    steward_action_parser.add_argument("inbox_id")
    steward_action_group = steward_action_parser.add_mutually_exclusive_group(
        required=True
    )
    steward_action_group.add_argument("--accept", action="store_true")
    steward_action_group.add_argument("--reject", action="store_true")
    steward_action_group.add_argument("--dismiss", action="store_true")
    steward_action_group.add_argument("--resolve", action="store_true")
    steward_action_group.add_argument("--request-evidence", action="store_true")
    steward_action_group.add_argument("--mark-stale", action="store_true")
    steward_action_group.add_argument("--keep-existing", action="store_true")
    steward_action_group.add_argument("--accept-new", action="store_true")
    steward_action_group.add_argument("--fork", action="store_true")
    steward_action_parser.add_argument("--reason", default="")
    steward_action_parser.add_argument("--reviewer", default="steward")

    self_model_parser = subparsers.add_parser("self-model")
    self_model_parser.add_argument("--compile", action="store_true")
    self_model_parser.add_argument("--output")

    growth_gate_parser = subparsers.add_parser("growth-gate")
    growth_gate_parser.add_argument(
        "action",
        choices=[action.value for action in GrowthGateAction],
    )
    growth_gate_parser.add_argument("--impact", default="low")

    growth_parser = subparsers.add_parser("growth")
    growth_parser.add_argument("--status")
    growth_parser.add_argument("--queue", action="store_true")

    subparsers.add_parser("conflicts")

    resolve_conflict_parser = subparsers.add_parser("resolve-conflict")
    resolve_conflict_parser.add_argument("conflict_id")
    conflict_decision_group = resolve_conflict_parser.add_mutually_exclusive_group(
        required=True
    )
    conflict_decision_group.add_argument("--accept-new", action="store_true")
    conflict_decision_group.add_argument("--keep-existing", action="store_true")
    conflict_decision_group.add_argument("--fork", action="store_true")
    resolve_conflict_parser.add_argument("--resolved-by", default="steward")
    resolve_conflict_parser.add_argument("--reason", required=True)

    propose_growth_parser = subparsers.add_parser("propose-growth")
    propose_growth_parser.add_argument("kind")
    propose_growth_parser.add_argument("--summary", required=True)
    propose_growth_parser.add_argument("--impact", default="low")
    propose_growth_parser.add_argument("--reason", default="")
    propose_growth_parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Evidence reference id or URI. May be repeated.",
    )

    accept_growth_parser = subparsers.add_parser("accept-growth")
    accept_growth_parser.add_argument("growth_id")
    accept_growth_parser.add_argument("--reason", default="")

    reject_growth_parser = subparsers.add_parser("reject-growth")
    reject_growth_parser.add_argument("growth_id")
    reject_growth_parser.add_argument("--reason", default="")

    review_growth_parser = subparsers.add_parser("review-growth")
    review_growth_parser.add_argument("growth_id")
    decision_group = review_growth_parser.add_mutually_exclusive_group(required=True)
    decision_group.add_argument("--accept", action="store_true")
    decision_group.add_argument("--reject", action="store_true")
    review_growth_parser.add_argument("--reviewer", default="operator")
    review_growth_parser.add_argument("--reason", default="")

    memory_signal_parser = subparsers.add_parser("memory-signal")
    memory_signal_parser.add_argument("memory_id")
    memory_signal_parser.add_argument(
        "--type",
        required=True,
        choices=["reinforced", "contradicted", "stale"],
    )
    memory_signal_parser.add_argument("--reason", default="")
    memory_signal_parser.add_argument("--confidence-delta", type=float)
    memory_signal_parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Evidence reference id or URI. May be repeated.",
    )

    anchor_parser = subparsers.add_parser("anchor-head")
    anchor_parser.add_argument("--authority", default="local_operator")
    anchor_parser.add_argument("--note", default="")

    subparsers.add_parser("verify-anchor")

    export_anchor_parser = subparsers.add_parser("export-anchor")
    export_anchor_parser.add_argument(
        "--output",
        default="reports/latest_anchor.json",
        help="Write the latest anchor verification checkpoint to this JSON file.",
    )

    report_parser = subparsers.add_parser("trace-report")
    report_parser.add_argument(
        "--html",
        help="Write a standalone HTML trace report to this path.",
    )

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument(
        "--html",
        default="reports/pca_dashboard.html",
        help="Write a standalone HTML dashboard to this path.",
    )

    cockpit_parser = subparsers.add_parser("cockpit")
    cockpit_parser.add_argument(
        "--html",
        default="reports/lucien_cockpit.html",
        help="Write the Lucien cockpit HTML to this path.",
    )

    gate_output_parser = subparsers.add_parser("gate-output")
    gate_output_parser.add_argument("text")
    gate_output_parser.add_argument("--channel", default="assistant")
    gate_output_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Output metadata as key=value. May be repeated.",
    )

    runtime_parser = subparsers.add_parser("runtime-signal")
    runtime_parser.add_argument(
        "state",
        choices=["GREEN", "AMBER", "RED", "green", "amber", "red"],
    )
    runtime_parser.add_argument("--source", default="runtime")
    runtime_parser.add_argument("--reason", default="")
    runtime_parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Runtime metric as key=value. May be repeated.",
    )

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("constraint")
    check_parser.add_argument("--value", default="true")

    breach_parser = subparsers.add_parser("breach")
    breach_parser.add_argument("constraint")
    breach_parser.add_argument("--severity", choices=["soft", "hard"], default="soft")

    fork_parser = subparsers.add_parser("fork")
    fork_parser.add_argument("child_id")
    fork_parser.add_argument("--reason", default="")

    transform_parser = subparsers.add_parser("transform")
    transform_parser.add_argument("transform")
    transform_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )
    transform_parser.add_argument(
        "--override",
        help="Override reason. Requires --authority.",
    )
    transform_parser.add_argument("--authority")
    transform_parser.add_argument(
        "--followup",
        action="append",
        default=[],
        help="Required follow-up action. May be repeated.",
    )

    override_parser = subparsers.add_parser("override")
    override_parser.add_argument("transform")
    override_parser.add_argument("--authority", required=True)
    override_parser.add_argument("--reason", required=True)
    override_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )
    override_parser.add_argument(
        "--followup",
        action="append",
        default=[],
        help="Required follow-up action. May be repeated.",
    )

    complete_parser = subparsers.add_parser("complete-followup")
    complete_parser.add_argument("followup_id")
    complete_parser.add_argument("--authority", default="operator")
    complete_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    fail_parser = subparsers.add_parser("fail-followup")
    fail_parser.add_argument("followup_id")
    fail_parser.add_argument("--reason", required=True)
    fail_parser.add_argument("--authority", default="steward")

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("audit_type")
    audit_parser.add_argument("--followup", required=True)
    audit_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    open_recovery_parser = subparsers.add_parser("open-recovery")
    open_recovery_parser.add_argument("--authority", required=True)
    open_recovery_parser.add_argument("--reason", required=True)

    subparsers.add_parser("recovery-status")

    complete_recovery_parser = subparsers.add_parser("complete-recovery-audit")
    complete_recovery_parser.add_argument("recovery_id")
    complete_recovery_parser.add_argument("--followup", required=True)
    complete_recovery_parser.add_argument("--authority", default="recovery_authority")
    complete_recovery_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    args = parser.parse_args()
    manifest, authorization_policy = apply_policy_packs(
        load_manifest(Path(args.manifest)),
        args.policy_pack,
        args.policies,
    )
    ledger = ContinuityLedger(args.ledger)

    if args.command == "seed-required":
        source_event_ids = []
        for constraint in manifest.constraints:
            if constraint.required:
                event = ledger.append(
                    "constraint.checked",
                    manifest.system_id,
                    {"constraint": constraint.name, "value": True},
                )
                source_event_ids.append(event.event_hash)
        claim = record_claim_if_changed(ledger, manifest, source_event_ids)
        print_json(
            {
                "seeded": True,
                "ledger": str(ledger.path),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "model-diagnostic":
        print_json({"model_adapter": model_environment_diagnostic()})
        return 0

    if args.command == "daily":
        daily = daily_command_center(ledger, manifest)
        if args.json:
            print_json({"daily": daily})
        else:
            print(render_daily_command_center_text(daily))
        return 0

    if args.command == "cold-open":
        report = cold_open_report(ledger, manifest)
        if args.json:
            print_json({"cold_open": report})
        else:
            print(render_cold_open_report_text(report))
        return 0

    if args.command == "daily-research-loop":
        result = run_auto_daily_research_loop(
            ledger,
            manifest,
            project_root=Path.cwd(),
            mission_id=args.mission,
            force=args.force,
            reason="manual CLI daily research loop",
        )
        if args.json:
            print_json({"daily_research_loop": result})
        else:
            print(render_auto_daily_research_loop_text(result))
        return 0

    if args.command == "research-autopilot":
        result = run_research_autopilot(
            ledger,
            manifest,
            project_root=Path.cwd(),
            force=args.force,
            reason="manual CLI research autopilot",
        )
        if args.json:
            print_json({"research_autopilot": result})
        else:
            print(render_research_autopilot_text(result))
        return 0

    if args.command == "coherence-corpus-index":
        result = index_coherence_corpus(
            ledger,
            manifest,
            project_root=Path.cwd(),
            mission_id=args.mission,
            roots=args.root or None,
            limit=args.limit,
            use_knowledge_hub=args.knowledge_hub,
            reason="manual CLI Coherence Physics corpus index",
        )
        if args.json:
            print_json({"coherence_corpus": result})
        else:
            print(render_coherence_corpus_index_text(result))
        return 0

    if args.command == "knowledge-hub-index":
        result = index_knowledge_hub(
            ledger,
            manifest,
            project_root=Path.cwd(),
            limit=args.limit,
            topic=args.topic,
            reason="manual CLI Master files knowledge hub index",
        )
        if args.json:
            print_json({"knowledge_hub": result})
        else:
            print(render_knowledge_hub_index_text(result))
        return 0

    if args.command == "knowledge-hub-sources":
        snapshot = knowledge_hub_snapshot(ledger.events(), topic=args.topic)
        if args.json:
            print_json({"knowledge_hub": snapshot})
        else:
            print(render_knowledge_hub_sources_text(snapshot))
        return 0

    if args.command == "coherence-source-notes":
        result = extract_source_notes_for_mission(
            ledger,
            manifest,
            project_root=Path.cwd(),
            mission_id=args.mission,
            limit_sources=args.limit,
            reason="manual CLI Coherence Physics source notes",
        )
        if args.json:
            print_json({"coherence_source_notes": result})
        else:
            print(render_source_notes_text(result))
        return 0

    if args.command == "coherence-paper-pipeline":
        result = run_coherence_paper_pipeline(
            ledger,
            manifest,
            project_root=Path.cwd(),
            mission_id=args.mission,
            corpus_roots=args.root or None,
            corpus_limit=args.limit,
            use_knowledge_hub=args.knowledge_hub,
            force=args.force,
            output_path=args.output,
            reason="manual CLI Coherence Physics paper pipeline",
        )
        if args.json:
            print_json({"coherence_paper_pipeline": result})
        else:
            print(render_coherence_paper_pipeline_text(result))
        return 0

    if args.command == "research-sandbox":
        status = research_sandbox_status(ledger, manifest)
        if args.json:
            print_json({"research_sandbox": status})
        else:
            print_json(status)
        return 0

    if args.command == "argument-graph-seed":
        result = seed_continuity_argument_graph(
            ledger,
            manifest,
            args.mission_id,
            project_root=Path.cwd(),
            reason="manual CLI argument graph seed",
        )
        if args.json:
            print_json({"argument_graph_seed": result})
        else:
            print(
                f"seeded argument graph: {result['node_count']} node(s), "
                f"{result['edge_count']} edge(s) "
                f"(+{result['created_node_count']} node(s), "
                f"+{result['created_edge_count']} edge(s) this run)"
            )
        return 0

    if args.command == "argument-graph-show":
        graph = mission_argument_graph(ledger, args.mission_id)
        if args.json:
            print_json({"argument_graph": graph})
        else:
            print(render_argument_graph_text(graph))
        return 0

    if args.command == "research-brief":
        result = create_research_output(
            ledger,
            manifest,
            args.mission_id,
            "research_brief",
            reason="manual research sandbox brief",
        )
        if args.json:
            print_json({"research_output": result})
        else:
            print(result["content"])
        return 0

    if args.command == "research-claim-map":
        result = create_research_output(
            ledger,
            manifest,
            args.mission_id,
            "claim_map_draft",
            reason="manual research sandbox claim map",
        )
        if args.json:
            print_json({"research_output": result})
        else:
            print(result["content"])
        return 0

    if args.command == "research-paper-draft":
        result = create_research_output(
            ledger,
            manifest,
            args.mission_id,
            "paper_draft",
            reason="manual research sandbox paper draft",
        )
        if args.json:
            print_json({"research_output": result})
        else:
            print(result["content"])
        return 0

    if args.command == "research-outputs":
        outputs = research_outputs_from_events(ledger.events(), args.mission)
        if args.json:
            print_json({"research_outputs": [output.to_dict() for output in outputs]})
        else:
            print(render_research_outputs_text(outputs))
        return 0

    if args.command == "research-pdf":
        result = export_research_pdf(ledger, manifest, args.mission_id, args.output)
        if args.json:
            print_json({"research_pdf": result})
        else:
            print(f"Research PDF written: {result['path']}")
        return 0

    if args.command == "research-review":
        result = research_review_desk(ledger, args.mission)
        if args.json:
            print_json({"research_review": result})
        else:
            print(render_research_review_text(result))
        return 0

    if args.command == "continuity-certification":
        certification = continuity_certification(ledger, manifest)
        if args.json:
            print_json({"continuity_certification": certification.to_dict()})
        else:
            print(render_continuity_certification_text(certification))
        return 0

    if args.command == "daily-plan":
        plan = daily_plan(ledger, manifest)
        if args.json:
            print_json({"daily_plan": plan})
        else:
            print(render_daily_plan_text(plan))
        return 0

    if args.command == "project-brief":
        brief = project_build_brief(Path.cwd())
        if args.json:
            print_json({"project_brief": brief})
        else:
            print(render_project_build_brief_text(brief))
        return 0

    if args.command == "build-review":
        review = build_review(Path.cwd())
        if args.json:
            print_json({"build_review": review})
        else:
            print(render_build_review_text(review))
        return 0

    if args.command == "commit-readiness":
        readiness = commit_readiness(Path.cwd())
        if args.json:
            print_json({"commit_readiness": readiness})
        else:
            print(render_commit_readiness_text(readiness))
        return 0

    if args.command == "checkpoint-story":
        story = checkpoint_story(Path.cwd())
        if args.json:
            print_json({"checkpoint_story": story})
        else:
            print(render_checkpoint_story_markdown(story))
        return 0

    if args.command == "next-build":
        proposal = next_governed_build(ledger, manifest)
        if args.json:
            print_json({"next_build": proposal})
        else:
            print(render_next_governed_build_text(proposal))
        return 0

    if args.command == "link-checkpoint":
        record = link_checkpoint_to_mission(
            ledger=ledger,
            identity_id=manifest.system_id,
            mission_id=args.mission,
            commit_hash=args.commit,
            mission_step_ids=args.step,
            evidence_ids=args.evidence,
            verification_checks=args.check,
            lesson_candidate=args.lesson,
            reason=args.reason,
            project_root=Path.cwd(),
        )
        print_json({"checkpoint_link": record.to_dict()})
        return 0

    if args.command == "checkpoint-history":
        history = checkpoint_history(ledger, args.mission)
        if args.json:
            print_json({"checkpoint_history": history})
        else:
            print(render_checkpoint_history_text(history))
        return 0

    if args.command == "checkpoint-lesson":
        result = propose_checkpoint_lesson(
            ledger,
            manifest.system_id,
            args.link_id,
            lesson_summary=args.summary,
            confidence=args.confidence,
            reason=args.reason,
        )
        print_json({"checkpoint_lesson": result})
        return 0

    if args.command == "checkpoint-skills":
        records = auto_propose_checkpoint_skill_candidates(
            ledger,
            manifest.system_id,
            minimum_checkpoints=args.minimum,
        )
        print_json({"skill_candidates": [record.to_dict() for record in records]})
        return 0

    if args.command == "autonomy-queue":
        items = autonomy_queue_items_from_events(ledger.events(), args.status)
        if args.json:
            print_json({"autonomy_queue": [item.to_dict() for item in items]})
        else:
            print(render_autonomy_queue_text(items))
        return 0

    if args.command == "autonomy-propose":
        payload = json.loads(args.payload)
        if not isinstance(payload, dict):
            raise ValueError("--payload must be a JSON object")
        item = propose_autonomy_action(
            ledger,
            manifest.system_id,
            args.type,
            reason=args.reason,
            payload=payload,
        )
        print_json({"autonomy_item": item.to_dict()})
        return 0

    if args.command == "autonomy-approve":
        item = review_autonomy_action(
            ledger,
            manifest.system_id,
            args.item_id,
            "approve",
            reason=args.reason,
        )
        print_json({"autonomy_item": item.to_dict()})
        return 0

    if args.command == "autonomy-reject":
        item = review_autonomy_action(
            ledger,
            manifest.system_id,
            args.item_id,
            "reject",
            reason=args.reason,
        )
        print_json({"autonomy_item": item.to_dict()})
        return 0

    if args.command == "autonomy-execute":
        result = execute_autonomy_action(
            ledger,
            manifest,
            args.item_id,
            project_root=Path.cwd(),
            reason=args.reason,
        )
        print_json({"autonomy_execution": result})
        return 0

    if args.command == "autonomy-execute-approved":
        results = execute_approved_autonomy_actions(
            ledger,
            manifest,
            project_root=Path.cwd(),
        )
        print_json({"autonomy_executions": results})
        return 0

    if args.command == "workbench-status":
        print_json({"workbench": workbench_status(ledger, manifest)})
        return 0

    if args.command == "startup-health":
        health = startup_health(ledger, manifest)
        if args.json:
            print_json({"startup_health": health})
        else:
            print(render_startup_health_text(health))
        return 0

    if args.command == "startup-fix":
        print_json(
            apply_startup_health_fix(
                ledger,
                manifest,
                args.action,
                reason=args.reason,
            )
        )
        return 0

    if args.command == "chat-once":
        print_json(
            chat_once(
                args.message,
                manifest_path=args.manifest,
                ledger_path=_chat_ledger_path(args.ledger),
                model_mode=args.model_mode,
                use_openai=args.use_openai,
            )
        )
        return 0

    if args.command == "live-chat":
        run_live_chat_server(
            host=args.host,
            port=args.port,
            manifest_path=args.manifest,
            ledger_path=_chat_ledger_path(args.ledger),
        )
        return 0

    if args.command == "demo":
        run_demo(
            host=args.host,
            port=args.port,
            manifest_path=args.manifest,
            ledger_path=(
                "data/lucien_chat.log"
                if args.ledger == "data/continuity.log"
                else args.ledger
            ),
            run_checks=not args.skip_checks,
            open_browser=not args.no_open,
            start_server=not args.no_server,
        )
        return 0

    if args.command == "anchor-head":
        anchor = append_ledger_anchor(
            ledger,
            args.anchors,
            authority=args.authority,
            note=args.note,
        )
        print_json(
            {
                "anchor_path": args.anchors,
                "anchor": anchor.to_dict(),
            }
        )
        return 0

    if args.command == "verify-anchor":
        verification = verify_latest_anchor(ledger, args.anchors)
        print_json(
            {
                "anchor_path": args.anchors,
                **verification.to_dict(),
            }
        )
        return 0

    if args.command == "export-anchor":
        export = export_latest_anchor(
            ledger=ledger,
            anchor_path=args.anchors,
            output_path=args.output,
        )
        print_json(
            {
                "output": args.output,
                **export.to_dict(),
            }
        )
        return 0

    if args.command == "constitution":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        if args.write:
            output_path = write_constitution_markdown(report, manifest, args.output)
            print_json(
                {
                    "output": str(output_path),
                    "summary": report.summary,
                }
            )
            return 0
        print(render_constitution_markdown(report, manifest), end="")
        return 0

    if args.command == "context":
        context = build_governed_context(
            ledger,
            manifest,
            mission_id=args.mission,
        )
        if args.prompt:
            print(context.render_prompt_context())
            return 0
        print_json(context.to_dict())
        return 0

    if args.command == "check":
        event = ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": args.constraint, "value": args.value},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command == "breach":
        event = ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": args.constraint, "severity": args.severity},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command == "fork":
        event = ledger.append(
            "identity.forked",
            manifest.system_id,
            {"child_id": args.child_id, "fork_reason": args.reason},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command in {"transform", "override"}:
        evidence = parse_key_values(args.evidence)
        evaluation = PolicyEngine().evaluate_transform(
            manifest,
            TransformRequest(transform=args.transform, evidence=evidence),
        )
        event = ledger.append(
            "transform.evaluated",
            manifest.system_id,
            {"transform": args.transform, **evaluation.to_dict()},
        )
        override_reason = getattr(args, "override", None) or getattr(args, "reason", None)
        if args.command == "override" or override_reason:
            if not args.authority:
                raise SystemExit("Override requires --authority.")
            if not evaluation.override_allowed:
                raise SystemExit(
                    f"Override is not allowed by policy pack: "
                    f"{evaluation.source_policy_pack or 'none'}"
                )
            authorization = authorize(
                args.authority,
                authorization_policy.override_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "override",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            required_followup = args.followup or evaluation.required_followups_on_override
            override = OverrideEngine().request_override(
                evaluation,
                OverrideRequest(
                    transform=args.transform,
                    authority=args.authority,
                    reason=override_reason,
                    required_followup=required_followup,
                ),
            )
            override_event = ledger.append(
                "transform.override",
                manifest.system_id,
                override.to_dict(),
            )
            followups = create_followups_for_override(
                ledger,
                manifest.system_id,
                override_event.event_hash,
                override.required_followup,
            )
            claim = record_claim_if_changed(
                ledger,
                manifest,
                [event.event_hash, override_event.event_hash],
            )
            print_json(
                {
                    "evaluation_event_hash": event.event_hash,
                    "authorization_event_hash": authorization_event.event_hash,
                    "override_event_hash": override_event.event_hash,
                    "override": override_event.payload,
                    "required_followups": [
                        record.to_dict() for record in followups
                    ],
                    "claim_record": claim.to_dict() if claim else None,
                }
            )
            return 0
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json(
            {
                "evaluation": event.payload,
                "event_hash": event.event_hash,
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "lineage":
        print_json(
            {
                "system_id": manifest.system_id,
                "lineage": [
                    record.to_dict() for record in lineage_records(ledger.events())
                ],
            }
        )
        return 0

    if args.command == "memories":
        memory_cards = memory_cards_from_events(
            ledger.events(),
            manifest.system_id,
        )
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(memory_cards),
                "memory_cards": [record.to_dict() for record in memory_cards],
            }
        )
        return 0

    if args.command == "memory-signals":
        records = memory_signal_records_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "memory_signals": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "memory-signal":
        record = record_memory_signal(
            ledger=ledger,
            identity_id=manifest.system_id,
            memory_id=args.memory_id,
            signal_type=args.type,
            reason=args.reason,
            evidence_refs=args.evidence_ref,
            confidence_delta=args.confidence_delta,
        )
        print_json({"memory_signal": record.to_dict()})
        return 0

    if args.command == "evidence-add":
        record = add_evidence(
            ledger=ledger,
            identity_id=manifest.system_id,
            source_type=args.type,
            source=args.source,
            summary=args.summary,
            confidence=args.confidence,
            reason=args.reason,
        )
        print_json({"evidence": record.to_dict()})
        return 0

    if args.command == "evidence-link":
        target_type, target_id = _evidence_target_from_args(args)
        try:
            record = link_evidence(
                ledger=ledger,
                identity_id=manifest.system_id,
                evidence_id=args.evidence_id,
                target_type=target_type,
                target_id=target_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"evidence_link": record.to_dict()})
        return 0

    if args.command == "evidence-review":
        if args.accept:
            status = "reviewed"
        elif args.dispute:
            status = "disputed"
        elif args.stale:
            status = "stale"
        else:
            status = "rejected"
        try:
            record = review_evidence(
                ledger=ledger,
                identity_id=manifest.system_id,
                evidence_id=args.evidence_id,
                review_status=status,
                reviewer=args.reviewer,
                confidence=args.confidence,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"evidence": record.to_dict()})
        return 0

    if args.command == "evidence-claim":
        try:
            record = add_evidence_claim(
                ledger=ledger,
                identity_id=manifest.system_id,
                statement=args.statement,
                evidence_ids=args.evidence_id,
                confidence=args.confidence,
                status=args.status,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"evidence_claim": record.to_dict()})
        return 0

    if args.command == "evidence-locker":
        snapshot = evidence_locker_snapshot(ledger.events())
        print_json({"system_id": manifest.system_id, **snapshot})
        return 0

    if args.command == "evidence-for":
        target_type, target_id = _evidence_target_from_args(args)
        records = evidence_for_target(ledger.events(), target_type, target_id)
        print_json(
            {
                "system_id": manifest.system_id,
                "target_type": target_type,
                "target_id": target_id,
                "count": len(records),
                "evidence": records,
            }
        )
        return 0

    if args.command == "missions":
        briefs = mission_briefs_from_events(ledger.events())
        if args.open:
            briefs = [
                brief
                for brief in briefs
                if brief.mission.status == MissionStatus.OPEN
            ]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(briefs),
                "missions": [brief.to_dict() for brief in briefs],
            }
        )
        return 0

    if args.command == "goal-create":
        goal = create_goal_record(
            ledger=ledger,
            identity_id=manifest.system_id,
            title=args.title,
            purpose=args.purpose,
            success_criteria=args.success_criteria,
            priority=args.priority,
            next_recommended_action=args.next_action,
            review_state=args.review_state,
            reason=args.reason,
        )
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "goals":
        goals = goal_records_from_events(ledger.events())
        if args.active:
            goals = [
                goal
                for goal in goals
                if goal.status == GoalStatus.ACTIVE
            ]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(goals),
                "goals": [goal.to_dict() for goal in goals],
            }
        )
        return 0

    if args.command == "coherence-seed":
        results = seed_coherence_physics_goals(ledger, manifest)
        if args.json:
            print_json({"coherence_seed": [result.to_dict() for result in results]})
        else:
            print(render_coherence_seed_text(results))
        return 0

    if args.command == "goal-status":
        try:
            goal = next(
                goal
                for goal in goal_records_from_events(ledger.events())
                if goal.goal_id == args.goal_id
            )
        except StopIteration as exc:
            raise SystemExit(f"Goal not found: {args.goal_id}") from exc
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "goal-link-mission":
        try:
            goal = link_goal_mission(
                ledger,
                manifest.system_id,
                args.goal_id,
                args.mission_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "goal-add-blocker":
        try:
            goal = add_goal_blocker(
                ledger,
                manifest.system_id,
                args.goal_id,
                args.text,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "goal-complete":
        try:
            goal = update_goal_status(
                ledger,
                manifest.system_id,
                args.goal_id,
                GoalStatus.COMPLETED,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "goal-archive":
        try:
            goal = update_goal_status(
                ledger,
                manifest.system_id,
                args.goal_id,
                GoalStatus.ARCHIVED,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"goal": goal.to_dict()})
        return 0

    if args.command == "mission-open":
        mission = open_mission(
            ledger=ledger,
            identity_id=manifest.system_id,
            title=args.title,
            problem_statement=args.problem,
            values=args.value,
            reason=args.reason,
        )
        print_json({"mission": mission.to_dict()})
        return 0

    if args.command == "mission-add":
        item = add_mission_item(
            ledger=ledger,
            identity_id=manifest.system_id,
            mission_id=args.mission_id,
            kind=args.kind,
            summary=args.summary,
            status=args.status,
            confidence=args.confidence,
            evidence_refs=args.evidence_ref,
            reason=args.reason,
        )
        print_json({"mission_item": item.to_dict()})
        return 0

    if args.command == "mission-status":
        mission = update_mission_status(
            ledger=ledger,
            identity_id=manifest.system_id,
            mission_id=args.mission_id,
            status=args.status,
            reason=args.reason,
        )
        print_json({"mission": mission.to_dict()})
        return 0

    if args.command == "mission-flow":
        if args.all:
            flows = mission_flows_from_events(ledger.events())
            print_json(
                {
                    "system_id": manifest.system_id,
                    "count": len(flows),
                    "flows": [flow.to_dict() for flow in flows],
                }
            )
            return 0
        if not args.mission_id:
            raise SystemExit("mission-flow requires MISSION_ID unless --all is used.")
        flow = mission_flow(ledger, args.mission_id)
        print_json({"mission_flow": flow.to_dict()})
        return 0

    if args.command == "mission-onboarding":
        print_json(
            {
                "mission_onboarding": mission_onboarding_state(
                    ledger,
                    args.mission_id,
                ).to_dict()
            }
        )
        return 0

    if args.command == "mission-onboard":
        print_json(
            create_mission_onboarding_pack(
                ledger,
                manifest.system_id,
                args.mission_id,
                reason=args.reason,
            )
        )
        return 0

    if args.command == "mission-advance":
        flow = mission_flow(ledger, args.mission_id)
        print_json(
            {
                "mission_id": args.mission_id,
                "can_advance": flow.ready_to_advance,
                "phase": flow.phase.value,
                "blockers": flow.blockers,
                "next_action": flow.next_action,
            }
        )
        return 0

    if args.command == "mission-steps":
        steps = mission_step_records_from_events(ledger.events(), args.mission)
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(steps),
                "steps": [step.to_dict() for step in steps],
            }
        )
        return 0

    if args.command == "mission-step-propose":
        step = propose_mission_step(
            ledger=ledger,
            identity_id=manifest.system_id,
            mission_id=args.mission_id,
            description=args.description,
            risk_level=args.risk,
            required_tool=args.tool,
            expected_outcome=args.expected_outcome,
            reason=args.reason,
        )
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "mission-next-step":
        try:
            if args.apply:
                result = propose_autonomous_mission_step(
                    ledger,
                    manifest.system_id,
                    args.mission_id,
                )
            else:
                recommendation = recommend_next_mission_step(
                    ledger,
                    manifest.system_id,
                    args.mission_id,
                )
                result = {
                    "recommendation": recommendation.to_dict(),
                    "mission_step": None,
                }
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_next_step": result})
        return 0

    if args.command == "mission-step-approve":
        try:
            step = approve_mission_step(
                ledger,
                manifest.system_id,
                args.step_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "mission-step-start":
        try:
            step = start_mission_step(
                ledger,
                manifest.system_id,
                args.step_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "mission-step-complete":
        try:
            step = complete_mission_step(
                ledger,
                manifest.system_id,
                args.step_id,
                actual_outcome=args.actual_outcome,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "mission-step-fail":
        try:
            step = fail_mission_step(
                ledger,
                manifest.system_id,
                args.step_id,
                failure_note=args.failure_note,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "mission-step-block":
        try:
            step = block_mission_step(
                ledger,
                manifest.system_id,
                args.step_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"mission_step": step.to_dict()})
        return 0

    if args.command == "tools":
        print_json(
            {
                "system_id": manifest.system_id,
                "tools": [spec.to_dict() for spec in tool_specs()],
            }
        )
        return 0

    if args.command == "tool-permission":
        try:
            permission = check_tool_permission(
                ledger,
                manifest.system_id,
                args.step_id,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"tool_permission": permission.to_dict()})
        return 0

    if args.command == "tool-dry-run":
        try:
            result = dry_run_tool_for_step(
                ledger,
                manifest.system_id,
                args.step_id,
                tool_args=parse_key_values(args.arg),
                project_root=Path.cwd(),
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"tool_dry_run": result})
        return 0

    if args.command == "tool-run":
        try:
            result = run_tool_for_step(
                ledger,
                manifest.system_id,
                args.step_id,
                tool_args=parse_key_values(args.arg),
                project_root=Path.cwd(),
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"tool_run": result})
        return 0

    if args.command == "tool-history":
        events = ledger.events()
        print_json(
            {
                "system_id": manifest.system_id,
                "permissions": [
                    record.to_dict()
                    for record in tool_permission_records_from_events(events)
                ],
                "executions": [
                    record.to_dict()
                    for record in tool_execution_records_from_events(events)
                ],
                "previews": [
                    record.to_dict()
                    for record in tool_preview_records_from_events(events)
                ],
            }
        )
        return 0

    if args.command == "learning-review":
        try:
            if args.latest_session or (not args.mission and not args.step):
                result = run_latest_session_learning_review(
                    ledger,
                    manifest.system_id,
                    apply=args.apply,
                    reason=args.reason,
                )
            elif args.mission:
                result = run_learning_review(
                    ledger,
                    manifest.system_id,
                    "mission",
                    args.mission,
                    apply=args.apply,
                    reason=args.reason,
                )
            else:
                result = run_learning_review(
                    ledger,
                    manifest.system_id,
                    "step",
                    args.step,
                    apply=args.apply,
                    reason=args.reason,
                )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"learning_review": result})
        return 0

    if args.command == "learning-reviews":
        records = learning_review_records_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "learning_reviews": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "skill-candidates":
        candidates = skill_candidates_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(candidates),
                "skill_candidates": [record.to_dict() for record in candidates],
            }
        )
        return 0

    if args.command == "skill-candidate":
        try:
            candidate = propose_skill_candidate(
                ledger=ledger,
                identity_id=manifest.system_id,
                step_id=args.step_id,
                name=args.name,
                procedure=args.procedure,
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"skill_candidate": candidate.to_dict()})
        return 0

    if args.command == "skill-auto-propose":
        records = auto_propose_skill_candidates(
            ledger,
            manifest.system_id,
            minimum_repetitions=args.minimum_repetitions,
        )
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "skill_candidates": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "skill-review":
        try:
            candidate = review_skill_candidate(
                ledger=ledger,
                identity_id=manifest.system_id,
                skill_id=args.skill_id,
                decision="accept" if args.accept else "reject",
                reason=args.reason,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        print_json({"skill_candidate": candidate.to_dict()})
        return 0

    if args.command == "skills":
        skills = accepted_skills_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(skills),
                "skills": [record.to_dict() for record in skills],
            }
        )
        return 0

    if args.command == "skill-suggestions":
        suggestions = skill_suggestions_for_mission(ledger.events(), args.mission_id)
        print_json(
            {
                "system_id": manifest.system_id,
                "mission_id": args.mission_id,
                "count": len(suggestions),
                "suggestions": suggestions,
            }
        )
        return 0

    if args.command == "reflect":
        record = record_reflection(ledger, manifest)
        tasks = open_tasks_from_reflection(ledger, record)
        print_json(
            {
                "reflection": record.to_dict(),
                "opened_tasks": [task.to_dict() for task in tasks],
            }
        )
        return 0

    if args.command == "reflections":
        records = reflection_records_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "reflections": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "reflection-queue":
        tasks = reflection_task_records_from_events(ledger.events())
        if args.open:
            tasks = [task for task in tasks if task.status.value == "open"]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(tasks),
                "tasks": [task.to_dict() for task in tasks],
            }
        )
        return 0

    if args.command == "reflection-task":
        status = "resolved" if args.resolve else "dismissed"
        task = update_reflection_task(
            ledger,
            manifest.system_id,
            args.task_id,
            status,
            reason=args.reason,
        )
        print_json({"task": task.to_dict()})
        return 0

    if args.command == "steward-inbox":
        items = steward_inbox(
            ledger,
            source_type=args.type,
            high_priority=args.high,
        )
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(items),
                "items": [item.to_dict() for item in items],
            }
        )
        return 0

    if args.command == "steward-action":
        if args.accept:
            action = "accept"
        elif args.reject:
            action = "reject"
        elif args.dismiss:
            action = "dismiss"
        elif args.resolve:
            action = "resolve"
        elif args.request_evidence:
            action = "request_evidence"
        elif args.mark_stale:
            action = "mark_stale"
        elif args.keep_existing:
            action = "keep_existing"
        elif args.accept_new:
            action = "accept_new"
        else:
            action = "fork"
        print_json(
            apply_steward_inbox_action(
                ledger,
                manifest,
                args.inbox_id,
                action,
                reason=args.reason,
                reviewer=args.reviewer,
            )
        )
        return 0

    if args.command == "sessions":
        print_json(
            {
                "system_id": manifest.system_id,
                "sessions": [
                    record.to_dict()
                    for record in chat_sessions_from_events(ledger.events())
                ],
                "turns": [
                    record.to_dict()
                    for record in chat_turns_from_events(ledger.events())
                ],
            }
        )
        return 0

    if args.command == "session-replay":
        session_id = args.session_id
        if args.latest or not session_id:
            session_id = latest_session_id(ledger)
        if not session_id:
            raise SystemExit("No chat sessions found.")
        replay = build_session_replay(ledger, manifest, session_id)
        payload = replay.to_dict()
        if args.html:
            payload["html_path"] = str(write_session_replay_html(replay, args.html))
        print_json(payload)
        return 0

    if args.command == "self-model":
        self_model = derive_self_model(
            ledger.events(),
            manifest.system_id,
        )
        if args.compile:
            compiled = compile_self_model(self_model)
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(compiled, encoding="utf-8")
            print(compiled, end="")
            return 0
        print_json({"self_model": self_model.to_dict()})
        return 0

    if args.command == "growth-gate":
        current_claim, _, _ = derive_current_claim(ledger, manifest)
        decision = GrowthGate().evaluate(
            current_claim,
            args.action,
            args.impact,
        )
        print_json(
            {
                "current_continuity_claim": current_claim,
                "growth_gate": decision.to_dict(),
            }
        )
        return 0

    if args.command == "growth":
        records = growth_records_from_events(ledger.events())
        if args.queue:
            records = [
                record
                for record in records
                if record.status
                in {GrowthStatus.PROPOSED, GrowthStatus.REQUIRES_REVIEW}
            ]
        if args.status:
            records = [record for record in records if record.status.value == args.status]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "growth": [record.to_dict() for record in records],
                "reviews": [
                    record.to_dict()
                    for record in growth_review_records_from_events(ledger.events())
                ],
            }
        )
        return 0

    if args.command == "conflicts":
        conflicts = growth_conflict_records_from_events(ledger.events())
        resolutions = growth_conflict_resolution_records_from_events(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(conflicts),
                "conflicts": [record.to_dict() for record in conflicts],
                "resolutions": [record.to_dict() for record in resolutions],
            }
        )
        return 0

    if args.command == "resolve-conflict":
        if args.accept_new:
            decision = "accept_new"
        elif args.keep_existing:
            decision = "keep_existing"
        else:
            decision = "fork"
        resolution = resolve_growth_conflict(
            ledger,
            manifest.system_id,
            args.conflict_id,
            decision,
            resolved_by=args.resolved_by,
            reason=args.reason,
        )
        resolved_tasks = resolve_matching_reflection_tasks(
            ledger,
            manifest.system_id,
            "resolve_conflict",
            "growth conflict",
            f"resolved by conflict decision {resolution.resolution_id}",
        )
        print_json(
            {
                "resolution": resolution.to_dict(),
                "resolved_tasks": [task.to_dict() for task in resolved_tasks],
            }
        )
        return 0

    if args.command == "propose-growth":
        record = propose_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            kind=args.kind,
            summary=args.summary,
            identity_impact=args.impact,
            evidence_refs=args.evidence_ref,
            reason=args.reason,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        print_json({"growth": record.to_dict()})
        return 0

    if args.command == "accept-growth":
        record = accept_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            growth_id=args.growth_id,
            reason=args.reason,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        print_json({"growth": record.to_dict()})
        return 0

    if args.command == "reject-growth":
        record = reject_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            growth_id=args.growth_id,
            reason=args.reason,
        )
        print_json({"growth": record.to_dict()})
        return 0

    if args.command == "review-growth":
        decision = (
            GrowthReviewDecision.ACCEPT
            if args.accept
            else GrowthReviewDecision.REJECT
        )
        growth, review = review_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            growth_id=args.growth_id,
            decision=decision,
            reviewer=args.reviewer,
            reason=args.reason,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        print_json(
            {
                "growth": growth.to_dict(),
                "review": review.to_dict(),
                "self_model": derive_self_model(
                    ledger.events(),
                    manifest.system_id,
                ).to_dict(),
            }
        )
        return 0

    if args.command == "runtime-signal":
        runtime = PCAIdentityRuntime(
            manifest=manifest,
            ledger=ledger,
            signal_source=args.source,
        )
        result = runtime.record_runtime_signal(
            args.state,
            metrics=parse_key_values(args.metric),
            reason=args.reason,
        )
        print_json(result.to_dict())
        return 0

    if args.command == "trace-report":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        output = report.to_dict()
        if args.html:
            output["html_path"] = str(write_trace_report_html(report, args.html))
        print_json(output)
        return 0

    if args.command == "dashboard":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        html_path = write_dashboard_html(report, args.html)
        print_json(
            {
                "html_path": str(html_path),
                "summary": report.summary,
            }
        )
        return 0

    if args.command == "cockpit":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        html_path = write_lucien_cockpit_html(report, args.html)
        print_json(
            {
                "html_path": str(html_path),
                "summary": report.summary,
            }
        )
        return 0

    if args.command == "gate-output":
        runtime = PCAIdentityRuntime(manifest=manifest, ledger=ledger)
        wrapper = PCAOutputWrapper(runtime)
        envelope = wrapper.emit(
            args.text,
            channel=args.channel,
            metadata=parse_key_values(args.metadata),
        )
        print_json(envelope.to_dict())
        return 0

    if args.command == "followups":
        records = followups_from_events(ledger.events())
        if args.status:
            records = [record for record in records if record.status.value == args.status]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "followups": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "claims":
        claims = claims_from_events(ledger.events())
        current = claims[-1] if claims else None
        if args.current and not args.history:
            print_json(
                {
                    "system_id": manifest.system_id,
                    "current": current.to_dict() if current else None,
                }
            )
            return 0
        print_json(
            {
                "system_id": manifest.system_id,
                "current": current.to_dict() if current else None,
                "history": [claim.to_dict() for claim in claims],
            }
        )
        return 0

    if args.command == "open-recovery":
        authorization = authorize(
            args.authority,
            authorization_policy.recovery_min_authority,
            authorization_policy,
        )
        authorization_event = log_authorization_check(
            ledger,
            manifest,
            "open-recovery",
            args.authority,
            authorization,
        )
        if not authorization.allowed:
            raise SystemExit(authorization.reason)
        current_claim = current_claim_record(ledger.events())
        if current_claim is not None and current_claim.claim == "certified_continuity":
            raise SystemExit("Recovery cannot open from certified_continuity.")
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by=args.authority,
            reason=args.reason,
            source_claim_id=current_claim.claim_id if current_claim else None,
        )
        recovery_event = ledger.append(
            "recovery_opened",
            manifest.system_id,
            recovery.to_dict(),
        )
        followups = []
        from pca import required_evidence_for

        for followup_type in recovery.required_followups:
            followup = FollowUpRecord.create(
                identity_id=manifest.system_id,
                source_event_id=recovery_event.event_hash,
                followup_type=followup_type,
                required_evidence=required_evidence_for(followup_type),
                reason=f"Created by recovery path {recovery.recovery_id}.",
            )
            ledger.append("followup_created", manifest.system_id, followup.to_dict())
            followups.append(followup)
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [authorization_event.event_hash, recovery_event.event_hash],
        )
        print_json(
            {
                "authorization_event_hash": authorization_event.event_hash,
                "recovery_event_hash": recovery_event.event_hash,
                "recovery": recovery.to_dict(),
                "required_followups": [record.to_dict() for record in followups],
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "recovery-status":
        records = recovery_records_from_events(ledger.events())
        current = current_recovery_record(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "current": current.to_dict() if current else None,
                "history": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "speak-gate":
        current_claim, _, _ = derive_current_claim(ledger, manifest)
        decision = OutputGate().evaluate(current_claim)
        print_json(
            {
                "system_id": manifest.system_id,
                "output_gate": decision.to_dict(),
            }
        )
        return 0

    if args.command == "complete-recovery-audit":
        authorization = authorize(
            args.authority,
            authorization_policy.recovery_min_authority,
            authorization_policy,
        )
        authorization_event = log_authorization_check(
            ledger,
            manifest,
            "complete-recovery-audit",
            args.authority,
            authorization,
        )
        if not authorization.allowed:
            raise SystemExit(authorization.reason)
        recovery = find_recovery(ledger.events(), args.recovery_id)
        if recovery is None:
            raise SystemExit(f"Unknown recovery: {args.recovery_id}")
        followup = find_followup(ledger.events(), args.followup)
        if followup is None:
            raise SystemExit(f"Unknown follow-up: {args.followup}")
        evidence = parse_key_values(args.evidence)
        audit = AuditEngine().run_audit(
            identity_id=manifest.system_id,
            audit_type="recovery",
            evidence=evidence,
            source_transform_event_id=followup.source_event_id,
            followup_id=followup.followup_id,
        )
        audit_event = ledger.append(
            "post_transform_audit",
            manifest.system_id,
            audit.to_dict(),
        )
        if audit.outcome == AuditOutcome.CERTIFY_CONTINUITY:
            updated_followup = followup.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason=f"Completed by recovery audit {audit.audit_id}.",
            )
            recovery_status = RecoveryStatus.CERTIFIED
        else:
            updated_followup = followup.with_status(
                FollowUpStatus.FAILED,
                provided_evidence=evidence,
                reason=audit.reason,
            )
            recovery_status = RecoveryStatus.REJECTED
        followup_event = ledger.append(
            "followup_updated",
            manifest.system_id,
            updated_followup.to_dict(),
        )
        updated_recovery = recovery.with_status(
            recovery_status,
            evidence=evidence,
        )
        recovery_event = ledger.append(
            "recovery_updated",
            manifest.system_id,
            updated_recovery.to_dict(),
        )
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [
                authorization_event.event_hash,
                audit_event.event_hash,
                followup_event.event_hash,
                recovery_event.event_hash,
            ],
        )
        print_json(
            {
                "authorization_event_hash": authorization_event.event_hash,
                "audit_event_hash": audit_event.event_hash,
                "followup_event_hash": followup_event.event_hash,
                "recovery_event_hash": recovery_event.event_hash,
                "audit": audit.to_dict(),
                "recovery": updated_recovery.to_dict(),
                "followup": updated_followup.to_dict(),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command in {"complete-followup", "fail-followup"}:
        record = find_followup(ledger.events(), args.followup_id)
        if record is None:
            raise SystemExit(f"Unknown follow-up: {args.followup_id}")
        if args.command == "complete-followup":
            authorization = authorize(
                args.authority,
                authorization_policy.complete_followup_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "complete-followup",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            evidence = parse_key_values(args.evidence)
            missing = [item for item in record.required_evidence if item not in evidence]
            if missing:
                raise SystemExit(
                    f"Missing required follow-up evidence: {', '.join(missing)}"
                )
            updated = record.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason="Follow-up completed with required evidence.",
            )
        else:
            authorization = authorize(
                args.authority,
                authorization_policy.fail_followup_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "fail-followup",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            updated = record.with_status(FollowUpStatus.FAILED, reason=args.reason)
        event = ledger.append(
            "followup_updated",
            manifest.system_id,
            updated.to_dict(),
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json(
            {
                "event_hash": event.event_hash,
                "authorization_event_hash": authorization_event.event_hash,
                "followup": updated.to_dict(),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "audit":
        followup = find_followup(ledger.events(), args.followup)
        if followup is None:
            raise SystemExit(f"Unknown follow-up: {args.followup}")
        evidence = parse_key_values(args.evidence)
        audit = AuditEngine().run_audit(
            identity_id=manifest.system_id,
            audit_type=args.audit_type,
            evidence=evidence,
            source_transform_event_id=followup.source_event_id,
            followup_id=followup.followup_id,
        )
        audit_event = ledger.append(
            "post_transform_audit",
            manifest.system_id,
            audit.to_dict(),
        )

        followup_event = None
        updated_followup = None
        if audit.outcome == AuditOutcome.CERTIFY_CONTINUITY:
            updated_followup = followup.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason=f"Completed by audit {audit.audit_id}.",
            )
        elif audit.outcome == AuditOutcome.MARK_CONTINUITY_BREAK:
            updated_followup = followup.with_status(
                FollowUpStatus.FAILED,
                provided_evidence=evidence,
                reason=audit.reason,
            )

        if updated_followup is not None:
            followup_event = ledger.append(
                "followup_updated",
                manifest.system_id,
                updated_followup.to_dict(),
            )
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [
                event_hash
                for event_hash in [
                    audit_event.event_hash,
                    followup_event.event_hash if followup_event else None,
                ]
                if event_hash
            ],
        )

        print_json(
            {
                "audit_event_hash": audit_event.event_hash,
                "audit": audit_event.payload,
                "followup_event_hash": (
                    followup_event.event_hash if followup_event else None
                ),
                "followup": (
                    updated_followup.to_dict() if updated_followup else followup.to_dict()
                ),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )
    current_claim, blocking_followups, _ = derive_current_claim(ledger, manifest)
    recorded_claim = current_claim_record(ledger.events())
    print_json(
        {
            "system_id": manifest.system_id,
            "name": manifest.name,
            "state": evaluation.state.value,
            "current_continuity_claim": current_claim,
            "output_gate": OutputGate().evaluate(current_claim).to_dict(),
            "recorded_claim": recorded_claim.to_dict() if recorded_claim else None,
            "blocking_followups": len(blocking_followups),
            "blocking_followup_ids": [
                record.followup_id for record in blocking_followups
            ],
            "reasons": evaluation.reasons,
            "chain_valid": ledger.verify_chain(),
            "event_count": len(ledger.events()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
