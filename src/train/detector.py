import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

class RBADetector:
    def __init__(self, random_state=42):
        self.model = XGBClassifier(
            n_estimators=100,
            random_state=random_state,
            tree_method='hist',
            device='cuda',
            scale_pos_weight=9,
            eval_metric='logloss'
        )
        self.is_trained = False

    def train(self, x_data: pd.DataFrame, y_true: pd.DataFrame):
        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(int)

        print(f"Starting training... (Samples: {len(x_data):,})")
        self.model.fit(x_data, y_labels)
        self.is_trained = True
        print("Training finished.")

    def evaluate_with_kfold(self, x_data: pd.DataFrame, y_true: pd.DataFrame, k: int = 5):
        print(f"\nStarting {k}-Fold cross validation")

        y_labels = y_true['Is Attack IP'].astype(int) if 'Is Attack IP' in y_true.columns else y_true.iloc[:, 0].astype(int)
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)

        f1_scores = []
        roc_auc_scores = []

        x_array = x_data.values
        y_array = y_labels.values

        for fold, (train_idx, val_idx) in enumerate(skf.split(x_array, y_array), 1):
            x_train_fold, y_train_fold = x_array[train_idx], y_array[train_idx]
            x_val_fold, y_val_fold = x_array[val_idx], y_array[val_idx]

            fold_model = XGBClassifier(
                n_estimators=100,
                random_state=42,
                tree_method='hist',
                device='cuda',
                scale_pos_weight=9,
                eval_metric='logloss'
            )
            fold_model.fit(x_train_fold, y_train_fold)

            fold_preds = fold_model.predict(x_val_fold)
            fold_probs = fold_model.predict_proba(x_val_fold)[:, 1]

            f1 = f1_score(y_val_fold, fold_preds, zero_division=0)
            roc_auc = roc_auc_score(y_val_fold, fold_probs)

            f1_scores.append(f1)
            roc_auc_scores.append(roc_auc)

            print(f"  - Fold {fold}/{k} | F1: {f1:.4f} | ROC-AUC: {roc_auc:.4f}")

        print("\n" + "=" * 50)
        print(f"{k}-Fold Final Results (Average)")
        print("=" * 50)
        print(f"- Mean F1-Score : {np.mean(f1_scores):.4f} (±{np.std(f1_scores):.4f})")
        print(f"- Mean ROC-AUC  : {np.mean(roc_auc_scores):.4f} (±{np.std(roc_auc_scores):.4f})")
        print("=" * 50)

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