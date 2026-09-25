"""Export tests: schema-v1 rows, append behaviour, and round-trips."""
import pandas as pd
import pytest

from cmj.app.decisions import Decision, apply_decision
from cmj.export import COLUMNS, SCHEMA_VERSION, append_result, result_row

from conftest import WEIGHING_START_S

META = {"participant": "P001", "session": "T1", "trial": "1"}


@pytest.fixture
def accept_row(synth_trial, synth_config):
    decision = Decision(weighing_start_s=WEIGHING_START_S, action="accept")
    result = apply_decision(decision, synth_trial, synth_config, config_preset="HD-raw")
    return result_row(result, decision, META)


def test_row_has_full_schema(accept_row):
    assert list(accept_row) == COLUMNS
    assert accept_row["schema_version"] == SCHEMA_VERSION
    assert accept_row["plate_type"] == "synthetic"
    assert accept_row["source_file"] == "synthetic_cmj.csv"
    assert accept_row["config_preset"] == "HD-raw"


def test_append_writes_header_once(tmp_path, accept_row):
    path = tmp_path / "results.csv"
    append_result(path, accept_row)
    append_result(path, accept_row)

    df = pd.read_csv(path)
    assert len(df) == 2
    assert list(df.columns) == COLUMNS
    # Header appears exactly once
    with open(path) as f:
        content = f.read()
    assert content.count("schema_version") == 1


def test_append_to_existing_file_preserves_rows(tmp_path, accept_row):
    path = tmp_path / "results.csv"
    df = pd.DataFrame([accept_row], columns=COLUMNS)
    df.to_csv(path, index=False)

    append_result(path, accept_row)
    reread = pd.read_csv(path)
    assert len(reread) == 2
    assert list(reread.columns) == COLUMNS


def test_weighing_start_round_trips_exactly(tmp_path, accept_row):
    """A logged click time must survive the CSV round-trip bit-for-bit
    (logged at microsecond precision, see result_row)."""
    accept_row = dict(accept_row, weighing_start_s=round(0.23699999999999997, 6))
    path = tmp_path / "results.csv"
    append_result(path, accept_row)
    reread = pd.read_csv(path)
    assert reread.loc[0, "weighing_start_s"] == accept_row["weighing_start_s"]
