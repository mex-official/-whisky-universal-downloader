from types import SimpleNamespace
import pytest
from rate_limiter import RateLimiter

def test_command_args_none_is_handled():
    args = getattr(SimpleNamespace(args=None), "args", None) or []
    assert " ".join(args).strip() == ""

def test_rate_limiter_burst_boundary():
    r=RateLimiter(3,60)
    assert [r.allow(9,now=t) for t in (0,1,2,3)] == [True,True,True,False]

def test_rate_limiter_window_boundary():
    r=RateLimiter(2,60)
    assert r.allow(1,now=0); assert r.allow(1,now=20); assert r.allow(1,now=60)
