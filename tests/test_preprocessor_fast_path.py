"""RBAPreprocessor.transform 최적화(딕셔너리 조회 경로)가 기존 sklearn 경로와 동일한 결과를 내는지 검증한다."""
import io
import random
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd

from src.prex.preprocessor import RBAPreprocessor

CATS = [
    'Country', 'Region', 'City',
    'OS Name and Version', 'Browser Name and Version', 'Device Type',
]
FEATS = CATS + ['hour', 'day_of_week', 'ASN', 'Login Successful']


def _make_raw(n, seed, cat_pool=None, noise=False):
    rng = random.Random(seed)
    pool = cat_pool or {c: [f"{c}_{i}" for i in range(30)] for c in CATS}
    data = {}
    for c in CATS:
        col = []
        for _ in range(n):
            r = rng.random()
            if noise and r < 0.08:
                col.append(f"UNSEEN_{rng.randint(0, 10**6)}")  # 학습에 없던 값
            elif noise and r < 0.12:
                col.append(None)  # 결측
            else:
                col.append(rng.choice(pool[c]))
        data[c] = col
    df = pd.DataFrame(data)
    df['ASN'] = [rng.randint(1, 400000) for _ in range(n)]
    df['Login Timestamp'] = [
        "garbage" if (noise and rng.random() < 0.05)
        else (datetime(2026, 1, 1) + timedelta(minutes=rng.randint(0, 500000))).isoformat()
        for _ in range(n)
    ]
    df['Login Successful'] = [rng.random() < 0.8 for _ in range(n)]
    return df


def _make_train(n=500, seed=0):
    df = _make_raw(n, seed)
    rng = random.Random(seed + 1)
    df['Is Attack IP'] = [rng.random() < 0.1 for _ in range(n)]
    df['Is Account Takeover'] = [rng.random() < 0.05 for _ in range(n)]
    return df


def _reference_transform(pre, raw):
    """최적화 이전의 transform 구현(sklearn OrdinalEncoder/StandardScaler 직접 호출)."""
    df = raw.copy()
    df[pre.categorical_cols] = df[pre.categorical_cols].fillna('unknown')
    df['Login Successful'] = df['Login Successful'].astype(int)
    df = pre.process_time_features(df)
    df[pre.categorical_cols] = pre.cat_encoder.transform(df[pre.categorical_cols].astype(str))
    feature_cols = pre.categorical_cols + ['hour', 'day_of_week', 'ASN', 'Login Successful']
    x_data = df[feature_cols].copy()
    x_data[feature_cols] = pre.scaler.transform(x_data[feature_cols])
    return x_data


def _fitted():
    pre = RBAPreprocessor()
    pre.fit_transform(_make_train())
    return pre


def test_matches_sklearn_path_including_unseen_missing_and_bad_timestamp():
    pre = _fitted()
    raw = _make_raw(2000, seed=42, noise=True)
    ref = _reference_transform(pre, raw)
    new = pre.transform(raw)
    assert list(new.columns) == list(ref.columns) == FEATS
    assert np.array_equal(new.to_numpy(), ref.to_numpy())


def test_single_row_matches_sklearn_path():
    pre = _fitted()
    raw = _make_raw(50, seed=7, noise=True)
    for i in range(len(raw)):
        row = raw.iloc[[i]]
        assert np.array_equal(pre.transform(row).to_numpy(), _reference_transform(pre, row).to_numpy())


def test_unknown_category_maps_to_unknown_value():
    pre = _fitted()
    raw = _make_raw(1, seed=3)
    raw.loc[0, 'City'] = "NEVER_SEEN_CITY"
    out = pre.transform(raw)
    city_idx = FEATS.index('City')
    unk = pre.cat_encoder.unknown_value
    expected = (unk - pre.scaler.mean_[city_idx]) / pre.scaler.scale_[city_idx]
    assert out.iloc[0, city_idx] == expected


def test_pickle_does_not_store_lookup_cache():
    pre = _fitted()
    pre.transform(_make_raw(3, seed=1))  # 캐시 생성
    assert getattr(pre, "_cat_maps", None) is not None
    buf = io.BytesIO()
    joblib.dump(pre, buf)
    buf.seek(0)
    restored = joblib.load(buf)
    assert getattr(restored, "_cat_maps", None) is None
    raw = _make_raw(20, seed=5, noise=True)
    assert np.array_equal(restored.transform(raw).to_numpy(), _reference_transform(restored, raw).to_numpy())


def test_refit_invalidates_cache():
    pre = _fitted()
    pre.transform(_make_raw(3, seed=1))
    new_pool = {c: [f"NEW_{c}_{i}" for i in range(10)] for c in CATS}
    train2 = _make_raw(300, seed=9, cat_pool=new_pool)
    train2['Is Attack IP'] = False
    train2['Is Account Takeover'] = False
    pre.fit_transform(train2)
    raw = _make_raw(100, seed=11, cat_pool=new_pool, noise=True)
    assert np.array_equal(pre.transform(raw).to_numpy(), _reference_transform(pre, raw).to_numpy())
