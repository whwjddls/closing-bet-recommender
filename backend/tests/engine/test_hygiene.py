from app.engine.signals.hygiene import passes_static, is_overheated, passes_dynamic

OK_STATIC = dict(
    sec_type="COMMON", avg_value_20d=5_000_000_000, is_managed=False,
    is_warning=False, is_caution=False, listing_days=300,
)


def test_passes_static_ok():
    assert passes_static(**OK_STATIC) is True


def test_static_excludes_sec_type():
    assert passes_static(**{**OK_STATIC, "sec_type": "ETF"}) is False
    assert passes_static(**{**OK_STATIC, "sec_type": "SPAC"}) is False


def test_static_excludes_low_liquidity():
    assert passes_static(**{**OK_STATIC, "avg_value_20d": 999_999_999}) is False  # <10억


def test_static_excludes_managed_warning_caution():
    assert passes_static(**{**OK_STATIC, "is_managed": True}) is False
    assert passes_static(**{**OK_STATIC, "is_warning": True}) is False
    assert passes_static(**{**OK_STATIC, "is_caution": True}) is False


def test_static_excludes_short_listing():
    assert passes_static(**{**OK_STATIC, "listing_days": 119}) is False


def test_is_overheated():
    assert is_overheated(20.0, False, False) is True   # 등락률 ≥ +20%
    assert is_overheated(5.0, True, False) is True     # 상한가
    assert is_overheated(5.0, False, True) is True      # VI
    assert is_overheated(5.0, False, False) is False


def test_passes_dynamic():
    assert passes_dynamic(5.0, False, False, False) is True
    assert passes_dynamic(5.0, False, False, True) is False   # 거래정지
    assert passes_dynamic(25.0, False, False, False) is False  # 과열
