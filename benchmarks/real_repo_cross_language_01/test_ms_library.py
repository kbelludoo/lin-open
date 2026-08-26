"""test_ms_library.py - Tests for Python ms library implementation"""

import pytest
from ms_library import ms, parse, format_ms


class TestParse:
    """Test parse function"""
    
    def test_preserve_ms(self):
        assert ms('100') == 100
    
    def test_convert_m_to_ms(self):
        assert ms('1m') == 60000
    
    def test_convert_h_to_ms(self):
        assert ms('1h') == 3600000
    
    def test_convert_d_to_ms(self):
        assert ms('2d') == 172800000
    
    def test_convert_w_to_ms(self):
        assert ms('3w') == 1814400000
    
    def test_convert_s_to_ms(self):
        assert ms('1s') == 1000
    
    def test_convert_ms_to_ms(self):
        assert ms('100ms') == 100
    
    def test_convert_y_to_ms(self):
        assert ms('1y') == 31557600000
    
    def test_decimals(self):
        assert ms('1.5h') == 5400000
    
    def test_multiple_spaces(self):
        assert ms('1   s') == 1000
    
    def test_case_insensitive(self):
        assert ms('1.5H') == 5400000
    
    def test_dot_prefix(self):
        assert ms('.5ms') == 0.5
    
    def test_negative_integers(self):
        assert ms('-100ms') == -100
    
    def test_negative_decimals(self):
        assert ms('-1.5h') == -5400000
        assert ms('-10.5h') == -37800000
    
    def test_negative_dot_prefix(self):
        assert ms('-.5h') == -1800000
    
    def test_long_strings(self):
        assert ms('53 milliseconds') == 53
        assert ms('17 msecs') == 17
        assert ms('1 sec') == 1000
        assert ms('3 mins') == 180000
        assert ms('2 hours') == 7200000
        assert ms('5 days') == 432000000
        assert ms('1 week') == 604800000
        assert ms('1 year') == 31557600000
        assert ms('1 month') == 2629800000
    
    def test_invalid_returns_nan(self):
        import math
        assert math.isnan(ms('☃'))
        assert math.isnan(ms('10-.5'))
        assert math.isnan(ms('ms'))


class TestFormat:
    """Test format function"""
    
    def test_format_seconds(self):
        assert format_ms(1000) == '1s'
    
    def test_format_minutes(self):
        assert format_ms(60000) == '1m'
    
    def test_format_hours(self):
        assert format_ms(3600000) == '1h'
    
    def test_format_days(self):
        assert format_ms(86400000) == '1d'
    
    def test_format_weeks(self):
        assert format_ms(604800000) == '1w'
    
    def test_format_months(self):
        assert format_ms(2629800000) == '1mo'
    
    def test_format_years(self):
        assert format_ms(31557600000) == '1y'
    
    def test_format_milliseconds(self):
        assert format_ms(100) == '100ms'
    
    def test_format_negative(self):
        assert format_ms(-60000) == '-1m'
    
    def test_format_long(self):
        assert format_ms(60000, long=True) == '1 minute'
        assert format_ms(3600000, long=True) == '1 hour'
        assert format_ms(86400000, long=True) == '1 day'
    
    def test_format_long_plural(self):
        assert format_ms(120000, long=True) == '2 minutes'
        assert format_ms(7200000, long=True) == '2 hours'


class TestRoundTrip:
    """Test round-trip conversion"""
    
    def test_parse_format_roundtrip(self):
        # Test cases that round-trip cleanly (whole numbers)
        test_cases = ['1m', '1h', '2d', '1y', '100ms', '5s']
        for case in test_cases:
            parsed = ms(case)
            formatted = format_ms(parsed)
            reparsed = ms(formatted)
            assert reparsed == parsed, f"Round-trip failed for {case}"
    
    def test_parse_format_roundtrip_with_decimals(self):
        # Test that decimals are preserved as much as possible
        # Note: 1.5h -> 5400000ms -> "2h" (rounds to nearest) -> 7200000ms
        # This is expected behavior - format rounds to nearest unit
        assert ms('1.5h') == 5400000
        assert format_ms(5400000) == '2h'  # Rounded to nearest
        assert ms('2h') == 7200000
