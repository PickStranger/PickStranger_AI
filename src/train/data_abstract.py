import pandas as pd
import os


def explore_dataset(file_path):
    print(f"[*] '{file_path}' 데이터를 분석합니다...\n")

    if not os.path.exists(file_path):
        print(f"[!] 에러: 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
        return

    df = pd.read_csv(file_path)

    print("=" * 50)
    print(" 1. 데이터 전체 크기 및 뼈대")
    print("=" * 50)
    print(f"- 총 로그인 로그 수 (행): {df.shape[0]:,} 개")
    print(f"- 수집된 특징 수 (열): {df.shape[1]} 개\n")

    print("- 🔍 [중요] 실제 컬럼명 목록 (오타/띄어쓰기 확인용):")
    for col in df.columns:
        print(f"  '{col}'")

    print("\n" + "=" * 50)
    print(" 2. 결측치(비어있는 데이터) 확인")
    print("=" * 50)
    info_df = pd.DataFrame({
        '데이터 타입': df.dtypes,
        '정상 데이터 수': df.notnull().sum(),
        '빈 데이터(Null) 수': df.isnull().sum()
    })
    print(info_df)

    print("\n" + "=" * 50)
    print(" 3. 정답지(Target) 분포 확인 (정상 vs 비정상)")
    print("=" * 50)

    attack_col = [c for c in df.columns if 'Attack' in c or 'attack' in c]
    if attack_col:
        col_name = attack_col[0]
        print(f"[{col_name} 비율]")
        print(round(df[col_name].value_counts(normalize=True) * 100, 2).astype(str) + ' %')
    else:
        print("[!] Attack 관련 컬럼을 찾을 수 없습니다.")

    print("\n" + "=" * 50)
    print(" 4. 데이터 미리보기 (상위 3줄)")
    print("=" * 50)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df.head(3))



dataset_path = "../../data/rba-dataset/rba-dataset.csv"
explore_dataset(dataset_path)