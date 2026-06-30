import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "plugins" / "homework-pipeline" / ".homework" / "orchestrator_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("orchestrator_state", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OrchestratorStateSmokeTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.prev_cwd = Path.cwd()
        os.chdir(self.temp_dir.name)
        self.addCleanup(os.chdir, self.prev_cwd)

    def _create_doc(self) -> Path:
        doc_path = Path(self.temp_dir.name) / "course.md"
        doc_path.write_text("# course requirements\n", encoding="utf-8")
        return doc_path

    def _state_path(self) -> Path:
        run_dirs = [path for path in (Path(self.temp_dir.name) / ".homework").iterdir() if path.is_dir()]
        self.assertEqual(len(run_dirs), 1)
        return run_dirs[0] / "state.yaml"

    def _run_main(self, argv):
        with redirect_stdout(io.StringIO()):
            return self.module.main(argv)

    def _complete_default_trade_item(self):
        return {
            "stage_id": "visual-report",
            "relaxed_requirement": "production visual polish",
            "fallback_reason": "default visual output is acceptable only as approximate",
            "evidence_source": "verifiability_report.yaml#stage_records.0",
            "non_real_output_marker": "approximate_fallback_not_measured",
            "source_ref": "verifiability_report.yaml#breakpoints_summary.sense_default_trade.0",
        }

    def _complete_supply_halt_item(self):
        return {
            "id": "service-key",
            "stage_id": "fetch-transit",
            "kind": "api_key",
            "trigger": "gate2",
            "closure": "outside",
            "has_default": False,
            "rationale": "need real API access",
            "obtain_steps": ["apply key"],
            "when_provided": "rerun fetch stage",
            "source_ref": "resource_plan.yaml#resources.0",
        }

    def test_smoke_create_classify_commit_happy_path(self):
        doc_path = self._create_doc()

        create_exit = self._run_main(["create-run", str(doc_path)])
        self.assertEqual(create_exit, 0)

        state_path = self._state_path()
        state_data = self.module._load_yaml(state_path)
        run_id = state_data["run_id"]

        self.assertEqual(state_data["current_phase"], "SPEC_EXTRACT")
        self.assertEqual(state_data["phase_status"], "ENTERING")
        self.assertEqual(state_data["breakpoints"]["supply_halt"]["batch"], [])

        report_path = Path(self.temp_dir.name) / "verifiability_report.yaml"
        self.module._dump_yaml(
            {
                "breakpoints_summary": {
                    "sense_default_trade": [self._complete_default_trade_item()],
                    "supply_halt": [],
                }
            },
            report_path,
        )

        classify_exit = self._run_main(["classify-breakpoints", run_id, str(report_path)])
        self.assertEqual(classify_exit, 0)

        classified_state = self.module._load_yaml(state_path)
        self.assertEqual(classified_state["phase_status"], "ENTERING")
        self.assertEqual(classified_state["auto_mode"], "full")
        self.assertEqual(
            classified_state["breakpoints"]["sense_default_trade"]["batch"],
            ["visual-report"],
        )
        self.assertEqual(
            classified_state["breakpoints"]["sense_default_trade"]["fallbacks"][0][
                "non_real_output_marker"
            ],
            "approximate_fallback_not_measured",
        )
        self.assertTrue(classified_state["breakpoints"]["supply_halt"]["resolved"])

        provenance = self.module.build_audit_provenance(
            self.module._load_state(run_id)
        )
        self.assertFalse(
            provenance["completion_sources"]["default_fallback"][0][
                "real_execution_evidence"
            ]
        )

        commit_exit = self._run_main(
            ["commit-phase", run_id, "SPEC_EXTRACT", "artifacts/spec.yaml"]
        )
        self.assertEqual(commit_exit, 0)

        committed_state = self.module._load_yaml(state_path)
        self.assertEqual(committed_state["phases"]["SPEC_EXTRACT"]["status"], "COMPLETED")
        self.assertEqual(
            committed_state["phases"]["SPEC_EXTRACT"]["artifact"],
            "artifacts/spec.yaml",
        )
        self.assertEqual(committed_state["current_phase"], "RESOURCE_PLANNER")
        self.assertEqual(committed_state["phase_status"], "ENTERING")

    def test_smoke_classify_supply_halt_pauses_and_blocks_commit(self):
        doc_path = self._create_doc()
        self.assertEqual(self._run_main(["create-run", str(doc_path)]), 0)

        state_path = self._state_path()
        run_id = self.module._load_yaml(state_path)["run_id"]

        report_path = Path(self.temp_dir.name) / "verifiability_report.yaml"
        self.module._dump_yaml(
            {
                "breakpoints_summary": {
                    "sense_default_trade": [],
                    "supply_halt": [self._complete_supply_halt_item()],
                }
            },
            report_path,
        )

        self.assertEqual(
            self._run_main(["classify-breakpoints", run_id, str(report_path)]),
            0,
        )

        paused_state = self.module._load_yaml(state_path)
        self.assertEqual(paused_state["phase_status"], "PAUSED")
        self.assertEqual(paused_state["auto_mode"], "scaffold_with_breakpoints")
        self.assertFalse(paused_state["breakpoints"]["supply_halt"]["resolved"])
        self.assertEqual(
            paused_state["breakpoints"]["supply_halt"]["batch"][0]["id"],
            "service-key",
        )

        state = self.module._load_state(run_id)
        state.phases["SPEC_EXTRACT"].status = "PAUSED"
        self.module._persist(state)

        with self.assertRaisesRegex(RuntimeError, "PAUSED"):
            self._run_main(["commit-phase", run_id, "SPEC_EXTRACT", "artifacts/spec.yaml"])

    def test_rejects_incomplete_supply_halt_before_pause(self):
        doc_path = self._create_doc()
        self.assertEqual(self._run_main(["create-run", str(doc_path)]), 0)

        state_path = self._state_path()
        run_id = self.module._load_yaml(state_path)["run_id"]

        item = self._complete_supply_halt_item()
        del item["obtain_steps"]
        report_path = Path(self.temp_dir.name) / "verifiability_report.yaml"
        self.module._dump_yaml(
            {
                "breakpoints_summary": {
                    "sense_default_trade": [],
                    "supply_halt": [item],
                }
            },
            report_path,
        )

        with self.assertRaisesRegex(self.module.BreakpointValidationError, "obtain_steps"):
            self._run_main(["classify-breakpoints", run_id, str(report_path)])

        state = self.module._load_yaml(state_path)
        self.assertEqual(state["phase_status"], "ENTERING")
        self.assertEqual(state["breakpoints"]["supply_halt"]["batch"], [])

    def test_add_supply_halt_item_validates_late_items(self):
        doc_path = self._create_doc()
        self.assertEqual(self._run_main(["create-run", str(doc_path)]), 0)
        state = self.module._load_state(self.module._load_yaml(self._state_path())["run_id"])

        with self.assertRaisesRegex(self.module.BreakpointValidationError, "source_ref"):
            self.module.add_supply_halt_item(
                state,
                id="late-api-key",
                stage_id="fetch-live-data",
                kind="api_key",
                trigger="executor",
                why="live data requires a user-owned credential",
                obtain_steps=["create the API key"],
                when_provided="rerun fetch-live-data",
                closure="outside",
                source_ref="",
            )

        updated = self.module.add_supply_halt_item(
            state,
            id="late-api-key",
            stage_id="fetch-live-data",
            kind="api_key",
            trigger="executor",
            why="live data requires a user-owned credential",
            obtain_steps=["create the API key"],
            when_provided="rerun fetch-live-data",
            closure="outside",
            has_default=False,
            source_ref="execution/traces/fetch-live-data__attempt1.txt",
        )

        self.assertEqual(updated.phase_status, "PAUSED")
        self.assertEqual(
            updated.breakpoints.supply_halt.batch[0].source_ref,
            "execution/traces/fetch-live-data__attempt1.txt",
        )

    def test_resolve_supply_halt_records_value_reference_only(self):
        doc_path = self._create_doc()
        self.assertEqual(self._run_main(["create-run", str(doc_path)]), 0)

        state_path = self._state_path()
        run_id = self.module._load_yaml(state_path)["run_id"]
        report_path = Path(self.temp_dir.name) / "verifiability_report.yaml"
        self.module._dump_yaml(
            {
                "breakpoints_summary": {
                    "sense_default_trade": [],
                    "supply_halt": [self._complete_supply_halt_item()],
                }
            },
            report_path,
        )
        self.assertEqual(
            self._run_main(["classify-breakpoints", run_id, str(report_path)]),
            0,
        )

        state = self.module._load_state(run_id)
        with self.assertRaisesRegex(self.module.BreakpointValidationError, "reference"):
            self.module.resolve_supply_halt(state, "service-key", "actual-secret-value")

        state = self.module.resolve_supply_halt(state, "service-key", "env:SERVICE_API_KEY")
        supplied = state.breakpoints.supply_halt.batch[0].supplied_items[0]
        self.assertEqual(supplied.provided_value_ref, "env:SERVICE_API_KEY")
        self.assertEqual(supplied.completion_source, "human_provided")

        provenance = self.module.build_audit_provenance(state)
        self.assertEqual(
            provenance["completion_sources"]["human_provided"][0][
                "provided_value_ref"
            ],
            "env:SERVICE_API_KEY",
        )


if __name__ == "__main__":
    unittest.main()
