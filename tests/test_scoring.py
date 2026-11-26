"""Invariants of the scoring helpers.

- Deriving the scorer's diagnostics adds the SPM selection and changes nothing
  else: undoing it gives back the input, for any diagnostics.
- Scoring reads the dataset the committed measurement read, from the release
  folder named for its revision, and refuses to start otherwise.
- The tables carry Microcosm's verdicts unchanged, whatever the errors, and the
  tally's counts follow from those verdicts. In the committed tables each
  verdict says whether the error, recomputed from the target and the estimate,
  is within the tolerance.
- The counterfactual withholds only columns the baseline engine does not read,
  and is needed exactly when the tested engine newly reads one.
- Scoring writes a new output folder; rendering may rewrite an existing one.
- The wheels fetched for scoring carry the versions the measured run recorded.
- The committed tables rebuild byte for byte from the committed ``drift.json``,
  the scores came from the scoring code in this tree, and they used the
  measured releases and dataset.
- Microcosm's batched scorer and this repository's whole-file panel give the
  same 2024 totals, for exactly the 13 totals both compute.
- Every committed score file still has the hash the record holds. Recording
  took those hashes from the run's artifact, so the committed files are the
  ones the recorded run uploaded; the tests do not download it again. The
  estimates are named for the build that made them.
- Four earlier runs agree with the committed scores to within rounding. The
  first two, whose installs were not constrained, differed in five packages;
  the other two ran under the constraints and earlier scoring code.
"""

import copy
import json
import math
import sys
import types
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import critical_targets  # noqa: E402
import fetch_wheels  # noqa: E402
import prepare_scoring  # noqa: E402
import provenance  # noqa: E402
from rules import stamped_by_one_run  # noqa: E402

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=5),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=4), children, max_size=3),
    max_leaves=12,
)
diagnostics = st.fixed_dictionaries(
    {"build": st.dictionaries(st.text(max_size=4).filter(lambda k: k != "post_export_scoring"), json_values, max_size=3)},
    optional={"targets": st.lists(json_values, max_size=3), "options": json_values},
)


@given(diagnostics)
def test_derive_adds_only_the_selection(original):
    before = copy.deepcopy(original)
    derived = prepare_scoring.derive(original)
    assert original == before, "derive must not change its input"
    assert derived["build"]["post_export_scoring"] == {"spm": prepare_scoring.SPM_SELECTION}
    restored = prepare_scoring.restore(derived)
    restored["build"].pop("post_export_scoring")
    assert restored == before
    assert json.loads(json.dumps(derived)) == derived


def test_derive_refuses_diagnostics_that_already_have_a_selection():
    with pytest.raises(ValueError):
        prepare_scoring.derive({"build": {"post_export_scoring": {"spm": {"geography_kind": "national"}}}})
    with pytest.raises(ValueError):
        prepare_scoring.derive({"targets": []})


def test_report_names_the_measured_dataset():
    measured = json.loads((ROOT / "results" / "pinned" / "environment.json").read_text())["dataset"]
    report = prepare_scoring.report()["dataset"]
    assert report["sha256"] == measured["sha256"] == prepare_scoring.DATASET_SHA256
    assert report["filename"] == measured["file"]


def measured_environments() -> dict[str, dict]:
    return {run: json.loads((ROOT / "results" / run / "environment.json").read_text()) for run in ("pinned", "head")}


def test_scoring_downloads_from_the_measured_release_folder(capsys):
    environments = measured_environments()
    assert prepare_scoring.measured_dataset_failures(environments) == []
    folder = prepare_scoring.check_measured()
    assert folder == (
        f"https://huggingface.co/datasets/{prepare_scoring.REPOSITORY}/resolve/{prepare_scoring.REVISION}/"
        f"{prepare_scoring.RELEASE_FOLDER}"
    )
    assert folder.endswith("/" + environments["pinned"]["dataset"]["revision"])
    assert prepare_scoring.url("calibration_diagnostics.json") == f"{folder}/calibration_diagnostics.json"
    assert prepare_scoring.main(["--check-measured"]) == 0
    assert capsys.readouterr().out == f"folder_url={folder}\n"


@pytest.mark.parametrize(
    "field, value",
    (
        ("sha256", "0" * 64),
        ("revision", "populace-us-2024-spm-20260909"),
        # The folder ends in "-20260915", not in a part named "20260915".
        ("revision", "20260915"),
        ("revision", None),
        ("repo", "policyengine/populace-uk"),
        ("file", "populace_us_2025.h5"),
    ),
)
@pytest.mark.parametrize("run", ("pinned", "head"))
def test_a_measurement_on_another_dataset_stops_scoring(tmp_path, run, field, value):
    environments = measured_environments()
    environments[run]["dataset"][field] = value
    found = prepare_scoring.measured_dataset_failures(environments)
    assert len(found) == 1 and f"the {run} measurement" in found[0], found
    for name, environment in environments.items():
        (tmp_path / "results" / name).mkdir(parents=True)
        (tmp_path / "results" / name / "environment.json").write_text(json.dumps(environment))
    with pytest.raises(ValueError, match=f"the {run} measurement"):
        prepare_scoring.check_measured(tmp_path)


def test_the_score_workflow_checks_the_dataset_before_any_download():
    """Both jobs that download from the release folder check the measured
    dataset first and take the folder from that check, not from a constant."""
    workflow = (ROOT / ".github" / "workflows" / "score.yml").read_text()
    assert "HF_FOLDER" not in workflow and "huggingface.co" not in workflow
    score, combine = workflow.split("\n  score:\n", 1)[1].split("\n  combine:\n", 1)
    for job in (score, combine):
        check = job.index("scripts/prepare_scoring.py --check-measured")
        downloads = [job.index(step) for step in ("fetch_wheels.py", "download-artifact", "curl ") if step in job]
        assert downloads and check < min(downloads)
        assert job.count("${{ steps.dataset.outputs.folder_url }}") == 1


@pytest.mark.parametrize("run", ("pinned", "head"))
def test_wheels_carry_the_measured_versions(run):
    environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
    pins = fetch_wheels.pins(environment)
    assert set(pins) == set(fetch_wheels.PACKAGES)
    assert all(pins[name] == environment["packages"][name] for name in pins)


def test_pins_refuse_an_environment_without_a_version():
    with pytest.raises(ValueError):
        fetch_wheels.pins({"packages": {"policyengine-us": "1", "policyengine-core": "2", "spm-calculator": None}})


def drift_row(requirement, target, baseline, tested, tolerance, within, build_estimate=None):
    """One row as Microcosm's ``combine_drift`` writes it. The verdicts
    (``within``, baseline then tested) are given, not computed from the errors,
    so a test of how the tables use them cannot pass by copying the relation."""
    row = {
        "metric_id": f"target:{requirement}",
        "label": requirement,
        "unit": "usd",
        "requirement_id": requirement,
        "baseline": baseline,
        "tested": tested,
        "difference": tested - baseline,
        "relative_difference": None if baseline == 0 else (tested - baseline) / abs(baseline),
        "target": target,
        "build_estimate": target if build_estimate is None else build_estimate,
    }
    if target:
        row["target_relative_error"] = {"baseline": (baseline - target) / abs(target), "tested": (tested - target) / abs(target)}
        row["tolerance"] = tolerance
        row["within_tolerance"] = dict(zip(("baseline", "tested"), within))
    return row


amounts = st.floats(min_value=1.0, max_value=1e12, allow_nan=False)
tolerances = st.sampled_from([0.05, 0.10, 0.15, 0.20, 0.25])
verdicts = st.tuples(st.booleans(), st.booleans())


@given(st.lists(st.tuples(amounts, amounts, amounts, amounts, tolerances, verdicts), min_size=1, max_size=8))
def test_tally_follows_from_the_verdicts(values):
    """The verdicts are drawn apart from the errors, so they often disagree:
    the tables must carry Microcosm's verdicts, not recompute them, and the
    tally must count those verdicts. The renderer's own arithmetic (the build
    estimate's error and the smallest margin) is checked against values the
    test recomputes from the target, estimates and tolerance."""
    drift = {
        "rows": [drift_row(f"r{i}", t, b, x, tol, within, built) for i, (t, b, x, built, tol, within) in enumerate(values)]
        + [{"metric_id": "snap_total", "label": "SNAP", "unit": "usd", "requirement_id": None, "baseline": 1.0, "tested": 2.0}]
    }
    rows = critical_targets.requirement_rows(drift)
    assert len(rows) == len(values)
    for row, (target, _, _, built, _, within) in zip(rows, values):
        assert (row["baseline_within"], row["tested_within"]) == within
        assert row["build_error"] == (built - target) / abs(target)
    tally = critical_targets.tally(rows)
    ids = [f"target:r{i}" for i in range(len(values))]
    drawn = {side: {id_: value[5][index] for id_, value in zip(ids, values)} for index, side in enumerate(("baseline", "tested"))}
    assert tally["rows"] == tally["rows_with_a_tolerance"] == len(values)
    for side in ("baseline", "tested"):
        assert tally[f"{side}_within"] == sum(drawn[side].values())
        assert tally[f"{side}_outside"] == sorted(id_ for id_ in ids if not drawn[side][id_])
    assert tally["leaving_tolerance"] == sorted(id_ for id_ in ids if drawn["baseline"][id_] and not drawn["tested"][id_])
    assert tally["entering_tolerance"] == sorted(id_ for id_ in ids if not drawn["baseline"][id_] and drawn["tested"][id_])
    margins = [tol - abs((x - t) / abs(t)) for t, _, x, _, tol, _ in values]
    assert tally["smallest_tested_margin"]["margin"] == min(margins)
    assert len(critical_targets.headline_rows(drift)) == 1


def test_committed_verdicts_follow_from_target_estimate_and_tolerance():
    """Microcosm's verdicts in the committed tables, recomputed here: a row is
    within tolerance exactly when its estimate's relative error against the
    target does not exceed the tolerance in size."""
    result = json.loads((SCORED / "critical_targets.json").read_text())
    rows = [row for part in ("exact", "table_1_4") for row in result[part]["rows"] if row["tolerance"] is not None]
    assert len(rows) == 30
    for row in rows:
        for side in ("baseline", "tested"):
            error = (row[side] - row["target"]) / abs(row["target"])
            assert row[f"{side}_error"] == error, (row["metric_id"], side)
            assert row[f"{side}_within"] is (abs(error) <= row["tolerance"]), (row["metric_id"], side)


def test_known_tolerance_edges():
    rows = critical_targets.requirement_rows(
        {"rows": [drift_row("a", 100.0, 105.0, 106.0, 0.05, (True, False)), drift_row("b", 100.0, 80.0, 90.0, 0.15, (False, True))]}
    )
    tally = critical_targets.tally(rows)
    assert tally["leaving_tolerance"] == ["target:a"]
    assert tally["entering_tolerance"] == ["target:b"]
    assert tally["baseline_within"] == 1 and tally["tested_within"] == 1


def reading(*columns):
    """A score document's engine, reading these stored columns."""
    return {"engine": {"column_changes": {"read": [{"column": c, "tables": ["person"]} for c in columns], "ignored": []}}}


def test_newly_read_columns_when_the_baseline_reads_none():
    """Today's pair: the baseline reads no register column."""
    assert critical_targets.newly_read_columns(reading("b", "a"), reading()) == ["a", "b"]


def test_a_column_the_baseline_also_reads_is_refused():
    """Microcosm's counterfactual would withhold it from the tested engine too,
    and label its effect as the newly read columns' effect."""
    with pytest.raises(SystemExit, match="already reads \\['a'\\]"):
        critical_targets.newly_read_columns(reading("a", "b"), reading("a"))


def test_an_engine_that_newly_reads_nothing_needs_no_counterfactual():
    assert critical_targets.newly_read_columns(reading(), reading()) == []
    # A column only the baseline reads is not one the tested engine newly reads.
    assert critical_targets.newly_read_columns(reading(), reading("a")) == []


def test_the_committed_counterfactual_withheld_what_the_tested_engine_newly_reads():
    drift = json.loads((SCORED / "drift.json").read_text())
    scores = drift["scores"]
    newly_read = critical_targets.newly_read_columns(scores["tested"], scores["baseline"])
    assert newly_read == drift["newly_read_columns"] == scores["counterfactual"]["variant"]["withheld_columns"]
    assert newly_read == ["tax_unit_role_input"]


def fake_microcosm(monkeypatch, read_columns):
    """Stand-ins for the Microcosm modules the counting mode imports, which
    record what it passes them."""
    calls = {}
    recert = types.ModuleType("microcosm.data.compatibility_recertification")
    stored_inputs = types.ModuleType("microcosm.data.stored_inputs")
    stored_inputs.US_STORED_NON_VARIABLE_COLUMNS = {"tax_unit_role_input": "reason"}
    def h5_stored_tables(path):
        calls["h5"] = path
        return {"person": ("tax_unit_role_input",)}

    def installed_us_engine():
        print("loading the engine")
        return types.SimpleNamespace(label="policyengine-us 9", variables=frozenset({"tax_unit_role_input"}))

    def stored_column_changes(tables, *, engine_variables, stored_input_register):
        calls["changes"] = (tables, engine_variables, stored_input_register)
        return {"ignored": [], "read": [{"column": c, "tables": ["person"]} for c in read_columns]}

    def combine_drift(**_):
        raise AssertionError("the refusals come before Microcosm combines anything")

    stored_inputs.h5_stored_tables = h5_stored_tables
    stored_inputs.installed_us_engine = installed_us_engine
    recert.stored_column_changes = stored_column_changes
    recert.combine_drift = combine_drift
    requirements = types.ModuleType("microcosm.data.us_critical_targets")
    requirements.US_EXACT_CRITICAL_TARGET_FIT_REQUIREMENTS = ()
    data = types.ModuleType("microcosm.data")
    data.compatibility_recertification, data.stored_inputs, data.us_critical_targets = recert, stored_inputs, requirements
    package = types.ModuleType("microcosm")
    package.data = data
    for module in (package, data, recert, stored_inputs, requirements):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return calls


@pytest.mark.parametrize("columns", ([], ["tax_unit_role_input"], ["b", "a"]))
def test_the_count_mode_prints_one_output_line(monkeypatch, capsys, columns):
    """The Score workflow appends the mode's standard output to
    $GITHUB_OUTPUT: one ``newly_read=<n>`` line, with what the engine prints
    sent to standard error."""
    calls = fake_microcosm(monkeypatch, columns)
    assert critical_targets.main(["--count-newly-read", "data.h5"]) == 0
    printed = capsys.readouterr()
    assert printed.out == f"newly_read={len(columns)}\n"
    assert "loading the engine" in printed.err
    tables, variables, register = calls["changes"]
    assert calls["h5"] == Path("data.h5") and tables == {"person": ("tax_unit_role_input",)}
    assert variables == frozenset({"tax_unit_role_input"}) and register == {"tax_unit_role_input": "reason"}


@pytest.mark.parametrize(
    "tested, baseline, counterfactual, refusal",
    (
        ((), (), True, "nothing to withhold"),
        (("a",), (), False, "pass its counterfactual"),
        (("a",), ("a",), True, "already reads"),
    ),
)
def test_combining_refuses_a_counterfactual_that_does_not_fit(monkeypatch, tmp_path, tested, baseline, counterfactual, refusal):
    """The Score workflow passes the counterfactual whenever its job scored.
    Combining needs one exactly when the tested engine newly reads a column
    the baseline does not."""
    fake_microcosm(monkeypatch, [])
    (tmp_path / "diagnostics.json").write_text("{}")
    sha256 = prepare_scoring.sha256_of(tmp_path / "diagnostics.json")
    files = {
        "baseline": reading(*baseline),
        "tested": reading(*tested),
        "inputs": {"derived_diagnostics": {"sha256": sha256}},
        "counterfactual": reading(*tested),
    }
    for name, document in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(document))
    argv = [f"--{name}={tmp_path / f'{name}.json'}" for name in ("baseline", "tested", "inputs", "diagnostics")]
    if counterfactual:
        argv.append(f"--counterfactual={tmp_path / 'counterfactual.json'}")
    with pytest.raises(SystemExit, match=refusal):
        critical_targets.main([*argv, f"--out={tmp_path / 'out'}"])
    assert not (tmp_path / "out").exists()


def test_scoring_refuses_an_existing_output_folder(tmp_path):
    critical_targets.refuse_existing(tmp_path / "new")
    (tmp_path / "file").write_text("")
    (tmp_path / "dangling").symlink_to(tmp_path / "nowhere")
    for existing in (tmp_path, tmp_path / "file", tmp_path / "dangling"):
        with pytest.raises(SystemExit, match="exists"):
            critical_targets.refuse_existing(existing)
    # The refusal comes before Microcosm is imported or any input is read.
    argv = ["--baseline", "b.json", "--tested", "t.json", "--diagnostics", "d.json", "--inputs", "i.json"]
    with pytest.raises(SystemExit, match="exists"):
        critical_targets.main([*argv, "--out", str(tmp_path)])


def test_rendering_rewrites_an_existing_folder(tmp_path):
    """The README renders the committed tables into their own folder."""
    for name in ("drift.json", "critical_targets.json"):
        (tmp_path / name).write_bytes((SCORED / name).read_bytes())
    (tmp_path / "other.txt").write_text("kept")
    assert critical_targets.main(["--render", str(tmp_path), "--out", str(tmp_path)]) == 0
    for name in ("drift.json", "critical_targets.json", "critical_targets.csv", "critical_targets.md"):
        assert (tmp_path / name).read_bytes() == (SCORED / name).read_bytes(), name
    assert (tmp_path / "other.txt").read_text() == "kept"


def score_document(version):
    return {
        "runtime": {
            "packages": {
                "policyengine-us": {"version": version},
                "policyengine-core": {"version": "3.0.0"},
                "spm-calculator": {"version": "1.1.0"},
            }
        },
        "scoring": {"n_households": 10, "period": 2024, "spm": {"geography_kind": "county"}},
        "code": {"git_commit": "0" * 40},
        "engine": {
            "stored_input_verdict": {"passed": False, "refused": ["would_claim_wic"]},
            "column_changes": {"read": [], "ignored": []},
        },
    }


def test_result_and_markdown_render_from_a_drift_document():
    drift = {
        "dataset_sha256": "ab" * 32,
        "newly_read_columns": ["tax_unit_role_input"],
        "unscored_critical_rows": [],
        "rows": [
            drift_row("eitc_amount", 100.0, 105.0, 120.0, 0.15, (True, False)),
            drift_row("ctc_amount", 200.0, 190.0, 195.0, 0.15, (True, True)),
            drift_row(critical_targets.TABLE_1_4, 50.0, 80.0, 51.0, 0.25, (False, True)),
            {
                "metric_id": "snap_total",
                "label": "SNAP benefits",
                "unit": "usd",
                "requirement_id": None,
                "baseline": 1e11,
                "tested": 9e10,
                "difference": -1e10,
                "relative_difference": -0.1,
            },
        ],
        "scores": {"baseline": score_document("1.0.0"), "tested": score_document("2.0.0")},
    }
    built = {"build_id": "build-x", "policyengine-us": "0.9.0", "policyengine-core": "0.1.0"}
    inputs = {"dataset": {}, "estimates_from": built}
    result = critical_targets.build_result(drift, {"exact_critical_rows": 2}, inputs, ["ctc_amount", "eitc_amount", "missing_one"])
    assert [row["requirement_id"] for row in result["exact"]["rows"]] == ["ctc_amount", "eitc_amount"]
    assert result["unscored_requirements"] == ["missing_one"]
    assert result["exact"]["tally"]["leaving_tolerance"] == ["target:eitc_amount"]
    assert result["table_1_4"]["tally"]["entering_tolerance"] == [f"target:{critical_targets.TABLE_1_4}"]
    text = critical_targets.markdown(result)
    assert "| eitc_amount |" in text and "OUT" in text and "missing_one" in text
    assert "policyengine-us 2.0.0" in text and "SNAP benefits" in text
    assert "`build-x`, made with policyengine-us 0.9.0" in text
    assert "eitc_amount (`eitc_amount`), 5.0 percentage points outside its tolerance." in text
    json.dumps(result)


@pytest.mark.parametrize(
    "tested, within, sentence",
    (
        (102.0, True, "3.0 percentage points inside its tolerance."),
        # An error exactly at the tolerance is within it.
        (105.0, True, "0.0 percentage points inside its tolerance."),
        # An 8% error against ±5%: 3 points outside, not "-3.0 points inside".
        (108.0, False, "3.0 percentage points outside its tolerance."),
        (92.0, False, "3.0 percentage points outside its tolerance."),
    ),
)
def test_the_smallest_margin_says_which_side_of_the_tolerance_it_is(tested, within, sentence):
    drift = {
        "dataset_sha256": "ab" * 32,
        "newly_read_columns": [],
        "unscored_critical_rows": [],
        "rows": [
            drift_row("eitc_amount", 100.0, 100.0, tested, 0.05, (True, within)),
            drift_row(critical_targets.TABLE_1_4, 50.0, 50.0, 50.0, 0.25, (True, True)),
        ],
        "scores": {"baseline": score_document("1.0.0"), "tested": score_document("2.0.0")},
    }
    inputs = {"dataset": {}, "estimates_from": {"build_id": "b", "policyengine-us": "1", "policyengine-core": "2"}}
    result = critical_targets.build_result(drift, {}, inputs, ["eitc_amount"])
    assert (result["exact"]["tally"]["smallest_tested_margin"]["margin"] >= 0) is within
    text = critical_targets.markdown(result)
    assert f"Smallest margin under the tested release: eitc_amount (`eitc_amount`), {sentence}" in text
    assert "-" not in text.split("Smallest margin", 1)[1].split("\n", 1)[0]


def test_source_is_the_first_three_name_parts():
    assert critical_targets.source("target:irs_soi.ty2022.historic_table_2.us.all.ctc_amount@2024") == (
        "irs_soi ty2022 historic_table_2"
    )
    assert critical_targets.source("plain") == "plain"


SCORED = ROOT / "results" / "critical-targets"


def test_committed_tables_regenerate_from_drift(tmp_path):
    critical_targets.render(SCORED, tmp_path)
    for name in ("drift.json", "critical_targets.json", "critical_targets.csv", "critical_targets.md"):
        assert (tmp_path / name).read_bytes() == (SCORED / name).read_bytes(), name


def test_scores_used_the_measured_releases_and_dataset():
    result = json.loads((SCORED / "critical_targets.json").read_text())
    inputs = json.loads((SCORED / "scoring_inputs-pinned.json").read_text())
    for side, run in (("baseline", "pinned"), ("tested", "head")):
        environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
        assert result[side]["versions"] == fetch_wheels.pins(environment)
        assert environment["dataset"]["sha256"] == result["dataset_sha256"] == inputs["dataset"]["sha256"]
    assert result["households"] == inputs["dataset"]["households"]
    assert inputs["published_diagnostics"]["sha256"] == prepare_scoring.PUBLISHED_DIAGNOSTICS_SHA256


# The scorer's programme totals that the 2024 panel also measures. The
# scorer's fourteenth, the Part B income-related surcharge, has no panel row.
SHARED_TOTALS = {
    "income_tax_net",
    "ctc_total",
    "eitc_total",
    "social_security_total",
    "snap_total",
    "snap_units",
    "ssi_total",
    "medicaid_enrollment",
    "medicaid_total",
    "state_income_tax_total",
    "medicare_part_d_irmaa_total",
    "medicare_cost_total",
    "adjusted_gross_income_total",
}


def test_scorer_totals_equal_the_measured_panel():
    """Two harnesses, one dataset: Microcosm's batched scorer and this
    repository's whole-file panel give the same 2024 totals."""
    result = json.loads((SCORED / "critical_targets.json").read_text())
    panels = {
        side: {row["id"]: row["value"] for row in json.loads((ROOT / "results" / run / "panel-2024.json").read_text())["rows"]}
        for side, run in (("baseline", "pinned"), ("tested", "head"))
    }
    shared = [row for row in result["headline"] if row["metric_id"] in panels["baseline"]]
    assert {row["metric_id"] for row in shared} == SHARED_TOTALS
    assert {row["metric_id"] for row in result["headline"]} - SHARED_TOTALS == {"medicare_part_b_irmaa_total"}
    for row in shared:
        for side in ("baseline", "tested"):
            measured = panels[side][row["metric_id"]]
            assert abs(row[side] - measured) <= 1e-8 * max(abs(measured), 1.0), (row["metric_id"], side)


def test_scores_come_from_this_scoring_code():
    assert not provenance.is_stale("score"), "scoring code changed since these scores: run Score again"
    record = json.loads((SCORED / "provenance.json").read_text())
    assert record["workflow"] == "Score"
    assert record["artifacts"] == ["results-critical-targets"]
    assert provenance.scores_differ_from_measured() == []


def test_every_score_file_is_the_recorded_runs_artifact():
    record = json.loads((SCORED / "provenance.json").read_text())
    assert provenance.files_differ_from_record("score") == []
    assert set(record["files"]) == set(provenance.committed("score"))
    for name in ("drift.json", "critical_targets.json", "combine.json"):
        assert f"results/critical-targets/{name}" in record["files"]


def test_estimates_are_named_for_the_build_that_made_them():
    inputs = json.loads((SCORED / "critical_targets.json").read_text())["inputs"]
    built = inputs["estimates_from"]
    assert built["manifest"]["sha256"] == prepare_scoring.PARENT_MANIFEST_SHA256
    assert inputs["published_diagnostics"]["sha256"] == prepare_scoring.PUBLISHED_DIAGNOSTICS_SHA256
    assert (built["policyengine-us"], built["policyengine-core"]) == ("1.764.6", "3.26.11")
    assert built["build_id"] in (SCORED / "critical_targets.md").read_text()


def test_a_parent_listing_other_diagnostics_is_refused():
    parent = {
        "artifacts": {"calibration_diagnostics": {"sha256": "a" * 64}},
        "build": {
            "build_id": "b",
            "built_at": "t",
            "built_with_model_package": {"version": "1"},
            "built_with_core_package": {"version": "2"},
        },
    }
    assert prepare_scoring.estimates_from(parent, "a" * 64)["policyengine-us"] == "1"
    with pytest.raises(ValueError):
        prepare_scoring.estimates_from(parent, "b" * 64)


def test_scores_are_stale_when_the_measured_releases_change(tmp_path):
    for run in ("pinned", "head"):
        (tmp_path / "results" / run).mkdir(parents=True)
        (tmp_path / "results" / run / "environment.json").write_bytes((ROOT / "results" / run / "environment.json").read_bytes())
    (tmp_path / "results" / "critical-targets").mkdir()
    (tmp_path / "results" / "critical-targets" / "critical_targets.json").write_bytes((SCORED / "critical_targets.json").read_bytes())
    assert provenance.scores_differ_from_measured(tmp_path) == []
    environment = json.loads((tmp_path / "results" / "head" / "environment.json").read_text())
    environment["packages"]["policyengine-us"] = "9.9.9"
    (tmp_path / "results" / "head" / "environment.json").write_text(json.dumps(environment))
    assert provenance.scores_differ_from_measured(tmp_path) != []


def test_every_scoring_job_names_the_recorded_run_and_code():
    """The three scoring jobs and the combining job each stamped their own
    output. All four name the recorded run and carry the hashes of the
    scoring code in this tree."""
    record = json.loads((SCORED / "provenance.json").read_text())
    stamps = provenance.stamps("score")
    assert len(stamps) == len(prepare_scoring.SCORING_JOBS) + 1
    assert stamped_by_one_run(stamps, provenance.REPOSITORY, record["workflow_run"]) == record["code_sha256"]
    assert record["code_sha256"] == provenance.code_hashes("score")


def test_the_scoring_jobs_read_the_same_inputs():
    files = [json.loads((SCORED / f"scoring_inputs-{name}.json").read_text()) for name in prepare_scoring.SCORING_JOBS]
    for key in ("dataset", "published_diagnostics", "derived_diagnostics"):
        assert files[0][key] == files[1][key] == files[2][key], key
    embedded = json.loads((SCORED / "critical_targets.json").read_text())["inputs"]
    assert embedded == files[0]


def test_a_stamp_names_the_run_and_the_scoring_code():
    stamp = prepare_scoring.stamp()
    assert set(stamp) == {"run", "code_sha256"}
    assert set(stamp["code_sha256"]) == set(prepare_scoring.SCORING_CODE)
    assert {"scripts/critical_targets.py", "scripts/rules.py", ".github/workflows/score.yml"} <= set(prepare_scoring.SCORING_CODE)
    assert provenance.KINDS["score"]["code"] is prepare_scoring.SCORING_CODE


@pytest.mark.parametrize("name, run", (("pinned", "pinned"), ("head", "head"), ("head-without-newly-read", "head")))
def test_each_scoring_environment_was_the_constrained_one(name, run):
    """Every PyPI package sat at its constrained version. The only other
    installs were the measured run's three engine wheels and Microcosm's two
    packages."""
    lines = (SCORED / f"freeze-{name}.txt").read_text().splitlines()
    constraints = (ROOT / "envs" / "score.constraints.txt").read_text().splitlines()
    assert [line for line in lines if "==" in line] == constraints
    others = [line for line in lines if "==" not in line]
    editable = [line for line in others if line.startswith("-e ")]
    assert sorted(line.rsplit("/", 1)[-1] for line in editable) == ["microcosm-data", "microcosm-diagnostics"]
    environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
    wheels = {line.split(" @ ", 1)[0]: line for line in others if " @ file://" in line}
    assert set(wheels) == set(fetch_wheels.PACKAGES)
    for package, version in fetch_wheels.pins(environment).items():
        assert wheels[package].endswith(f"/{package.replace('-', '_')}-{version}-py3-none-any.whl"), package
    assert len(others) == len(editable) + len(wheels)


# Each earlier run, with the date its rows file records (GitHub's start time).
EARLIER_RUNS = {
    44345993218: "2026-11-18",
    44903905024: "2026-11-21",
    44910821596: "2026-11-21",
    45199019867: "2026-11-23T14:53:13Z",
    # The run recorded before this one, at commit 2a03f3e.
    45207756243: "2026-11-23T15:39:56Z",
}
# The two earlier runs whose installs were not constrained.
UNCONSTRAINED_RUNS = tuple(EARLIER_RUNS)[:2]
# Every earlier run scored policyengine-us 2.2.2 as the baseline and 2.144.4
# as the tested release.
EARLIER_RELEASES = {"baseline": "2.2.2", "tested": "2.144.4"}


@pytest.mark.parametrize("run, date", EARLIER_RUNS.items())
def test_an_earlier_scoring_run_gave_the_same_rows(run, date):
    """Earlier runs, the first two under installs that were not constrained
    and the others under earlier scoring code, agree with the committed scores
    for each side that scored the same release: every estimate to within 1
    part in 10^15, and every target, tolerance and verdict exactly. A side
    that now scores another release is kept, not compared."""
    earlier = json.loads((SCORED / "earlier" / f"run-{run}-rows.json").read_text())
    record = json.loads((SCORED / "provenance.json").read_text())
    assert earlier["workflow_run"] == run != record["workflow_run"]
    assert earlier["date"] == date < record["started"]
    now = {row["metric_id"]: row for row in json.loads((SCORED / "drift.json").read_text())["rows"]}
    assert set(now) == {row["metric_id"] for row in earlier["rows"]}
    result = json.loads((SCORED / "critical_targets.json").read_text())
    same = [side for side in EARLIER_RELEASES if result[side]["versions"]["policyengine-us"] == EARLIER_RELEASES[side]]
    assert "baseline" in same, "the baseline no longer scores the release the earlier runs scored"
    estimates = ["baseline"] + (["tested", "without_newly_read_inputs"] if "tested" in same else [])
    for row in earlier["rows"]:
        current = now[row["metric_id"]]
        for key in estimates:
            assert math.isclose(current[key], row[key], rel_tol=1e-15, abs_tol=0.0), (row["metric_id"], key)
        for key in ("requirement_id", "target", "tolerance"):
            assert current.get(key) == row[key], (row["metric_id"], key)
        if row["within_tolerance"] is None:
            assert current.get("within_tolerance") is None, row["metric_id"]
        else:
            for side in same:
                assert current["within_tolerance"][side] == row["within_tolerance"][side], (row["metric_id"], side)


def exact_pins(path: Path) -> dict[str, str]:
    return dict(line.split("==", 1) for line in path.read_text().splitlines() if "==" in line)


@pytest.mark.parametrize("job", prepare_scoring.SCORING_JOBS)
def test_the_earlier_runs_installs_differed_in_five_packages(job):
    first, second = (exact_pins(SCORED / "earlier" / f"run-{run}-freeze-{job}.txt") for run in UNCONSTRAINED_RUNS)
    assert set(first) == set(second)
    assert sorted(name for name in first if first[name] != second[name]) == [
        "certifi",
        "decorator",
        "pydantic",
        "pydantic-core",
        "pyyaml",
    ]
