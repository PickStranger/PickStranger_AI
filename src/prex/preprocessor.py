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

        return x_data, y_target

    def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        df = raw_data.copy()

        df[self.categorical_cols] = df[self.categorical_cols].fillna('unknown')
        df['Login Successful'] = df['Login Successful'].astype(int)

        df = self.process_time_features(df)

        df[self.categorical_cols] = self.cat_encoder.transform(df[self.categorical_cols].astype(str))

        feature_cols = self.categorical_cols + ['hour', 'day_of_week', 'ASN', 'Login Successful']
        x_data = df[feature_cols].copy()

        x_data[feature_cols] = self.scaler.transform(x_data[feature_cols])

        return x_data