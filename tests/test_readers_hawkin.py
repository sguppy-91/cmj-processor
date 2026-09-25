"""Hawkin Dynamics export reader tests, against a small synthetic
fixture with the real export's layout (CRLF, quoted header, extra
columns beyond the four the analysis needs)."""
from pathlib import Path

import pytest

from cmj.errors import FormatError
from cmj.readers import HawkinReader, read_csv_any

DATA = Path(__file__).parent / "data"
FIXTURE = DATA / "hawkin_fixture.csv"


class TestFixture:
    def test_single_trial(self):
        trials = read_csv_any(FIXTURE)
        assert len(trials) == 1
        trial = trials[0]
        assert trial.plate_type == "hawkin"
        assert trial.fs == pytest.approx(1000.0)
        assert trial.t.size == 150
        assert trial.meta["source_file"] == FIXTURE.name

    def test_values(self):
        trial = read_csv_any(FIXTURE)[0]
        # Synthetic fixture: constant 444 + 441 N channels
        assert trial.fz[0] == pytest.approx(885.0)
        assert trial.t[0] == pytest.approx(0.0)
        assert trial.t[-1] == pytest.approx(0.149)


class TestSniffAndErrors:
    def test_sniff(self):
        reader = HawkinReader()
        assert reader.sniff(["Time (s)", "Left (N)", "Right (N)", "Combined (N)"])
        assert not reader.sniff(["Time (s) Run #1", "Fz (N) Run #1"])

    def test_missing_combined_column(self, tmp_path):
        p = tmp_path / "bad_hd.csv"
        p.write_text('"Time (s)","Left (N)"\n0.000,444.0\n', encoding="utf-8")
        # Auto-detection rejects it (not a valid HD header); forcing the
        # reader exercises the explicit missing-column error.
        with pytest.raises(FormatError, match="unrecognised plate export"):
            read_csv_any(p)
        with pytest.raises(FormatError, match="missing columns"):
            read_csv_any(p, plate_type="hawkin")

    def test_bom_is_stripped(self, tmp_path):
        """Some HD-style exports carry a UTF-8 BOM; the reader must not
        let it corrupt the first column name."""
        p = tmp_path / "bom_hd.csv"
        p.write_text(
            '"Time (s)","Combined (N)"\n0.000,885.0\n0.001,885.0\n',
            encoding="utf-8-sig",
        )
        trial = read_csv_any(p)[0]
        assert trial.fz[0] == pytest.approx(885.0)
