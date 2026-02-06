import pytest

from scripts.tsv2sqlite import _validate_table_name, parse_date


class TestValidateTableName:
    def test_valid_name(self):
        assert _validate_table_name("arxiv_papers") == "arxiv_papers"

    def test_valid_name_with_numbers(self):
        assert _validate_table_name("table_1") == "table_1"

    def test_rejects_sql_injection(self):
        with pytest.raises(ValueError):
            _validate_table_name("papers; DROP TABLE --")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            _validate_table_name("bad name")

    def test_rejects_leading_number(self):
        with pytest.raises(ValueError):
            _validate_table_name("1table")


class TestParseDate:
    def test_timezone_format(self):
        dt = parse_date("2024-01-15 10:30:00+0000")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_iso_format(self):
        dt = parse_date("2024-01-15T10:30:00.000000")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_date("not-a-date")
