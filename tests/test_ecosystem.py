from polaris_guidance.ecosystem import (
    CareNetwork,
    classify_intent,
    minimize_payload,
    safety_level,
)


def test_deterministic_safety_gate_runs_before_routing() -> None:
    network = CareNetwork()
    assert safety_level("I have chest pain") == "emergency"
    assert safety_level("Can I take another dose?") == "clinical"

    result = network.route(
        patient_id="p1",
        text="I cannot breathe",
        hospital_id="stmarys",
        consent_to_share=False,
    )

    assert result["status"] == "human_escalated"
    assert network.hospital_view("stmarys")["human_escalations"] == 1
    assert network.hospital_view("riverside")["human_escalations"] == 0
    assert network.sharing_log("p1") == []


def test_clinical_question_requires_consent_then_routes_to_human_nurse() -> None:
    network = CareNetwork()
    waiting = network.route(
        patient_id="p1",
        text="What does my result mean?",
        hospital_id="stmarys",
        consent_to_share=False,
    )
    routed = network.route(
        patient_id="p1",
        text="What does my result mean?",
        hospital_id="stmarys",
        consent_to_share=True,
    )

    assert waiting["status"] == "consent_required"
    assert routed["status"] == "human_nurse_required"
    assert routed["routed_to"] == "nursing"
    assert routed["shared_fields"] == ["question"]


def test_data_minimization_strips_out_of_scope_fields() -> None:
    payload, stripped = minimize_payload(
        "pharmacy",
        {"prescription_ids": ["rx1"], "allergies": ["penicillin"], "insurance": "private"},
    )

    assert payload == {"prescription_ids": ["rx1"], "allergies": ["penicillin"]}
    assert stripped == ["insurance"]


def test_router_classifies_operational_needs() -> None:
    assert classify_intent("please check me in") == "check_in"
    assert classify_intent("can I get a wheelchair?") == "accessibility"
    assert classify_intent("I would like a payment plan") == "payment_plan"


def test_hospital_views_are_isolated() -> None:
    network = CareNetwork()
    network.readiness("p1", "stmarys", "cafeteria", None)

    assert network.hospital_view("stmarys")["readiness_count"] == 1
    assert network.hospital_view("riverside")["readiness_count"] == 0


def test_cross_hospital_conflict_shares_only_busy_window() -> None:
    network = CareNetwork()
    conflict = network.conflicts("demo-patient")[0]

    result = network.resolve_conflict("demo-patient", str(conflict["id"]))
    record = network.sharing_log("demo-patient")[-1]

    assert result["status"] == "resolved"
    assert network.conflicts("demo-patient") == []
    assert record["fields"] == ["appointment_id", "busy_window"]
    assert record["hospital_id"] == "riverside"
    assert "stmarys" not in str(record).lower()


def test_specialist_outage_routes_to_named_backup() -> None:
    network = CareNetwork()
    network.set_specialist_availability("stmarys", "billing", False)

    result = network.route(
        patient_id="p1",
        text="I have a bill question",
        hospital_id="stmarys",
        consent_to_share=True,
        payload={"invoice_id": "inv1", "insurance": "demo"},
    )

    assert result["status"] == "backup_routed"
    assert result["routed_to"] == "patient services"


def test_readiness_prepositions_without_clinical_data() -> None:
    network = CareNetwork()
    result = network.readiness("p1", "stmarys", "cafeteria", 5)
    record = network.sharing_log("p1")[-1]

    assert result["status"] == "prepositioned"
    assert record["fields"] == ["zone", "eta_minutes"]


def test_surge_opens_human_escalation_and_notification() -> None:
    network = CareNetwork()
    before = network.hospital_view("stmarys")["human_escalations"]
    result = network.set_surge("stmarys", "diagnostics", True)

    assert result["active"] is True
    assert result["affected"] == 1
    assert network.hospital_view("stmarys")["human_escalations"] == before + 1
    assert network.snapshot()["notifications"][-1]["kind"] == "delay"


def test_every_disclosure_has_fields_and_expiry() -> None:
    network = CareNetwork()
    network.route(
        patient_id="p1",
        text="Where is my appointment?",
        hospital_id="stmarys",
        consent_to_share=True,
        payload={"appointment_id": "a1", "zone": "lobby"},
    )

    records = network.sharing_log("p1")
    assert records
    assert all(record["fields"] and record["expires_at"] for record in records)
