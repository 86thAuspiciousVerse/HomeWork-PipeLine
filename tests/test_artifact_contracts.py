import copy
import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "plugins"
    / "homework-pipeline"
    / ".homework"
    / "artifact_contracts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("artifact_contracts", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_artifacts():
    spec = {
        "course": {
            "name": "Synthetic course",
            "source_files": ["requirements.md"],
            "extraction_confidence": "high",
            "missing_signals": [],
        },
        "constraints": {
            "hard": [
                {
                    "id": "C_OUTPUT",
                    "rule": "produce the required local artifact",
                    "verify": "check the artifact exists and contains the required fields",
                    "source_refs": ["requirements.md#deliverable"],
                }
            ],
            "soft": [
                {
                    "id": "C_STYLE",
                    "rule": "keep the report readable",
                    "verify": "review the report against the rubric wording",
                    "source_refs": ["requirements.md#rubric"],
                }
            ],
            "bonus": [],
        },
        "deliverables": [
            {
                "id": "D_REPORT",
                "type": "report",
                "path": "output/report.md",
                "source_refs": ["requirements.md#deliverable"],
                "stages": [
                    {
                        "id": "S_BUILD",
                        "name": "Build deliverable artifact",
                        "verification_expectation": "machine-check the output file",
                        "source_refs": ["requirements.md#deliverable"],
                    },
                    {
                        "id": "S_CREDENTIAL",
                        "name": "Use external credential if supplied",
                        "verification_expectation": "halt if the credential remains unavailable",
                        "source_refs": ["requirements.md#credential"],
                    },
                ],
            }
        ],
    }

    resource_plan = {
        "resources": [
            {
                "id": "R_LOCAL",
                "stage_id": "S_BUILD",
                "kind": "library",
                "closure": "inside",
                "supply_needed": False,
                "why": "local code can generate the artifact",
                "source_refs": ["spec.yaml#deliverables.0.stages.0"],
            },
            {
                "id": "R_API_KEY",
                "stage_id": "S_CREDENTIAL",
                "kind": "api_key",
                "closure": "outside",
                "supply_needed": True,
                "why": "real account access is required",
                "obtain_steps": ["create the account", "provide env:COURSE_API_KEY"],
                "source_refs": ["spec.yaml#deliverables.0.stages.1"],
            },
        ],
        "constants": [
            {
                "name": "required_count",
                "value": 10,
                "for_constraint": "C_OUTPUT",
                "rationale": "explicit rubric threshold",
            }
        ],
    }

    verifiability_report = {
        "summary": {
            "total_stages": 2,
            "tier_a": 1,
            "tier_b": 0,
            "tier_a_default_trade": 0,
            "tier_c_supply_halt": 1,
            "verdict": "requires external supply",
        },
        "stage_records": [
            {
                "stage_id": "S_BUILD",
                "verification_tier": "machine_verifiable",
                "evidence_required": {
                    "artifacts": ["output/report.md"],
                    "invariants": ["file exists", "contains required fields"],
                },
                "rationale": "the local output can be checked deterministically",
                "source_refs": ["spec.yaml#deliverables.0.stages.0"],
                "downgrade_attempts": [],
            },
            {
                "stage_id": "S_CREDENTIAL",
                "verification_tier": "supply_halt",
                "evidence_required": {
                    "artifacts": [],
                    "invariants": ["external key must be supplied"],
                },
                "rationale": "no credible language-equivalent path can replace the credential",
                "source_refs": ["resource_plan.yaml#resources.1"],
                "downgrade_attempts": [
                    {
                        "restatement": "replace live access with a documented manual supply point",
                        "source": "LLM self-restatement",
                        "outcome": "not equivalent without the actual credential",
                        "evidence_required": {"invariants": ["credential provided"]},
                        "rationale": "the original requirement depends on live account access",
                    }
                ],
            },
        ],
        "breakpoints_summary": {
            "sense_default_trade": [],
            "supply_halt": [
                {
                    "id": "BP_API_KEY",
                    "stage_id": "S_CREDENTIAL",
                    "kind": "api_key",
                    "trigger": "gate2",
                    "closure": "outside",
                    "has_default": False,
                    "why": "real account access is required",
                    "obtain_steps": [
                        "create the account",
                        "provide env:COURSE_API_KEY",
                    ],
                    "when_provided": "rerun the credential-dependent stage",
                    "source_ref": "resource_plan.yaml#resources.1",
                }
            ],
        },
    }

    plan = {
        "candidate_stack": [],
        "decisions": [],
        "final_dag": {
            "nodes": [
                {
                    "name": "build_report",
                    "stage_id": "S_BUILD",
                    "tier": "machine_verifiable",
                    "acceptance": "output/report.md exists and contains the required fields.",
                    "evidence_required": {
                        "artifacts": ["output/report.md"],
                        "invariants": ["contains required fields"],
                    },
                    "failure_policy": "retry local generation, then escalate",
                    "source_refs": [
                        "spec.yaml#deliverables.0.stages.0",
                        "verifiability_report.yaml#stage_records.0",
                    ],
                },
                {
                    "name": "wait_for_credential",
                    "stage_id": "S_CREDENTIAL",
                    "tier": "supply_halt",
                    "acceptance": "credential is supplied before live access is attempted.",
                    "evidence_required": {
                        "artifacts": [],
                        "invariants": ["env:COURSE_API_KEY exists"],
                    },
                    "failure_policy": "pause for human supply",
                    "source_refs": [
                        "resource_plan.yaml#resources.1",
                        "verifiability_report.yaml#stage_records.1",
                    ],
                },
            ],
            "edges": [{"from": "build_report", "to": "wait_for_credential"}],
        },
        "relaxed_verify": [],
        "decision_trace_preserved": True,
    }
    return spec, resource_plan, verifiability_report, plan


def _add_default_trade_stage(spec, resource_plan, report, plan):
    spec["deliverables"][0]["stages"].append(
        {
            "id": "S_VISUAL_DEFAULT",
            "name": "Render a visual style fallback",
            "verification_expectation": "mark approximate visual output as fallback",
            "source_refs": ["requirements.md#visual"],
        }
    )
    resource_plan["resources"].append(
        {
            "id": "R_VISUAL_STYLE",
            "stage_id": "S_VISUAL_DEFAULT",
            "kind": "visual_style",
            "closure": "inside",
            "supply_needed": False,
            "why": "a basic static style can be produced locally",
            "source_refs": ["spec.yaml#deliverables.0.stages.2"],
        }
    )
    fallback_metadata = {
        "stage_id": "S_VISUAL_DEFAULT",
        "relaxed_requirement": "interactive production-quality visual polish",
        "fallback_reason": "the course allows an approximate static fallback",
        "evidence_source": "default_trade policy in verifiability_report.yaml",
        "non_real_output_marker": "approximate_fallback_not_measured",
        "source_ref": "verifiability_report.yaml#stage_records.2",
    }
    report["summary"]["tier_a_default_trade"] = 1
    report["stage_records"].append(
        {
            "stage_id": "S_VISUAL_DEFAULT",
            "verification_tier": "default_trade",
            "evidence_required": {
                "artifacts": ["output/visual.html"],
                "invariants": ["marked as default fallback"],
            },
            "rationale": "fallback is allowed only when marked as approximate",
            "source_refs": ["spec.yaml#deliverables.0.stages.2"],
            "downgrade_attempts": [
                {
                    "restatement": "render an approximate static visual artifact",
                    "source": "LLM self-restatement",
                    "outcome": "accepted as default fallback only",
                    "evidence_required": {"invariants": ["fallback marker present"]},
                    "rationale": "not equivalent to real measured visual validation",
                }
            ],
            "default_trade": fallback_metadata,
        }
    )
    report["breakpoints_summary"]["sense_default_trade"].append(fallback_metadata)
    plan["final_dag"]["nodes"].append(
        {
            "name": "render_default_visual",
            "stage_id": "S_VISUAL_DEFAULT",
            "tier": "default_trade",
            "acceptance": "output/visual.html exists and is marked as approximate fallback.",
            "evidence_required": {
                "artifacts": ["output/visual.html"],
                "invariants": ["fallback marker present"],
            },
            "failure_policy": "mark fallback provenance; do not claim measured output",
            "source_refs": [
                "spec.yaml#deliverables.0.stages.2",
                "verifiability_report.yaml#stage_records.2",
            ],
        }
    )


class ArtifactContractTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_valid_synthetic_artifacts_cover_generic_contracts(self):
        spec, resource_plan, report, plan = _valid_artifacts()

        issues = self.module.validate_artifact_contracts(
            spec=spec,
            resource_plan=resource_plan,
            verifiability_report=report,
            plan=plan,
            raise_on_error=False,
        )

        self.assertEqual(issues, [])

    def test_rejects_missing_required_fields(self):
        cases = [
            ("constraint verify", ("spec", "constraints", "hard", 0, "verify")),
            ("resource closure", ("resource_plan", "resources", 0, "closure")),
            (
                "verifiability evidence",
                ("report", "stage_records", 0, "evidence_required"),
            ),
            ("plan failure policy", ("plan", "final_dag", "nodes", 0, "failure_policy")),
        ]

        for _label, target in cases:
            spec, resource_plan, report, plan = copy.deepcopy(_valid_artifacts())
            artifacts = {
                "spec": spec,
                "resource_plan": resource_plan,
                "report": report,
                "plan": plan,
            }
            parent = artifacts[target[0]]
            for part in target[1:-1]:
                parent = parent[part]
            del parent[target[-1]]

            with self.subTest(target=target):
                issues = self.module.validate_artifact_contracts(
                    spec=spec,
                    resource_plan=resource_plan,
                    verifiability_report=report,
                    plan=plan,
                    raise_on_error=False,
                )
                self.assertTrue(issues)

    def test_rejects_scenario_specific_control_fields(self):
        spec, resource_plan, report, plan = _valid_artifacts()
        plan["final_dag"]["domain_template"] = "gis_network"
        spec["task_family"] = "dashboard"

        issues = self.module.validate_artifact_contracts(
            spec=spec,
            resource_plan=resource_plan,
            verifiability_report=report,
            plan=plan,
            raise_on_error=False,
        )

        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(
            any("scenario-specific control field" in issue.message for issue in issues)
        )

    def test_accepts_default_trade_with_audit_metadata(self):
        spec, resource_plan, report, plan = _valid_artifacts()
        _add_default_trade_stage(spec, resource_plan, report, plan)

        issues = self.module.validate_artifact_contracts(
            spec=spec,
            resource_plan=resource_plan,
            verifiability_report=report,
            plan=plan,
            raise_on_error=False,
        )

        self.assertEqual(issues, [])

    def test_rejects_default_trade_without_fallback_metadata(self):
        spec, resource_plan, report, plan = _valid_artifacts()
        _add_default_trade_stage(spec, resource_plan, report, plan)
        del report["stage_records"][-1]["default_trade"]["fallback_reason"]

        issues = self.module.validate_artifact_contracts(
            spec=spec,
            resource_plan=resource_plan,
            verifiability_report=report,
            plan=plan,
            raise_on_error=False,
        )

        self.assertTrue(
            any("fallback_reason" in issue.message for issue in issues)
        )

    def test_allows_domain_words_as_content_not_controls(self):
        spec, resource_plan, report, plan = _valid_artifacts()
        spec["constraints"]["hard"][0][
            "rule"
        ] = "Discuss GIS, dashboard, time series, and API collection as course content."
        report["stage_records"][0][
            "rationale"
        ] = "The dashboard and API collection words are content, not planner controls."
        plan["final_dag"]["nodes"][0][
            "acceptance"
        ] = "The report may mention GIS and time series content."

        issues = self.module.validate_artifact_contracts(
            spec=spec,
            resource_plan=resource_plan,
            verifiability_report=report,
            plan=plan,
            raise_on_error=False,
        )

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
