import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from cart import total


def test_no_discount():
    assert total([("a", 10.0), ("b", 5.0)], 0) == 15.0


def test_ten_percent():
    assert total([("x", 100.0)], 10) == 90.0, f"10% off 100 should be 90, got {total([('x',100.0)],10)}"


if __name__ == "__main__":
    test_no_discount()
    test_ten_percent()
    print("ok - 2 passed")
