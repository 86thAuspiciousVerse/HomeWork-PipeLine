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
                    "sense_default_trade": ["visual-report"],
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
        self.assertTrue(classified_state["breakpoints"]["supply_halt"]["resolved"])

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
                    "supply_halt": [
                        {
                            "id": "amap-key",
                            "stage_id": "fetch-transit",
                            "kind": "api_key",
                            "rationale": "need real API access",
                            "obtain_steps": ["apply key"],
                            "when_provided": "rerun fetch stage",
                        }
                    ],
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
            "amap-key",
        )

        state = self.module._load_state(run_id)
        state.phases["SPEC_EXTRACT"].status = "PAUSED"
        self.module._persist(state)

        with self.assertRaisesRegex(RuntimeError, "PAUSED"):
            self._run_main(["commit-phase", run_id, "SPEC_EXTRACT", "artifacts/spec.yaml"])


if __name__ == "__main__":
    unittest.main()
