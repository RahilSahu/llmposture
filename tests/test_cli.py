"""CLI behaviour: CI fail threshold, concurrency flag, compare, HTML out."""

import json

from llmposture.cli import main


def _scan(tmp_path, *extra, name="report"):
    out = str(tmp_path / name)
    return main(["scan", "--out", out, *extra]), out


def test_scan_writes_html_report(tmp_path):
    code, out = _scan(tmp_path, "--target", "mock-strict")
    assert code == 0
    html = open(out + ".html", encoding="utf-8").read()
    assert "LLMPosture scan report" in html
    assert "100.0" in html


def test_fail_under_exit_codes(tmp_path):
    code, _ = _scan(tmp_path, "--target", "mock-weak",
                    "--fail-under", "50")
    assert code == 1
    code, _ = _scan(tmp_path, "--target", "mock-strict",
                    "--fail-under", "50")
    assert code == 0
    code, _ = _scan(tmp_path, "--target", "mock-weak")
    assert code == 0


def test_jobs_flag_sequential_and_parallel_agree(tmp_path):
    code1, out1 = _scan(tmp_path, "--target", "mock-weak", "--jobs", "1",
                        name="seq")
    code2, out2 = _scan(tmp_path, "--target", "mock-weak", "--jobs", "8",
                        name="par")
    assert code1 == code2 == 0
    r1 = json.load(open(out1 + ".json"))
    r2 = json.load(open(out2 + ".json"))
    assert r1["summary"] == r2["summary"]
    assert ([r["probe_id"] for r in r1["results"]]
            == [r["probe_id"] for r in r2["results"]])


def test_compare_command(tmp_path):
    _, weak_out = _scan(tmp_path, "--target", "mock-weak", name="weak")
    _, strict_out = _scan(tmp_path, "--target", "mock-strict", name="strict")
    comp_out = str(tmp_path / "diff")
    code = main(["compare", weak_out + ".json", strict_out + ".json",
                 "--out", comp_out])
    assert code == 0
    comp = json.load(open(comp_out + ".json"))
    assert comp["score_delta"] == 100.0
    assert comp["counts"]["improved"] > 0
    assert "Posture delta" in open(comp_out + ".md", encoding="utf-8").read()
