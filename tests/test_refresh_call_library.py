import argparse
import unittest
from pathlib import Path

from scripts.refresh_call_library import build_refresh_commands


def _args(**overrides):
    defaults = {
        "target_active": 300,
        "limit": 0,
        "page_size": 100,
        "max_pages": 30,
        "theme_threshold": 2,
        "max_candidates": 260,
        "minimum_score": 40,
        "skip_live_api": True,
        "apply": False,
        "qa": "none",
        "log": Path("unused.json"),
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class RefreshCallLibraryTests(unittest.TestCase):
    def test_preview_builds_staging_commands_without_import_or_apply(self) -> None:
        commands = build_refresh_commands(_args(apply=False, qa="none"))
        flattened = [" ".join(command["command"]) for command in commands]

        self.assertTrue(any("expand_dataset_from_eu_api.py" in command for command in flattened))
        self.assertTrue(any("review_eu_expansion_candidates.py" in command for command in flattened))
        self.assertTrue(any("enrich_eu_promotion_candidates.py" in command for command in flattened))
        self.assertTrue(any("promote_active_call_library.py" in command for command in flattened))
        self.assertFalse(any(" --apply" in command for command in flattened))
        self.assertFalse(any("import_calls.py" in command for command in flattened))

    def test_apply_rebuilds_sqlite_and_runs_requested_qa(self) -> None:
        commands = build_refresh_commands(_args(apply=True, qa="quick"))
        flattened = [" ".join(command["command"]) for command in commands]

        self.assertTrue(any("promote_active_call_library.py" in command and " --apply" in command for command in flattened))
        self.assertTrue(any("init_db.py" in command for command in flattened))
        self.assertTrue(any("import_calls.py --replace" in command for command in flattened))
        self.assertTrue(any("-m unittest discover -s tests" in command for command in flattened))

    def test_full_qa_includes_semantic_and_retrieval_audit(self) -> None:
        commands = build_refresh_commands(_args(apply=True, qa="full"))
        flattened = [" ".join(command["command"]) for command in commands]

        self.assertTrue(any("check_semantic_stack.py" in command for command in flattened))
        self.assertTrue(any("run_gillis_retrieval_quality_audit.py" in command for command in flattened))


if __name__ == "__main__":
    unittest.main()
