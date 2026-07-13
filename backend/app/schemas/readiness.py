from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReadinessCheckOut(BaseModel):
    model_config = ConfigDict(extra='allow')

    category: str | None = None
    code: str | None = None
    severity: str | None = None
    ok: bool | None = None
    message: str | None = None
    action: str | None = None
    actual: Any | None = None
    target: Any | None = None


class ReadinessSectionOut(BaseModel):
    model_config = ConfigDict(extra='allow')

    key: str | None = None
    title: str | None = None
    status: str | None = None
    check_count: int | None = None
    blocker_count: int | None = None
    warning_count: int | None = None


class OperationReportBase(BaseModel):
    """Stable base contract for operational/readiness reports.

    Many existing reports predate strict Pydantic schemas and contain
    report-specific fields. `extra='allow'` preserves backward compatibility,
    while the shared fields below become a stable FE/API contract.
    """

    model_config = ConfigDict(extra='allow')

    version: str | None = None
    report_type: str | None = None
    generated_at: str | None = None
    status: str | None = None
    summary_label: str | None = None
    message: str | None = None
    blocker_count: int | None = None
    warning_count: int | None = None
    info_count: int | None = None
    checks: list[ReadinessCheckOut] | None = None
    sections: list[ReadinessSectionOut] | None = None
    next_actions: list[str] | None = None
    safe_policy: str | None = None
    read_only_guarantees: list[str] | None = None
    disclaimer: str | None = None


class ProductionReadinessReport(OperationReportBase):
    readiness: str | None = None
    stage_status: str | None = None
    primary_blocker: Any | None = None


class SecurityReadinessReport(OperationReportBase):
    app_env: str | None = None
    can_pilot: bool | None = None
    can_broad_production: bool | None = None
    primary_blocker: Any | None = None


class PerformanceReadinessReport(OperationReportBase):
    table_estimates: dict[str, Any] | None = None
    queue_pressure: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None


class QueryHotspotReport(OperationReportBase):
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class ReleaseCandidateReport(OperationReportBase):
    release_candidate: str | None = None
    go_no_go: str | None = None
    ready_for_pilot: bool | None = None
    ready_for_broad_production: bool | None = None
    gates: list[dict[str, Any]] | None = None
    blockers: list[dict[str, Any]] | None = None
    warnings: list[dict[str, Any]] | None = None
    reports: dict[str, Any] | None = None


class PilotOperationsReport(OperationReportBase):
    decision: str | None = None
    release_candidate: str | None = None
    ready_for_pilot: bool | None = None
    ready_for_broad_production: bool | None = None
    release_candidate_summary: dict[str, Any] | None = None
    gates: list[dict[str, Any]] | None = None
    phases: list[dict[str, Any]] | None = None
    monitoring_cadence: list[dict[str, Any]] | None = None
    rollback_triggers: list[dict[str, Any]] | None = None
    evidence_required: list[str] | None = None
    signoff: dict[str, Any] | None = None
    blockers: list[dict[str, Any]] | None = None
    warnings: list[dict[str, Any]] | None = None


class MaintainabilityContractReport(OperationReportBase):
    report_type: Literal['maintainability_contract'] = 'maintainability_contract'
    status: Literal['READY', 'READY_WITH_WARNINGS', 'BLOCKED'] | str
    file_metrics: list[dict[str, Any]] = Field(default_factory=list)
    contract_modules: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class SecurityAttackSimulationReport(OperationReportBase):
    report_type: Literal['security_attack_simulation_v1'] | str = 'security_attack_simulation_v1'
    attack_count: int | None = None
    protected_count: int | None = None
    needs_review_count: int | None = None
    attacks: list[dict[str, Any]] = Field(default_factory=list)


class ProductionPilotFinalReport(OperationReportBase):
    report_type: Literal['production_pilot_final_gate'] | str = 'production_pilot_final_gate'
    decision: str | None = None
    ready_for_pilot: bool | None = None
    ready_for_broad_production: bool | None = None
    gates: list[dict[str, Any]] | None = None
    final_checks: list[dict[str, Any]] | None = None
    evidence_required: list[str] | None = None
    load_test_plan: list[dict[str, Any]] | None = None
    rollback_drill: dict[str, Any] | None = None
    signoff: dict[str, Any] | None = None
    reports: dict[str, Any] | None = None
