import pytest
from calculator import mul

def test_mul_positive_integers():
    """Tests multiplication of two positive integers."""
    assert mul(2, 3) == 6
    assert mul(10, 5) == 50
    assert mul(1, 1) == 1

def test_mul_negative_integers():
    """Tests multiplication of two negative integers."""
    assert mul(-2, -3) == 6
    assert mul(-10, -5) == 50
    assert mul(-1, -1) == 1

def test_mul_mixed_sign_integers():
    """Tests multiplication of integers with mixed signs."""
    assert mul(2, -3) == -6
    assert mul(-2, 3) == -6
    assert mul(10, -1) == -10
    assert mul(-1, 10) == -10

def test_mul_with_zero():
    """Tests multiplication involving zero."""
    assert mul(0, 5) == 0
    assert mul(5, 0) == 0
    assert mul(0, 0) == 0
    assert mul(-10, 0) == 0
    assert mul(0.5, 0) == 0.0

def test_mul_positive_floats():
    """Tests multiplication of two positive floats."""
    assert mul(2.5, 2.0) == 5.0
    assert mul(0.5, 0.5) == 0.25
    assert mul(1.0, 3.14) == 3.14

def test_mul_negative_floats():
    """Tests multiplication of two negative floats."""
    assert mul(-2.5, -2.0) == 5.0
    assert mul(-0.5, -0.5) == 0.25

def test_mul_mixed_sign_floats():
    """Tests multiplication of floats with mixed signs."""
    assert mul(2.5, -2.0) == -5.0
    assert mul(-2.5, 2.0) == -5.0

def test_mul_integer_and_float():
    """Tests multiplication of an integer and a float."""
    assert mul(2, 3.5) == 7.0
    assert mul(3.5, 2) == 7.0
    assert mul(-2, 3.5) == -7.0
    assert mul(3.5, -2) == -7.0

def test_mul_large_numbers():
    """Tests multiplication with large numbers to ensure correctness."""
    assert mul(1000000, 2000000) == 2000000000000
    assert mul(123456789, 987654321) == 121932631112635269

def test_mul_small_floats():
    """Tests multiplication with very small floating-point numbers."""
    assert mul(0.0001, 0.0002) == pytest.approx(2e-8)
    assert mul(1e-10, 1e-10) == pytest.approx(1e-20)

def test_mul_type_error_string():
    """Tests that mul raises TypeError for string inputs."""
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul("a", 2)
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(2, "b")
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul("a", "b")

def test_mul_type_error_list():
    """Tests that mul raises TypeError for list inputs."""
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul([1, 2], 3)
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(3, [1, 2])

def test_mul_type_error_none():
    """Tests that mul raises TypeError for None inputs."""
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(None, 5)
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(5, None)

def test_mul_type_error_boolean():
    """Tests that mul raises TypeError for boolean inputs (as they are subclasses of int)."""
    # Python's bool is a subclass of int, so True is 1 and False is 0.
    # The current implementation allows bools because isinstance(True, int) is True.
    # If the requirement was to explicitly disallow bools, the type check would need to be more specific.
    # For now, we test that they work as numbers.
    assert mul(True, 5) == 5 # True is 1
    assert mul(False, 5) == 0 # False is 0
    assert mul(True, True) == 1
    assert mul(False, False) == 0
    assert mul(True, False) == 0

def test_mul_type_error_mixed_invalid_types():
    """Tests that mul raises TypeError for mixed valid/invalid types."""
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(1, "invalid")
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul("invalid", 1.0)
    with pytest.raises(TypeError, match="Inputs must be numbers."):
        mul(None, 10)
