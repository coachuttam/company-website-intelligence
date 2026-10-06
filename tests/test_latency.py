"""B-74 (AC-10): per-stage timing on a run, and the p50/p95 latency/token/cost report built from
run JSONs. Offline: a fake clock stands in for real time, and run JSONs are plain dicts."""
from wi.eval.latency import PhaseTimer, latency_report, percentile, run_record


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _run(total_s, tokens=1000, cost=0.01, cache_status="miss", jev_cost=None):
    return {
        "cache_status": cache_status,
        "timing": {"crawl_s": total_s - 1, "extract_s": 1.0, "total_s": total_s},
        "usage": {"total_tokens": tokens, "estimated_cost_usd": cost},
        "classifier": ({"input_tokens": 100, "output_tokens": 5, "estimated_cost_usd": jev_cost}
                       if jev_cost is not None else {"provider": "none"}),
        "crawl": {"pages": [{"url": "u"}] * 3},
    }


def test_phase_timer_records_each_phase_and_the_end_to_end_total():
    clock = FakeClock()
    timer = PhaseTimer(clock=clock)
    with timer.phase("crawl"):
        clock.now += 40.0
    clock.now += 2.0                      # time between phases still counts toward the total
    with timer.phase("extract"):
        clock.now += 25.5
    assert timer.as_dict() == {"crawl_s": 40.0, "extract_s": 25.5, "total_s": 67.5}


def test_phase_timer_records_a_phase_even_when_it_raises():
    clock = FakeClock()
    timer = PhaseTimer(clock=clock)
    try:
        with timer.phase("crawl"):
            clock.now += 3.0
            raise RuntimeError("site down")
    except RuntimeError:
        pass
    assert timer.as_dict()["crawl_s"] == 3.0


def test_percentile_interpolates_between_ranks():
    assert percentile([], 50) is None
    assert percentile([7.0], 95) == 7.0
    assert percentile([10.0, 20.0, 30.0, 40.0], 50) == 25.0
    assert abs(percentile([10.0, 20.0, 30.0, 40.0, 50.0], 95) - 48.0) < 1e-9


def test_cache_hits_and_pre_b74_runs_are_skipped_not_counted():
    old_run = _run(50.0)
    del old_run["timing"]
    report = latency_report([
        ("fresh", _run(50.0)),
        ("cached", _run(1.0, cache_status="hit")),
        ("old", old_run),
    ])
    assert [r["site"] for r in report["sites"]] == ["fresh"]
    reasons = {s["site"]: s["reason"] for s in report["skipped"]}
    assert "cache hit" in reasons["cached"]
    assert "predates B-74" in reasons["old"]
    assert report["summary"]["latency_p50_s"] == 50.0


def test_cost_adds_jev_to_the_llm_and_an_unknown_llm_price_is_not_a_free_run():
    record, _ = run_record("a", _run(30.0, cost=0.01, jev_cost=0.0005))
    assert record["cost_usd"] == 0.0105
    assert record["jev_tokens"] == 105

    report = latency_report([("priced", _run(30.0, cost=0.02)), ("unpriced", _run(30.0, cost=None))])
    assert report["summary"]["cost_mean_usd"] == 0.02
    assert report["summary"]["sites_with_unknown_cost"] == 1


def test_summary_is_checked_against_config_targets():
    runs = [(f"s{i}", _run(t, cost=c)) for i, (t, c) in enumerate([(40, 0.01), (50, 0.02), (200, 0.30)])]
    report = latency_report(runs, {"latency_p50_s": 60, "latency_p95_s": 180,
                                   "cost_mean_usd": 0.10, "cost_p95_usd": 0.25})
    assert report["targets"]["latency_p50_s"]["met"] is True      # p50 = 50 s
    assert report["targets"]["latency_p95_s"]["met"] is False     # p95 = 185 s
    assert report["targets"]["cost_mean_usd"]["met"] is False     # mean = 0.11
    assert report["targets"]["cost_p95_usd"]["met"] is False      # p95 = 0.272
