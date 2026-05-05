"""Tests for CSV import validation helpers."""

from django.test import TestCase

from apps.planning.views._csv_import import _validate_developer_rows
from apps.planning.views._csv_import import _validate_rows


class TestValidateRows(TestCase):
    """Tests for the generic _validate_rows() helper."""

    def _make_validator(self, error_msg=None):
        """Return a validator that always passes or always fails."""

        def validator(value):
            return error_msg

        return validator

    def test_returns_empty_list_for_valid_rows(self):
        rows = [{"field": "ok"}]
        result = _validate_rows(rows, {"field": self._make_validator(None)})
        self.assertEqual(result, [])

    def test_returns_error_with_row_number(self):
        rows = [{"field": "bad"}]
        result = _validate_rows(
            rows, {"field": self._make_validator("something wrong")},
        )
        self.assertEqual(len(result), 1)
        self.assertIn("Row 2:", result[0])
        self.assertIn("something wrong", result[0])

    def test_multiple_errors_per_row(self):
        rows = [{"a": "bad", "b": "also bad"}]
        result = _validate_rows(
            rows,
            {
                "a": self._make_validator("error a"),
                "b": self._make_validator("error b"),
            },
        )
        self.assertEqual(len(result), 2)

    def test_row_numbering_starts_at_2(self):
        rows = [{"field": "bad"}]
        result = _validate_rows(rows, {"field": self._make_validator("oops")})
        self.assertTrue(result[0].startswith("Row 2:"))

    def test_multiple_rows_numbered_correctly(self):
        rows = [{"field": "bad"}, {"field": "bad"}]
        result = _validate_rows(rows, {"field": self._make_validator("oops")})
        self.assertIn("Row 2:", result[0])
        self.assertIn("Row 3:", result[1])

    def test_missing_field_treated_as_empty_string(self):
        rows = [{}]
        called_with = []

        def capture(value):
            called_with.append(value)

        _validate_rows(rows, {"missing": capture})
        self.assertEqual(called_with, [""])


class TestValidateDeveloperRows(TestCase):
    """Regression tests for _validate_developer_rows() using the generic helper."""

    def _row(self, email="dev@example.com", name="Dev Name", effort="26"):
        return {"email": email, "name": name, "effort_available": effort}

    def test_valid_rows_pass(self):
        errors = _validate_developer_rows([self._row()])
        self.assertEqual(errors, [])

    def test_invalid_email_caught(self):
        errors = _validate_developer_rows([self._row(email="not-an-email")])
        self.assertEqual(len(errors), 1)
        self.assertIn("Row 2:", errors[0])
        self.assertIn("invalid email", errors[0])

    def test_missing_email_caught(self):
        errors = _validate_developer_rows([self._row(email="")])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Row 2:"))
        self.assertIn("email is required", errors[0])

    def test_missing_name_caught(self):
        errors = _validate_developer_rows([self._row(name="")])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Row 2:"))
        self.assertIn("name is required", errors[0])

    def test_invalid_effort_caught(self):
        errors = _validate_developer_rows([self._row(effort="not-a-number")])
        self.assertEqual(len(errors), 1)
        self.assertIn("Row 2:", errors[0])
        self.assertIn("effort_available must be a number", errors[0])

    def test_negative_effort_caught(self):
        errors = _validate_developer_rows([self._row(effort="-5")])
        self.assertEqual(len(errors), 1)
        self.assertIn("Row 2:", errors[0])
        self.assertIn("effort_available must be zero or positive", errors[0])

    def test_empty_effort_is_valid(self):
        errors = _validate_developer_rows([self._row(effort="")])
        self.assertEqual(errors, [])
