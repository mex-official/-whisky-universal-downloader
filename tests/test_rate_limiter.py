import pytest
from rate_limiter import RateLimiter

def test_allows_limit_then_blocks():
    r=RateLimiter(2, 60)
    assert r.allow(1, now=0); assert r.allow(1, now=1); assert not r.allow(1, now=2)
def test_resets_after_period():
    r=RateLimiter(1, 10)
    assert r.allow(1, now=0); assert r.allow(1, now=10)
def test_users_are_isolated():
    r=RateLimiter(1, 10)
    assert r.allow(1, now=0); assert r.allow(2, now=0)
@pytest.mark.parametrize("limit,period", [(0,1),(1,0),(-1,4),(2,-1)])
def test_invalid_config(limit,period):
    with pytest.raises(ValueError): RateLimiter(limit,period)
def test_same_timestamp_counts():
    r=RateLimiter(1,10); assert r.allow(1,now=2); assert not r.allow(1,now=2)
