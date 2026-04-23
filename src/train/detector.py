import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

class RBADetector:
    def __init__(self, params=None, random_state=42):
        self.params = {
            'n_estimators': 100,
            'tree_method': 'hist',
            'device': 'cuda',
            'scale_pos_weight': 9,
            'eval_metric': 'logloss'
        }

        if params:
            self.params.update(params)

        self.random_state = random_state
        self.model = XGBClassifier(random_state=self.random_state, **self.params)
        self.is_trained = False

    def train(self, x_data: pd.DataFrame, y_true: pd.DataFrame):
        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(int)

        print(f"Starting final training... (Samples: {len(x_data):,})")
        self.model.fit(x_data, y_labels)
        self.is_trained = True
        print("Training finished.")

    def evaluate_with_kfold(self, x_data: pd.DataFrame, y_true: pd.DataFrame, k: int = 5):
        print(f"\nStarting {k}-Fold Time Series Cross Validation (on 80% Train Data)")

        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(int)
        tscv = TimeSeriesSplit(n_splits=k)

        f1_scores = []
        roc_auc_scores = []

        x_array = x_data.values
        y_array = y_labels.values

        for fold, (train_idx, val_idx) in enumerate(tscv.split(x_array), 1):
            x_train_fold, y_train_fold = x_array[train_idx], y_array[train_idx]
            x_val_fold, y_val_fold = x_array[val_idx], y_array[val_idx]

            fold_model = XGBClassifier(random_state=self.random_state, **self.params)
            fold_model.fit(x_train_fold, y_train_fold)

            fold_preds = fold_model.predict(x_val_fold)
            fold_probs = fold_model.predict_proba(x_val_fold)[:, 1]

            f1 = f1_score(y_val_fold, fold_preds, zero_division=0)
            roc_auc = roc_auc_score(y_val_fold, fold_probs)

            f1_scores.append(f1)
            roc_auc_scores.append(roc_auc)

            print(f"  - Fold {fold}/{k} | F1: {f1:.4f} | ROC-AUC: {roc_auc:.4f}")

        print("\n" + "-" * 50)
        print(f"[{k}-Fold CV Results] Mean F1: {np.mean(f1_scores):.4f} | Mean ROC-AUC: {np.mean(roc_auc_scores):.4f}")
        print("-" * 50)

        return np.mean(f1_scores)

    def evaluate_test_set(self, x_test: pd.DataFrame, y_true: pd.DataFrame):
        if not self.is_trained:
            raise ValueError("Error: Model has not been trained yet.")

        print("\n" + "=" * 50)
        print("[FINAL TEST] Evaluating on Unseen 20% Test Data")
        print("=" * 50)

        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(int)

        preds = self.model.predict(x_test)
        probs = self.model.predict_proba(x_test)[:, 1]

        f1 = f1_score(y_labels, preds, zero_division=0)
        roc_auc = roc_auc_score(y_labels, probs)

        print(f"Final Test F1-Score : {f1:.4f}")
        print(f"Final Test ROC-AUC  : {roc_auc:.4f}")

        cm = confusion_matrix(y_labels, preds)
        print("\n[Confusion Matrix]")
        print(f"True Normal : {cm[0][0]:,} | False Alarm : {cm[0][1]:,}")
        print(f"Miss Attack : {cm[1][0]:,} | True Attack : {cm[1][1]:,}")
        print("=" * 50 + "\n")

    def predict(self, x_data: pd.DataFrame) -> list[dict]:
        if not self.is_trained:
            raise ValueError("Error: Model has not been trained yet.")

        predictions = self.model.predict(x_data)
        probabilities = self.model.predict_proba(x_data)[:, 1]

        results = []
        for pred, prob in zip(predictions, probabilities):
            risk_score = round(prob * 100, 2)
            results.append({
                "is_anomaly": bool(pred == 1),
                "risk_score": risk_score
            })
        return results

    def save_model(self, file_path: str):
        if not self.is_trained:
            raise ValueError("Error: No model to save.")
        if file_path.endswith('.pkl'):
            file_path = file_path.replace('.pkl', '.json')

        self.model.save_model(file_path)
        print(f"Model saved to: {file_path}")

    def load_model(self, file_path: str):
        if file_path.endswith('.pkl'):
            file_path = file_path.replace('.pkl', '.json')

        self.model = XGBClassifier()
        self.model.load_model(file_path)
        self.is_trained = True
        print(f"Model loaded from: {file_path}")