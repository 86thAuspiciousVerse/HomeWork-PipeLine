"""Test-only semantic regression helpers for representative P0-P4 fixtures.

These helpers intentionally know nothing about assignment domains or technical
artifact categories. Fixture YAML declares the exact paths and facts to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # pragma: no cover - import probe only
    import yaml as _yaml  # type: ignore
except Exception:  # pragma: no cover
    _yaml = None


@dataclass(frozen=True)
class SemanticIssue:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def load_expectations(path: str | Path) -> dict[str, Any]:
    if _yaml is None:
        raise RuntimeError("PyYAML is required to load semantic expectations")
    loaded = _yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def normalize_semantic_facts(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    spec = _mapping(artifacts.get("spec")) or {}
    resource_plan = _mapping(artifacts.get("resource_plan")) or {}
    report = _mapping(artifacts.get("verifiability_report")) or {}
    plan = _mapping(artifacts.get("plan")) or {}

    deliverables = [_mapping(item) or {} for item in spec.get("deliverables", [])]
    resources = [_mapping(item) or {} for item in _first_list(resource_plan, ("resources",))]
    summary = _mapping(report.get("breakpoints_summary")) or {}
    supply_halts = [
        _mapping(item) or {}
        for item in summary.get("supply_halt", [])
        if isinstance(item, Mapping)
    ]

    return {
        "all_text": " ".join(_walk_text(artifacts)).lower(),
        "deliverable_paths": sorted(
            path for item in deliverables if (path := _text(item.get("path")))
        ),
        "plan_artifact_paths": sorted(_plan_artifact_paths(plan)),
        "resources": [
            {
                "id": _text(item.get("id")),
                "kind": _text(item.get("kind") or item.get("type")),
                "closure": _text(item.get("closure")),
                "stage_id": _text(item.get("stage_id")),
                "supply_needed": bool(item.get("supply_needed")),
            }
            for item in resources
        ],
        "supply_halts": [
            {
                "id": _text(item.get("id")),
                "kind": _text(item.get("kind")),
                "closure": _text(item.get("closure")),
                "stage_id": _text(item.get("stage_id")),
                "source_ref": _source_ref(item),
                "obtain_steps": [
                    _text(step)
                    for step in item.get("obtain_steps", [])
                    if _text(step)
                ],
            }
            for item in supply_halts
        ],
    }


def validate_semantic_expectations(
    expectations: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> list[SemanticIssue]:
    facts = normalize_semantic_facts(artifacts)
    issues: list[SemanticIssue] = []

    for index, group in enumerate(expectations.get("required_text", [])):
        tokens = [str(token).lower() for token in group]
        if not all(token in facts["all_text"] for token in tokens):
            issues.append(
                SemanticIssue(
                    "missing_text",
                    f"required_text[{index}] tokens not found together: {tokens}",
                )
            )

    for expected in expectations.get("required_resource_closures", []):
        kind = _text((_mapping(expected) or {}).get("kind"))
        closure = _text((_mapping(expected) or {}).get("closure"))
        if not any(
            resource["kind"] == kind and resource["closure"] == closure
            for resource in facts["resources"]
        ):
            issues.append(
                SemanticIssue(
                    "missing_resource_closure",
                    f"no resource has kind={kind!r} closure={closure!r}",
                )
            )

    forbidden_kinds = set(expectations.get("forbidden_supply_halt_kinds", []))
    for halt in facts["supply_halts"]:
        if halt["kind"] in forbidden_kinds:
            issues.append(
                SemanticIssue(
                    "forbidden_supply_halt",
                    f"supply_halt kind {halt['kind']!r} is forbidden",
                )
            )

    for expected in expectations.get("required_supply_halts", []):
        _validate_required_supply_halt(issues, expected, facts["supply_halts"])

    _require_paths(
        issues,
        "missing_deliverable_path",
        expectations.get("required_deliverable_paths", []),
        facts["deliverable_paths"],
        "deliverable",
    )
    _require_paths(
        issues,
        "missing_traceable_artifact_path",
        expectations.get("required_traceable_artifact_paths", []),
        facts["plan_artifact_paths"],
        "traceable plan artifact",
    )

    return issues


def _validate_required_supply_halt(
    issues: list[SemanticIssue],
    expected: Any,
    supply_halts: Iterable[Mapping[str, Any]],
) -> None:
    expected_map = _mapping(expected) or {}
    kind = _text(expected_map.get("kind"))
    closure = _text(expected_map.get("closure"))
    source_ref_required = bool(expected_map.get("source_ref_required"))
    obtain_steps_required = bool(expected_map.get("obtain_steps_required"))
    candidates = [
        halt
        for halt in supply_halts
        if halt["kind"] == kind and (closure is None or halt["closure"] == closure)
    ]
    if not candidates:
        issues.append(
            SemanticIssue(
                "missing_supply_halt",
                f"no supply_halt has kind={kind!r} closure={closure!r}",
            )
        )
        return
    if source_ref_required and not any(halt["source_ref"] for halt in candidates):
        issues.append(
            SemanticIssue(
                "missing_supply_source_ref",
                f"supply_halt kind={kind!r} lacks source/provenance ref",
            )
        )
    if obtain_steps_required and not any(halt["obtain_steps"] for halt in candidates):
        issues.append(
            SemanticIssue(
                "missing_supply_steps",
                f"supply_halt kind={kind!r} lacks obtain_steps",
            )
        )


def _require_paths(
    issues: list[SemanticIssue],
    code: str,
    expected: Iterable[str],
    actual: Iterable[str],
    label: str,
) -> None:
    actual_set = set(actual)
    for path in expected:
        if path not in actual_set:
            issues.append(SemanticIssue(code, f"missing {label} path {path!r}"))


def _plan_artifact_paths(plan: Mapping[str, Any]) -> set[str]:
    final_dag = _mapping(plan.get("final_dag")) or {}
    paths: set[str] = set()
    for node in final_dag.get("nodes", []):
        node_map = _mapping(node) or {}
        for key in ("evidence_required", "evidence_expectation"):
            evidence = _mapping(node_map.get(key)) or {}
            for path in evidence.get("artifacts", []):
                if text := _text(path):
                    paths.add(text)
    return paths


def _first_list(mapping: Mapping[str, Any], keys: Iterable[str]) -> list[Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return []


def _source_ref(item: Mapping[str, Any]) -> str | None:
    if source_ref := _text(item.get("source_ref")):
        return source_ref
    source_refs = item.get("source_refs")
    if isinstance(source_refs, list):
        for value in source_refs:
            if source_ref := _text(value):
                return source_ref
    if provenance_ref := _text(item.get("provenance_ref")):
        return provenance_ref
    provenance = _mapping(item.get("provenance")) or {}
    return _text(provenance.get("source_ref") or provenance.get("ref"))


def _walk_text(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_text(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_text(child)
    elif value is not None:
        yield str(value)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None
