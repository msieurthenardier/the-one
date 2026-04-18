import pytest

def test_run_tests():
    result = run_tests()
    assert 'no tests ran' not in result, "Test suite should have found and executed some tests."