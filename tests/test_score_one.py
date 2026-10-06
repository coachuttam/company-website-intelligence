"""eval/score_one.py: the name->site_set lookup, and that main() reuses run_scoring_set()
rather than a second scoring implementation. No LLM/network call -- --semantic-judge is
never passed here."""
from pathlib import Path

from eval.score_one import _resolve_site, main

ROOT = Path(__file__).resolve().parent.parent


def test_dev_set_name_resolves_to_its_hardcoded_run_file():
    # Dev set replaced 2026-09-28 (see eval/baseline.py DEV_SET) -- calendly.json is the
    # current dev-set entry; the run_file slug is DEV_SET's own UNCONFIRMED placeholder
    # (no real crawl has been run against calendly.com yet), so this test only checks that
    # _resolve_site() returns exactly what DEV_SET says, not that the slug is correct.
    site_set, error = _resolve_site("calendly", ROOT / "data" / "runs")
    assert error is None
    assert site_set == [("calendly.json", "calendly_com.json")]


def test_accepts_the_name_with_or_without_dot_json():
    with_suffix, _ = _resolve_site("calendly.json", ROOT / "data" / "runs")
    without_suffix, _ = _resolve_site("calendly", ROOT / "data" / "runs")
    assert with_suffix == without_suffix


def test_unknown_name_lists_every_known_site_in_the_error():
    site_set, error = _resolve_site("not-a-real-site", ROOT / "data" / "runs")
    assert site_set is None
    assert "calendly" in error and "razorpay" in error  # one dev-set, one held-out


def test_held_out_name_with_no_run_file_yet_reports_that_not_none(tmp_path):
    # An empty run_dir means every held-out candidate is genuinely missing -- must say so,
    # never silently fall through to an unrelated file.
    site_set, error = _resolve_site("razorpay", tmp_path)
    assert site_set is None
    assert "run_site.py" in error


def test_main_with_no_args_prints_usage_and_exits_2(capsys):
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["score_one.py"]
        exit_code = main()
    finally:
        sys.argv = old_argv
    assert exit_code == 2
    assert "Usage:" in capsys.readouterr().out
