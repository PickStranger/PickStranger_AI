import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, roc_auc_score


class RBADetector:
    def __init__(self, random_state=42):
        """
        Random Forest 기반 로그인 이상탐지 엔진 (지도 학습)
        """
        # class_weight='balanced': 해킹 데이터(10%)가 적어도 무시하지 않고 가중치를 두어 균형을 맞춥니다.
        self.model = RandomForestClassifier(
            n_estimators=100,
            random_state=random_state,
            n_jobs=-1,
            class_weight='balanced'
        )
        self.is_trained = False

    def train(self, x_data: pd.DataFrame, y_true: pd.DataFrame):
        """
        [변경점] 지도 학습이므로 문제(x_data)와 정답지(y_true)를 같이 넣어줍니다.
        """
        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(
            int)

        print(f"[*] AI 모델 학습 시작... (입력 데이터 수: {len(x_data)}건)")
        self.model.fit(x_data, y_labels)
        self.is_trained = True
        print("[*] AI 모델 학습 완료!")

    def evaluate_with_kfold(self, x_data: pd.DataFrame, y_true: pd.DataFrame, k: int = 10):
        print(f"\n[*] {k}-Fold 교차 검증을 시작합니다. (Random Forest)")

        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(
            int)
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)

        f1_scores = []
        roc_auc_scores = []

        x_array = x_data.values
        y_array = y_labels.values

        for fold, (train_idx, val_idx) in enumerate(skf.split(x_array, y_array), 1):
            x_train_fold, y_train_fold = x_array[train_idx], y_array[train_idx]
            x_val_fold, y_val_fold = x_array[val_idx], y_array[val_idx]

            # 1. Fold별 모델 생성 및 학습 (문제와 정답을 모두 줍니다)
            fold_model = RandomForestClassifier(
                n_estimators=100,
                random_state=42,
                n_jobs=-1,
                class_weight='balanced'
            )
            fold_model.fit(x_train_fold, y_train_fold)

            # 2. Fold별 검증 데이터 추론
            fold_preds = fold_model.predict(x_val_fold)
            # predict_proba는 각 클래스일 확률을 반환합니다. [:, 1]은 '해킹(1)일 확률'만 가져옵니다.
            fold_probs = fold_model.predict_proba(x_val_fold)[:, 1]

            # 3. 평가 지표 계산
            f1 = f1_score(y_val_fold, fold_preds, zero_division=0)
            roc_auc = roc_auc_score(y_val_fold, fold_probs)

            f1_scores.append(f1)
            roc_auc_scores.append(roc_auc)

            print(f"  - Fold {fold}/{k} | F1-Score: {f1:.4f} | ROC-AUC: {roc_auc:.4f}")

        print("\n" + "=" * 50)
        print(f"🏆 {k}-Fold 교차 검증 최종 결과 (평균)")
        print("=" * 50)
        print(f"- 평균 F1-Score : {np.mean(f1_scores):.4f} (±{np.std(f1_scores):.4f})")
        print(f"- 평균 ROC-AUC  : {np.mean(roc_auc_scores):.4f} (±{np.std(roc_auc_scores):.4f})")
        print("=" * 50)

    def predict(self, x_data: pd.DataFrame) -> list[dict]:
        if not self.is_trained:
            raise ValueError("에러: 모델이 학습되지 않았습니다.")

        # 0(정상) 또는 1(해킹) 예측
        predictions = self.model.predict(x_data)
        # 해킹일 확률 (0.0 ~ 1.0)
        probabilities = self.model.predict_proba(x_data)[:, 1]

        results = []
        for pred, prob in zip(predictions, probabilities):
            # 확률을 0~100점의 위험 점수로 직관적으로 변환
            risk_score = round(prob * 100, 2)

            results.append({
                "is_anomaly": bool(pred == 1),
                "risk_score": risk_score
            })
        return results

    def save_model(self, file_path: str):
        if not self.is_trained:
            raise ValueError("에러: 저장할 모델이 없습니다.")
        joblib.dump(self.model, file_path)
        print(f"[*] 모델 가중치 파일 저장 완료: {file_path}")

    def load_model(self, file_path: str):
        self.model = joblib.load(file_path)
        self.is_trained = True
        print(f"[*] 모델 가중치 파일 로드 완료: {file_path}")