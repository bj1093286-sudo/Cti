import unittest
from datetime import date

from cti.periods import Period, resolve


class ResolveTest(unittest.TestCase):
    def test_today_vs_yesterday(self):
        cur, prev = resolve("today", date(2026, 10, 12))
        self.assertEqual(cur, Period(date(2026, 10, 12), date(2026, 10, 12)))
        self.assertEqual(prev, Period(date(2026, 10, 11), date(2026, 10, 11)))

    def test_yesterday(self):
        cur, prev = resolve("yesterday", date(2026, 10, 1))
        self.assertEqual(cur.start, date(2026, 9, 30))
        self.assertEqual(prev.start, date(2026, 9, 29))

    def test_this_week_to_date(self):
        cur, prev = resolve("this_week", date(2026, 10, 15))  # 목요일
        self.assertEqual(cur, Period(date(2026, 10, 12), date(2026, 10, 15)))
        self.assertEqual(prev, Period(date(2026, 10, 5), date(2026, 10, 8)))

    def test_this_month_clamps_previous_month_end(self):
        cur, prev = resolve("this_month", date(2026, 3, 31))
        self.assertEqual(cur, Period(date(2026, 3, 1), date(2026, 3, 31)))
        self.assertEqual(prev, Period(date(2026, 2, 1), date(2026, 2, 28)))

    def test_this_month_january(self):
        _, prev = resolve("this_month", date(2026, 1, 10))
        self.assertEqual(prev, Period(date(2025, 12, 1), date(2025, 12, 10)))

    def test_custom_previous_same_length(self):
        cur, prev = resolve("custom", date(2026, 10, 12), date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual(cur.days, 7)
        self.assertEqual(prev, Period(date(2026, 9, 24), date(2026, 9, 30)))

    def test_custom_swaps_reversed_range(self):
        cur, _ = resolve("custom", date(2026, 10, 12), date(2026, 10, 7), date(2026, 10, 1))
        self.assertEqual(cur.start, date(2026, 10, 1))

    def test_custom_requires_dates_and_limits_length(self):
        with self.assertRaises(ValueError):
            resolve("custom", date(2026, 10, 12))
        with self.assertRaises(ValueError):
            resolve("custom", date(2026, 10, 12), date(2024, 1, 1), date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
