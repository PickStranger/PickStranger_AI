import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from xgboost import XGBClassifier
from sklearn.metrics import confusion_matrix

def plot_results():
    print("Loading data and model...")

    data_path = "../../data/rba-dataset/rba-dataset.csv"
    preprocessor_path = "../../models/preprocessor_v1.pkl"
    model_path = "../../models/xgboost_v1.json"

    raw_data = pd.read_csv(data_path)

    split_index = int(len(raw_data) * 0.8)
    test_raw = raw_data.iloc[split_index:].copy()

    preprocessor = joblib.load(preprocessor_path)
    y_test = test_raw['Is Attack IP'].astype(int) if 'Is Attack IP' in test_raw.columns else test_raw.iloc[:, 0].astype(int)
    x_test = preprocessor.transform(test_raw)

    model = XGBClassifier()
    model.load_model(model_path)

    print("Running inference...")
    probs = model.predict_proba(x_test)[:, 1]
    preds = (probs >= 0.5).astype(int)

    plt.figure(figsize=(8, 6))
    cm = confusion_matrix(y_test, preds)
    group_names = ['TN', 'FP', 'FN', 'TP']
    group_counts = ["{0:,.0f}".format(value) for value in cm.flatten()]
    group_percentages = ["{0:.2%}".format(value) for value in cm.flatten() / np.sum(cm)]
    labels = [f"{v1}\n\n{v2}\n({v3})" for v1, v2, v3 in zip(group_names, group_counts, group_percentages)]
    labels = np.asarray(labels).reshape(2, 2)

    sns.heatmap(cm, annot=labels, fmt='', cmap='Blues', annot_kws={"size": 12},
                xticklabels=['Pred: 0', 'Pred: 1'], yticklabels=['Actual: 0', 'Actual: 1'])
    plt.title('Confusion Matrix')
    plt.show(block=False)

    plt.figure(figsize=(10, 6))
    sns.kdeplot(probs[y_test == 0], fill=True, color="green", label="Actual Normal (0)", bw_adjust=1.5)
    sns.kdeplot(probs[y_test == 1], fill=True, color="red", label="Actual Attack (1)", bw_adjust=1.5)
    plt.axvline(x=0.5, color='black', linestyle='--', label='Threshold 0.5')
    plt.xlabel('Probability')
    plt.ylabel('Probability Density')
    plt.title('Probability Density Plot')
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.show(block=False)

    plt.figure(figsize=(10, 6))
    sns.histplot(probs[y_test == 0], color="green", label="Actual Normal (0)", bins=50, alpha=0.5, kde=False)
    sns.histplot(probs[y_test == 1], color="red", label="Actual Attack (1)", bins=50, alpha=0.5, kde=False)
    plt.axvline(x=0.5, color='black', linestyle='--', label='Threshold 0.5')
    plt.xlabel('Probability')
    plt.ylabel('Count')
    plt.title('Probability Histogram')
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.6)

    print("Plots generated.")
    plt.show()

if __name__ == "__main__":
    plot_results()