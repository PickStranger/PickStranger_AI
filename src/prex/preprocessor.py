import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, OrdinalEncoder


class RBAPreprocessor:
    def __init__(self):
        self.cat_encoder = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.scaler = StandardScaler()

        self.categorical_cols = [
            'Country', 'Region', 'City',
            'OS Name and Version', 'Browser Name and Version', 'Device Type'
        ]
        self.numerical_cols = [
            'ASN', 'Login Timestamp', 'Login Successful'
        ]

    # ---- 추론 경로 최적화: 범주 -> 인덱스 딕셔너리를 한 번만 만들어 재사용 ----
    # sklearn OrdinalEncoder.transform은 호출마다 범주 전체(약 4.3만 개)로 매핑을 다시 만들어
    # 행이 1개여도 요청당 약 56ms가 걸렸다. 결과는 동일하다(2,000건 동등성 검증).
    def _ensure_fast_path(self):
        # pickle로 복원된 객체는 __init__이 호출되지 않으므로 처음 쓸 때 지연 초기화
        if getattr(self, "_cat_maps", None) is None:
            self._cat_maps = [
                {c: i for i, c in enumerate(cats)}
                for cats in self.cat_encoder.categories_
            ]
            self._unknown = self.cat_encoder.unknown_value
            self._feature_cols = self.categorical_cols + [
                'hour', 'day_of_week', 'ASN', 'Login Successful'
            ]

    def __getstate__(self):
        # 캐시는 저장 파일에 넣지 않는다(재학습 후 오래된 매핑이 남는 것 방지)
        state = self.__dict__.copy()
        for k in ("_cat_maps", "_unknown", "_feature_cols"):
            state.pop(k, None)
        return state

    def process_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        datetime_col = pd.to_datetime(df['Login Timestamp'], errors='coerce')

        df['hour'] = datetime_col.dt.hour.fillna(-1)
        df['day_of_week'] = datetime_col.dt.dayofweek.fillna(-1)
        return df

    def fit_transform(self, raw_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = raw_data.copy()
        df[self.categorical_cols] = df[self.categorical_cols].fillna('unknown')
        df['Login Successful'] = df['Login Successful'].astype(int)

        df = self.process_time_features(df)
        y_target = df[['Is Attack IP', 'Is Account Takeover']].copy()

        df[self.categorical_cols] = self.cat_encoder.fit_transform(df[self.categorical_cols].astype(str))
        feature_cols = self.categorical_cols + ['hour', 'day_of_week', 'ASN', 'Login Successful']
        x_data = df[feature_cols].copy()

        x_data[feature_cols] = self.scaler.fit_transform(x_data[feature_cols])

        self._cat_maps = None  # 재학습으로 범주가 바뀌었으니 캐시 무효화
        return x_data, y_target

    def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        self._ensure_fast_path()
        df = raw_data.copy()
        cat = df[self.categorical_cols].fillna('unknown').astype(str)
        df['Login Successful'] = df['Login Successful'].astype(int)
        df = self.process_time_features(df)

        cats = np.empty((len(df), len(self.categorical_cols)))
        for j, col in enumerate(self.categorical_cols):
            m = self._cat_maps[j]
            cats[:, j] = [m.get(v, self._unknown) for v in cat[col]]
        rest = df[['hour', 'day_of_week', 'ASN', 'Login Successful']].to_numpy(dtype=float)

        x = (np.hstack([cats, rest]) - self.scaler.mean_) / self.scaler.scale_
        return pd.DataFrame(x, columns=self._feature_cols)
