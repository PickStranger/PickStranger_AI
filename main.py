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
    print("[*] 데이터 전처리 진행 중...")
    preprocessor = RBAPreprocessor()
    # 학습(fit)과 변환(transform)을 동시에 진행
    x_train, y_target = preprocessor.fit_transform(raw_data)

    # 4. AI 모델 학습
    # 데이터가 적은 테스트 상황이므로 contamination(이상치 비율)을 20%로 임시 설정
    detector = RBADetector()
    # K-Fold 검증 실행 (10-Fold)
    detector.evaluate_with_kfold(x_train, y_target, k=5)

    # 검증이 끝난 후, 실서비스 배포용으로 전체 데이터를 다 넣고 최종 학습
    detector.train(x_train, y_target)

    # 5. 가중치 파일 저장 (실무 핵심!)
    # 모델 가중치 저장
    detector.save_model("models/xgboost_v1.pkl")

    # ⚠️ 매우 중요: 전처리기(Scaler, Encoder)도 함께 저장해야 합니다.
    # 그래야 나중에 들어오는 새로운 로그도 똑같은 기준으로 수치화할 수 있습니다.
    joblib.dump(preprocessor, "models/preprocessor_v1.pkl")
    print("[*] 전처리기 가중치 파일 저장 완료: models/preprocessor_v1.pkl")

    print("pipeline finished")


if __name__ == "__main__":
    main()