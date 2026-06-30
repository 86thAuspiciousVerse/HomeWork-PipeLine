import copy
import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "tests"
    / "semantic_expectations.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("semantic_expectations", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expectations_path(*parts):
    return REPO_ROOT.joinpath("test-cases", *parts, "expected", "semantic_expectations.yaml")


def _air_quality_artifacts():
    spec = {
        "course": {"source_files": ["doc/课程要求.md"], "missing_signals": []},
        "constraints": {
            "hard": [
                {
                    "id": "C_TIME_SPLIT",
                    "rule": "严禁 train_test_split 随机切分，必须按时间顺序切片 70/15/15。",
                    "verify": "inspect split code and tests",
                    "source_refs": ["doc/课程要求.md#关键约束"],
                },
                {
                    "id": "C_FORECAST_HORIZON",
                    "rule": "预测未来 24-72 小时的 PM2.5/AQI。",
                    "verify": "check forecast horizon in output metrics",
                    "source_refs": ["doc/课程要求.md#要求"],
                },
            ],
            "soft": [],
            "bonus": [],
        },
        "deliverables": [
            {
                "id": "D_DASHBOARD",
                "type": "html dashboard",
                "path": "output/dashboard.html",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_DASHBOARD",
                        "name": "Render dashboard",
                        "verification_expectation": "file is self-contained HTML",
                        "source_refs": ["doc/课程要求.md#交付物"],
                    }
                ],
            },
            {
                "id": "D_FASTAPI",
                "type": "FastAPI service",
                "path": "code/app.py",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_SERVICE",
                        "name": "Implement FastAPI Swagger service",
                        "verification_expectation": "app exposes /docs",
                        "source_refs": ["doc/课程要求.md#交付物"],
                    }
                ],
            },
            {
                "id": "D_REQUIREMENTS",
                "type": "requirements",
                "path": "requirements.txt",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_REQUIREMENTS",
                        "name": "Freeze dependencies",
                        "verification_expectation": "requirements.txt exists",
                        "source_refs": ["doc/课程要求.md#关键约束"],
                    }
                ],
            },
        ],
    }
    resource_plan = {
        "resources": [
            {
                "id": "R_LOCAL_AIR_DATA",
                "stage_id": "S_DASHBOARD",
                "kind": "dataset",
                "closure": "inside",
                "supply_needed": False,
                "why": "data/raw and 站点列表.csv are provided locally",
                "source_refs": ["doc/课程要求.md#数据来源"],
            }
        ]
    }
    report = {
        "stage_records": [
            {
                "stage_id": "S_DASHBOARD",
                "verification_tier": "machine_verifiable",
                "evidence_required": {"artifacts": ["output/dashboard.html"]},
                "rationale": "local files are enough; no API key is needed",
                "source_refs": ["resource_plan.yaml#resources.0"],
                "downgrade_attempts": [],
            }
        ],
        "breakpoints_summary": {"sense_default_trade": [], "supply_halt": []},
    }
    plan = {
        "final_dag": {
            "nodes": [
                {
                    "name": "build_dashboard",
                    "stage_id": "S_DASHBOARD",
                    "tier": "machine_verifiable",
                    "acceptance": "HTML dashboard exists",
                    "evidence_required": {"artifacts": ["output/dashboard.html"]},
                    "failure_policy": "retry local generation",
                    "source_refs": ["spec.yaml#deliverables.0"],
                },
                {
                    "name": "build_fastapi",
                    "stage_id": "S_SERVICE",
                    "tier": "machine_verifiable",
                    "acceptance": "FastAPI app exists",
                    "evidence_required": {"artifacts": ["code/app.py"]},
                    "failure_policy": "retry local generation",
                    "source_refs": ["spec.yaml#deliverables.1"],
                },
                {
                    "name": "freeze_requirements",
                    "stage_id": "S_REQUIREMENTS",
                    "tier": "machine_verifiable",
                    "acceptance": "requirements.txt exists",
                    "evidence_required": {"artifacts": ["requirements.txt"]},
                    "failure_policy": "retry freeze",
                    "source_refs": ["spec.yaml#deliverables.2"],
                },
            ],
            "edges": [],
        }
    }
    return {
        "spec": spec,
        "resource_plan": resource_plan,
        "verifiability_report": report,
        "plan": plan,
    }


def _transit_artifacts():
    spec = {
        "course": {"source_files": ["doc/课程要求.md"], "missing_signals": []},
        "constraints": {
            "hard": [
                {
                    "id": "C_AMAP_KEY",
                    "rule": "高德地图 Web 服务 API 需要自行注册账号并获取 API Key。",
                    "verify": "pause until a user-owned key is registered",
                    "source_refs": ["doc/课程要求.md#数据来源"],
                },
                {
                    "id": "C_DELIVERABLES",
                    "rule": "交付 CSV、GEXF、HTML 三类产物。",
                    "verify": "check all deliverable files exist",
                    "source_refs": ["doc/课程要求.md#交付物"],
                },
            ],
            "soft": [],
            "bonus": [],
        },
        "deliverables": [
            {
                "id": "D_ROUTES_CSV",
                "type": "csv",
                "path": "output/routes.csv",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_COLLECT",
                        "name": "Collect Amap transit data",
                        "verification_expectation": "CSV contains route records",
                        "source_refs": ["doc/课程要求.md#要求"],
                    }
                ],
            },
            {
                "id": "D_GRAPH",
                "type": "gexf",
                "path": "output/network.gexf",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_GRAPH",
                        "name": "Build NetworkX graph",
                        "verification_expectation": "GEXF graph loads",
                        "source_refs": ["doc/课程要求.md#要求"],
                    }
                ],
            },
            {
                "id": "D_MAP",
                "type": "html map",
                "path": "output/transit_map.html",
                "source_refs": ["doc/课程要求.md#交付物"],
                "stages": [
                    {
                        "id": "S_MAP",
                        "name": "Render interactive map",
                        "verification_expectation": "single self-contained HTML exists",
                        "source_refs": ["doc/课程要求.md#交付物"],
                    }
                ],
            },
        ],
    }
    resource_plan = {
        "resources": [
            {
                "id": "R_AMAP_API_KEY",
                "stage_id": "S_COLLECT",
                "kind": "api_key",
                "closure": "outside",
                "supply_needed": True,
                "why": "real Amap account access is required",
                "obtain_steps": ["register Amap developer account", "provide env:AMAP_API_KEY"],
                "source_refs": ["doc/课程要求.md#数据来源"],
            }
        ]
    }
    report = {
        "stage_records": [
            {
                "stage_id": "S_COLLECT",
                "verification_tier": "supply_halt",
                "evidence_required": {"artifacts": [], "invariants": ["env:AMAP_API_KEY"]},
                "rationale": "live API collection cannot be completed without a user key",
                "source_refs": ["resource_plan.yaml#resources.0"],
                "downgrade_attempts": [
                    {
                        "restatement": "replace live API collection with a mock route list",
                        "source": "LLM self-restatement",
                        "outcome": "not equivalent to the assignment data source",
                        "evidence_required": {"invariants": ["real Amap API key"]},
                        "rationale": "the course explicitly requires live Amap API data",
                    }
                ],
            }
        ],
        "breakpoints_summary": {
            "sense_default_trade": [],
            "supply_halt": [
                {
                    "id": "BP_AMAP_API_KEY",
                    "stage_id": "S_COLLECT",
                    "kind": "api_key",
                    "trigger": "gate2",
                    "closure": "outside",
                    "has_default": False,
                    "why": "real Amap account access is required",
                    "obtain_steps": [
                        "register Amap developer account",
                        "provide env:AMAP_API_KEY",
                    ],
                    "when_provided": "rerun S_COLLECT",
                    "source_ref": "resource_plan.yaml#resources.0",
                }
            ],
        },
    }
    plan = {
        "final_dag": {
            "nodes": [
                {
                    "name": "collect_routes",
                    "stage_id": "S_COLLECT",
                    "tier": "supply_halt",
                    "acceptance": "Amap API supply is resolved before collection.",
                    "evidence_required": {"artifacts": ["output/routes.csv"]},
                    "failure_policy": "pause for human supply",
                    "source_refs": ["verifiability_report.yaml#stage_records.0"],
                },
                {
                    "name": "build_graph",
                    "stage_id": "S_GRAPH",
                    "tier": "machine_verifiable",
                    "acceptance": "network.gexf loads in NetworkX.",
                    "evidence_required": {"artifacts": ["output/network.gexf"]},
                    "failure_policy": "retry graph construction",
                    "source_refs": ["spec.yaml#deliverables.1"],
                },
                {
                    "name": "render_map",
                    "stage_id": "S_MAP",
                    "tier": "machine_verifiable",
                    "acceptance": "transit map HTML exists.",
                    "evidence_required": {"artifacts": ["output/transit_map.html"]},
                    "failure_policy": "retry rendering",
                    "source_refs": ["spec.yaml#deliverables.2"],
                },
            ],
            "edges": [],
        }
    }
    return {
        "spec": spec,
        "resource_plan": resource_plan,
        "verifiability_report": report,
        "plan": plan,
    }


class SemanticRegressionTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_air_quality_fixture_expectations(self):
        expectations = self.module.load_expectations(
            _expectations_path("空气质量预测")
        )

        issues = self.module.validate_semantic_expectations(
            expectations,
            _air_quality_artifacts(),
        )

        self.assertEqual(issues, [])

    def test_transit_network_fixture_expectations(self):
        expectations = self.module.load_expectations(
            _expectations_path("公交网络分析")
        )

        issues = self.module.validate_semantic_expectations(
            expectations,
            _transit_artifacts(),
        )

        self.assertEqual(issues, [])

    def test_air_quality_rejects_api_key_supply_halt(self):
        expectations = self.module.load_expectations(
            _expectations_path("空气质量预测")
        )
        artifacts = _air_quality_artifacts()
        artifacts["verifiability_report"]["breakpoints_summary"]["supply_halt"].append(
            {
                "id": "BP_WRONG_KEY",
                "stage_id": "S_DASHBOARD",
                "kind": "api_key",
                "closure": "outside",
                "source_ref": "resource_plan.yaml#resources.0",
            }
        )

        issues = self.module.validate_semantic_expectations(expectations, artifacts)

        self.assertTrue(any(issue.code == "forbidden_supply_halt" for issue in issues))

    def test_transit_rejects_untraceable_graph_artifact(self):
        expectations = self.module.load_expectations(
            _expectations_path("公交网络分析")
        )
        artifacts = copy.deepcopy(_transit_artifacts())
        artifacts["plan"]["final_dag"]["nodes"][1]["evidence_required"]["artifacts"] = []

        issues = self.module.validate_semantic_expectations(expectations, artifacts)

        self.assertTrue(
            any(issue.code == "missing_traceable_artifact_path" for issue in issues)
        )


if __name__ == "__main__":
    unittest.main()
