"""Tests for the budget, guard and replay layer.

Copier-vendored from the agentic-engineering-template guard
subtemplate — change it there, pull via `copier update`.

Stdlib `unittest`, no fixture repo: the git-facing adapters are thin
and the decisions they feed live in pure functions, which is what this
exercises. Run from the repo root:

    python .github/store/tests/test_store.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

STORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, STORE_DIR)

import budget as store_budget  # noqa: E402
import config as store_config  # noqa: E402
import preferences_guard as guard  # noqa: E402
import replay  # noqa: E402


def make_record(record_id, chosen_slot, stream="cold", options=None):
    return {
        "v": 1,
        "type": "decision",
        "id": record_id,
        "date": "2026-07-15",
        "project": "factory",
        "question": "q?",
        "context": "ctx",
        "options": options
        or [
            {
                "slot": 1,
                "label": "a",
                "role": "prediction+recommendation",
                "rules_cited": [],
                "reasoning": "because the old rule said so",
            },
            {"slot": 2, "label": "b", "if_clause": "if x"},
        ],
        "prediction_stream": stream,
        "artifact_ref": None,
        "chosen_slot": chosen_slot,
        "chosen": "a",
        "rejections": [],
        "outcome": "hit",
    }


def make_prediction(record_id, slot, rules=()):
    return {"id": record_id, "predicted_slot": slot, "rules_cited": list(rules)}


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(store_config.validate_config(dict(store_config.DEFAULTS)), [])

    def test_repo_config_loads(self):
        root = os.path.dirname(os.path.dirname(STORE_DIR))
        config = store_config.load_config(root)
        self.assertGreater(config["budget_tokens"], 0)

    def test_missing_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(store_config.load_config(tmp), dict(store_config.DEFAULTS))

    def test_budget_above_vendored_backstop_is_rejected(self):
        config = dict(store_config.DEFAULTS)
        config["budget_tokens"] = config["budget_tokens"] + 1
        errors = store_config.validate_config(config)
        self.assertTrue(any("vendored backstop" in e for e in errors))

    def test_bad_values_are_rejected(self):
        config = dict(store_config.DEFAULTS)
        config.update(
            {"warn_at_percent": 0, "replay_window": -1, "carve_out_label": ""}
        )
        self.assertEqual(len(store_config.validate_config(config)), 3)

    def test_unknown_keys_are_tolerated(self):
        config = dict(store_config.DEFAULTS)
        config["_comment"] = "hi"
        self.assertEqual(store_config.validate_config(config), [])

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(
                os.path.join(tmp, store_config.CONFIG_FILENAME), "w", encoding="utf-8"
            ) as handle:
                handle.write("{nope")
            with self.assertRaises(store_config.ConfigError):
                store_config.load_config(tmp)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(store_config.DEFAULTS)
        self.config.update({"budget_tokens": 100, "warn_at_percent": 80})

    def test_levels(self):
        # estimate_tokens is len // 4, the vendored heuristic.
        self.assertEqual(
            store_budget.budget_status("x" * 4, self.config)["level"], "ok"
        )
        self.assertEqual(
            store_budget.budget_status("x" * 320, self.config)["level"], "warn"
        )
        self.assertEqual(
            store_budget.budget_status("x" * 404, self.config)["level"], "over"
        )

    def test_at_budget_exactly_is_not_over(self):
        status = store_budget.budget_status("x" * 400, self.config)
        self.assertEqual(status["tokens"], 100)
        self.assertEqual(status["percent"], 100.0)
        self.assertEqual(status["level"], "warn")

    def test_issue_body_mentions_the_skill_and_numbers(self):
        body = store_budget.issue_body(
            store_budget.budget_status("x" * 404, self.config), sha="abc123"
        )
        self.assertIn("compact-preferences", body)
        self.assertIn("over budget", body)
        self.assertIn("abc123", body)


class CarveOutTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(store_config.DEFAULTS)

    @staticmethod
    def commit(subject, diff, sha="abcdef1234"):
        return {"sha": sha, "subject": subject, "pref_diff": diff}

    def test_pure_addition_needs_no_label(self):
        commits = [self.commit("pref-promote: new rule", "+- a new rule\n")]
        required, _ = guard.classify_pref_commits(commits)
        self.assertFalse(required)

    def test_valid_counter_bump_is_exempt(self):
        diff = (
            "--- a/preferences.md\n"
            "+++ b/preferences.md\n"
            "-- rule text. [confirmed: 3, last: 2026-07-15]\n"
            "+- rule text. [confirmed: 4, last: 2026-07-20]\n"
        )
        required, notes = guard.classify_pref_commits(
            [self.commit("pref-confirm: rule text (n=4)", diff)]
        )
        self.assertFalse(required)
        self.assertTrue(any("exempt" in note for note in notes))

    def test_counter_bump_that_rewrites_the_rule_needs_the_label(self):
        diff = (
            "-- old rule text. [confirmed: 3, last: 2026-07-15]\n"
            "+- new rule text. [confirmed: 4, last: 2026-07-20]\n"
        )
        required, _ = guard.classify_pref_commits(
            [self.commit("pref-confirm: rule text (n=4)", diff)]
        )
        self.assertTrue(required)

    def test_rewrite_needs_the_label(self):
        diff = "-- old rule\n+- merged rule\n"
        commits = [self.commit("pref-promote: merged rule", diff)]
        errors, _ = guard.evaluate(
            commits=commits,
            labels=[],
            body="",
            head_preferences="short",
            preferences_touched=True,
            config=self.config,
        )
        self.assertTrue(any("without the" in e for e in errors))

    def test_labelled_rewrite_requires_a_replay_report(self):
        diff = "-- old rule\n+- merged rule\n"
        errors, _ = guard.evaluate(
            commits=[self.commit("pref-promote: merged rule", diff)],
            labels=[self.config["carve_out_label"]],
            body="no report here",
            head_preferences="short",
            preferences_touched=True,
            config=self.config,
        )
        self.assertTrue(any("no replay report" in e for e in errors))

    def test_labelled_rewrite_passes_with_a_matching_passing_report(self):
        head = "compacted rules"
        report = {
            "gate": "pass",
            "candidate_preferences_sha256": guard.preferences_sha256(head),
        }
        body = f"{guard.REPLAY_MARKER}\n```json\n{json.dumps(report)}\n```\n"
        errors, _ = guard.evaluate(
            commits=[self.commit("pref-promote: merged rule", "-- old\n+- new\n")],
            labels=[self.config["carve_out_label"]],
            body=body,
            head_preferences=head,
            preferences_touched=True,
            config=self.config,
        )
        self.assertEqual(errors, [])

    def test_stale_report_is_rejected(self):
        report = {
            "gate": "pass",
            "candidate_preferences_sha256": guard.preferences_sha256("older text"),
        }
        body = f"{guard.REPLAY_MARKER}\n```json\n{json.dumps(report)}\n```\n"
        errors = guard.check_replay_report(body, "current text")
        self.assertTrue(any("different preferences.md" in e for e in errors))

    def test_failing_gate_is_rejected(self):
        head = "compacted"
        report = {
            "gate": "fail",
            "candidate_preferences_sha256": guard.preferences_sha256(head),
        }
        body = f"{guard.REPLAY_MARKER}\n```json\n{json.dumps(report)}\n```\n"
        self.assertTrue(
            any("gate is" in e for e in guard.check_replay_report(body, head))
        )


class BudgetGateTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(store_config.DEFAULTS)
        self.config.update({"budget_tokens": 10, "warn_at_percent": 80})

    def test_over_budget_blocks_a_pr_that_touches_the_file(self):
        errors, _ = guard.evaluate(
            commits=[],
            labels=[],
            body="",
            head_preferences="x" * 100,
            preferences_touched=True,
            config=self.config,
        )
        self.assertTrue(any("blocked until it is compacted" in e for e in errors))

    def test_over_budget_does_not_block_unrelated_prs(self):
        errors, notes = guard.evaluate(
            commits=[],
            labels=[],
            body="",
            head_preferences="x" * 100,
            preferences_touched=False,
            config=self.config,
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("not blocked" in note for note in notes))


class ReplayTests(unittest.TestCase):
    def test_mask_strips_leaky_fields(self):
        case = replay.mask_record(make_record("20260715T143205Z-a", 1))
        self.assertNotIn("chosen_slot", case)
        self.assertNotIn("outcome", case)
        for option in case["options"]:
            self.assertNotIn("role", option)
            self.assertNotIn("rules_cited", option)
            self.assertNotIn("reasoning", option)
        self.assertEqual(case["options"][1]["if_clause"], "if x")

    def test_mask_can_keep_reasoning(self):
        case = replay.mask_record(
            make_record("20260715T143205Z-a", 1), include_reasoning=True
        )
        self.assertIn("reasoning", case["options"][0])

    def test_window_takes_the_most_recent(self):
        records = [make_record(f"2026071{i}T143205Z-a", 1) for i in range(5)]
        selected = replay.select_window(records, 2)
        self.assertEqual(
            [r["id"] for r in selected], [records[3]["id"], records[4]["id"]]
        )

    def test_scoring_splits_streams(self):
        records = [
            make_record("20260715T143205Z-a", 1),
            make_record("20260716T143205Z-b", 2),
        ]
        predictions, errors = replay.normalise_predictions(
            {
                "predictions": [
                    make_prediction("20260715T143205Z-a", 1, ["rule one"]),
                    make_prediction("20260716T143205Z-b", 1),
                ]
            }
        )
        self.assertEqual(errors, [])
        report, score_errors = replay.score(records, predictions, 20, "prefs")
        self.assertEqual(score_errors, [])
        self.assertEqual(
            report["streams"]["preference-driven"], {"n": 1, "hits": 1, "hit_rate": 1.0}
        )
        self.assertEqual(
            report["streams"]["cold"], {"n": 1, "hits": 0, "hit_rate": 0.0}
        )

    def test_stream_shift_is_reported(self):
        records = [make_record("20260715T143205Z-a", 1, stream="cold")]
        predictions, _ = replay.normalise_predictions(
            [make_prediction("20260715T143205Z-a", 1, ["a merged rule"])]
        )
        report, _ = replay.score(records, predictions, 20, "prefs")
        self.assertEqual(
            report["stream_shifts"],
            [
                {
                    "id": "20260715T143205Z-a",
                    "recorded": "cold",
                    "candidate": "preference-driven",
                }
            ],
        )

    def test_missing_and_extra_predictions_are_errors(self):
        records = [make_record("20260715T143205Z-a", 1)]
        predictions, _ = replay.normalise_predictions(
            [make_prediction("20260799T143205Z-z", 1)]
        )
        _, errors = replay.score(records, predictions, 20, "prefs")
        self.assertEqual(len(errors), 2)

    def test_bad_prediction_entries_are_rejected(self):
        _, errors = replay.normalise_predictions(
            [{"id": "x", "predicted_slot": "one"}, {"predicted_slot": 1}, "nope"]
        )
        self.assertEqual(len(errors), 3)

    def test_gate_passes_when_the_hit_rate_holds(self):
        baseline = self._report(pd=(4, 5), cold=(1, 5), sha="base")
        candidate = self._report(pd=(4, 5), cold=(0, 5), sha="cand")
        result = replay.gate(baseline, candidate)
        self.assertEqual(result["gate"], "pass")
        self.assertEqual(result["candidate_preferences_sha256"], "cand")

    def test_gate_fails_on_degradation(self):
        baseline = self._report(pd=(4, 5), cold=(1, 5), sha="base")
        candidate = self._report(pd=(2, 5), cold=(5, 5), sha="cand")
        result = replay.gate(baseline, candidate)
        self.assertEqual(result["gate"], "fail")
        self.assertTrue(any("degraded" in reason for reason in result["reasons"]))

    def test_gate_fails_when_the_candidate_drives_nothing(self):
        baseline = self._report(pd=(0, 3), cold=(1, 2), sha="base")
        candidate = self._report(pd=(0, 0), cold=(1, 5), sha="cand")
        result = replay.gate(baseline, candidate)
        self.assertEqual(result["gate"], "fail")

    def test_gate_fails_on_mismatched_windows(self):
        baseline = self._report(pd=(1, 1), cold=(0, 0), sha="base", ids=["a"])
        candidate = self._report(pd=(1, 1), cold=(0, 0), sha="cand", ids=["b"])
        self.assertEqual(replay.gate(baseline, candidate)["gate"], "fail")

    @staticmethod
    def _report(pd, cold, sha, ids=("a",)):
        def stream(hits_total):
            hits, total = hits_total
            return {
                "n": total,
                "hits": hits,
                "hit_rate": round(hits / total, 4) if total else None,
            }

        return {
            "window": 20,
            "scored": len(ids),
            "preferences_sha256": sha,
            "preferences_tokens": 100,
            "streams": {"preference-driven": stream(pd), "cold": stream(cold)},
            "stream_shifts": [],
            "cases": [{"id": case_id} for case_id in ids],
        }


class CorpusReplayTests(unittest.TestCase):
    """The harness must cope with the real corpus, not just fixtures."""

    def test_cases_build_from_the_real_decisions(self):
        root = os.path.dirname(os.path.dirname(STORE_DIR))
        records = replay.load_records(root)
        if not records:
            # No corpus: this file also runs from the template that
            # vendors it, where decisions/ does not exist. The fixture
            # tests above still cover the harness; only this
            # real-corpus check needs a store to be meaningful.
            self.skipTest("no decisions/ corpus here — not a store checkout")
        cases = replay.build_cases(records, 20)
        self.assertEqual(cases["count"], min(20, len(records)))
        for case in cases["cases"]:
            self.assertIn("question", case)
            self.assertTrue(case["options"])


if __name__ == "__main__":
    unittest.main()
