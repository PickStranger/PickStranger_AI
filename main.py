import os
import joblib
import pandas as pd
from src import RBAPreprocessor, RBADetector


def main():
    print("main start")

    # 1. 가중치 파일을 저장할 폴더 준비
    os.makedirs("models", exist_ok=True)

    # 2. 데이터 로드
    # data 폴더에 rba_dataset.csv가 있으면 읽고, 없으면 테스트용 가짜 데이터를 만듭니다.
    data_path = "./data/rba-dataset/rba-dataset.csv"

    print(f"[*] 데이터셋 로드 중: {data_path}")
    raw_data = pd.read_csv(data_path)

    # 3. 데이터 전처리
    split_index = int(len(raw_data) * 0.8)

    train_raw = raw_data.iloc[:split_index].copy()
    test_raw = raw_data.iloc[split_index:].copy()

    preprocessor = RBAPreprocessor()

    x_train, y_train = preprocessor.fit_transform(train_raw)

    y_test = test_raw[['Is Attack IP', 'Is Account Takeover']].copy()
    x_test = preprocessor.transform(test_raw)

    detector = RBADetector()
    detector.evaluate_with_kfold(x_train, y_train, k=5)

    detector.train(x_train, y_train)

    detector.evaluate_test_set(x_test, y_test)

    detector.save_model("models/xgboost_v1.json")

    # ⚠️ 매우 중요: 전처리기(Scaler, Encoder)도 함께 저장해야 합니다.
    # 그래야 나중에 들어오는 새로운 로그도 똑같은 기준으로 수치화할 수 있습니다.
    joblib.dump(preprocessor, "models/preprocessor_v1.pkl")
    print("[*] 전처리기 가중치 파일 저장 완료: models/preprocessor_v1.pkl")

    print("pipeline finished")


if __name__ == "__main__":
    main()