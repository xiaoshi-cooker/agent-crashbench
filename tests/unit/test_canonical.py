"""Tests for canonical JSON and content addressing."""

from harness.core.canonical import canonical_json, digest, now_us, sha256_hex


def test_canonical_json_is_order_invariant():
    a = {"b": 1, "a": {"y": 2, "x": [3, 1]}}
    b = {"a": {"x": [3, 1], "y": 2}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_is_compact_and_sorted():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_rejects_nan():
    import pytest

    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_sha256_known_vector():
    # sha256("") is a fixed universal constant
    assert (
        sha256_hex("")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_digest_stable_across_key_order():
    assert digest({"k": 1, "j": 2}) == digest({"j": 2, "k": 1})


def test_now_us_is_integer_microseconds():
    t1 = now_us()
    t2 = now_us()
    assert isinstance(t1, int)
    assert t2 >= t1
    # sanity: after 2020-01-01 and before 2100-01-01, in microseconds
    assert 1_577_836_800_000_000 < t1 < 4_102_444_800_000_000
