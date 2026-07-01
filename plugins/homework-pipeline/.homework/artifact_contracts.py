"""Generic P0-P4 runtime artifact contract validation.

OpenSpec describes the behavior these artifacts must support. This module is
the plugin-owned executable surface for checking the runtime YAML facts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # pragma: no cover - import probe only
    import yaml as _yaml  # type: ignore
except Exception:  # pragma: no cover
    _yaml = None


GENERIC_TIERS = {
    "A": "machine_verifiable",
    "A(machine_verifiable)": "machine_verifiable",
    "machine_verifiable": "machine_verifiable",
    "machine-verifiable": "machine_verifiable",
    "B": "language_equivalent",
    "B(language_equivalent)": "language_equivalent",
    "language_equivalent": "language_equivalent",
    "language-equivalent": "language_equivalent",
    "A(default_trade)": "default_trade",
    "default_trade": "default_trade",
    "default-trade": "default_trade",
    "C_irreducible": "supply_halt",
    "C(supply_halt)": "supply_halt",
    "supply_halt": "supply_halt",
    "supply-halt": "supply_halt",
}

SCENARIO_CONTROL_KEYS = {
    "assignment_family",
    "course_family_selector",
    "domain_profile",
    "domain_package",
    "domain_template",
    "fixed_dag_template",
    "planner_template",
    "scenario_branch",
    "scenario_template",
    "task_family",
    "task_family_selector",
    "task_profile",
    "template_selector",
}

SCENARIO_CONTROL_SUFFIXES = ("_selector", "_template")


@dataclass(frozen=True)
class ContractIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ArtifactContractError(ValueError):
    def __init__(self, issues: Sequence[ContractIssue]) -> None:
        self.issues = list(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    if _yaml is None:
        raise RuntimeError("PyYAML is required to load artifact contract files")
    loaded = _yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ArtifactContractError(
            [ContractIssue(str(path), "artifact must load as a YAML mapping")]
        )
    return loaded


def validate_artifact_contract_files(
    *,
    spec_path: str | Path,
    resource_plan_path: str | Path,
    verifiability_report_path: str | Path,
    plan_path: str | Path,
    raise_on_error: bool = True,
) -> list[ContractIssue]:
    return validate_artifact_contracts(
        spec=load_yaml_file(spec_path),
        resource_plan=load_yaml_file(resource_plan_path),
        verifiability_report=load_yaml_file(verifiability_report_path),
        plan=load_yaml_file(plan_path),
        raise_on_error=raise_on_error,
    )


def validate_artifact_contracts(
    *,
    spec: Mapping[str, Any],
    resource_plan: Mapping[str, Any],
    verifiability_report: Mapping[str, Any],
    plan: Mapping[str, Any],
    raise_on_error: bool = True,
) -> list[ContractIssue]:
    """Validate generic fields and cross-artifact references for P0-P4 YAML."""

    issues: list[ContractIssue] = []

    for name, artifact in (
        ("spec", spec),
        ("resource_plan", resource_plan),
        ("verifiability_report", verifiability_report),
        ("plan", plan),
    ):
        _reject_scenario_controls(artifact, name, issues)

    contract = _validate_spec(spec, issues)
    _validate_resource_plan(resource_plan, contract, issues)
    report_tiers = _validate_verifiability_report(
        verifiability_report, contract, issues
    )
    _validate_plan(plan, contract, report_tiers, issues)

    if issues and raise_on_error:
        raise ArtifactContractError(issues)
    return issues


def _validate_spec(
    spec: Mapping[str, Any], issues: list[ContractIssue]
) -> dict[str, set[str]]:
    course = _mapping(spec.get("course"))
    if course is None:
        _add(issues, "spec.course", "required mapping is missing")
    else:
        _require_non_empty(course, ("source_files",), "spec.course", issues)
        missing = course.get("missing_signals")
        if not isinstance(missing, list):
            _add(
                issues,
                "spec.course.missing_signals",
                "must be present as a list, even when empty",
            )

    constraint_ids: set[str] = set()
    constraints = _mapping(spec.get("constraints"))
    if constraints is None:
        _add(issues, "spec.constraints", "required mapping is missing")
    else:
        for bucket in ("hard", "soft", "bonus"):
            value = constraints.get(bucket, [])
            if not isinstance(value, list):
                _add(issues, f"spec.constraints.{bucket}", "must be a list")
                continue
            for index, item in enumerate(value):
                path = f"spec.constraints.{bucket}[{index}]"
                item_map = _mapping(item)
                if item_map is None:
                    _add(issues, path, "constraint must be a mapping")
                    continue
                constraint_id = _require_non_empty(item_map, ("id",), path, issues)
                if constraint_id:
                    constraint_ids.add(constraint_id)
                _require_non_empty(item_map, ("rule",), path, issues)
                _require_non_empty(item_map, ("verify",), path, issues)
                _require_non_empty(
                    item_map, ("source_refs", "source_ref"), path, issues
                )

    deliverable_ids: set[str] = set()
    stage_ids: set[str] = set()
    deliverables = spec.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        _add(issues, "spec.deliverables", "must be a non-empty list")
    else:
        for index, item in enumerate(deliverables):
            path = f"spec.deliverables[{index}]"
            deliverable = _mapping(item)
            if deliverable is None:
                _add(issues, path, "deliverable must be a mapping")
                continue
            deliverable_id = _require_non_empty(deliverable, ("id",), path, issues)
            if deliverable_id:
                deliverable_ids.add(deliverable_id)
            _require_non_empty(deliverable, ("type",), path, issues)
            _require_non_empty(deliverable, ("path",), path, issues)
            _require_non_empty(deliverable, ("source_refs", "source_ref"), path, issues)
            stages = deliverable.get("stages")
            if not isinstance(stages, list) or not stages:
                _add(issues, f"{path}.stages", "must be a non-empty list")
                continue
            for stage_index, stage_item in enumerate(stages):
                stage_path = f"{path}.stages[{stage_index}]"
                stage = _mapping(stage_item)
                if stage is None:
                    _add(issues, stage_path, "stage must be a mapping")
                    continue
                stage_id = _require_non_empty(stage, ("id",), stage_path, issues)
                if stage_id:
                    stage_ids.add(stage_id)
                _require_non_empty(
                    stage, ("description", "name"), stage_path, issues
                )
                _require_non_empty(
                    stage,
                    ("verification_expectation", "verify", "evidence_expectation"),
                    stage_path,
                    issues,
                )
                _require_non_empty(
                    stage, ("source_refs", "source_ref"), stage_path, issues
                )

    return {
        "constraint_ids": constraint_ids,
        "deliverable_ids": deliverable_ids,
        "stage_ids": stage_ids,
    }


def _validate_resource_plan(
    resource_plan: Mapping[str, Any],
    contract: Mapping[str, set[str]],
    issues: list[ContractIssue],
) -> None:
    resources = _first_list(resource_plan, ("resources", "resource_stubs"))
    if not resources:
        _add(issues, "resource_plan.resources", "must be a non-empty list")
        return

    stage_ids = contract["stage_ids"]
    constraint_ids = contract["constraint_ids"]
    resource_ids: set[str] = set()

    for index, item in enumerate(resources):
        path = f"resource_plan.resources[{index}]"
        resource = _mapping(item)
        if resource is None:
            _add(issues, path, "resource must be a mapping")
            continue
        resource_id = _require_non_empty(resource, ("id",), path, issues)
        if resource_id:
            resource_ids.add(resource_id)
        stage_id = _require_non_empty(resource, ("stage_id",), path, issues)
        if stage_id and stage_id not in stage_ids:
            _add(issues, f"{path}.stage_id", f"unknown stage_id {stage_id!r}")
        _require_non_empty(resource, ("kind", "type"), path, issues)
        acquisition = _mapping(resource.get("acquisition")) or {}
        closure = _require_non_empty(resource, ("closure",), path, issues, fallback_mapping=acquisition)
        _require_non_empty(resource, ("why", "rationale"), path, issues, fallback_mapping=acquisition)
        _require_non_empty(resource, ("source_refs", "source_ref"), path, issues)

        human_supply = _mapping(resource.get("human_supply")) or _mapping(
            resource.get("human_in_loop")
        )
        supply_needed = bool(resource.get("supply_needed"))
        outside_closure = closure == "outside"
        if human_supply or supply_needed or outside_closure:
            _require_non_empty(
                resource,
                ("obtain_steps",),
                path,
                issues,
                fallback_mapping=human_supply,
            )

    constants = resource_plan.get("constants", [])
    if isinstance(constants, list):
        for index, item in enumerate(constants):
            item_map = _mapping(item)
            if item_map is None:
                _add(issues, f"resource_plan.constants[{index}]", "must be a mapping")
                continue
            constraint_id = _string(item_map.get("for_constraint"))
            if constraint_id:
                for single_id in constraint_id.split(";"):
                    single_id = single_id.strip()
                    if single_id and single_id not in constraint_ids:
                        _add(
                            issues,
                            f"resource_plan.constants[{index}].for_constraint",
                            f"unknown constraint id {single_id!r}",
                        )

    if not resource_ids:
        _add(issues, "resource_plan.resources", "no stable resource ids found")


def _validate_verifiability_report(
    report: Mapping[str, Any],
    contract: Mapping[str, set[str]],
    issues: list[ContractIssue],
) -> dict[str, str]:
    records = _first_list(
        report,
        (
            "stage_records",
            "stage_verifications",
            "verifications",
            "verifiability",
            "records",
            "stages",
        ),
    )
    if not records:
        _add(
            issues,
            "verifiability_report.stage_records",
            "must be a non-empty list of per-stage decisions",
        )
        records = []

    stage_ids = contract["stage_ids"]
    report_tiers: dict[str, str] = {}
    for index, item in enumerate(records):
        path = f"verifiability_report.stage_records[{index}]"
        record = _mapping(item)
        if record is None:
            _add(issues, path, "stage decision must be a mapping")
            continue
        stage_id = _require_non_empty(record, ("stage_id",), path, issues)
        if stage_id and stage_id not in stage_ids:
            _add(issues, f"{path}.stage_id", f"unknown stage_id {stage_id!r}")

        tier = _require_non_empty(
            record, ("verification_tier", "resolved_tier", "tier"), path, issues
        )
        canonical_tier = _canonical_tier(tier)
        if tier and canonical_tier is None:
            _add(issues, f"{path}.verification_tier", f"unknown tier {tier!r}")
        elif stage_id and canonical_tier:
            report_tiers[stage_id] = canonical_tier

        _require_non_empty(
            record,
            ("evidence_required", "evidence_expectation"),
            path,
            issues,
        )
        _require_non_empty(record, ("rationale",), path, issues)
        _require_non_empty(record, ("source_refs", "source_ref"), path, issues)

        attempts = record.get("downgrade_attempts")
        if not isinstance(attempts, list):
            _add(issues, f"{path}.downgrade_attempts", "must be present as a list")
            attempts = []
        if canonical_tier in {"language_equivalent", "default_trade", "supply_halt"}:
            if not attempts:
                _add(
                    issues,
                    f"{path}.downgrade_attempts",
                    f"{canonical_tier} decisions require at least one attempt",
                )
        if canonical_tier == "default_trade":
            _validate_default_trade_metadata(record, path, issues)
        for attempt_index, attempt_item in enumerate(attempts):
            attempt_path = f"{path}.downgrade_attempts[{attempt_index}]"
            attempt = _mapping(attempt_item)
            if attempt is None:
                _add(issues, attempt_path, "attempt must be a mapping")
                continue
            _require_non_empty(
                attempt,
                ("restatement", "path", "proposed_restatement"),
                attempt_path,
                issues,
            )
            _require_non_empty(attempt, ("source",), attempt_path, issues)
            _require_non_empty(attempt, ("outcome", "result"), attempt_path, issues)
            _require_non_empty(
                attempt,
                ("evidence_required", "evidence_expectation"),
                attempt_path,
                issues,
            )
            _require_non_empty(attempt, ("rationale",), attempt_path, issues)

    summary = _mapping(report.get("breakpoints_summary"))
    if summary is None:
        _add(issues, "verifiability_report.breakpoints_summary", "required mapping")
    else:
        if not isinstance(summary.get("sense_default_trade", []), list):
            _add(
                issues,
                "verifiability_report.breakpoints_summary.sense_default_trade",
                "must be a list",
            )
        else:
            for index, item in enumerate(summary.get("sense_default_trade", [])):
                path = f"verifiability_report.breakpoints_summary.sense_default_trade[{index}]"
                metadata = _mapping(item)
                if metadata is None:
                    _add(
                        issues,
                        path,
                        "default_trade entry must be a mapping with fallback metadata",
                    )
                    continue
                _validate_default_trade_metadata(metadata, path, issues)
        supply_halt = summary.get("supply_halt", [])
        if not isinstance(supply_halt, list):
            _add(
                issues,
                "verifiability_report.breakpoints_summary.supply_halt",
                "must be a list",
            )
        else:
            for index, item in enumerate(supply_halt):
                path = f"verifiability_report.breakpoints_summary.supply_halt[{index}]"
                halt = _mapping(item)
                if halt is None:
                    _add(issues, path, "supply_halt entry must be a mapping")
                    continue
                for field in (
                    "id",
                    "stage_id",
                    "kind",
                    "trigger",
                    "closure",
                    "has_default",
                    "when_provided",
                ):
                    _require_non_empty(halt, (field,), path, issues)
                _require_non_empty(halt, ("why", "rationale"), path, issues)
                _require_non_empty(halt, ("obtain_steps",), path, issues)
                if not _has_source_or_provenance_ref(halt):
                    _add(
                        issues,
                        path,
                        "missing required field: source_ref or provenance_ref",
                    )
                stage_id = _string(halt.get("stage_id"))
                if stage_id and stage_id not in stage_ids:
                    _add(issues, f"{path}.stage_id", f"unknown stage_id {stage_id!r}")

    return report_tiers


def _validate_default_trade_metadata(
    record: Mapping[str, Any],
    path: str,
    issues: list[ContractIssue],
) -> None:
    metadata = _mapping(record.get("default_trade")) or record
    _require_non_empty(
        metadata,
        ("relaxed_requirement", "relaxed_requirement_id", "requirement"),
        path,
        issues,
    )
    _require_non_empty(
        metadata,
        ("fallback_reason", "reason", "rationale"),
        path,
        issues,
    )
    _require_non_empty(
        metadata,
        ("evidence_source", "source", "synthetic_evidence_source"),
        path,
        issues,
    )
    if not _truthy_marker(metadata.get("non_real_output_marker")) and not _truthy_marker(
        metadata.get("not_real_execution_evidence")
    ):
        _add(
            issues,
            path,
            "missing required field: non_real_output_marker",
        )
    if not _has_source_or_provenance_ref(metadata):
        _add(
            issues,
            path,
            "missing required field: source_ref or provenance_ref",
        )


def _has_source_or_provenance_ref(mapping: Mapping[str, Any]) -> bool:
    if _string(mapping.get("source_ref")) or _string(mapping.get("provenance_ref")):
        return True
    source_refs = mapping.get("source_refs")
    if isinstance(source_refs, list) and any(_string(value) for value in source_refs):
        return True
    provenance = _mapping(mapping.get("provenance"))
    if provenance is not None:
        return bool(_string(provenance.get("source_ref")) or _string(provenance.get("ref")))
    return False


def _truthy_marker(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(_string(value))


def _validate_plan(
    plan: Mapping[str, Any],
    contract: Mapping[str, set[str]],
    report_tiers: Mapping[str, str],
    issues: list[ContractIssue],
) -> None:
    final_dag = _mapping(plan.get("final_dag"))
    if final_dag is None:
        _add(issues, "plan.final_dag", "required mapping is missing")
        return

    nodes = final_dag.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        _add(issues, "plan.final_dag.nodes", "must be a non-empty list")
        return

    stage_ids = contract["stage_ids"]
    node_names: set[str] = set()
    for index, item in enumerate(nodes):
        path = f"plan.final_dag.nodes[{index}]"
        node = _mapping(item)
        if node is None:
            _add(issues, path, "node must be a mapping")
            continue
        name = _require_non_empty(node, ("name", "id"), path, issues)
        if name:
            node_names.add(name)
        stage_id = _require_non_empty(node, ("stage_id",), path, issues)
        if stage_id and stage_id not in stage_ids:
            _add(issues, f"{path}.stage_id", f"unknown stage_id {stage_id!r}")

        tier = _require_non_empty(node, ("tier", "verification_tier"), path, issues)
        canonical_tier = _canonical_tier(tier)
        if tier and canonical_tier is None:
            _add(issues, f"{path}.tier", f"unknown tier {tier!r}")
        if stage_id and canonical_tier and report_tiers.get(stage_id):
            if report_tiers[stage_id] != canonical_tier:
                _add(
                    issues,
                    f"{path}.tier",
                    f"tier {tier!r} conflicts with report tier {report_tiers[stage_id]!r}",
                )

        _require_non_empty(node, ("acceptance",), path, issues)
        _require_non_empty(
            node,
            ("evidence_required", "evidence_expectation"),
            path,
            issues,
        )
        _require_non_empty(node, ("failure_policy",), path, issues)
        _require_non_empty(node, ("source_refs", "source_ref"), path, issues)

    edges = final_dag.get("edges", [])
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            edge_map = _mapping(edge)
            if edge_map is None:
                continue
            for key in ("from", "to"):
                node_name = _string(edge_map.get(key))
                if node_name and node_name not in node_names:
                    _add(
                        issues,
                        f"plan.final_dag.edges[{index}].{key}",
                        f"unknown node {node_name!r}",
                    )


def _reject_scenario_controls(
    value: Any, path: str, issues: list[ContractIssue]
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_scenario_control_key(key_text):
                _add(
                    issues,
                    child_path,
                    "scenario-specific control field is not allowed in generic contracts",
                )
            _reject_scenario_controls(child, child_path, issues)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_scenario_controls(child, f"{path}[{index}]", issues)


def _is_scenario_control_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SCENARIO_CONTROL_KEYS:
        return True
    return normalized.endswith(SCENARIO_CONTROL_SUFFIXES)


def _first_list(mapping: Mapping[str, Any], keys: Iterable[str]) -> list[Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return []


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _canonical_tier(value: str | None) -> str | None:
    if value is None:
        return None
    return GENERIC_TIERS.get(value.strip())


def _require_non_empty(
    mapping: Mapping[str, Any],
    keys: Sequence[str],
    path: str,
    issues: list[ContractIssue],
    *,
    fallback_mapping: Mapping[str, Any] | None = None,
) -> str | None:
    for key in keys:
        if _is_non_empty(mapping.get(key)):
            return _string(mapping.get(key)) or key
        if fallback_mapping is not None and _is_non_empty(fallback_mapping.get(key)):
            return _string(fallback_mapping.get(key)) or key
    names = " or ".join(keys)
    _add(issues, path, f"missing required field: {names}")
    return None


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _add(issues: list[ContractIssue], path: str, message: str) -> None:
    issues.append(ContractIssue(path=path, message=message))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--resource-plan", required=True)
    parser.add_argument("--verifiability-report", required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    issues = validate_artifact_contract_files(
        spec_path=args.spec,
        resource_plan_path=args.resource_plan,
        verifiability_report_path=args.verifiability_report,
        plan_path=args.plan,
        raise_on_error=False,
    )
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("artifact contracts OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
