import json

from cci.cli import main
from cci.dashboard import render as dash_render
from cci.insights import build_report
from cci.normalize import collect
from cci.sampledata import generate, write


def test_selftest_command_passes():
    assert main(["selftest", "--quiet"]) == 0


def test_json_command_runs(tmp_path, capsys):
    sample = tmp_path / "u.jsonl"
    write(sample, seed=7)
    rc = main(["json", "--path", str(sample), "--compact"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["totals"]["cost"] > 0
    assert "waste" in data


def test_report_command_runs(tmp_path):
    sample = tmp_path / "u.jsonl"
    write(sample, seed=7)
    assert main(["report", "--path", str(sample)]) == 0


def test_dashboard_command_writes_html(tmp_path):
    sample = tmp_path / "u.jsonl"
    write(sample, seed=7)
    out = tmp_path / "d.html"
    assert main(["dashboard", "--path", str(sample), "--out", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "__DATA__" not in html
    assert "Claude Cost Intelligence" in html
    assert html.count("<script") >= 2


def test_dashboard_render_is_self_contained():
    report = build_report(collect(generate(7)))
    html = dash_render(report, budget=None)
    # embedded JSON must be parseable after un-escaping the script-guard
    a = html.index('<script id="data" type="application/json">') + len('<script id="data" type="application/json">')
    b = html.index("</script>", a)
    blob = html[a:b].replace("<\\/", "</")
    data = json.loads(blob)
    assert data["schema"] == "cci/report@1"


def test_filters_by_project(tmp_path, capsys):
    sample = tmp_path / "u.jsonl"
    write(sample, seed=7)
    rc = main(["json", "--path", str(sample), "--project", "data-pipeline", "--compact"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(p["key"] == "data-pipeline" for p in data["by_project"])
