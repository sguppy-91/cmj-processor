"""PASCO export reader tests.

The fixture (tests/data/pasco_multi_run.csv) is a trimmed excerpt of a
real five-run Capstone export: the first 121 rows (all runs have data)
plus the last 5 ragged rows, so per-run length differences and
time-without-force rows are exercised against real formatting.
"""
from pathlib import Path

import pytest

from cmj.errors import FormatError, UnknownFormatError
from cmj.readers import PascoReader, read_csv_any
from cmj.readers.pasco import PascoReader as PR

DATA = Path(__file__).parent / "data"
FIXTURE = DATA / "pasco_multi_run.csv"
HAWKIN_FIXTURE = DATA / "hawkin_fixture.csv"

EXPECTED_LENGTHS = {1: 121, 2: 125, 3: 121, 4: 121, 5: 121}


def write_pasco_csv(path, header, rows):
    import csv

    with open(path, "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(rows)


class TestFixture:
    def test_five_runs_read(self):
        trials = read_csv_any(FIXTURE)
        assert len(trials) == 5
        assert [t.meta["run"] for t in trials] == ["1", "2", "3", "4", "5"]
        assert all(t.plate_type == "pasco" for t in trials)

    def test_ragged_run_lengths(self):
        """Runs end at different times; each keeps only its own rows."""
        trials = read_csv_any(FIXTURE)
        assert {int(t.meta["run"]): t.t.size for t in trials} == EXPECTED_LENGTHS

    def test_values_and_metadata(self):
        trials = read_csv_any(FIXTURE)
        first = trials[0]
        assert first.fs == pytest.approx(1000.0)
        assert first.t[0] == pytest.approx(0.0)
        assert first.t.size == first.fz.size
        assert first.meta["source_file"] == FIXTURE.name
        # First data row of the real export: Fz 1105.32 N
        assert first.fz[0] == pytest.approx(1105.32, abs=1e-2)


class TestSniffAndDispatch:
    def test_sniff_accepts_pasco_header(self):
        reader = PascoReader()
        cols = ["Time (s) Run #1", "Fz (N) Run #1", "weight (N) Run #1"]
        assert reader.sniff(cols)
        assert not reader.sniff(["Time (s)", "Combined (N)"])

    def test_auto_dispatch(self):
        assert all(t.plate_type == "pasco" for t in read_csv_any(FIXTURE))
        assert all(t.plate_type == "hawkin" for t in read_csv_any(HAWKIN_FIXTURE))

    def test_plate_type_override(self):
        trials = read_csv_any(FIXTURE, plate_type="pasco")
        assert len(trials) == 5

    def test_unknown_override_rejected(self):
        with pytest.raises(UnknownFormatError, match="No reader for plate_type"):
            read_csv_any(FIXTURE, plate_type="kistler")


class TestSyntheticVariants:
    """Per-run sample rates and non-zero time offsets, as Capstone/SPARK
    exports can contain runs recorded at different rates."""

    def _write_two_rate_runs(self, path):
        header = ["Time (s) Run #1", "Fz (N) Run #1", "Time (s) Run #2", "Fz (N) Run #2"]
        rows = []
        for k in range(50):
            rows.append([f"{12.345 + k * 0.002:.4f}", "800.0",
                         f"{k * 0.001:.4f}" if k < 30 else "", "750.0" if k < 30 else ""])
        write_pasco_csv(path, header, rows)

    def test_per_run_rate_and_offset(self, tmp_path):
        p = tmp_path / "two_rates.csv"
        self._write_two_rate_runs(p)
        trials = read_csv_any(p)

        assert len(trials) == 2
        run1, run2 = trials
        # fs is derived from the data, never from metadata
        assert run1.fs == pytest.approx(500.0)
        assert run2.fs == pytest.approx(1000.0)
        # non-zero time offset is preserved, not re-zeroed
        assert run1.t[0] == pytest.approx(12.345)
        assert run2.t.size == 30  # ragged second run

    def test_missing_fz_column_rejected(self, tmp_path):
        p = tmp_path / "bad.csv"
        write_pasco_csv(p, ["Time (s) Run #1", "weight (N) Run #1"],
                       [["0.000", "800.0"], ["0.001", "800.1"]])
        with pytest.raises(FormatError, match="missing columns"):
            read_csv_any(p, plate_type="pasco")

    def test_run_group_without_run_suffix_rejected(self, tmp_path):
        p = tmp_path / "no_runs.csv"
        write_pasco_csv(p, ["Time (s)", "Fz (N)"], [["0.000", "800.0"], ["0.001", "800.1"]])
        with pytest.raises(FormatError, match="no 'Run #N'"):
            read_csv_any(p, plate_type="pasco")
