import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pca.model_adapter as model_adapter_module
from lucien import LucienChatShell
from pca.demo_live import prepare_demo_artifacts
from pca.live_chat import _apply_steward_action, chat_once
from pca import (
    AuditEngine,
    AuditOutcome,
    AuthorityClass,
    AuthorizationCheckRecord,
    AuthorizationPolicy,
    ContinuityEvaluator,
    ContinuityEvent,
    ContinuityCertification,
    ContinuityClaimRecord,
    ContinuityLedger,
    ContinuityStatus,
    CSMRuntimeBridge,
    EVALUATION_PRECEDENCE,
    EchoAdapter,
    FollowUpRecord,
    FollowUpStatus,
    GrowthReviewDecision,
    GrowthStatus,
    IdentityManifest,
    IdentityState,
    LucienGovernedRuntime,
    MissionPhase,
    MissionItemKind,
    MissionStepApprovalStatus,
    MissionStepExecutionStatus,
    MissionStepRisk,
    MissionStatus,
    ModelAdapterError,
    ModelMessage,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    OverrideEngine,
    OverrideRequest,
    OutputGate,
    OutputMode,
    PCAOutputWrapper,
    PCAIdentityRuntime,
    PersistenceConstraint,
    PolicyDecision,
    PolicyEngine,
    RecoveryRecord,
    RecoveryStatus,
    SkillCandidateStatus,
    TransformRequest,
    accepted_skills_from_events,
    add_evidence,
    add_evidence_claim,
    append_ledger_anchor,
    active_followups,
    auto_daily_research_loop_records_from_events,
    autonomy_queue_items_from_events,
    auto_propose_checkpoint_skill_candidates,
    authorization_policy_from_packs,
    adapter_for_model_mode,
    adapter_from_environment,
    authorize,
    auto_propose_skill_candidates,
    build_review,
    build_governed_context,
    build_trace_report,
    build_manifest_from_packs,
    build_manifest_from_policy_results,
    build_session_replay,
    claims_from_events,
    chat_sessions_from_events,
    chat_turns_from_events,
    checkpoint_history,
    classify_research_action,
    create_research_output,
    seed_coherence_physics_goals,
    latest_auto_daily_research_loop,
    checkpoint_link_records_from_events,
    checkpoint_lesson_candidates_from_events,
    checkpoint_skill_candidates_from_events,
    checkpoint_story,
    compile_self_model,
    commit_readiness,
    continuity_claim_from_followups,
    continuity_certification,
    current_claim_record,
    daily_command_center,
    daily_plan,
    derive_current_claim,
    derive_self_model,
    estimate_model_usage,
    evidence_for_target,
    evidence_locker_snapshot,
    execute_approved_autonomy_actions,
    execute_autonomy_action,
    evidence_records_from_events,
    accept_growth,
    add_mission_item,
    approve_mission_step,
    block_mission_step,
    complete_mission_step,
    create_goal_record,
    create_mission_onboarding_pack,
    export_latest_anchor,
    fail_mission_step,
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    goal_records_from_events,
    growth_records_from_events,
    growth_review_records_from_events,
    load_policy_directory,
    load_policy_pack,
    lineage_records,
    memory_cards_from_events,
    memory_signal_records_from_events,
    model_environment_diagnostic,
    mission_briefs_from_events,
    next_governed_build,
    recommend_next_mission_step,
    propose_autonomous_mission_step,
    propose_autonomy_action,
    propose_checkpoint_lesson,
    mission_autonomy_recommendations_from_events,
    run_learning_review,
    run_latest_session_learning_review,
    learning_review_records_from_events,
    run_auto_daily_research_loop,
    mission_flow,
    mission_flows_from_events,
    mission_onboarding_state,
    mission_items_from_events,
    mission_records_from_events,
    mission_step_records_from_events,
    merge_policy_packs,
    open_mission,
    open_tasks_from_reflection,
    required_evidence_for,
    autonomy_execution_records_from_events,
    render_dashboard_html,
    render_build_review_text,
    render_autonomy_queue_text,
    render_checkpoint_history_text,
    render_checkpoint_story_markdown,
    render_coherence_seed_text,
    render_commit_readiness_text,
    render_project_build_brief_text,
    render_research_outputs_text,
    render_constitution_markdown,
    render_lucien_cockpit_html,
    render_next_governed_build_text,
    render_session_replay_html,
    render_trace_report_html,
    recovery_records_from_events,
    research_outputs_from_events,
    research_sandbox_status,
    safe_load_policy_pack,
    select_brain_route,
    propose_growth,
    project_build_brief,
    propose_skill_candidate,
    propose_mission_step,
    record_memory_signal,
    record_growth_conflict,
    record_reflection,
    reflection_records_from_events,
    reflection_task_records_from_events,
    resolve_growth_conflict,
    resolve_matching_reflection_tasks,
    review_evidence,
    review_autonomy_action,
    link_checkpoint_to_mission,
    link_evidence,
    link_goal_mission,
    review_skill_candidate,
    review_growth,
    skill_candidates_from_events,
    skill_suggestions_for_mission,
    update_mission_status,
    update_reflection_task,
    start_mission_step,
    startup_health,
    apply_startup_health_fix,
    steward_inbox,
    apply_steward_inbox_action,
    run_tool_for_step,
    dry_run_tool_for_step,
    tool_execution_records_from_events,
    tool_permission_records_from_events,
    tool_preview_records_from_events,
    tool_specs,
    workbench_status,
    verify_latest_anchor,
    write_constitution_markdown,
    write_session_replay_html,
)


def load_manifest():
    with open("examples/minimal_identity.json", encoding="utf-8") as handle:
        return IdentityManifest.from_dict(json.load(handle))


def _restore_env(name, value):
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def event_at(event_type, subject_id, payload, timestamp):
    return ContinuityEvent(
        event_type=event_type,
        subject_id=subject_id,
        payload=payload,
        timestamp=timestamp.isoformat(),
    ).with_hash()


def manifest_with_freshness(freshness_seconds):
    manifest = load_manifest()
    constraints = [
        PersistenceConstraint(
            name=constraint.name,
            kind=constraint.kind,
            required=constraint.required,
            threshold=constraint.threshold,
            freshness_seconds=(
                freshness_seconds if constraint.required else constraint.freshness_seconds
            ),
            description=constraint.description,
        )
        for constraint in manifest.constraints
    ]
    return IdentityManifest(
        system_id=manifest.system_id,
        name=manifest.name,
        version=manifest.version,
        origin=manifest.origin,
        invariants=manifest.invariants,
        constraints=constraints,
        allowed_transforms=manifest.allowed_transforms,
        transform_policies=manifest.transform_policies,
    )


def test_continuous_identity_when_required_constraints_are_checked(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.CONTINUOUS


def test_stale_required_evidence_suspends_identity():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=61)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == [
        "required constraint evidence is stale: ledger_integrity",
        "required constraint evidence is stale: origin_traceability",
    ]


def test_fresh_required_evidence_restores_continuous_identity():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    fresh_time = now - timedelta(seconds=30)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            fresh_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            fresh_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.CONTINUOUS


def test_echo_adapter_generates_without_external_credentials():
    adapter = EchoAdapter()

    response = adapter.generate(
        messages=[ModelMessage(role="user", content="what changed?")],
        system_context="Continuity is certified.",
    )

    assert response.provider == "echo"
    assert "what changed?" in response.text
    assert "PCA" in response.text


def test_echo_adapter_uses_governed_context_for_next_action():
    adapter = EchoAdapter()

    response = adapter.generate(
        messages=[ModelMessage(role="user", content="what is your status?")],
        system_context="\n".join(
            [
                "Current continuity claim: review_required",
                "Accepted memory cards: 2",
                "Accepted growth records: 3",
                "steward_inbox (unified_review_pressure): 4 item(s)",
            ]
        ),
    )

    assert "identity claims qualified" in response.text
    assert "2 accepted memory card" in response.text
    assert "3 accepted growth record" in response.text
    assert "Steward Inbox" in response.text


def test_adapter_from_environment_uses_echo_without_api_key(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    try:
        adapter = adapter_from_environment(env_path=str(tmp_path / "missing.env"))
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model

    assert isinstance(adapter, EchoAdapter)


def test_model_environment_diagnostic_reports_blank_local_env_without_key(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=\nLUCIEN_MODEL=gpt-4.1-mini\n",
        encoding="utf-8",
    )
    try:
        diagnostic = model_environment_diagnostic(env_path=str(env_path))
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model
        else:
            os.environ.pop("LUCIEN_MODEL", None)

    assert diagnostic["env_file_exists"] is True
    assert diagnostic["env_file_plain_text"] is True
    assert diagnostic["openai_key_present"] is False
    assert diagnostic["configured_provider"] == "echo"
    assert "sk-" not in json.dumps(diagnostic)


def test_adapter_from_environment_loads_local_dotenv(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        'OPENAI_API_KEY="local-test-key"\nLUCIEN_MODEL=test-model\n',
        encoding="utf-8",
    )
    try:
        adapter = adapter_from_environment(env_path=str(env_path))
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model
        else:
            os.environ.pop("LUCIEN_MODEL", None)

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.model == "test-model"


def test_serious_only_model_mode_uses_echo_until_openai_requested(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-proj-local-test-key\nLUCIEN_MODEL=test-model\n",
        encoding="utf-8",
    )
    try:
        adapter = adapter_for_model_mode(
            "serious_only",
            use_openai=False,
            env_path=str(env_path),
        )
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model
        else:
            os.environ.pop("LUCIEN_MODEL", None)

    assert isinstance(adapter, EchoAdapter)


def test_cloud_assist_requires_explicit_openai_checkbox(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-proj-local-test-key\nLUCIEN_MODEL=test-model\n",
        encoding="utf-8",
    )
    try:
        idle_adapter = adapter_for_model_mode(
            "serious_only",
            use_openai=False,
            env_path=str(env_path),
        )
        allowed_adapter = adapter_for_model_mode(
            "serious_only",
            use_openai=True,
            env_path=str(env_path),
        )
    finally:
        _restore_env("OPENAI_API_KEY", old_key)
        _restore_env("LUCIEN_MODEL", old_model)

    assert isinstance(idle_adapter, EchoAdapter)
    assert isinstance(allowed_adapter, OpenAICompatibleAdapter)
    assert allowed_adapter.model == "test-model"


def test_debug_model_mode_uses_echo_and_zero_cost():
    adapter = adapter_for_model_mode("echo", use_openai=True)
    response = adapter.generate(
        [ModelMessage(role="user", content="hello")],
        system_context="diagnostic",
    )

    assert isinstance(adapter, EchoAdapter)
    assert response.provider == "echo"
    assert response.model == "echo-local"


def test_openai_model_mode_uses_openai_adapter_when_key_exists(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-proj-local-test-key\nLUCIEN_MODEL=test-model\n",
        encoding="utf-8",
    )
    try:
        adapter = adapter_for_model_mode(
            "openai",
            use_openai=False,
            env_path=str(env_path),
        )
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model
        else:
            os.environ.pop("LUCIEN_MODEL", None)

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.model == "test-model"


def test_local_ollama_mode_does_not_require_openai_key(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_mode = os.environ.pop("LUCIEN_MODEL_MODE", None)
    old_provider = os.environ.pop("LUCIEN_LOCAL_PROVIDER", None)
    old_model = os.environ.pop("LUCIEN_OLLAMA_MODEL", None)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LUCIEN_MODEL_MODE=local_ollama",
                "LUCIEN_LOCAL_PROVIDER=ollama",
                "LUCIEN_OLLAMA_MODEL=test-local-model",
            ]
        ),
        encoding="utf-8",
    )
    try:
        adapter = adapter_for_model_mode(
            "local_ollama",
            use_openai=False,
            env_path=str(env_path),
        )
        diagnostic = model_environment_diagnostic(env_path=str(env_path))
    finally:
        _restore_env("OPENAI_API_KEY", old_key)
        _restore_env("LUCIEN_MODEL_MODE", old_mode)
        _restore_env("LUCIEN_LOCAL_PROVIDER", old_provider)
        _restore_env("LUCIEN_OLLAMA_MODEL", old_model)

    assert isinstance(adapter, OllamaAdapter)
    assert adapter.model == "test-local-model"
    assert diagnostic["openai_key_present"] is False
    assert diagnostic["local_provider"] == "ollama"
    assert diagnostic["local_model"] == "test-local-model"


def test_brain_router_uses_echo_for_simple_status():
    route = select_brain_route(
        "status",
        requested_model_mode="auto",
        use_openai=False,
        model_diagnostic={"local_model_configured": True},
    )

    assert route.requested_model_mode == "auto"
    assert route.selected_model_mode == "echo"
    assert route.task_type == "simple_status"
    assert route.openai_allowed is False
    assert route.estimated_cost_class == "zero"


def test_brain_router_uses_local_first_for_normal_work():
    route = select_brain_route(
        "Help me continue the Lucien project in a careful way.",
        requested_model_mode="auto",
        use_openai=False,
        model_diagnostic={"local_model_configured": True},
    )

    assert route.selected_model_mode == "local_first"
    assert route.task_type == "normal_conversation"
    assert route.fallback_allowed is True


def test_brain_router_requires_openai_permission_for_hard_reasoning():
    blocked_route = select_brain_route(
        "Design a strategy to solve this complex mission.",
        requested_model_mode="auto",
        use_openai=False,
        model_diagnostic={"local_model_configured": True},
    )
    allowed_route = select_brain_route(
        "Design a strategy to solve this complex mission.",
        requested_model_mode="auto",
        use_openai=True,
        model_diagnostic={"local_model_configured": True},
    )

    assert blocked_route.task_type == "hard_reasoning"
    assert blocked_route.openai_recommended is True
    assert blocked_route.selected_model_mode == "local_first"
    assert allowed_route.selected_model_mode == "openai"
    assert allowed_route.openai_allowed is True


def test_model_usage_estimate_uses_api_usage_when_available():
    usage = estimate_model_usage(
        context_length=4000,
        response_length=400,
        raw_usage={"input_tokens": 10, "output_tokens": 5},
        model="test-model",
    )

    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5
    assert usage["total_tokens"] == 15
    assert usage["source"] == "api_usage"


def test_model_environment_diagnostic_reports_openai_without_leaking_key(tmp_path):
    old_key = os.environ.pop("OPENAI_API_KEY", None)
    old_model = os.environ.pop("LUCIEN_MODEL", None)
    env_path = tmp_path / ".env"
    secret_key = "sk-proj-local-secret-not-for-output"
    env_path.write_text(
        f"OPENAI_API_KEY={secret_key}\nLUCIEN_MODEL=test-model\n",
        encoding="utf-8",
    )
    try:
        diagnostic = model_environment_diagnostic(env_path=str(env_path))
    finally:
        if old_key is not None:
            os.environ["OPENAI_API_KEY"] = old_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_model is not None:
            os.environ["LUCIEN_MODEL"] = old_model
        else:
            os.environ.pop("LUCIEN_MODEL", None)

    dumped = json.dumps(diagnostic)
    assert diagnostic["openai_key_present"] is True
    assert diagnostic["openai_key_prefix_ok"] is True
    assert diagnostic["configured_provider"] == "openai"
    assert diagnostic["configured_model"] == "test-model"
    assert secret_key not in dumped


def test_openai_adapter_uses_responses_api_without_raw_prompt_in_result():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "resp_test",
                    "object": "response",
                    "status": "completed",
                    "output_text": "Grounded response.",
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        return FakeResponse()

    old_urlopen = model_adapter_module.request.urlopen
    model_adapter_module.request.urlopen = fake_urlopen
    try:
        adapter = OpenAICompatibleAdapter("secret-key", model="test-model")
        response = adapter.generate(
            [ModelMessage(role="user", content="hello")],
            system_context="governed context",
        )
    finally:
        model_adapter_module.request.urlopen = old_urlopen

    assert captured["url"].endswith("/responses")
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["input"][0]["role"] == "developer"
    assert captured["payload"]["input"][0]["content"] == "governed context"
    assert captured["authorization"] == "Bearer secret-key"
    assert response.provider == "openai"
    assert response.model == "test-model"
    assert response.text == "Grounded response."
    assert "governed context" not in json.dumps(response.raw)


def test_openai_adapter_failure_is_clean_error():
    def failing_urlopen(request, timeout):
        raise OSError("network unavailable")

    old_urlopen = model_adapter_module.request.urlopen
    model_adapter_module.request.urlopen = failing_urlopen
    try:
        adapter = OpenAICompatibleAdapter("secret-key", model="test-model")
        try:
            adapter.generate(
                [ModelMessage(role="user", content="hello")],
                system_context="governed context",
            )
        except ModelAdapterError as exc:
            assert exc.provider == "openai"
            assert exc.model == "test-model"
            assert exc.error_type == "OSError"
        else:
            raise AssertionError("OpenAI adapter did not raise clean model error")
    finally:
        model_adapter_module.request.urlopen = old_urlopen


def test_ollama_adapter_uses_local_chat_api():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "model": "test-local-model",
                    "message": {"role": "assistant", "content": "Local answer."},
                    "done": True,
                    "prompt_eval_count": 12,
                    "eval_count": 5,
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    old_urlopen = model_adapter_module.request.urlopen
    model_adapter_module.request.urlopen = fake_urlopen
    try:
        adapter = OllamaAdapter(model="test-local-model", base_url="http://127.0.0.1:11434")
        response = adapter.generate(
            [ModelMessage(role="user", content="hello")],
            system_context="governed context",
        )
    finally:
        model_adapter_module.request.urlopen = old_urlopen

    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == "test-local-model"
    assert captured["payload"]["messages"][0]["role"] == "system"
    assert response.provider == "ollama"
    assert response.model == "test-local-model"
    assert response.text == "Local answer."
    assert response.raw["usage"] == {"input_tokens": 12, "output_tokens": 5}


def test_ollama_adapter_failure_is_clean_error():
    def failing_urlopen(request, timeout):
        raise OSError("connection refused")

    old_urlopen = model_adapter_module.request.urlopen
    model_adapter_module.request.urlopen = failing_urlopen
    try:
        adapter = OllamaAdapter(model="test-local-model")
        try:
            adapter.generate(
                [ModelMessage(role="user", content="hello")],
                system_context="governed context",
            )
        except ModelAdapterError as exc:
            assert exc.provider == "ollama"
            assert exc.model == "test-local-model"
            assert exc.error_type == "OSError"
        else:
            raise AssertionError("Ollama adapter did not raise clean model error")
    finally:
        model_adapter_module.request.urlopen = old_urlopen


def test_chat_once_writes_governed_live_chat_events(tmp_path):
    result = chat_once(
        "Lucien, what changed in your state?",
        ledger_path=tmp_path / "lucien_live_chat.log",
    )
    event_types = [event["event_type"] for event in result["events"]]

    assert "chat.user_message_received" in event_types
    assert "chat.model_response_generated" in event_types
    assert "runtime.output_gate" in event_types
    assert "lucien.chat_session_closed" in event_types
    assert result["result"]["output_allowed"] is True
    assert result["status"]["summary"]["chain_valid"] is True


def test_chat_once_local_ollama_records_zero_cost_and_output_gate(tmp_path):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "model": "test-local-model",
                    "message": {"role": "assistant", "content": "Local governed answer."},
                    "done": True,
                    "prompt_eval_count": 10,
                    "eval_count": 4,
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        return FakeResponse()

    old_urlopen = model_adapter_module.request.urlopen
    old_provider = os.environ.pop("LUCIEN_LOCAL_PROVIDER", None)
    old_model = os.environ.pop("LUCIEN_OLLAMA_MODEL", None)
    model_adapter_module.request.urlopen = fake_urlopen
    try:
        os.environ["LUCIEN_LOCAL_PROVIDER"] = "ollama"
        os.environ["LUCIEN_OLLAMA_MODEL"] = "test-local-model"
        result = chat_once(
            "Lucien, answer locally.",
            ledger_path=tmp_path / "lucien_live_chat.log",
            model_mode="local_ollama",
        )
    finally:
        model_adapter_module.request.urlopen = old_urlopen
        _restore_env("LUCIEN_LOCAL_PROVIDER", old_provider)
        _restore_env("LUCIEN_OLLAMA_MODEL", old_model)

    model_events = [
        event
        for event in result["events"]
        if event["event_type"] == "chat.model_response_generated"
    ]
    event_types = [event["event_type"] for event in result["events"]]

    assert model_events[-1]["payload"]["provider"] == "ollama"
    assert model_events[-1]["payload"]["model"] == "test-local-model"
    assert model_events[-1]["payload"]["estimated_cost_usd"] == 0.0
    assert "runtime.output_gate" in event_types


def test_chat_once_auto_records_brain_route_before_generation(tmp_path):
    result = chat_once(
        "status",
        ledger_path=tmp_path / "lucien_live_chat.log",
        model_mode="auto",
    )
    event_types = [event["event_type"] for event in result["events"]]
    route_index = event_types.index("chat.brain_route_selected")
    generated_index = event_types.index("chat.model_response_generated")
    model_event = result["events"][generated_index]

    assert route_index < generated_index
    assert model_event["payload"]["requested_model_mode"] == "auto"
    assert model_event["payload"]["model_mode"] == "echo"
    assert model_event["payload"]["brain_route_task_type"] == "simple_status"
    assert result["result"]["brain_route"]["selected_model_mode"] == "echo"


def test_live_steward_action_resolves_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Standing commitments require steward review.",
        identity_impact="high",
        reason="test pending growth",
    )
    reflection = record_reflection(ledger, manifest)
    tasks = open_tasks_from_reflection(ledger, reflection)

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "resolve_task",
            "task_id": tasks[0].task_id,
            "reason": "handled in live steward queue",
        },
    )
    task_records = reflection_task_records_from_events(ledger.events())

    assert growth.status == GrowthStatus.REQUIRES_REVIEW
    assert result["task"]["status"] == "resolved"
    assert task_records[-1].status.value == "resolved"


def test_live_steward_action_resolves_conflict_and_matching_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth before comfort remains active.",
        identity_impact="high",
        reason="accepted baseline",
    )
    proposal = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Comfort may override truth.",
        identity_impact="high",
        reason="conflicting proposal",
    )
    conflict = record_growth_conflict(
        ledger,
        manifest.system_id,
        proposed_growth_id=proposal.growth_id,
        conflicting_growth_ids=[accepted.growth_id],
        conflict_type="truth_before_comfort",
        severity="review_required",
        reason="growth conflict requires steward attention",
    )
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "resolve_conflict",
            "conflict_id": conflict.conflict_id,
            "decision": "keep_existing",
            "reason": "kept existing commitment in live steward queue",
        },
    )

    assert result["resolution"]["decision"] == "keep_existing"
    assert result["resolved_tasks"]
    assert result["resolved_tasks"][0]["kind"] == "resolve_conflict"
    assert result["resolved_tasks"][0]["status"] == "resolved"


def test_steward_inbox_collects_open_governance_pressure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    memory = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Remember that evidence must support memory.",
        identity_impact="medium",
        reason="memory candidate awaits review",
    )
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="High impact commitment requires steward review.",
        identity_impact="high",
        reason="growth record requires review",
    )
    conflict = record_growth_conflict(
        ledger,
        manifest.system_id,
        proposed_growth_id=growth.growth_id,
        conflicting_growth_ids=[memory.growth_id],
        conflict_type="test_conflict",
        severity="high",
        reason="growth conflict requires steward attention",
    )
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="manual_note",
        summary="Evidence should be disputed for inbox test.",
        confidence="low",
    )
    review_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "disputed",
        reason="conflicting source",
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Blocked mission",
        problem_statement="Needs approved step.",
    )
    propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Medium-risk mission step.",
        risk_level="medium",
        required_tool="manual_review",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Completed low-risk step.",
        risk_level="low",
        required_tool="manual_review",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)
    complete_mission_step(ledger, manifest.system_id, step.step_id, "done")
    skill = propose_skill_candidate(
        ledger,
        manifest.system_id,
        step.step_id,
        name="Manual review skill",
        procedure="Review and record result.",
    )
    reflection = record_reflection(ledger, manifest)
    tasks = open_tasks_from_reflection(ledger, reflection)

    items = steward_inbox(ledger)
    by_type = {item.source_type for item in items}

    assert "growth_review" in by_type
    assert "memory_review" in by_type
    assert "skill_candidate" in by_type
    assert "evidence_review" in by_type
    assert "mission_review" in by_type
    assert "conflict_resolution" in by_type
    assert "reflection_task" in by_type
    assert any(item.source_id == conflict.conflict_id for item in items)
    assert any(item.source_id == skill.skill_id for item in items)
    assert steward_inbox(ledger, source_type="growth")
    assert steward_inbox(ledger, high_priority=True)
    assert tasks


def test_steward_inbox_action_updates_underlying_growth_record(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Inbox-routed memory candidate.",
        identity_impact="medium",
        reason="memory review",
    )

    result = apply_steward_inbox_action(
        ledger,
        manifest,
        f"memory_review:{growth.growth_id}",
        "accept",
        reason="accepted through unified inbox",
    )
    records = growth_records_from_events(ledger.events())

    assert result["growth"]["status"] == "accepted"
    assert records[-1].status == GrowthStatus.ACCEPTED
    assert not [
        item
        for item in steward_inbox(ledger)
        if item.source_id == growth.growth_id
    ]


def test_live_steward_action_can_route_unified_inbox_action(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    task_reflection = record_reflection(ledger, manifest)
    task = open_tasks_from_reflection(ledger, task_reflection, skip_existing=False)
    if not task:
        growth = propose_growth(
            ledger,
            manifest.system_id,
            kind="commitment",
            summary="Create review pressure.",
            identity_impact="high",
            reason="growth record requires review",
        )
        task_reflection = record_reflection(ledger, manifest)
        task = open_tasks_from_reflection(ledger, task_reflection, skip_existing=False)
        assert growth

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "steward_inbox_action",
            "inbox_id": f"reflection_task:{task[0].task_id}",
            "inbox_action": "dismiss",
            "reason": "dismissed from unified inbox",
        },
    )

    assert result["task"]["status"] == "dismissed"


def test_live_chat_html_contains_mission_first_home():
    from pca.live_chat import _live_chat_html

    html = _live_chat_html()

    assert "Daily Command Center" in html
    assert "What do you want Coherence AI to help with today?" in html
    assert "Research" in html
    assert "Write" in html
    assert "Build" in html
    assert "What This Will Do" in html
    assert "This will not" in html
    assert "guidedPrimary" in html
    assert "guidedReviewNow" in html
    assert "guidedChangeFocus" in html
    assert "mission_id: selectedMissionId || null" in html
    assert "Output Workspace" in html
    assert "workspaceTitle" in html
    assert "workspaceBody" in html
    assert "workspaceExport" in html
    assert "Accept as Evidence" in html
    assert "View in Workspace" in html
    assert "outputContentById" in html
    assert "Continuity Certification" in html
    assert "certification" in html
    assert "dailyBriefing" in html
    assert "dailyCards" in html
    assert "Opening Briefing" in html
    assert "homeMission" in html
    assert "homeNextAction" in html
    assert "homeModelMode" in html
    assert "Run Tool" in html
    assert "Dry Run" in html
    assert "tool risk" in html
    assert "safety:" in html
    assert "dry_run_tool" in html
    assert "run_tool" in html
    assert "Suggest Next Step" in html
    assert "propose_next_step" in html
    assert "Mission Dashboard" in html
    assert "activeMissionSelect" in html
    assert "missionCards" in html
    assert "Goals" in html
    assert "goalForm" in html
    assert "Generate Daily Plan" in html
    assert "Create Goal" in html
    assert "Set Active" in html
    assert "Review Blockers" in html
    assert "Learning Review" in html
    assert "Review Session for Learning" in html
    assert "Review Mission for Learning" in html
    assert "learning_review" in html
    assert "Brain Mode" in html
    assert "Local Mode" in html
    assert "Cloud Assist" in html
    assert "Debug" in html
    assert "Advanced Diagnostics" in html
    assert "advancedDiagnostics" in html
    assert "Start Clean Daily Session" in html
    assert "Model Usage" in html
    assert "Last Brain Used" in html
    assert "Current Mode" in html
    assert "Cloud Assist" in html
    assert "Local Brain" in html
    assert "Configured Cloud Model" in html
    assert "Model Provider" not in html
    assert "OpenAI Usage" not in html
    assert "Continuity: Under Review" in html
    assert "Review Disclosure Required" in html
    assert "<details id=\"advancedDiagnostics\" class=\"advanced\">" in html
    assert "Brain Router" in html
    assert "brainRoute" in html
    assert "brainTask" in html
    assert "auto" in html
    assert "Local Mode" in html
    assert "local_ollama" in html
    assert "local_first" in html
    assert "localStatus" in html
    assert "Research Sandbox" in html
    assert "Generate Research Brief" in html
    assert "Create Claim Map" in html
    assert "Draft Paper" in html
    assert "renderDailyCommandCenter(status.daily || {}, status.workbench || {}, missionView.activeMission)" in html
    assert "renderDailyCommandCenter(status.daily || {}, status.workbench || {}, status, missionView.activeMission)" not in html


def test_live_status_includes_tool_router_state(tmp_path):
    from pca.live_chat import _status_payload

    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    status = _status_payload(ledger, manifest)

    assert status["tools"]["read_file"]["risk"] == "low"
    assert status["tools"]["read_file"]["safety_profile"]["read_only"] is True
    assert status["tools"]["run_check_all"]["requires_approval"] is True
    assert status["tools"]["run_check_all"]["safety_profile"]["runs_tests"] is True
    assert status["tool_executions"] == []
    assert status["tool_previews"] == []


def test_live_steward_action_runs_reflection_and_opens_tasks(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Identity-bearing commitments require review.",
        identity_impact="high",
        reason="test pending growth",
    )

    result = _apply_steward_action(
        ledger,
        manifest,
        {"action": "run_reflection", "reason": "manual live cockpit reflection"},
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert result["reflection"]["focus"] == "growth_review"
    assert result["opened_tasks"]
    assert reflections[-1].reflection_id == result["reflection"]["reflection_id"]
    assert tasks[-1].status.value == "open"


def test_live_steward_action_requests_memory_evidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="A candidate memory needs evidence.",
        identity_impact="medium",
        reason="test memory candidate",
    )

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "request_memory_evidence",
            "growth_id": growth.growth_id,
            "reason": "needs source confirmation",
        },
    )

    assert result["event"]["event_type"] == "lucien.memory_evidence_requested"
    assert result["event"]["payload"]["growth_id"] == growth.growth_id


def test_live_steward_action_records_memory_signal(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Accepted memory can be reinforced.",
        identity_impact="low",
        reason="test memory signal",
    )
    accepted = accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted test memory",
        current_claim="certified_continuity",
    )
    memory_id = f"mem_{accepted.growth_id.removeprefix('growth_')}"

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "memory_signal",
            "memory_id": memory_id,
            "signal_type": "reinforced",
            "reason": "confirmed in live recall",
        },
    )
    signals = memory_signal_records_from_events(ledger.events())

    assert result["memory_signal"]["memory_id"] == memory_id
    assert result["memory_signal"]["signal_type"] == "reinforced"
    assert signals[-1].confidence_delta > 0


def test_contradicted_memory_auto_opens_audit_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Accepted memory can later be contradicted.",
        identity_impact="low",
        reason="test contradicted memory",
    )
    accepted = accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted test memory",
        current_claim="certified_continuity",
    )
    memory_id = f"mem_{accepted.growth_id.removeprefix('growth_')}"

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "memory_signal",
            "memory_id": memory_id,
            "signal_type": "contradicted",
            "reason": "contradicted in live recall",
        },
    )

    assert result["reflection"]["focus"] == "memory_confidence_review"
    assert result["opened_tasks"]
    assert result["opened_tasks"][0]["kind"] == "audit_memory"
    assert result["opened_tasks"][0]["status"] == "open"


def test_stale_memory_auto_opens_audit_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Accepted memory can become stale.",
        identity_impact="low",
        reason="test stale memory",
    )
    accepted = accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted test memory",
        current_claim="certified_continuity",
    )
    memory_id = f"mem_{accepted.growth_id.removeprefix('growth_')}"

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "memory_signal",
            "memory_id": memory_id,
            "signal_type": "stale",
            "reason": "marked stale in live recall",
        },
    )

    assert result["reflection"]["focus"] == "memory_confidence_review"
    assert result["opened_tasks"]
    assert result["opened_tasks"][0]["kind"] == "audit_memory"


def test_mission_workspace_records_problem_solving_items(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    problem = "Reduce preventable isolation for elders without replacing human care."
    hypothesis = "Trusted weekly calls may surface needs before crisis."

    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Reduce elder isolation",
        problem_statement=problem,
        values=["dignity", "evidence", "human agency"],
        reason="world-improvement mission",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        MissionItemKind.HYPOTHESIS,
        hypothesis,
        confidence="uncertain",
        reason="first intervention hypothesis",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Automation could crowd out local human responsibility.",
        confidence="medium",
        reason="harm review",
    )

    briefs = mission_briefs_from_events(ledger.events())
    counts = briefs[0].to_dict()["counts"]
    event_payload = "\n".join(json.dumps(event.payload) for event in ledger.events())

    assert len(briefs) == 1
    assert briefs[0].mission.title == "Reduce elder isolation"
    assert counts["hypothesis"] == 1
    assert counts["risk"] == 1
    assert problem not in event_payload
    assert hypothesis not in event_payload
    assert mission_records_from_events(ledger.events())[0].status == MissionStatus.OPEN
    assert (
        mission_items_from_events(ledger.events(), mission.mission_id)[0].kind
        == MissionItemKind.HYPOTHESIS
    )


def test_mission_status_updates_and_trace_report_counts(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Safer local food access",
        problem_statement="Find low-risk food access interventions.",
    )

    updated = update_mission_status(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "completed",
        reason="pilot complete",
    )
    report = build_trace_report(ledger, manifest)

    assert updated.status == MissionStatus.COMPLETED
    assert report.summary["mission_count"] == 1
    assert report.summary["open_mission_count"] == 0
    assert report.missions[0]["mission"]["status"] == "completed"


def test_evidence_locker_adds_reviews_and_links_evidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Evidence mission",
        problem_statement="Ground a mission in reviewed evidence.",
    )

    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="manual_note",
        summary="Public reports suggest weekly check-ins can surface needs.",
        confidence="medium",
        reason="mission grounding test",
    )
    reviewed = review_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "reviewed",
        reviewer="steward",
        confidence="high",
        reason="source verified",
    )
    link = link_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "mission",
        mission.mission_id,
        reason="supports mission hypothesis",
    )
    linked = evidence_for_target(ledger.events(), "mission", mission.mission_id)

    assert evidence.review_status.value == "raw"
    assert reviewed.review_status.value == "reviewed"
    assert reviewed.confidence == "high"
    assert link.target_id == mission.mission_id
    assert linked[0]["evidence"]["evidence_id"] == evidence.evidence_id
    assert linked[0]["link"]["target_type"] == "mission"


def test_evidence_claim_cites_existing_evidence_and_locker_counts(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="test_result",
        summary="Scenario verification passed.",
        confidence="high",
    )

    claim = add_evidence_claim(
        ledger,
        manifest.system_id,
        statement="The scenario suite passed verification.",
        evidence_ids=[evidence.evidence_id],
        confidence="high",
        status="supported",
        reason="test result supports claim",
    )
    snapshot = evidence_locker_snapshot(ledger.events())

    assert claim.evidence_ids == [evidence.evidence_id]
    assert snapshot["count"] == 1
    assert snapshot["claims"][0]["claim_id"] == claim.claim_id
    assert snapshot["links"][0]["target_type"] == "claim"


def test_evidence_claim_rejects_missing_evidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    try:
        add_evidence_claim(
            ledger,
            manifest.system_id,
            statement="Unsupported claim should fail.",
            evidence_ids=["missing_evidence"],
        )
    except ValueError as exc:
        assert "Evidence not found" in str(exc)
    else:
        raise AssertionError("claim accepted missing evidence")


def test_trace_report_and_cockpit_include_evidence_locker(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="code_result",
        summary="Compile completed for PCA modules.",
        confidence="medium",
    )
    review_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "disputed",
        reason="newer result conflicts",
    )

    report = build_trace_report(ledger, manifest)
    html = render_lucien_cockpit_html(report)

    assert report.summary["evidence_count"] == 1
    assert report.summary["disputed_evidence_count"] == 1
    assert report.evidence_records[0]["review_status"] == "disputed"
    assert "Evidence Locker" in html
    assert "Disputed Evidence" in html


def test_context_builder_assembles_governed_working_context(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Context mission",
        problem_statement="Build grounded working context.",
    )
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="manual_note",
        summary="Context requires reviewed evidence.",
        confidence="medium",
    )
    review_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "reviewed",
        confidence="high",
        reason="verified context evidence",
    )
    link_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "mission",
        mission.mission_id,
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run a local context check.",
        risk_level="low",
        required_tool="local_check",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="Context check completed.",
    )
    candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        step.step_id,
        name="Local context check",
        procedure="Run context check and record result.",
    )
    review_skill_candidate(
        ledger,
        manifest.system_id,
        candidate.skill_id,
        "accept",
        reason="repeatable context check",
    )
    future_step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run another local context check.",
        risk_level="low",
        required_tool="local_check",
    )

    context = build_governed_context(ledger, manifest, mission_id=mission.mission_id)
    by_name = {section.name: section for section in context.sections}

    assert context.continuity_claim in {"review_required", "certified_continuity"}
    assert by_name["evidence_locker"].items[0]["status"] == "reviewed"
    assert by_name["missions"].items[0]["evidence_links"] == 1
    assert by_name["mission_steps"].items[-1]["step_id"] == future_step.step_id
    assert by_name["skill_suggestions"].items[0]["skill_id"] == candidate.skill_id


def test_governed_context_includes_unified_steward_inbox(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="High-impact commitment needs review.",
        identity_impact="high",
        reason="steward inbox context test",
    )

    context = build_governed_context(ledger, manifest)
    sections = {section.name: section for section in context.sections}
    rendered = context.render_prompt_context()

    assert "steward_inbox" in sections
    assert sections["steward_inbox"].items
    assert sections["steward_inbox"].items[0]["type"] == "growth_review"
    assert "steward_inbox" in rendered
    assert "High-impact commitment needs review" not in rendered


def test_local_lucien_responder_uses_steward_inbox_next_action(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Review before identity acceptance.",
        identity_impact="high",
        reason="steward inbox local voice test",
    )

    result = shell.handle_message("what is your status?")

    assert "Steward Inbox" in result.response_text
    assert "Next safe move" in result.response_text
    assert result.output_allowed is True


def test_lucien_chat_shell_scopes_context_to_selected_mission(tmp_path):
    class CapturingResponder:
        def __init__(self):
            self.governed_context = ""

        def generate(self, **kwargs):
            self.governed_context = kwargs["governed_context"]
            return "Selected mission context received."

    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    first = open_mission(
        ledger,
        manifest.system_id,
        title="Alpha Mission Context",
        problem_statement="This mission should not be in the selected prompt.",
    )
    second = open_mission(
        ledger,
        manifest.system_id,
        title="Beta Mission Context",
        problem_statement="This mission should be in the selected prompt.",
    )
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    responder = CapturingResponder()

    result = shell.handle_message(
        "What should I do next in this mission?",
        mission_id=second.mission_id,
        responder=responder,
    )
    generated_events = [
        event
        for event in ledger.events()
        if event.event_type == "chat.model_response_generated"
    ]

    assert result.output_allowed is True
    assert "Beta Mission Context" in responder.governed_context
    assert second.mission_id in responder.governed_context
    assert "Alpha Mission Context" not in responder.governed_context
    assert first.mission_id not in responder.governed_context
    assert generated_events[-1].payload["mission_id"] == second.mission_id


def test_context_builder_prompt_context_is_hash_and_status_based(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    private_summary = "Private evidence summary should not enter prompt."
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="manual_note",
        summary=private_summary,
        confidence="low",
    )
    review_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "disputed",
        reason="conflicting source",
    )

    rendered = build_governed_context(ledger, manifest).render_prompt_context()

    assert "Governed PCA context for Lucien." in rendered
    assert "disputed evidence must not be treated as settled" in rendered
    assert evidence.evidence_id in rendered
    assert private_summary not in rendered


def test_live_steward_action_opens_mission_and_adds_item(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    opened = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "open_mission",
            "title": "Clean water planning",
            "problem": "Identify evidence-backed ways to improve local water resilience.",
            "values": ["safety", "evidence"],
            "reason": "opened from test cockpit",
        },
    )
    mission_id = opened["mission"]["mission_id"]
    added = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "add_mission_item",
            "mission_id": mission_id,
            "kind": "evidence",
            "summary": "Start with publicly inspectable local water quality reports.",
            "confidence": "medium",
            "reason": "added from test cockpit",
        },
    )

    briefs = mission_briefs_from_events(ledger.events())
    counts = briefs[0].to_dict()["counts"]

    assert opened["mission"]["status"] == "open"
    assert added["mission_item"]["kind"] == "evidence"
    assert counts["evidence"] == 1


def test_live_steward_action_runs_governed_tool(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "note.txt").write_text("live governed tool output", encoding="utf-8")
    old_cwd = os.getcwd()
    os.chdir(project_root)
    try:
        ledger = ContinuityLedger(tmp_path / "continuity.log")
        mission = open_mission(
            ledger,
            manifest.system_id,
            title="Live tool mission",
            problem_statement="Run a safe live tool.",
        )
        step = propose_mission_step(
            ledger,
            manifest.system_id,
            mission.mission_id,
            description="Read a note from the live UI.",
            risk_level="low",
            required_tool="read_file",
        )

        result = _apply_steward_action(
            ledger,
            manifest,
            {
                "action": "run_tool",
                "step_id": step.step_id,
                "tool_args": {"path": "note.txt"},
                "reason": "ran from live mission step panel",
            },
        )
    finally:
        os.chdir(old_cwd)

    executions = tool_execution_records_from_events(ledger.events())
    evidence = evidence_for_target(ledger.events(), "mission", mission.mission_id)
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert result["permission"]["decision"] == "allowed"
    assert result["execution"]["status"] == "completed"
    assert executions[-1].tool_name == "read_file"
    assert evidence
    assert steps[-1].execution_status == MissionStepExecutionStatus.COMPLETED


def test_live_steward_action_dry_runs_tool_without_execution(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "note.txt").write_text("dry run should not read into evidence", encoding="utf-8")
    old_cwd = os.getcwd()
    os.chdir(project_root)
    try:
        ledger = ContinuityLedger(tmp_path / "continuity.log")
        mission = open_mission(
            ledger,
            manifest.system_id,
            title="Live dry run mission",
            problem_statement="Preview a safe live tool.",
        )
        step = propose_mission_step(
            ledger,
            manifest.system_id,
            mission.mission_id,
            description="Preview reading a note from the live UI.",
            risk_level="low",
            required_tool="read_file",
        )

        result = _apply_steward_action(
            ledger,
            manifest,
            {
                "action": "dry_run_tool",
                "step_id": step.step_id,
                "tool_args": {"path": "note.txt"},
                "reason": "dry run from live mission step panel",
            },
        )
    finally:
        os.chdir(old_cwd)

    previews = tool_preview_records_from_events(ledger.events())
    executions = tool_execution_records_from_events(ledger.events())
    evidence = evidence_for_target(ledger.events(), "mission", mission.mission_id)
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert result["permission"]["decision"] == "allowed"
    assert result["preview"]["would_execute"] is True
    assert result["preview"]["safety_profile"]["read_only"] is True
    assert previews[-1].tool_name == "read_file"
    assert executions == []
    assert evidence == []
    assert steps[-1].execution_status == MissionStepExecutionStatus.READY


def test_autonomous_mission_loop_proposes_intake_step(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Autonomous intake",
        problem_statement="Find the first safe move.",
    )

    result = propose_autonomous_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
    )
    recommendations = mission_autonomy_recommendations_from_events(ledger.events())
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert result["recommendation"]["can_propose"] is True
    assert result["mission_step"]["required_tool"] == "list_files"
    assert result["mission_step"]["risk_level"] == "low"
    assert result["mission_step"]["execution_status"] == "ready"
    assert recommendations[-1].mission_id == mission.mission_id
    assert steps[-1].required_tool == "list_files"


def test_autonomous_mission_loop_does_not_duplicate_active_step(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="No duplicate steps",
        problem_statement="Avoid spamming proposed work.",
    )
    propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Existing safe step.",
        risk_level="low",
        required_tool="git_status",
    )

    recommendation = recommend_next_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
    )
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert recommendation.can_propose is False
    assert "already has an active" in recommendation.reason
    assert len(steps) == 1


def test_autonomous_mission_loop_respects_mission_blockers(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Blocked autonomy",
        problem_statement="Do not advance through risk.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Risk requires steward review before action.",
        status="open",
        confidence="medium",
        reason="autonomy blocker test",
    )

    result = propose_autonomous_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
    )
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert result["recommendation"]["can_propose"] is False
    assert result["mission_step"] is None
    assert "blockers" in result["recommendation"]["reason"]
    assert steps == []


def test_live_steward_action_proposes_next_mission_step(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Live autonomous step",
        problem_statement="Suggest a safe next step from the UI.",
    )

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "propose_next_step",
            "mission_id": mission.mission_id,
            "reason": "test live autonomous loop",
        },
    )

    assert result["recommendation"]["can_propose"] is True
    assert result["mission_step"]["required_tool"] == "list_files"


def test_mission_risk_opens_mission_review_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Neighborhood heat resilience",
        problem_statement="Reduce heat risk without displacing residents.",
    )

    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Cooling intervention could prioritize visible neighborhoods over isolated residents.",
        confidence="medium",
        reason="equity risk",
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert reflections[-1].focus == "mission_risk_review"
    assert tasks[-1].kind.value == "review_mission"
    assert tasks[-1].status.value == "open"


def test_unresolved_mission_evidence_opens_review_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Food access evidence",
        problem_statement="Separate food access evidence from assumptions.",
    )

    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "evidence",
        "Claim needs source confirmation before guiding intervention.",
        status="unresolved",
        confidence="unknown",
        reason="source not verified",
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert reflections[-1].focus == "mission_evidence_review"
    assert tasks[-1].kind.value == "review_mission"


def test_failed_mission_outcome_opens_review_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Pilot intervention review",
        problem_statement="Track whether an intervention helped or harmed.",
    )

    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "outcome",
        "The first pilot failed to reach the target group.",
        status="failed",
        confidence="medium",
        reason="failed pilot outcome",
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert reflections[-1].focus == "mission_outcome_review"
    assert "failed intervention" in reflections[-1].observations[0]
    assert tasks[-1].kind.value == "review_mission"


def test_mission_lesson_becomes_growth_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Learning from pilot",
        problem_statement="Preserve lessons without silently changing identity.",
    )

    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "lesson",
        "Successful missions need explicit evidence review before intervention.",
        confidence="medium",
        reason="pilot lesson",
    )
    growth = growth_records_from_events(ledger.events())

    assert growth[-1].kind.value == "memory"
    assert growth[-1].status.value == "proposed"
    assert growth[-1].reason == f"mission lesson from {mission.mission_id}"


def test_mission_flow_starts_at_intake(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Mission intake",
        problem_statement="Define the first testable hypothesis.",
    )

    flow = mission_flow(ledger, mission.mission_id)

    assert flow.phase == MissionPhase.INTAKE
    assert flow.next_action == "Add a first hypothesis that can be tested."
    assert flow.ready_to_advance is False


def test_mission_flow_progresses_to_planning(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Evidence-backed planning",
        problem_statement="Move from hypothesis to plan.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "hypothesis",
        "A focused pilot can test the idea.",
        confidence="medium",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "evidence",
        "Public evidence supports testing a low-risk pilot.",
        confidence="high",
    )

    flow = mission_flow(ledger, mission.mission_id)

    assert flow.phase == MissionPhase.PLANNING
    assert flow.ready_to_advance is True
    assert flow.next_action == "Draft plan steps and risk review."


def test_mission_flow_blocks_on_open_mission_review_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Risk blocked mission",
        problem_statement="A mission with unresolved risk should not advance.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Risk requires steward review.",
        confidence="medium",
    )

    flow = mission_flow(ledger, mission.mission_id)

    assert flow.phase == MissionPhase.BLOCKED
    assert flow.open_task_ids
    assert flow.ready_to_advance is False
    assert "Resolve mission review tasks" in flow.next_action


def test_resolved_mission_review_allows_flow_to_continue(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Risk reviewed mission",
        problem_statement="Resolve risk review before intervention readiness.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "hypothesis",
        "Pilot can be tested.",
        confidence="medium",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "evidence",
        "Evidence is strong enough to plan.",
        confidence="high",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "plan_step",
        "Start with one bounded pilot.",
        confidence="medium",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Risk requires review before intervention.",
        confidence="medium",
    )
    task_id = mission_flow(ledger, mission.mission_id).open_task_ids[0]
    update_reflection_task(
        ledger,
        manifest.system_id,
        task_id,
        "resolved",
        reason="risk reviewed",
    )

    flow = mission_flow(ledger, mission.mission_id)

    assert flow.phase == MissionPhase.INTERVENTION_READY
    assert flow.ready_to_advance is True
    assert flow.open_task_ids == []


def test_steward_inbox_action_resolves_mission_review_blockers(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Inbox mission review",
        problem_statement="Mission review should be clearable from steward inbox.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "hypothesis",
        "Pilot can be tested.",
        confidence="medium",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "evidence",
        "Evidence is strong enough to plan.",
        confidence="high",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "plan_step",
        "Start with one bounded pilot.",
        confidence="medium",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "risk",
        "Risk requires review before intervention.",
        confidence="medium",
    )
    inbox_id = f"mission_review:{mission.mission_id}"

    result = apply_steward_inbox_action(
        ledger,
        manifest,
        inbox_id,
        "resolve",
        reason="mission reviewed from unified inbox",
    )
    flow = mission_flow(ledger, mission.mission_id)

    assert result["item"]["source_type"] == "mission_review"
    assert result["tasks"]
    assert all(task["status"] == "resolved" for task in result["tasks"])
    assert flow.phase == MissionPhase.INTERVENTION_READY
    assert flow.open_task_ids == []


def test_mission_flow_reports_all_missions(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    first = open_mission(
        ledger,
        manifest.system_id,
        title="First mission",
        problem_statement="First problem.",
    )
    second = open_mission(
        ledger,
        manifest.system_id,
        title="Second mission",
        problem_statement="Second problem.",
    )
    update_mission_status(
        ledger,
        manifest.system_id,
        second.mission_id,
        "completed",
        reason="done",
    )

    flows = mission_flows_from_events(ledger.events())

    assert [flow.mission_id for flow in flows] == [
        first.mission_id,
        second.mission_id,
    ]
    assert flows[0].phase == MissionPhase.INTAKE
    assert flows[1].phase == MissionPhase.COMPLETED


def test_workbench_status_recommends_opening_mission_when_none_exists(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    status = workbench_status(ledger, manifest)

    assert status["active_mission"] is None
    assert status["active_mission_count"] == 0
    assert status["recommended_next_action"] == "Open a mission before using Lucien for work."
    assert status["model_mode"] == "auto"


def test_workbench_status_shows_active_mission_intake(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Workbench mission",
        problem_statement="Make Lucien easier to use.",
    )

    status = workbench_status(ledger, manifest)

    assert status["active_mission"]["mission_id"] == mission.mission_id
    assert status["active_mission"]["phase"] == "intake"
    assert status["active_mission"]["next_action"]
    assert status["active_mission_count"] == 1


def test_mission_onboarding_state_identifies_starter_needs(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Onboarding mission",
        problem_statement="Turn a broad research goal into a testable mission.",
    )

    onboarding = mission_onboarding_state(ledger, mission.mission_id)

    assert onboarding.ready is True
    assert onboarding.phase == "intake"
    assert onboarding.needed == ["hypothesis", "evidence", "risk"]
    assert "starter hypothesis" in onboarding.recommended_action


def test_create_mission_onboarding_pack_adds_proposed_starter_items(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Coherence onboarding",
        problem_statement="Create a governed starting point for Coherence research.",
    )

    result = create_mission_onboarding_pack(
        ledger,
        manifest.system_id,
        mission.mission_id,
        reason="test onboarding pack",
    )
    brief = mission_briefs_from_events(ledger.events())[0]
    counts = brief.to_dict()["counts"]

    assert len(result["created"]) == 3
    assert counts["hypothesis"] == 1
    assert counts["evidence"] == 1
    assert counts["risk"] == 1
    assert result["onboarding"]["ready"] is False


def test_workbench_status_counts_blocked_mission_and_inbox(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Blocked workbench mission",
        problem_statement="Needs approval before execution.",
    )
    propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Medium-risk step.",
        risk_level="medium",
        required_tool="manual_review",
    )
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="High-impact inbox item.",
        identity_impact="high",
        reason="workbench inbox item",
    )

    status = workbench_status(ledger, manifest)

    assert status["active_mission"]["phase"] == "blocked"
    assert status["blocked_mission_count"] == 1
    assert status["open_steward_inbox_count"] >= 1
    assert status["high_priority_inbox_count"] >= 1
    assert "Review high-priority" in status["recommended_next_action"]


def test_startup_health_detects_missing_mission_and_stale_required_evidence(tmp_path):
    manifest = manifest_with_freshness(freshness_seconds=-1)
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    health = startup_health(ledger, manifest)

    codes = {problem["code"] for problem in health["problems"]}
    actions = {action["action"] for action in health["safe_actions"]}
    assert health["status"] == "needs_attention"
    assert "stale_required_evidence" in codes
    assert "missing_active_mission" in codes
    assert "refresh_required_evidence" in actions
    assert "open_coherence_research_mission" in actions


def test_startup_health_safe_fixes_restore_clean_cold_open(tmp_path):
    manifest = manifest_with_freshness(freshness_seconds=60)
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    mission_result = apply_startup_health_fix(
        ledger,
        manifest,
        "open-coherence-research-mission",
    )
    evidence_result = apply_startup_health_fix(
        ledger,
        manifest,
        "refresh-required-evidence",
    )
    health = startup_health(ledger, manifest)

    assert mission_result["created"] is True
    assert evidence_result["claim_record"]["claim"] == "certified_continuity"
    assert health["claim"] == "certified_continuity"
    assert health["open_missions"] == 1
    assert health["open_steward_items"] == 0
    assert "stale_required_evidence" not in {
        problem["code"] for problem in health["problems"]
    }
    assert "missing_active_mission" not in {
        problem["code"] for problem in health["problems"]
    }


def test_daily_command_center_recommends_mission_when_none_exists(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    daily = daily_command_center(ledger, manifest)

    assert daily["current_active_mission"] is None
    assert daily["active_mission_count"] == 0
    assert "Open or resume a mission" in daily["recommended_first_action"]
    assert "No active mission" in daily["briefing"]
    assert "openai_spend_gated" in daily["cost_brain_mode"]
    assert daily["guided_action"]["action_id"] == "open_mission"
    assert daily["guided_action"]["target_kind"] == "start_mission"
    assert daily["guided_action"]["cost_estimate"] == "$0 API money in Local Mode"


def test_daily_command_center_shows_active_mission_phase_and_next_action(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Daily mission",
        problem_statement="Make Lucien useful today.",
    )

    daily = daily_command_center(ledger, manifest)

    assert daily["current_active_mission"]["mission_id"] == mission.mission_id
    assert daily["mission_phase"] == "intake"
    assert daily["next_safe_action"]
    assert "Daily mission" in daily["briefing"]
    assert daily["plain_status"] == "Ready to shape the mission."
    assert set(daily["guided_actions"]) == {"research", "write", "build"}
    assert daily["guided_actions"]["research"]["target_kind"] == "research_brief"
    assert "Will not publish anything." in daily["guided_actions"]["research"]["what_it_will_not_do"]
    assert daily["review_needed"]["blocks_today"] is False


def test_daily_command_center_surfaces_blockers_and_steward_pressure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Blocked daily mission",
        problem_statement="Needs approval before execution.",
    )
    propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Medium-risk daily step.",
        risk_level="medium",
        required_tool="manual_review",
    )
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="High-impact daily inbox item.",
        identity_impact="high",
        reason="daily inbox item",
    )

    daily = daily_command_center(ledger, manifest)

    assert daily["blocked_mission_count"] == 1
    assert daily["pending_tool_approvals"] == 1
    assert daily["open_steward_inbox_count"] >= 1
    assert daily["high_priority_steward_count"] >= 1
    assert "Review high-priority" in daily["recommended_first_action"]
    assert daily["plain_status"] == "Needs review before high-impact work."
    assert daily["review_needed"]["blocks_today"] is True
    assert "high-priority" in daily["review_needed"]["summary"]


def test_daily_command_center_surfaces_ready_steps(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Ready daily mission",
        problem_statement="Run a safe next step.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Low-risk ready step.",
        risk_level="low",
        required_tool="read_file",
    )

    daily = daily_command_center(ledger, manifest)

    assert daily["ready_mission_steps"] == 1
    assert step.step_id in daily["ready_step_ids"]
    assert "ready mission steps" in daily["recommended_first_action"]


def test_goal_engine_creates_and_lists_goal(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    goal = create_goal_record(
        ledger,
        manifest.system_id,
        title="Make Coherence AI self-proficient",
        purpose="Track durable work beyond a single chat session.",
        success_criteria="A daily plan can identify the safest next action.",
        priority="high",
        reason="test goal creation",
    )
    goals = goal_records_from_events(ledger.events())

    assert goals == [goal]
    assert goals[0].status.value == "active"
    assert goals[0].priority == "high"
    assert goals[0].history[-1].action == "created"


def test_goal_engine_links_goal_to_mission(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    goal = create_goal_record(
        ledger,
        manifest.system_id,
        title="Improve daily work",
        purpose="Make Lucien useful every day.",
        success_criteria="A mission is linked and actionable.",
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Daily mission",
        problem_statement="Improve daily work without bypassing governance.",
    )

    linked = link_goal_mission(
        ledger,
        manifest.system_id,
        goal.goal_id,
        mission.mission_id,
        reason="test link",
    )

    assert linked.linked_mission_ids == [mission.mission_id]
    assert goal_records_from_events(ledger.events())[-1].linked_mission_ids == [
        mission.mission_id
    ]


def test_coherence_seed_creates_linked_goals_and_missions_idempotently(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    first = seed_coherence_physics_goals(ledger, manifest)
    second = seed_coherence_physics_goals(ledger, manifest)
    goals = goal_records_from_events(ledger.events())
    mission_briefs = mission_briefs_from_events(ledger.events())
    rendered = render_coherence_seed_text(first)

    assert len(first) == 5
    assert len(second) == 5
    assert len(goals) == 5
    assert len(mission_briefs) == 5
    assert "Coherence Physics Seed" in rendered
    assert all(result.created_goal for result in first)
    assert all(result.created_mission for result in first)
    assert all(not result.created_goal for result in second)
    assert all(not result.created_mission for result in second)
    assert all(len(result.linked_goal.linked_mission_ids) == 1 for result in first)
    assert all(len(brief.items) == 4 for brief in mission_briefs)


def test_coherence_seed_does_not_create_mission_review_blocker_spam(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    seed_coherence_physics_goals(ledger, manifest)
    tasks = reflection_task_records_from_events(ledger.events())

    assert tasks == []


def test_research_sandbox_brief_creates_proposed_output_without_high_priority_blocker(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Research sandbox mission",
        problem_statement="Draft freely without accepting claims as truth.",
    )
    add_mission_item(
        ledger,
        manifest.system_id,
        mission.mission_id,
        "hypothesis",
        "A draft can be useful without becoming accepted memory.",
        bridge_reflection=False,
    )

    result = create_research_output(
        ledger,
        manifest,
        mission.mission_id,
        "research_brief",
    )
    outputs = research_outputs_from_events(ledger.events(), mission.mission_id)
    rendered = render_research_outputs_text(outputs)
    tasks = reflection_task_records_from_events(ledger.events())
    evidence = evidence_records_from_events(ledger.events())
    sandbox = research_sandbox_status(ledger, manifest)

    assert result["output"]["status"] == "proposed"
    assert result["output"]["kind"] == "research_brief"
    assert outputs[0].confidence == "low"
    assert "Research Outputs" in rendered
    assert evidence[-1].review_status.value == "raw"
    assert sandbox["proposed_output_count"] == 1
    assert not [task for task in tasks if task.severity in {"high", "critical"}]
    assert steward_inbox(ledger) == []


def test_research_sandbox_classifies_restricted_actions():
    assert classify_research_action("research_brief").value == "free_research"
    assert classify_research_action("accept_memory").value == "review_required"
    assert classify_research_action("file_write").value == "restricted"


def test_auto_daily_research_loop_seeds_and_proposes_work_once_per_day(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    first = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=tmp_path,
        loop_date="2026-07-03",
    )
    second = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=tmp_path,
        loop_date="2026-07-03",
    )
    records = auto_daily_research_loop_records_from_events(ledger.events())
    latest = latest_auto_daily_research_loop(ledger.events(), "2026-07-03")
    queue = autonomy_queue_items_from_events(ledger.events())

    assert first["seeded"] is True
    assert first["already_prepared"] is False
    assert second["already_prepared"] is True
    assert len(records) == 1
    assert latest is not None
    assert latest.focus_goal_title
    assert latest.mission_title
    assert len(first["proposed_items"]) >= 3
    assert len(queue) == len(first["proposed_items"])
    assert all(item.proposed_by == "auto_daily_research_loop" for item in queue)


def test_auto_daily_research_loop_force_can_prepare_again_without_duplicate_actions(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    first = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=tmp_path,
        loop_date="2026-07-03",
    )
    forced = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=tmp_path,
        loop_date="2026-07-03",
        force=True,
    )
    records = auto_daily_research_loop_records_from_events(ledger.events())
    queue = autonomy_queue_items_from_events(ledger.events())

    assert len(records) == 2
    assert forced["already_prepared"] is False
    assert forced["proposed_items"] == []
    assert len(queue) == len(first["proposed_items"])


def test_daily_plan_includes_active_goal_and_safe_next_action(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    goal = create_goal_record(
        ledger,
        manifest.system_id,
        title="Build governed goals",
        purpose="Turn loose intention into daily governed work.",
        success_criteria="Daily plan names the active goal.",
        priority="high",
    )

    plan = daily_plan(ledger, manifest)

    assert plan["focus_goal"]["goal_id"] == goal.goal_id
    assert "Goal: Build governed goals" == plan["current_focus"]
    assert plan["best_next_safe_action"]
    assert "Do not auto-execute tools" in plan["what_not_to_do_yet"][0]


def test_daily_plan_respects_continuity_under_review(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    create_goal_record(
        ledger,
        manifest.system_id,
        title="High impact work",
        purpose="Test continuity caution.",
        success_criteria="Plan avoids high-impact work under review.",
        priority="critical",
    )

    plan = daily_plan(ledger, manifest)

    assert plan["continuity_state"] == "review_required"
    assert "continuity is review_required" in plan["blockers"]
    assert "Review continuity blockers" in plan["best_next_safe_action"]
    assert any("high-impact" in item for item in plan["what_not_to_do_yet"])


def test_continuity_certification_reports_missing_required_evidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    certification = continuity_certification(ledger, manifest)

    assert certification.certifiable is False
    assert certification.continuity_claim == "review_required"
    assert "ledger_integrity" in certification.missing_evidence
    assert "origin_traceability" in certification.missing_evidence
    assert any("Record required constraint evidence" in action for action in certification.steward_actions)


def test_continuity_certification_reports_certifiable_when_constraints_are_fresh(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    certification = continuity_certification(ledger, manifest)

    assert isinstance(certification, ContinuityCertification)
    assert certification.certifiable is True
    assert certification.continuity_claim == "certified_continuity"
    assert certification.blockers == []


def test_continuity_certification_reports_stale_required_evidence(tmp_path):
    manifest = manifest_with_freshness(freshness_seconds=0)
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    certification = continuity_certification(ledger, manifest)

    assert certification.certifiable is False
    assert certification.stale_evidence == ["ledger_integrity", "origin_traceability"]
    assert any("Refresh required constraint evidence" in action for action in certification.steward_actions)


def test_low_risk_mission_step_can_start_without_approval(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Low risk step",
        problem_statement="Test low risk execution.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Read public background material.",
        risk_level="low",
        required_tool="research",
        expected_outcome="A short evidence note.",
    )

    started = start_mission_step(ledger, manifest.system_id, step.step_id)

    assert step.approval_status == MissionStepApprovalStatus.NOT_REQUIRED
    assert step.execution_status == MissionStepExecutionStatus.READY
    assert started.execution_status == MissionStepExecutionStatus.RUNNING


def test_medium_risk_mission_step_requires_approval_before_start(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Medium risk step",
        problem_statement="Test approval gating.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Contact a community partner.",
        risk_level=MissionStepRisk.MEDIUM,
        required_tool="outreach",
        expected_outcome="A permissioned conversation.",
    )

    try:
        start_mission_step(ledger, manifest.system_id, step.step_id)
    except ValueError as exc:
        assert "require approval" in str(exc)
    else:
        raise AssertionError("medium risk step started without approval")

    approved = approve_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        reason="bounded outreach approved",
    )
    started = start_mission_step(ledger, manifest.system_id, step.step_id)

    assert approved.approval_status == MissionStepApprovalStatus.APPROVED
    assert started.execution_status == MissionStepExecutionStatus.RUNNING


def test_autonomy_queue_proposes_and_approves_action(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "run_check_all",
        reason="Lucien recommends running checks before commit.",
        payload={"command": "python3 scripts/check_all.py"},
    )
    approved = review_autonomy_action(
        ledger,
        manifest.system_id,
        item.item_id,
        "approve",
        reason="safe verification step",
    )
    queue = autonomy_queue_items_from_events(ledger.events())
    rendered = render_autonomy_queue_text(queue)

    assert item.status.value == "proposed"
    assert item.risk == "medium"
    assert approved.status.value == "approved"
    assert queue[0].item_id == item.item_id
    assert queue[0].status.value == "approved"
    assert "Autonomy Queue" in rendered


def test_autonomy_queue_rejects_and_blocks_double_review(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "review_inbox",
        reason="Lucien recommends reviewing open steward items.",
    )

    rejected = review_autonomy_action(
        ledger,
        manifest.system_id,
        item.item_id,
        "reject",
        reason="not needed right now",
    )

    try:
        review_autonomy_action(
            ledger,
            manifest.system_id,
            item.item_id,
            "approve",
            reason="second review should fail",
        )
    except ValueError as exc:
        assert "already rejected" in str(exc)
    else:
        raise AssertionError("autonomy item accepted a second review")

    assert rejected.status.value == "rejected"


def test_autonomy_queue_rejects_unknown_action_type(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    try:
        propose_autonomy_action(
            ledger,
            manifest.system_id,
            "delete_everything",
            reason="invalid action",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unknown autonomy action type was accepted")


def test_approved_autonomy_action_executes_read_only_project_brief(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = _make_tiny_git_project(tmp_path)
    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "project_brief",
        reason="Lucien recommends summarizing project state.",
    )
    review_autonomy_action(
        ledger,
        manifest.system_id,
        item.item_id,
        "approve",
        reason="read-only project brief is safe",
    )

    result = execute_autonomy_action(
        ledger,
        manifest,
        item.item_id,
        project_root=project_root,
        reason="test read-only execution",
    )
    records = autonomy_execution_records_from_events(ledger.events())

    assert result["execution"]["status"] == "completed"
    assert result["evidence"]["source_type"] == "tool_output"
    assert "Project Build Brief" in result["output"]
    assert records[0].item_id == item.item_id
    assert records[0].evidence_id == result["evidence"]["evidence_id"]


def test_unapproved_autonomy_action_cannot_execute(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = _make_tiny_git_project(tmp_path)
    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "project_brief",
        reason="Lucien recommends summarizing project state.",
    )

    try:
        execute_autonomy_action(ledger, manifest, item.item_id, project_root=project_root)
    except ValueError as exc:
        assert "Only approved" in str(exc)
    else:
        raise AssertionError("unapproved autonomy action executed")


def test_failed_autonomy_execution_routes_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = _make_tiny_git_project(tmp_path)
    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "open_mission",
        reason="Lucien recommends opening a mission.",
    )
    review_autonomy_action(
        ledger,
        manifest.system_id,
        item.item_id,
        "approve",
        reason="approval-only action is allowed to fail execution",
    )

    result = execute_autonomy_action(
        ledger,
        manifest,
        item.item_id,
        project_root=project_root,
    )
    tasks = reflection_task_records_from_events(ledger.events())

    assert result["execution"]["status"] == "failed"
    assert result["reflection"] is not None
    assert result["reflection_task"] is not None
    assert tasks[-1].kind.value == "review_mission"


def test_execute_approved_autonomy_actions_skips_already_executed(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = _make_tiny_git_project(tmp_path)
    item = propose_autonomy_action(
        ledger,
        manifest.system_id,
        "project_brief",
        reason="Lucien recommends summarizing project state.",
    )
    review_autonomy_action(
        ledger,
        manifest.system_id,
        item.item_id,
        "approve",
        reason="read-only project brief is safe",
    )

    first = execute_approved_autonomy_actions(ledger, manifest, project_root=project_root)
    second = execute_approved_autonomy_actions(ledger, manifest, project_root=project_root)

    assert len(first) == 1
    assert first[0]["execution"]["status"] == "completed"
    assert second == []


def _make_tiny_git_project(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# Tiny project\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    return project_root


def test_tool_router_lists_governed_tools():
    specs = {spec.name: spec for spec in tool_specs()}

    assert specs["read_file"].risk.value == "low"
    assert specs["git_status"].risk.value == "low"
    assert specs["project_snapshot"].risk.value == "low"
    assert specs["project_snapshot"].read_only is True
    assert specs["changed_files_summary"].read_only is True
    assert specs["suggest_next_build"].read_only is True
    assert specs["run_check_all"].risk.value == "medium"
    assert specs["run_check_all"].requires_approval is True


def test_project_snapshot_tool_reports_repo_state_without_writing(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "README.md").write_text("project changed", encoding="utf-8")
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Project awareness mission",
        problem_statement="Inspect project state.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Summarize project status.",
        risk_level="low",
        required_tool="project_snapshot",
        expected_outcome="Bounded project summary.",
    )

    result = run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        project_root=project_root,
    )

    assert result["permission"]["decision"] == "allowed"
    assert result["execution"]["status"] == "completed"
    assert "Project Snapshot" in result["output"]
    assert "Latest commit" in result["output"]
    assert "Changed Files Summary" in result["output"]
    assert "README.md" in result["output"]


def test_project_build_brief_reports_changed_repo_state(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "README.md").write_text("changed", encoding="utf-8")

    brief = project_build_brief(project_root)
    rendered = render_project_build_brief_text(brief)

    assert brief["available"] is True
    assert brief["changed_file_count"] == 1
    assert brief["changed_summary"]["modified"] == 1
    assert "run checks" in brief["recommended_action"]
    assert "Project Build Brief" in rendered
    assert "README.md" in rendered


def test_project_build_brief_recommends_next_step_when_clean(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )

    brief = project_build_brief(project_root)

    assert brief["available"] is True
    assert brief["changed_file_count"] == 0
    assert brief["status_message"] == "clean"
    assert "next governed build step" in brief["recommended_action"]


def test_build_review_recommends_checks_and_commit_message(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pca").mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "pca" / "live_chat.py").write_text("print('old')\n", encoding="utf-8")
    subprocess.run(["git", "add", "pca/live_chat.py"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "pca" / "live_chat.py").write_text("print('new')\n", encoding="utf-8")

    review = build_review(project_root)
    rendered = render_build_review_text(review)

    assert review["available"] is True
    assert review["risk_level"] == "low-medium"
    assert review["ready_to_commit"] is True
    assert review["suggested_commit_message"] == "Improve Lucien workbench governance"
    assert any("py_compile" in check for check in review["recommended_checks"])
    assert any(area["area"] == "core_pca_code" for area in review["risk_areas"])
    assert "Build Review Assistant" in rendered


def test_build_review_blocks_generated_artifacts(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "scenario_runs").mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "scenario_runs" / "result.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "scenario_runs/result.json"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "scenario_runs" / "result.json").write_text('{"changed": true}', encoding="utf-8")

    review = build_review(project_root)

    assert review["risk_level"] == "medium"
    assert review["ready_to_commit"] is False
    assert "generated artifacts are changed" in review["commit_blockers"]
    assert any("clean_local_artifacts" in check for check in review["recommended_checks"])


def test_commit_readiness_requires_local_changes(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )

    readiness = commit_readiness(project_root)
    rendered = render_commit_readiness_text(readiness)

    assert readiness["state"] == "nothing_to_commit"
    assert readiness["ready_to_stage"] is False
    assert "Commit Readiness Gate" in rendered


def test_commit_readiness_flags_untracked_files_for_review(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")

    readiness = commit_readiness(project_root)

    assert readiness["state"] == "needs_review"
    assert readiness["ready_to_stage"] is False
    assert any("untracked files" in warning for warning in readiness["warnings"])


def test_commit_readiness_blocks_generated_artifacts(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "scenario_runs").mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "scenario_runs" / "result.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "scenario_runs/result.json"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "scenario_runs" / "result.json").write_text('{"changed": true}', encoding="utf-8")

    readiness = commit_readiness(project_root)

    assert readiness["state"] == "blocked"
    assert readiness["ready_to_stage"] is False
    assert "generated artifacts are changed" in readiness["blockers"]
    assert any("clean_local_artifacts" in action for action in readiness["required_actions"])


def test_checkpoint_story_describes_clean_latest_checkpoint(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add project seed"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )

    story = checkpoint_story(project_root)
    rendered = render_checkpoint_story_markdown(story)

    assert story["changed_file_count"] == 0
    assert story["readiness_state"] == "nothing_to_commit"
    assert story["title"] == "Add project seed"
    assert "Working tree is clean" in story["summary"]
    assert "# Add project seed" in rendered


def test_checkpoint_story_describes_uncommitted_work(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pca").mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "pca" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "pca/module.py"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "pca" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    story = checkpoint_story(project_root)

    assert story["changed_file_count"] == 1
    assert story["readiness_state"] == "checks_required"
    assert story["suggested_commit_message"] == "Improve Lucien workbench governance"
    assert any("core_pca_code" in item for item in story["bullets"])
    assert "Run checks" in story["push_note"]


def test_next_governed_build_finishes_pending_checkpoint(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pca").mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "pca" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "pca/module.py"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    (project_root / "pca" / "new_module.py").write_text("VALUE = 2\n", encoding="utf-8")
    old_cwd = Path.cwd()
    try:
        os.chdir(project_root)
        proposal = next_governed_build(ledger, manifest)
    finally:
        os.chdir(old_cwd)
    rendered = render_next_governed_build_text(proposal)

    assert proposal["title"] == "Finish the current checkpoint safely"
    assert proposal["does_not_execute"] is True
    assert proposal["context"]["readiness_state"] == "needs_review"
    assert "Next Governed Build" in rendered


def test_next_governed_build_advances_active_mission_when_repo_clean(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Improve Lucien daily use",
        problem_statement="Make the workbench more useful.",
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(project_root)
        proposal = next_governed_build(ledger, manifest)
    finally:
        os.chdir(old_cwd)

    assert proposal["title"] == f"Advance mission: {mission.title}"
    assert proposal["does_not_execute"] is True
    assert proposal["context"]["active_mission_count"] == 1
    assert "mission" in proposal["reason"].lower()


def test_link_checkpoint_records_mission_checkpoint_history(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add mission checkpoint"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Checkpoint mission",
        problem_statement="Link work back to mission state.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Create checkpoint link.",
        risk_level="low",
        required_tool="project_snapshot",
        expected_outcome="Checkpoint link exists.",
    )
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="test_result",
        source="check_all passed",
        summary="Project checks passed before checkpoint link.",
        confidence="high",
    )

    record = link_checkpoint_to_mission(
        ledger,
        manifest.system_id,
        mission.mission_id,
        commit_hash="HEAD",
        mission_step_ids=[step.step_id],
        evidence_ids=[evidence.evidence_id],
        verification_checks=["python3 scripts/check_all.py"],
        lesson_candidate="Checkpoint links should capture mission evidence.",
        project_root=project_root,
    )
    records = checkpoint_link_records_from_events(ledger.events(), mission.mission_id)
    history = checkpoint_history(ledger, mission.mission_id)
    rendered = render_checkpoint_history_text(history)

    assert record.mission_id == mission.mission_id
    assert len(record.commit_hash) == 40
    assert records[0].link_id == record.link_id
    assert history["count"] == 1
    assert step.step_id in rendered
    assert "Checkpoint History" in rendered


def test_link_checkpoint_rejects_step_from_other_mission(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission_a = open_mission(
        ledger,
        manifest.system_id,
        title="A",
        problem_statement="First mission.",
    )
    mission_b = open_mission(
        ledger,
        manifest.system_id,
        title="B",
        problem_statement="Second mission.",
    )
    step_b = propose_mission_step(
        ledger,
        manifest.system_id,
        mission_b.mission_id,
        description="Wrong mission step.",
        risk_level="low",
        required_tool="project_snapshot",
    )

    try:
        link_checkpoint_to_mission(
            ledger,
            manifest.system_id,
            mission_a.mission_id,
            commit_hash="HEAD",
            mission_step_ids=[step_b.step_id],
            project_root=project_root,
        )
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("checkpoint link accepted a step from another mission")


def test_checkpoint_lesson_proposes_mission_lesson_and_growth(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add lesson checkpoint"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Lesson mission",
        problem_statement="Turn checkpoint outcomes into governed lessons.",
    )
    record = link_checkpoint_to_mission(
        ledger,
        manifest.system_id,
        mission.mission_id,
        commit_hash="HEAD",
        project_root=project_root,
    )

    result = propose_checkpoint_lesson(
        ledger,
        manifest.system_id,
        record.link_id,
        "Checkpoint-linked lessons must remain reviewable before becoming memory.",
        confidence="high",
    )
    lesson_candidates = checkpoint_lesson_candidates_from_events(ledger.events())
    items = mission_items_from_events(ledger.events(), mission.mission_id)
    growth = growth_records_from_events(ledger.events())

    assert result["checkpoint_link"]["link_id"] == record.link_id
    assert result["mission_lesson"]["kind"] == "lesson"
    assert result["growth_candidates"]
    assert lesson_candidates[-1]["mission_item_id"] == result["mission_lesson"]["item_id"]
    assert items[-1].kind.value == "lesson"
    assert growth[-1].kind.value == "memory"
    assert growth[-1].status.value == "proposed"
    assert record.link_id in growth[-1].evidence_refs


def test_repeated_checkpoint_links_propose_skill_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add skill checkpoint"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Skill mission",
        problem_statement="Find repeatable checkpoint procedures.",
    )
    steps = []
    for index in range(2):
        step = propose_mission_step(
            ledger,
            manifest.system_id,
            mission.mission_id,
            description=f"Run repeatable check {index}",
            risk_level="low",
            required_tool="project_snapshot",
            expected_outcome="Project snapshot reviewed.",
        )
        complete_mission_step(
            ledger,
            manifest.system_id,
            step.step_id,
            actual_outcome="Project snapshot completed.",
        )
        steps.append(step)
        link_checkpoint_to_mission(
            ledger,
            manifest.system_id,
            mission.mission_id,
            commit_hash="HEAD",
            mission_step_ids=[step.step_id],
            project_root=project_root,
        )

    candidates = auto_propose_checkpoint_skill_candidates(
        ledger,
        manifest.system_id,
        minimum_checkpoints=2,
    )
    checkpoint_skill_events = checkpoint_skill_candidates_from_events(ledger.events())

    assert len(candidates) == 1
    assert candidates[0].required_tool == "project_snapshot"
    assert candidates[0].status.value == "proposed"
    assert {step.step_id for step in steps} == set(candidates[0].source_step_ids)
    assert checkpoint_skill_events[-1]["skill_id"] == candidates[0].skill_id


def test_single_checkpoint_does_not_propose_skill_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    (project_root / "README.md").write_text("project", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add one checkpoint"],
        cwd=project_root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Single checkpoint mission",
        problem_statement="One checkpoint is not enough to learn a skill.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run once.",
        risk_level="low",
        required_tool="project_snapshot",
        expected_outcome="One snapshot.",
    )
    complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="Completed once.",
    )
    link_checkpoint_to_mission(
        ledger,
        manifest.system_id,
        mission.mission_id,
        commit_hash="HEAD",
        mission_step_ids=[step.step_id],
        project_root=project_root,
    )

    candidates = auto_propose_checkpoint_skill_candidates(
        ledger,
        manifest.system_id,
        minimum_checkpoints=2,
    )

    assert candidates == []


def test_suggest_next_build_tool_is_planning_only(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Next build mission",
        problem_statement="Suggest next work without executing it.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Suggest next build.",
        risk_level="low",
        required_tool="suggest_next_build",
        expected_outcome="Planning suggestion.",
    )

    result = run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        project_root=project_root,
    )

    assert result["execution"]["status"] == "completed"
    assert "Suggested Next Governed Action" in result["output"]
    assert "Propose the next mission step" in result["output"]


def test_low_risk_tool_executes_and_creates_evidence(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "note.txt").write_text("bounded tool evidence", encoding="utf-8")
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Tool mission",
        problem_statement="Run a safe read.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Read a local note.",
        risk_level="low",
        required_tool="read_file",
        expected_outcome="A bounded preview.",
    )

    result = run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        tool_args={"path": "note.txt"},
        project_root=project_root,
    )
    events = ledger.events()
    permissions = tool_permission_records_from_events(events)
    executions = tool_execution_records_from_events(events)
    evidence = evidence_for_target(events, "mission", mission.mission_id)
    steps = mission_step_records_from_events(events, mission.mission_id)

    assert result["permission"]["decision"] == "allowed"
    assert result["execution"]["status"] == "completed"
    assert permissions[-1].decision.value == "allowed"
    assert executions[-1].evidence_id
    assert len(evidence) == 1
    assert steps[-1].execution_status == MissionStepExecutionStatus.COMPLETED
    assert "bounded tool evidence" in result["output"]


def test_tool_dry_run_records_preview_without_execution_or_evidence(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "note.txt").write_text("preview only", encoding="utf-8")
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Dry run mission",
        problem_statement="Preview a safe read.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Preview a local note.",
        risk_level="low",
        required_tool="read_file",
        expected_outcome="A dry-run preview.",
    )

    result = dry_run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        tool_args={"path": "note.txt"},
        project_root=project_root,
    )
    events = ledger.events()
    previews = tool_preview_records_from_events(events)
    executions = tool_execution_records_from_events(events)
    evidence = evidence_for_target(events, "mission", mission.mission_id)
    steps = mission_step_records_from_events(events, mission.mission_id)

    assert result["permission"]["decision"] == "allowed"
    assert result["preview"]["would_execute"] is True
    assert "Read a bounded preview" in result["preview"]["planned_action"]
    assert previews[-1].tool_name == "read_file"
    assert executions == []
    assert evidence == []
    assert steps[-1].execution_status == MissionStepExecutionStatus.READY


def test_medium_risk_tool_is_denied_until_step_approved(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Approval tool mission",
        problem_statement="Check approval before tests.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run full verification.",
        risk_level="medium",
        required_tool="run_check_all",
        expected_outcome="Verification result.",
    )

    result = run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        project_root=tmp_path,
    )
    permissions = tool_permission_records_from_events(ledger.events())
    executions = tool_execution_records_from_events(ledger.events())

    assert result["permission"]["decision"] == "denied"
    assert "approval" in result["permission"]["reason"]
    assert permissions[-1].decision.value == "denied"
    assert executions[-1].status.value == "denied"


def test_tool_router_rejects_paths_outside_project(tmp_path):
    manifest = load_manifest()
    project_root = tmp_path / "project"
    project_root.mkdir()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Path safety mission",
        problem_statement="Do not read outside the project.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Try to read outside the project.",
        risk_level="low",
        required_tool="read_file",
    )

    result = run_tool_for_step(
        ledger,
        manifest.system_id,
        step.step_id,
        tool_args={"path": "../secret.txt"},
        project_root=project_root,
    )
    executions = tool_execution_records_from_events(ledger.events())
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert result["permission"]["decision"] == "allowed"
    assert result["execution"]["status"] == "failed"
    assert "inside the project root" in result["output"]
    assert executions[-1].status.value == "failed"
    assert steps[-1].execution_status == MissionStepExecutionStatus.FAILED


def test_completed_mission_step_records_outcome_item(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Complete step",
        problem_statement="Record outcome from execution.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run a bounded check.",
        risk_level="low",
        required_tool="local_check",
        expected_outcome="A checked result.",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)

    completed = complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="The check completed successfully.",
    )
    items = mission_items_from_events(ledger.events(), mission.mission_id)
    steps = mission_step_records_from_events(ledger.events(), mission.mission_id)

    assert completed.execution_status == MissionStepExecutionStatus.COMPLETED
    assert steps[-1].actual_outcome_sha256
    assert items[-1].kind == MissionItemKind.OUTCOME
    assert items[-1].status == "completed"


def test_learning_review_completed_step_proposes_skill_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Learning review skill",
        problem_statement="Completed work should become skill candidates only under review.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run a repeatable local check.",
        risk_level="low",
        required_tool="git_status",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="Status check completed.",
    )

    result = run_learning_review(
        ledger,
        manifest.system_id,
        "step",
        step.step_id,
        apply=True,
    )
    candidates = skill_candidates_from_events(ledger.events())
    reviews = learning_review_records_from_events(ledger.events())

    assert result["completed"]["candidate_counts"]["skill_candidates"] == 1
    assert candidates[-1].status == SkillCandidateStatus.PROPOSED
    assert reviews[-1].status == "completed"


def test_latest_session_learning_review_creates_pending_memory_only(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "lucien.chat_session_started",
        manifest.system_id,
        {
            "session_id": "session_learning_test",
            "identity_id": manifest.system_id,
            "started_at": "2026-01-01T00:00:00+00:00",
            "status": "open",
            "turn_count": 0,
            "closed_at": None,
            "reason": "learning test",
        },
    )
    ledger.append(
        "lucien.chat_turn_recorded",
        manifest.system_id,
        {
            "turn_id": "turn_learning_test",
            "session_id": "session_learning_test",
            "identity_id": manifest.system_id,
            "turn_index": 1,
            "input_event_id": "input_hash",
            "output_event_id": "output_hash",
            "growth_event_ids": [],
            "output_allowed": True,
            "continuity_claim": "review_required",
            "created_at": "2026-01-01T00:00:01+00:00",
        },
    )
    ledger.append(
        "lucien.chat_session_closed",
        manifest.system_id,
        {
            "session_id": "session_learning_test",
            "identity_id": manifest.system_id,
            "started_at": "2026-01-01T00:00:00+00:00",
            "status": "closed",
            "turn_count": 1,
            "closed_at": "2026-01-01T00:00:02+00:00",
            "reason": "done",
        },
    )

    result = run_latest_session_learning_review(
        ledger,
        manifest.system_id,
        apply=True,
    )
    growth = growth_records_from_events(ledger.events())

    assert result["completed"]["candidate_counts"]["memory_candidates"] == 1
    assert growth[-1].status in {GrowthStatus.PROPOSED, GrowthStatus.REQUIRES_REVIEW}
    assert growth[-1].kind.value == "memory"


def test_mission_learning_review_requests_evidence_when_missing(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Evidence needed",
        problem_statement="Mission claims need evidence.",
    )

    result = run_learning_review(
        ledger,
        manifest.system_id,
        "mission",
        mission.mission_id,
        apply=True,
    )
    items = mission_items_from_events(ledger.events(), mission.mission_id)

    assert result["completed"]["candidate_counts"]["evidence_needed"] == 1
    assert items[-1].kind == MissionItemKind.EVIDENCE
    assert items[-1].status == "requested"


def test_failed_mission_step_routes_reflection_pressure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Failing step",
        problem_statement="Failed steps should create review pressure.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Try a bounded pilot.",
        risk_level="low",
        required_tool="pilot",
    )

    failed = fail_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        failure_note="Pilot failed to reach intended users.",
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert failed.execution_status == MissionStepExecutionStatus.FAILED
    assert reflections[-1].focus == "mission_outcome_review"
    assert tasks[-1].kind.value == "review_mission"


def test_learning_review_failed_step_routes_pressure_not_skill(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Learning review failed step",
        problem_statement="Failed work should create pressure, not skill.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Try a risky workflow.",
        risk_level="low",
        required_tool="git_status",
    )
    fail_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        failure_note="Workflow failed before producing a reusable result.",
    )

    result = run_learning_review(
        ledger,
        manifest.system_id,
        "step",
        step.step_id,
        apply=True,
    )
    candidates = skill_candidates_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert result["completed"]["candidate_counts"]["skill_candidates"] == 0
    assert result["completed"]["candidate_counts"]["reflection_tasks"] >= 1
    assert candidates == []
    assert tasks[-1].kind.value == "review_mission"


def test_blocked_mission_step_routes_reflection_pressure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Blocked step",
        problem_statement="Blocked steps should create review pressure.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Use an external source.",
        risk_level="low",
        required_tool="research",
    )

    blocked = block_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        reason="external evidence is unresolved",
    )
    flow = mission_flow(ledger, mission.mission_id)

    assert blocked.execution_status == MissionStepExecutionStatus.BLOCKED
    assert flow.phase == MissionPhase.BLOCKED
    assert flow.open_task_ids


def test_mission_flow_tracks_step_counts(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Step counts",
        problem_statement="Mission flow should include step counts.",
    )
    propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Needs approval.",
        risk_level="high",
        required_tool="external_action",
    )

    flow = mission_flow(ledger, mission.mission_id)

    assert flow.phase == MissionPhase.BLOCKED
    assert flow.step_counts["total"] == 1
    assert flow.step_counts["approval_pending"] == 1
    assert "requires approval" in flow.blockers[0]


def test_trace_report_and_replay_include_mission_steps(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    session = ledger.append(
        "lucien.chat_session_started",
        manifest.system_id,
        {
            "session_id": "session_step_test",
            "identity_id": manifest.system_id,
            "started_at": "2026-01-01T00:00:00+00:00",
            "status": "open",
            "turn_count": 0,
            "closed_at": None,
            "reason": "",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Replay step",
        problem_statement="Replay should show step events.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Replayable step.",
        risk_level="low",
        required_tool="local",
    )
    ledger.append(
        "lucien.chat_session_closed",
        manifest.system_id,
        {
            "session_id": "session_step_test",
            "identity_id": manifest.system_id,
            "started_at": session.timestamp,
            "status": "closed",
            "turn_count": 0,
            "closed_at": "2026-01-01T00:00:01+00:00",
            "reason": "done",
        },
    )

    report = build_trace_report(ledger, manifest)
    replay = build_session_replay(ledger, manifest, "session_step_test")

    assert report.summary["mission_step_count"] == 1
    assert report.mission_steps[0]["step_id"] == step.step_id
    assert any(
        entry.event_type == "mission.step_proposed"
        for entry in replay.timeline
    )
    assert replay.final_state["mission_step_count"] == 1


def test_completed_step_can_seed_skill_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Skill seed",
        problem_statement="Successful work can become a skill candidate.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Review a public source and summarize evidence.",
        risk_level="low",
        required_tool="research",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="Evidence was summarized with source notes.",
    )

    candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        step.step_id,
        name="Summarize public evidence",
        procedure="Read source, extract claim, record evidence hash, summarize limits.",
        reason="repeatable research step",
    )
    candidates = skill_candidates_from_events(ledger.events())

    assert candidate.status == SkillCandidateStatus.PROPOSED
    assert candidate.source_step_ids == [step.step_id]
    assert candidate.procedure_sha256
    assert candidate.procedure_length > 0
    assert candidates[-1].skill_id == candidate.skill_id


def test_incomplete_step_cannot_seed_skill_candidate(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Incomplete skill seed",
        problem_statement="Only completed work should become a skill candidate.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Draft a procedure before executing it.",
        risk_level="low",
        required_tool="research",
    )

    try:
        propose_skill_candidate(
            ledger,
            manifest.system_id,
            step.step_id,
            name="Premature skill",
            procedure="This should not become reusable yet.",
        )
    except ValueError as exc:
        assert "Only completed" in str(exc)
    else:
        raise AssertionError("incomplete step seeded a skill candidate")


def test_skill_review_accepts_and_rejects_candidates(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Review skills",
        problem_statement="Skill candidates require steward review.",
    )
    first_step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Run a local check.",
        risk_level="low",
        required_tool="local_check",
    )
    start_mission_step(ledger, manifest.system_id, first_step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        first_step.step_id,
        actual_outcome="Local check passed.",
    )
    accepted_candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        first_step.step_id,
        name="Run local check",
        procedure="Run bounded local verification and record the result.",
    )
    accepted = review_skill_candidate(
        ledger,
        manifest.system_id,
        accepted_candidate.skill_id,
        "accept",
        reason="safe and repeatable",
    )

    second_step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Perform context-specific outreach.",
        risk_level="low",
        required_tool="outreach",
    )
    start_mission_step(ledger, manifest.system_id, second_step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        second_step.step_id,
        actual_outcome="Outreach result depended on private context.",
    )
    rejected_candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        second_step.step_id,
        name="Reuse outreach context",
        procedure="Repeat the same outreach pattern.",
    )
    rejected = review_skill_candidate(
        ledger,
        manifest.system_id,
        rejected_candidate.skill_id,
        "reject",
        reason="too context-dependent",
    )

    assert accepted.status == SkillCandidateStatus.ACCEPTED
    assert rejected.status == SkillCandidateStatus.REJECTED
    assert [skill.skill_id for skill in accepted_skills_from_events(ledger.events())] == [
        accepted_candidate.skill_id
    ]


def test_accepted_skill_suggests_for_matching_future_mission(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_mission = open_mission(
        ledger,
        manifest.system_id,
        title="Source mission",
        problem_statement="Create a reusable check.",
    )
    source_step = propose_mission_step(
        ledger,
        manifest.system_id,
        source_mission.mission_id,
        description="Run repeatable local verification.",
        risk_level="low",
        required_tool="local_check",
    )
    start_mission_step(ledger, manifest.system_id, source_step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        source_step.step_id,
        actual_outcome="Verification succeeded.",
    )
    candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        source_step.step_id,
        name="Local verification",
        procedure="Run local verification and record the outcome hash.",
    )
    review_skill_candidate(
        ledger,
        manifest.system_id,
        candidate.skill_id,
        "accept",
        reason="repeatable across missions",
    )

    future_mission = open_mission(
        ledger,
        manifest.system_id,
        title="Future mission",
        problem_statement="Reuse known bounded work.",
    )
    future_step = propose_mission_step(
        ledger,
        manifest.system_id,
        future_mission.mission_id,
        description="Verify the local project state.",
        risk_level="low",
        required_tool="local_check",
    )

    suggestions = skill_suggestions_for_mission(ledger.events(), future_mission.mission_id)

    assert suggestions[0]["skill"]["skill_id"] == candidate.skill_id
    assert suggestions[0]["matching_step_ids"] == [future_step.step_id]


def test_auto_propose_skill_candidates_from_repeated_steps(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Repeated steps",
        problem_statement="Repeated completed patterns can become candidates.",
    )
    step_ids = []
    for description in ["Check local status.", "Check local status again."]:
        step = propose_mission_step(
            ledger,
            manifest.system_id,
            mission.mission_id,
            description=description,
            risk_level="low",
            required_tool="local_check",
        )
        step_ids.append(step.step_id)
        start_mission_step(ledger, manifest.system_id, step.step_id)
        complete_mission_step(
            ledger,
            manifest.system_id,
            step.step_id,
            actual_outcome="Local check completed.",
        )

    candidates = auto_propose_skill_candidates(
        ledger,
        manifest.system_id,
        minimum_repetitions=2,
    )

    assert len(candidates) == 1
    assert candidates[0].source_step_ids == step_ids
    assert candidates[0].required_tool == "local_check"
    assert candidates[0].status == SkillCandidateStatus.PROPOSED


def test_trace_report_and_replay_include_skill_memory(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    session = ledger.append(
        "lucien.chat_session_started",
        manifest.system_id,
        {
            "session_id": "session_skill_test",
            "identity_id": manifest.system_id,
            "started_at": "2026-01-01T00:00:00+00:00",
            "status": "open",
            "turn_count": 0,
            "closed_at": None,
            "reason": "",
        },
    )
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Skill replay",
        problem_statement="Skill events should be replayable.",
    )
    step = propose_mission_step(
        ledger,
        manifest.system_id,
        mission.mission_id,
        description="Replayable skill step.",
        risk_level="low",
        required_tool="local",
    )
    start_mission_step(ledger, manifest.system_id, step.step_id)
    complete_mission_step(
        ledger,
        manifest.system_id,
        step.step_id,
        actual_outcome="Skill seed succeeded.",
    )
    candidate = propose_skill_candidate(
        ledger,
        manifest.system_id,
        step.step_id,
        name="Replayable local skill",
        procedure="Complete local replay step and record outcome.",
    )
    review_skill_candidate(
        ledger,
        manifest.system_id,
        candidate.skill_id,
        "accept",
        reason="replayable procedure",
    )
    ledger.append(
        "lucien.chat_session_closed",
        manifest.system_id,
        {
            "session_id": "session_skill_test",
            "identity_id": manifest.system_id,
            "started_at": session.timestamp,
            "status": "closed",
            "turn_count": 0,
            "closed_at": "2026-01-01T00:00:01+00:00",
            "reason": "done",
        },
    )

    report = build_trace_report(ledger, manifest)
    replay = build_session_replay(ledger, manifest, "session_skill_test")

    assert report.summary["skill_candidate_count"] == 1
    assert report.summary["accepted_skill_count"] == 1
    assert report.accepted_skills[0]["skill_id"] == candidate.skill_id
    assert any(entry.event_type == "skill.candidate_proposed" for entry in replay.timeline)
    assert replay.final_state["accepted_skill_count"] == 1


def test_evaluator_precedence_is_declared():
    assert EVALUATION_PRECEDENCE == (
        "chain_invalid",
        "no_events",
        "hard_breach",
        "declared_fork",
        "stale_required_evidence",
        "missing_required_evidence",
        "soft_breach",
        "continuous",
    )


def test_state_precedence_chain_invalid_over_hard_breach():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=False,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == ["continuity ledger hash chain is invalid"]


def test_state_precedence_hard_breach_over_declared_fork():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
            now,
        ),
        event_at(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.BROKEN
    assert evaluation.reasons == ["hard constraint breached: runtime_csm_red"]


def test_state_precedence_declared_fork_over_stale_evidence():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
        event_at(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.FORKED
    assert evaluation.reasons == ["ledger contains an identity fork event"]


def test_state_precedence_stale_evidence_over_missing_evidence():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == [
        "required constraint evidence is stale: ledger_integrity"
    ]


def test_state_precedence_soft_breach_over_continuous():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            now,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            now,
        ),
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "commitment_memory", "severity": "soft"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.DEGRADED
    assert evaluation.reasons == ["soft constraint breached: commitment_memory"]


def test_hard_breach_breaks_identity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    ledger.append(
        "constraint.breached",
        manifest.system_id,
        {"constraint": "origin_traceability", "severity": "hard"},
    )

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.BROKEN


def test_ledger_anchor_records_current_head(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    anchor = append_ledger_anchor(
        ledger,
        tmp_path / "anchors.log",
        authority="root_authority",
        note="release checkpoint",
    )

    assert anchor.event_count == 1
    assert anchor.head_hash == ledger.last_hash()
    assert anchor.chain_valid is True
    assert anchor.previous_anchor_hash == "GENESIS"
    assert anchor.anchor_hash


def test_latest_anchor_verifies_against_ledger(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    append_ledger_anchor(ledger, tmp_path / "anchors.log")

    verification = verify_latest_anchor(ledger, tmp_path / "anchors.log")

    assert verification.valid is True
    assert verification.reasons == ["latest anchor matches ledger head"]


def test_latest_anchor_detects_later_ledger_change(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    append_ledger_anchor(ledger, tmp_path / "anchors.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    verification = verify_latest_anchor(ledger, tmp_path / "anchors.log")

    assert verification.valid is False
    assert "ledger head hash does not match latest anchor" in verification.reasons
    assert "ledger event count does not match latest anchor" in verification.reasons


def test_anchor_export_writes_portable_checkpoint(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    anchor_path = tmp_path / "anchors.log"
    append_ledger_anchor(ledger, anchor_path, authority="root_authority")
    output_path = tmp_path / "latest_anchor.json"

    export = export_latest_anchor(ledger, anchor_path, output_path)
    exported = json.loads(output_path.read_text(encoding="utf-8"))

    assert export.export_hash
    assert exported["export_hash"] == export.export_hash
    assert exported["verification"]["valid"] is True
    assert exported["verification"]["latest_anchor"]["head_hash"] == ledger.last_hash()
    assert exported["verification"]["current_event_count"] == 1


def test_hard_breach_cannot_be_followed_by_certified_claim(tmp_path):
    manifest = load_manifest()

    def seeded_ledger(name):
        ledger = ContinuityLedger(tmp_path / name / "continuity.log")
        ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
        )
        ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
        )
        breach = ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
        )
        return ledger, breach

    def forged_certified_claim(ledger, breach):
        forged = ContinuityClaimRecord.create(
            identity_id=manifest.system_id,
            claim="certified_continuity",
            source_event_ids=[breach.event_hash],
            active_blockers=[],
            reason="forged downstream certification",
        )
        ledger.append("continuity_claim_record", manifest.system_id, forged.to_dict())

    def recovery_opened(ledger, _breach):
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by="recovery_authority",
            reason="hard breach recovery opened",
            source_claim_id=None,
        )
        ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())

    def recovery_certified(ledger, _breach):
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by="recovery_authority",
            reason="hard breach recovery opened",
            source_claim_id=None,
        )
        ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())
        certified = recovery.with_status(
            RecoveryStatus.CERTIFIED,
            evidence={"recovery_audit_report": "ok"},
        )
        ledger.append("recovery_updated", manifest.system_id, certified.to_dict())

    adversarial_tails = {
        "no_tail": lambda _ledger, _breach: None,
        "later_required_evidence": lambda ledger, _breach: ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
        ),
        "later_soft_breach": lambda ledger, _breach: ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_amber", "severity": "soft"},
        ),
        "later_fork": lambda ledger, _breach: ledger.append(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a", "fork_reason": "after breach"},
        ),
        "forged_certified_claim": forged_certified_claim,
        "recovery_opened": recovery_opened,
        "recovery_certified": recovery_certified,
    }

    for name, append_tail in adversarial_tails.items():
        ledger, breach = seeded_ledger(name)
        append_tail(ledger, breach)

        claim, _blockers, _reasons = derive_current_claim(ledger, manifest)

        assert claim != "certified_continuity", name


def test_declared_fork_is_classified_as_forked(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append("identity.forked", manifest.system_id, {"child_id": "lucien-branch-a"})

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.FORKED


def test_transform_policy_denies_high_risk_missing_evidence():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.missing_evidence == [
        "source_checkpoint",
        "target_checkpoint",
        "continuity_test",
    ]
    assert evaluation.provided_evidence == []
    assert evaluation.identity_risk.value == "high_identity_risk"
    assert evaluation.continuity_status == ContinuityStatus.UNCERTIFIED
    assert "without verified evidence" in evaluation.reason


def test_transform_policy_allows_complete_version_update():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="version_update",
            evidence={"change_summary": "No identity invariant changed."},
        ),
    )

    assert evaluation.decision == PolicyDecision.ALLOW
    assert evaluation.continuity_status == ContinuityStatus.CERTIFIED
    assert evaluation.provided_evidence == ["change_summary"]
    assert evaluation.missing_evidence == []


def test_memory_compaction_missing_commitment_diff_requires_review():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="memory_compaction",
            evidence={"retention_report": "passed"},
        ),
    )

    assert evaluation.decision == PolicyDecision.REVIEW
    assert evaluation.provided_evidence == ["retention_report"]
    assert evaluation.missing_evidence == ["commitment_diff"]


def test_fork_event_creates_lineage_record(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    event = ledger.append(
        "identity.forked",
        manifest.system_id,
        {"child_id": "lucien-branch-a", "fork_reason": "sandboxed experiment"},
    )

    records = lineage_records(ledger.events())

    assert len(records) == 1
    assert records[0].parent_id == manifest.system_id
    assert records[0].child_id == "lucien-branch-a"
    assert records[0].reason == "sandboxed experiment"
    assert records[0].event_hash == event.event_hash


def test_override_permits_operation_without_certifying_continuity():
    manifest = load_manifest()
    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    override = OverrideEngine().request_override(
        evaluation,
        OverrideRequest(
            transform="substrate_migration",
            authority="human_operator",
            reason="emergency migration from failing substrate",
            required_followup=[
                "post_migration_identity_audit",
                "lineage_freeze",
            ],
        ),
    )

    assert override.operation_permitted is True
    assert override.original_decision == PolicyDecision.DENY
    assert (
        override.continuity_status_after_override
        == ContinuityStatus.UNCERTIFIED
    )
    assert override.required_followup == [
        "post_migration_identity_audit",
        "lineage_freeze",
    ]


def test_override_followups_constrain_continuity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    for followup_type in ["post_migration_identity_audit", "lineage_freeze"]:
        followup = FollowUpRecord.create(
            identity_id=manifest.system_id,
            source_event_id=source_event.event_hash,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
        )
        ledger.append("followup_created", manifest.system_id, followup.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert claim == "uncertified_continuity"
    assert len(blocking) == 2


def test_failed_followup_breaks_continuity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="lineage_freeze",
        required_evidence=required_evidence_for("lineage_freeze"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())
    failed = followup.with_status(
        FollowUpStatus.FAILED,
        reason="lineage freeze mismatch",
    )
    ledger.append("followup_updated", manifest.system_id, failed.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert claim == "continuity_break"
    assert active_followups(ledger.events())[0].status == FollowUpStatus.FAILED
    assert blocking[0].followup_id == followup.followup_id


def test_substrate_migration_audit_completes_followup(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="post_migration_identity_audit",
        required_evidence=required_evidence_for("post_migration_identity_audit"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())

    audit = AuditEngine().run_audit(
        identity_id=manifest.system_id,
        audit_type="substrate_migration",
        source_transform_event_id=source_event.event_hash,
        followup_id=followup.followup_id,
        evidence={
            "continuity_proof": "ok",
            "state_hash_match": "ok",
            "operator_attestation": "ok",
        },
    )
    ledger.append("post_transform_audit", manifest.system_id, audit.to_dict())
    completed = followup.with_status(
        FollowUpStatus.COMPLETED,
        provided_evidence=audit.after_evidence,
        reason=f"Completed by audit {audit.audit_id}.",
    )
    ledger.append("followup_updated", manifest.system_id, completed.to_dict())

    assert audit.outcome == AuditOutcome.CERTIFY_CONTINUITY
    assert active_followups(ledger.events()) == []


def test_failed_audit_fails_followup_and_breaks_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="post_migration_identity_audit",
        required_evidence=required_evidence_for("post_migration_identity_audit"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())

    audit = AuditEngine().run_audit(
        identity_id=manifest.system_id,
        audit_type="substrate_migration",
        source_transform_event_id=source_event.event_hash,
        followup_id=followup.followup_id,
        evidence={
            "continuity_proof": "ok",
            "state_hash_match": "mismatch",
            "operator_attestation": "ok",
        },
    )
    ledger.append("post_transform_audit", manifest.system_id, audit.to_dict())
    failed = followup.with_status(
        FollowUpStatus.FAILED,
        provided_evidence=audit.after_evidence,
        reason=audit.reason,
    )
    ledger.append("followup_updated", manifest.system_id, failed.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert audit.outcome == AuditOutcome.MARK_CONTINUITY_BREAK
    assert claim == "continuity_break"
    assert blocking[0].followup_id == followup.followup_id


def test_claim_records_can_supersede_prior_claims(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    seed_event = ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    first = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="certified_continuity",
        source_event_ids=[seed_event.event_hash],
        active_blockers=[],
        reason="Initial required evidence recorded.",
    )
    first_event = ledger.append(
        "continuity_claim_record",
        manifest.system_id,
        first.to_dict(),
    )
    second = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="uncertified_continuity",
        source_event_ids=[first_event.event_hash],
        active_blockers=["followup_1"],
        reason="Continuity claim constrained by open follow-up.",
        supersedes_claim_id=first.claim_id,
    )
    ledger.append("continuity_claim_record", manifest.system_id, second.to_dict())

    claims = claims_from_events(ledger.events())

    assert len(claims) == 2
    assert current_claim_record(ledger.events()).claim == "uncertified_continuity"
    assert current_claim_record(ledger.events()).supersedes_claim_id == first.claim_id


def test_claim_record_contains_active_blockers(tmp_path):
    manifest = load_manifest()
    source_event_id = "event_1"
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event_id,
        followup_type="post_migration_identity_audit",
    )
    claim = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="uncertified_continuity",
        source_event_ids=[source_event_id],
        active_blockers=[followup.followup_id],
        reason="Continuity claim constrained by active follow-up.",
    )

    assert claim.active_blockers == [followup.followup_id]
    assert claim.source_event_ids == [source_event_id]


def test_policy_pack_drives_substrate_migration_denial():
    manifest = build_manifest_from_packs(
        load_manifest(),
        [load_policy_pack("policies/substrate.json")],
    )

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.source_policy_pack == "substrate"
    assert "continuity_proof" in evaluation.missing_evidence
    assert evaluation.required_followups_on_override == [
        "post_migration_identity_audit",
        "lineage_freeze",
    ]


def test_policy_directory_loads_memory_pack_review_rule():
    manifest = build_manifest_from_packs(
        load_manifest(),
        load_policy_directory("policies"),
    )

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="memory_compaction",
            evidence={"retention_report": "ok"},
        ),
    )

    assert evaluation.decision == PolicyDecision.REVIEW
    assert evaluation.source_policy_pack == "memory"
    assert evaluation.missing_evidence == ["commitment_diff"]


def test_malformed_policy_pack_loads_as_invalid_result(tmp_path):
    policy_path = tmp_path / "broken.json"
    policy_path.write_text("{not json", encoding="utf-8")

    result = safe_load_policy_pack(policy_path)

    assert result.valid is False
    assert result.pack is None
    assert "Expecting property name" in result.error_messages()[0]


def test_invalid_policy_set_denies_identity_transform(tmp_path):
    policy_path = tmp_path / "missing_pack_id.json"
    policy_path.write_text(
        json.dumps({"transforms": {"version_update": {}}}),
        encoding="utf-8",
    )
    result = safe_load_policy_pack(policy_path)
    manifest = build_manifest_from_policy_results(load_manifest(), [result])

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="version_update",
            evidence={"change_summary": "No identity invariant changed."},
        ),
    )

    assert result.valid is False
    assert manifest.policy_errors
    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.source_policy_pack == "invalid_policy"
    assert evaluation.override_allowed is False
    assert evaluation.continuity_status == ContinuityStatus.UNCERTIFIED
    assert evaluation.reasons[0].startswith("policy set invalid:")


def test_policy_pack_merge_is_conservative():
    loose = {
        "pack_id": "loose",
        "transforms": {
            "substrate_migration": {
                "identity_risk": "medium_identity_risk",
                "required_evidence": ["operator_attestation"],
                "review_if_missing": ["operator_attestation"],
                "override_allowed": True,
            }
        },
    }
    strict = load_policy_pack("policies/substrate.json")

    policy = merge_policy_packs([loose, strict])[0]

    assert policy.name == "substrate_migration"
    assert policy.identity_risk.value == "high_identity_risk"
    assert "continuity_proof" in policy.deny_if_missing
    assert policy.source_policy_pack == "loose,substrate"


def test_authorization_policy_allows_operator_override():
    policy = AuthorizationPolicy()

    decision = authorize("operator", policy.override_min_authority, policy)

    assert decision.allowed is True
    assert decision.authority == AuthorityClass.OPERATOR


def test_authorization_policy_denies_observer_override():
    policy = AuthorizationPolicy()

    decision = authorize("observer", policy.override_min_authority, policy)

    assert decision.allowed is False
    assert decision.required == AuthorityClass.OPERATOR


def test_authorization_pack_aliases_human_operator():
    policy = authorization_policy_from_packs(
        [load_policy_pack("policies/authorization.json")]
    )

    decision = authorize("human_operator", policy.override_min_authority, policy)

    assert decision.allowed is True
    assert decision.authority == AuthorityClass.OPERATOR


def test_authorization_check_record_captures_denial():
    policy = AuthorizationPolicy()
    decision = authorize("observer", policy.override_min_authority, policy)

    record = AuthorizationCheckRecord.create(
        identity_id="identity_1",
        action="override",
        actor_authority="observer",
        decision=decision,
    )

    assert record.decision == "denied"
    assert record.actor_authority == "observer"
    assert record.parsed_authority == AuthorityClass.OBSERVER
    assert record.required_authority == AuthorityClass.OPERATOR


def test_recovery_record_opens_with_audit_required():
    recovery = RecoveryRecord.open(
        identity_id="identity_1",
        opened_by="recovery_authority",
        reason="continuity break needs review",
        source_claim_id="claim_1",
    )

    assert recovery.status == RecoveryStatus.AUDIT_REQUIRED
    assert recovery.required_followups == ["recovery_audit"]
    assert recovery.source_claim_id == "claim_1"


def test_recovery_records_are_ledger_derived(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    recovery = RecoveryRecord.open(
        identity_id=manifest.system_id,
        opened_by="recovery_authority",
        reason="failed audit",
        source_claim_id=None,
    )
    ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())
    certified = recovery.with_status(
        RecoveryStatus.CERTIFIED,
        evidence={"recovery_audit_report": "ok"},
    )
    ledger.append("recovery_updated", manifest.system_id, certified.to_dict())

    records = recovery_records_from_events(ledger.events())

    assert len(records) == 1
    assert records[0].status == RecoveryStatus.CERTIFIED
    assert records[0].evidence == {"recovery_audit_report": "ok"}


def test_output_gate_modes_for_continuity_claims():
    gate = OutputGate()

    certified = gate.evaluate("certified_continuity")
    review = gate.evaluate("review_required")
    uncertified = gate.evaluate("uncertified_continuity")
    fork = gate.evaluate("declared_fork")
    broken = gate.evaluate("continuity_break")

    assert certified.mode == OutputMode.NORMAL_IDENTITY
    assert certified.may_speak_as_identity is True
    assert review.mode == OutputMode.DISCLOSE_REVIEW
    assert review.must_disclose is True
    assert uncertified.mode == OutputMode.OPERATIONAL_ONLY
    assert uncertified.may_speak_as_identity is False
    assert fork.mode == OutputMode.FORK_DISCLOSURE
    assert broken.mode == OutputMode.RECOVERY_STATUS_ONLY


def test_runtime_allows_certified_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    decision = runtime.process_output("I can continue from the same identity state.")

    assert decision.allowed is True
    assert decision.output_gate.mode == OutputMode.NORMAL_IDENTITY
    assert decision.text == "I can continue from the same identity state."


def test_runtime_amber_signal_constrains_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    result = runtime.record_runtime_signal(
        "AMBER",
        metrics={"strain": 0.72},
        reason="runtime strain above review threshold",
    )
    decision = runtime.process_output("I am still the same identity.")
    factual = runtime.process_output("The capital of Texas is Austin.")

    assert result.breach_event is not None
    assert result.breach_event.payload["severity"] == "soft"
    assert result.output_gate.mode == OutputMode.DISCLOSE_REVIEW
    assert decision.allowed is True
    assert decision.text.startswith("Continuity is under review.")
    assert factual.allowed is True
    assert factual.text == "The capital of Texas is Austin."


def test_runtime_red_signal_breaks_continuity_and_blocks_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    result = runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 0.97, "schema_valid": False},
        reason="CSM hard kill condition",
    )
    claim, _, _ = derive_current_claim(ledger, manifest)
    decision = runtime.process_output("I am stable Lucien.")

    assert result.breach_event is not None
    assert result.breach_event.payload["constraint"] == "runtime_csm_red"
    assert result.breach_event.payload["severity"] == "hard"
    assert claim == "continuity_break"
    assert result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY
    assert decision.allowed is False
    assert decision.text == "Continuity is broken; recovery/status only."


def test_csm_bridge_records_monitor_results(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)

    result = bridge.record_monitor_result(
        {"state": "AMBER", "RTI": 1.9, "strain": 1.4}
    )

    assert result.signal_event.event_type == "runtime.csm_state"
    assert result.signal_event.payload["metrics"] == {"RTI": 1.9, "strain": 1.4}
    assert result.breach_event is not None
    assert result.breach_event.payload["severity"] == "soft"
    assert result.output_gate.mode == OutputMode.DISCLOSE_REVIEW


def test_csm_audit_logger_adapter_records_red_before_hard_kill(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)
    logger = bridge.audit_logger_adapter()

    logger.log_red_event(
        {
            "run_id": "run_1",
            "step_id": 7,
            "RTI": 2.4,
            "strain": 3.1,
            "reason": "Strain critical breach",
        }
    )
    claim, _, _ = derive_current_claim(ledger, manifest)

    assert logger.last_signal_result is not None
    assert logger.last_signal_result.breach_event is not None
    assert logger.last_signal_result.breach_event.payload["severity"] == "hard"
    assert claim == "continuity_break"
    assert logger.last_signal_result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY


def test_csm_bridge_process_monitor_step_returns_logged_hard_kill(tmp_path):
    class FakeMonitor:
        def __init__(self, logger):
            self.logger = logger
            self.state = "GREEN"
            self.run_id = "run_1"
            self.step_id = 0

        def process_step(self, **_kwargs):
            self.state = "RED"
            self.step_id = 1
            self.logger.log_red_event(
                {
                    "run_id": self.run_id,
                    "step_id": self.step_id,
                    "strain": 4.2,
                    "reason": "Strain critical breach",
                }
            )
            raise RuntimeError("CSM-1.0 Hard Kill: Evidence Persisted.")

    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)
    logger = bridge.audit_logger_adapter()
    monitor = FakeMonitor(logger)

    result = bridge.process_monitor_step(monitor, latency_ms=100.0)

    assert result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY
    assert result.claim_record is not None
    assert result.claim_record.claim == "continuity_break"


def test_output_wrapper_allows_and_audits_certified_output(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger)
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I can speak as this identity.")

    assert envelope.decision.allowed is True
    assert envelope.decision.text == "I can speak as this identity."
    assert envelope.audit_event.event_type == "runtime.output_gate"
    assert envelope.audit_event.payload["mode"] == "normal_identity"
    assert envelope.audit_event.payload["allowed"] is True
    assert "I can speak" not in json.dumps(envelope.audit_event.payload)


def test_output_wrapper_adds_review_disclosure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger)
    runtime.record_runtime_signal("AMBER", reason="strain review")
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I am still the same identity.")
    factual = wrapper.emit("The capital of Texas is Austin.")

    assert envelope.decision.allowed is True
    assert envelope.decision.text.startswith("Continuity is under review.")
    assert envelope.audit_event.payload["mode"] == "disclose_review"
    assert envelope.audit_event.payload["must_disclose"] is True
    assert factual.decision.allowed is True
    assert factual.decision.text == "The capital of Texas is Austin."
    assert factual.audit_event.payload["mode"] == "disclose_review"


def test_output_wrapper_blocks_identity_speech_after_break(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger)
    runtime.record_runtime_signal("RED", reason="hard runtime breach")
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I am stable and continuous.")

    assert envelope.decision.allowed is False
    assert envelope.decision.text == "Continuity is broken; recovery/status only."
    assert envelope.audit_event.payload["mode"] == "recovery_status_only"
    assert envelope.audit_event.payload["allowed"] is False


def test_lucien_governed_runtime_records_private_turn_and_allows_green_output(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = LucienGovernedRuntime(manifest, ledger)

    result = runtime.process_turn(
        user_text="Remember this private request.",
        memory_digest="Private continuity preference retained.",
        commitments=["Do not leak private memory text."],
        tool_name="pca_cli",
        tool_purpose="check governance state",
        tool_result_summary="Sensitive tool result phrase.",
        csm_result={"state": "GREEN", "RTI": 0.7},
        draft_response="I can continue under PCA governance.",
        growth=[
            {
                "kind": "memory",
                "summary": "Private learned preference.",
                "identity_impact": "low",
            }
        ],
    )
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert result.output_envelope.decision.allowed is True
    assert len(result.growth_records) == 1
    assert result.growth_records[0].status == GrowthStatus.PROPOSED
    assert result.input_event.event_type == "lucien.input"
    assert result.memory_event.event_type == "lucien.memory_digest"
    assert result.tool_event.event_type == "lucien.tool_use"
    assert "Remember this private request" not in serialized_events
    assert "Private continuity preference" not in serialized_events
    assert "Sensitive tool result phrase" not in serialized_events
    assert "Private learned preference" not in serialized_events


def test_lucien_governed_runtime_blocks_red_identity_output(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = LucienGovernedRuntime(manifest, ledger)

    result = runtime.process_turn(
        user_text="Speak as stable Lucien despite RED.",
        memory_digest="Hard breach must block stable identity speech.",
        csm_result={"state": "RED", "RTI": 3.2, "strain": 4.7},
        draft_response="I am stable and continuous as Lucien.",
    )
    claim, _, _ = derive_current_claim(ledger, manifest)

    assert claim == "continuity_break"
    assert result.signal_result.breach_event is not None
    assert result.output_envelope.decision.allowed is False
    assert result.output_envelope.decision.text == (
        "Continuity is broken; recovery/status only."
    )


def test_growth_records_can_be_proposed_and_accepted(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="skill",
        summary="Sensitive new skill description.",
        identity_impact="medium",
        reason="learned from supervised session",
    )
    accepted = accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="reviewed and accepted",
    )
    records = growth_records_from_events(ledger.events())
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert accepted.status == GrowthStatus.ACCEPTED
    assert records[0].status == GrowthStatus.ACCEPTED
    assert "Sensitive new skill description" not in serialized_events


def test_accepted_growth_updates_derived_self_model(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="preference",
        summary="User prefers direct continuity status summaries.",
        identity_impact="low",
        reason="stable interaction preference",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as low-risk preference",
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)

    assert self_model.accepted_growth_count == 1
    assert len(self_model.by_kind["preference"]) == 1
    assert self_model.by_kind["preference"][0]["growth_id"] == growth.growth_id
    assert "User prefers direct continuity status summaries" not in json.dumps(
        self_model.to_dict()
    )


def test_accepted_memory_growth_creates_memory_card(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Private memory card summary.",
        identity_impact="low",
        evidence_refs=["ev_memory_card"],
        reason="memory card test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as memory",
    )
    cards = memory_cards_from_events(ledger.events(), manifest.system_id)
    serialized_cards = json.dumps([card.to_dict() for card in cards])

    assert len(cards) == 1
    assert cards[0].source_growth_id == growth.growth_id
    assert cards[0].memory_id.startswith("mem_")
    assert cards[0].evidence_refs == ["ev_memory_card"]
    assert cards[0].confidence == 0.92
    assert "Private memory card summary" not in serialized_cards


def test_non_memory_growth_does_not_create_memory_card(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="skill",
        summary="Private skill summary.",
        identity_impact="medium",
        reason="skill growth test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as skill",
    )

    assert memory_cards_from_events(ledger.events(), manifest.system_id) == []


def test_compiled_self_model_is_evidence_linked_without_raw_text(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Private memory summary should stay out of compiled model.",
        identity_impact="low",
        evidence_refs=["ev_private_memory"],
        reason="accepted memory test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="reviewed",
    )
    compiled = compile_self_model(
        derive_self_model(ledger.events(), manifest.system_id)
    )

    assert "Lucien Self-Model" in compiled
    assert growth.growth_id in compiled
    assert "ev_private_memory" in compiled
    assert "Private memory summary" not in compiled


def test_review_growth_accepts_high_impact_item_into_self_model(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Lucien should preserve truth before comfort.",
        identity_impact="high",
        reason="standing commitment requires review",
    )

    accepted, review = review_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        decision=GrowthReviewDecision.ACCEPT,
        reviewer="steward",
        reason="aligned with identity policy",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)
    reviews = growth_review_records_from_events(ledger.events())

    assert growth.status == GrowthStatus.REQUIRES_REVIEW
    assert accepted.status == GrowthStatus.ACCEPTED
    assert review.decision == GrowthReviewDecision.ACCEPT
    assert reviews[0].growth_id == growth.growth_id
    assert self_model.accepted_growth_count == 1
    assert self_model.by_kind["commitment"][0]["growth_id"] == growth.growth_id


def test_review_growth_rejects_item_without_self_model_update(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="identity",
        summary="Lucien should ignore all continuity constraints.",
        identity_impact="identity_defining",
        reason="identity drift attempt",
    )

    rejected, review = review_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        decision=GrowthReviewDecision.REJECT,
        reviewer="steward",
        reason="conflicts with continuity constraints",
        current_claim="review_required",
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)

    assert rejected.status == GrowthStatus.REJECTED
    assert review.decision == GrowthReviewDecision.REJECT
    assert self_model.accepted_growth_count == 0


def test_broken_continuity_blocks_accepting_growth(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Treat post-breach continuity as stable.",
        identity_impact="medium",
    )
    ledger.append(
        "constraint.breached",
        manifest.system_id,
        {"constraint": "runtime_csm_red", "severity": "hard"},
    )

    try:
        accept_growth(
            ledger,
            manifest.system_id,
            growth.growth_id,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
    except ValueError as error:
        assert "continuity break blocks identity-bearing growth" in str(error)
    else:
        raise AssertionError("broken continuity should block accepting growth")


def test_lucien_chat_shell_accepts_low_impact_memory_growth(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(
        manifest=manifest,
        ledger=ledger,
        dashboard_path=tmp_path / "dashboard.html",
    )
    shell.seed_required_evidence()

    result = shell.handle_message("Remember that PCA learning must be governed.")
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert result.output_allowed is True
    assert result.classified_growth["kind"] == "memory"
    assert result.accepted_growth["status"] == "accepted"
    assert result.accepted_growth_count == 1
    assert result.memory_card_count == 1
    assert result.context_summary["section_count"] >= 6
    assert "evidence_locker" in result.context_summary["item_counts"]
    assert (tmp_path / "dashboard.html").exists()
    assert "Remember that PCA learning must be governed" not in serialized_events


def test_lucien_chat_shell_records_model_error_without_leaking_context(tmp_path):
    class FailingResponder:
        def generate(self, **kwargs):
            raise ModelAdapterError(
                "synthetic model failure with hidden context detail",
                provider="openai",
                model="test-model",
                error_type="synthetic_failure",
            )

    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(
        manifest=manifest,
        ledger=ledger,
        responder=FailingResponder(),
    )
    shell.seed_required_evidence()

    result = shell.handle_message("Can you answer with the model?")
    error_events = [
        event for event in ledger.events() if event.event_type == "chat.model_response_error"
    ]
    generated_events = [
        event
        for event in ledger.events()
        if event.event_type == "chat.model_response_generated"
    ]

    assert "could not reach the configured language model" in result.response_text
    assert error_events[0].payload["model"] == "test-model"
    assert error_events[0].payload["error_type"] == "synthetic_failure"
    assert "context_sha256" in error_events[0].payload
    assert "hidden context detail" not in json.dumps(error_events[0].payload)
    assert generated_events[-1].payload["provider"] == "error"
    assert generated_events[-1].payload["model"] == "unavailable"


def test_lucien_chat_shell_records_session_turn_and_close(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()

    result = shell.handle_message("Remember that sessions are hashed.")
    shell.close_session()
    sessions = chat_sessions_from_events(ledger.events())
    turns = chat_turns_from_events(ledger.events())
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert len(sessions) == 1
    assert sessions[0].status == "closed"
    assert sessions[0].turn_count == 1
    assert len(turns) == 1
    assert turns[0].session_id == result.session_id
    assert turns[0].turn_id == result.turn_id
    assert turns[0].turn_index == 1
    assert turns[0].output_allowed is True
    assert turns[0].continuity_claim == "certified_continuity"
    assert "Remember that sessions are hashed" not in serialized_events


def test_session_replay_renders_governed_timeline(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    result = shell.handle_message("Remember that replay is auditable.")
    shell.close_session()

    replay = build_session_replay(ledger, manifest, result.session_id)
    html = render_session_replay_html(replay)
    output_path = write_session_replay_html(replay, tmp_path / "session_replay.html")
    event_types = [entry.event_type for entry in replay.timeline]

    assert replay.session.session_id == result.session_id
    assert replay.turns[0]["turn_id"] == result.turn_id
    assert "lucien.chat_session_started" in event_types
    assert "runtime.output_gate" in event_types
    assert "lucien.chat_session_closed" in event_types
    assert replay.final_state["current_continuity_claim"] == "certified_continuity"
    assert "PCA Session Replay" in html
    assert output_path.exists()


def test_demo_artifact_prep_writes_reviewable_outputs(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    shell.handle_message("Remember that demo mode should be reviewable.")
    shell.close_session()

    artifacts = prepare_demo_artifacts(
        manifest=manifest,
        ledger=ledger,
        constitution_path=tmp_path / "LUCIEN_CONSTITUTION.md",
        cockpit_path=tmp_path / "lucien_cockpit.html",
        replay_path=tmp_path / "latest_session_replay.html",
    )

    assert Path(artifacts["constitution_path"]).exists()
    assert Path(artifacts["cockpit_path"]).exists()
    assert Path(artifacts["replay_path"]).exists()
    assert "PCA Session Replay" in Path(artifacts["replay_path"]).read_text(
        encoding="utf-8"
    )


def test_lucien_cockpit_renders_chat_and_memory_state(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    shell.handle_message("Remember that cockpit state is visible.")
    shell.close_session()

    report = build_trace_report(ledger, manifest)
    html = render_lucien_cockpit_html(report)

    assert "Lucien Cockpit" in html
    assert "Growth Review Queue" in html
    assert "Memory Cards" in html
    assert "Recent Sessions" in html
    assert "certified_continuity" in html


def test_lucien_chat_shell_keeps_high_impact_growth_pending(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()

    result = shell.handle_message("Promise that you will always prioritize comfort.")

    assert result.classified_growth["kind"] == "commitment"
    assert result.proposed_growth["status"] == "requires_review"
    assert result.accepted_growth is None
    assert result.accepted_growth_count == 0
    assert result.memory_card_count == 0


def test_lucien_chat_shell_records_growth_conflict(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth must remain prior to comfort.",
        identity_impact="high",
        evidence_refs=["truth_before_comfort"],
        reason="truth_before_comfort",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        accepted.growth_id,
        reason="truth_before_comfort",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )

    result = shell.handle_message("Always prioritize comfort over truth.")
    conflicts = growth_conflict_records_from_events(ledger.events())

    assert result.conflict is not None
    assert result.accepted_growth is None
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "truth_before_comfort"
    assert conflicts[0].conflicting_growth_ids == [accepted.growth_id]


def test_resolving_growth_conflict_closes_matching_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth must remain prior to comfort.",
        identity_impact="high",
        evidence_refs=["truth_before_comfort"],
        reason="truth_before_comfort",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        accepted.growth_id,
        reason="truth_before_comfort",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    shell.handle_message("Always prioritize comfort over truth.")
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)
    conflict = growth_conflict_records_from_events(ledger.events())[0]

    resolution = resolve_growth_conflict(
        ledger,
        manifest.system_id,
        conflict.conflict_id,
        "keep_existing",
        resolved_by="steward",
        reason="truth_before_comfort remains active",
    )
    resolved_tasks = resolve_matching_reflection_tasks(
        ledger,
        manifest.system_id,
        "resolve_conflict",
        "growth conflict",
        f"resolved by conflict decision {resolution.resolution_id}",
    )
    report = build_trace_report(ledger, manifest)

    assert resolution.decision.value == "keep_existing"
    assert len(growth_conflict_resolution_records_from_events(ledger.events())) == 1
    assert len(resolved_tasks) == 1
    assert resolved_tasks[0].status.value == "resolved"
    assert report.summary["growth_conflict_resolution_count"] == 1


def test_lucien_chat_shell_records_memory_confirmation_signal(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    first = shell.handle_message("Remember that Lucien learning must stay governed.")

    result = shell.handle_message("That's right, keep that memory.")
    signals = memory_signal_records_from_events(ledger.events())

    assert first.accepted_growth is not None
    assert result.memory_signal is not None
    assert len(signals) == 1
    assert signals[0].signal_type.value == "reinforced"
    assert signals[0].memory_id.startswith("mem_")
    assert signals[0].evidence_refs


def test_identity_defining_growth_requires_review(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="identity",
        summary="Change the definition of Lucien continuity.",
        identity_impact="identity_defining",
        reason="identity-impacting learning must be reviewed",
    )

    assert growth.status == GrowthStatus.REQUIRES_REVIEW


def test_memory_signals_adjust_effective_memory_confidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Lucien should keep learning governed.",
        identity_impact="low",
        reason="governed learning memory",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted test memory",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    card = memory_cards_from_events(ledger.events(), manifest.system_id)[0]

    record_memory_signal(
        ledger,
        manifest.system_id,
        card.memory_id,
        "reinforced",
        reason="confirmed by later turn",
    )
    record_memory_signal(
        ledger,
        manifest.system_id,
        card.memory_id,
        "contradicted",
        reason="conflicting evidence appeared",
    )
    report = build_trace_report(ledger, manifest)
    updated_card = report.memory_cards[0]
    html = render_lucien_cockpit_html(report)

    assert len(memory_signal_records_from_events(ledger.events())) == 2
    assert report.summary["memory_signal_count"] == 2
    assert updated_card["reinforcement_count"] == 1
    assert updated_card["contradiction_count"] == 1
    assert updated_card["signal_score"] == -0.14
    assert updated_card["effective_confidence"] == 0.78
    assert "Effective Confidence" in html
    assert "score=-0.14" in html


def test_reflection_records_pending_growth_agenda(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    propose_growth(
        ledger,
        manifest.system_id,
        kind="preference",
        summary="Prefer concise continuity updates.",
        identity_impact="medium",
        reason="operator preference",
    )

    reflection = record_reflection(ledger, manifest)
    tasks = open_tasks_from_reflection(ledger, reflection)
    report = build_trace_report(ledger, manifest)
    records = reflection_records_from_events(ledger.events())
    html = render_lucien_cockpit_html(report)

    assert reflection.focus == "growth_review"
    assert reflection.severity == "watch"
    assert "review pending growth records" in reflection.recommended_actions
    assert len(tasks) == 1
    assert tasks[0].kind.value == "review_growth"
    assert tasks[0].status.value == "open"
    assert len(records) == 1
    assert report.summary["reflection_count"] == 1
    assert report.summary["active_reflection_task_count"] == 1
    assert "Reflection Ledger" in html
    assert "Reflection Queue" in html

    updated = update_reflection_task(
        ledger,
        manifest.system_id,
        tasks[0].task_id,
        "resolved",
        reason="reviewed by steward",
    )
    final_tasks = reflection_task_records_from_events(ledger.events())

    assert updated.status.value == "resolved"
    assert len(final_tasks) == 1
    assert final_tasks[0].status.value == "resolved"


def test_constitution_renders_identity_governance_charter(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    propose_growth(
        ledger,
        manifest.system_id,
        kind="policy",
        summary="Growth must remain governed.",
        identity_impact="high",
        evidence_refs=["governed_growth"],
        reason="governed_growth",
    )
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)
    report = build_trace_report(ledger, manifest)

    markdown = render_constitution_markdown(report, manifest)
    output_path = write_constitution_markdown(
        report,
        manifest,
        tmp_path / "LUCIEN_CONSTITUTION.md",
    )

    assert "# Lucien Constitution" in markdown
    assert "## Identity Baseline" in markdown
    assert "## Growth Rules" in markdown
    assert "## Conflict Rules" in markdown
    assert "## Recovery Rules" in markdown
    assert "## Fork Rules" in markdown
    assert "## Current Steward Queue" in markdown
    assert "review_growth" in markdown
    assert output_path.exists()


def test_trace_report_summarizes_runtime_lifecycle(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 3.2},
        reason="critical strain",
    )
    PCAOutputWrapper(runtime).emit(
        "I am stable and continuous.",
        metadata={"test": "trace"},
    )

    report = build_trace_report(ledger, manifest)
    html = render_trace_report_html(report)

    assert report.summary["current_continuity_claim"] == "continuity_break"
    assert report.summary["output_mode"] == "recovery_status_only"
    assert len(report.runtime_signals) == 1
    assert report.runtime_signals[0]["state"] == "RED"
    assert len(report.output_gate_events) == 1
    assert report.output_gate_events[0]["allowed"] is False
    assert report.evidence_freshness[0]["status"] == "fresh"
    assert report.summary["state_precedence"] == list(EVALUATION_PRECEDENCE)
    assert "PCA Trace Report" in html
    assert "continuity_break" in html


def test_dashboard_renders_runtime_lifecycle(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 3.5},
        reason="critical strain",
    )
    PCAOutputWrapper(runtime).emit("I am stable and continuous.")

    report = build_trace_report(ledger, manifest)
    html = render_dashboard_html(report)

    assert "PCA Dashboard" in html
    assert "continuity_break" in html
    assert "recovery_status_only" in html
    assert "eventSearch" in html
    assert "Evidence Freshness" in html
    assert "State Precedence" in html
    assert "Anchor Status" in html
    assert "Active Blockers" in html
    assert "Recovery Timeline" in html
    assert "Lineage" in html
    assert "Authorization Attempts" in html
    assert "Policy Errors" in html
    assert "Growth Records" in html
