import pandas as pd


def show_statistics(file_path):
    print(f"[*] '{file_path}' 데이터 통계 분석을 시작합니다... (10만 건 샘플링)\n")
    # 메모리 보호를 위해 10만 개만 샘플링하여 로드
    df = pd.read_csv(file_path, nrows=100000)

    print("=" * 50)
    print(" 1. 수치형 데이터 기초 통계 (Numerical Stats)")
    print("=" * 50)
    # describe()를 통해 개수, 평균, 표준편차, 최솟값, 최댓값 등을 확인합니다.
    num_cols = ['ASN']  # 주요 수치형 데이터
    existing_num_cols = [col for col in num_cols if col in df.columns]
    if existing_num_cols:
        print(df[existing_num_cols].describe().round(2))
    else:
        print("수치형 데이터 컬럼을 찾을 수 없습니다.")

    print("\n" + "=" * 50)
    print(" 2. 범주형 데이터 TOP 5 (Categorical Stats)")
    print("=" * 50)
    # 각 문자열 특징에서 가장 많이 등장하는 상위 5개 항목을 뽑습니다.
    cat_cols = ['Country', 'Device Type', 'OS Name and Version', 'Browser Name and Version']
    for col in cat_cols:
        if col in df.columns:
            print(f"\n📌 [ {col} TOP 5 ]")
            # 전체 대비 비율(%)과 함께 출력
            counts = df[col].value_counts().head(5)
            ratios = df[col].value_counts(normalize=True).head(5) * 100

            stat_df = pd.DataFrame({'건수': counts, '비율(%)': ratios.round(2)})
            print(stat_df)

    print("\n" + "=" * 50)
    print(" 3. 시간대별 접속 통계 (Hourly Login Stats)")
    print("=" * 50)
    if 'Login Timestamp' in df.columns:
        # 시간대(Hour) 추출
        df['Login Timestamp'] = pd.to_datetime(df['Login Timestamp'], errors='coerce')
        df['Hour'] = df['Login Timestamp'].dt.hour

        # 새벽 시간대(0시~5시) 접속 비중 계산
        dawn_logins = df[df['Hour'].isin([0, 1, 2, 3, 4, 5])].shape[0]
        dawn_ratio = (dawn_logins / len(df)) * 100
        print(f"- 새벽 시간대(0시~5시) 접속 건수: {dawn_logins:,}건 ({dawn_ratio:.2f}%)")
        print("- 시간대별 접속량 요약 (0~23시):")
        print(df['Hour'].value_counts().sort_index().to_dict())

    print("\n" + "=" * 50)
    print(" 4. 핵심 지표 비율 (KPIs)")
    print("=" * 50)
    if 'Login Successful' in df.columns:
        success_rate = df['Login Successful'].mean() * 100
        print(f"✅ 로그인 성공률: {success_rate:.2f}%")

    if 'Is Attack IP' in df.columns:
        attack_rate = df['Is Attack IP'].mean() * 100
        print(f"🚨 공격/비정상 접속(Attack IP) 비율: {attack_rate:.2f}%")

dataset_path = "../../data/rba-dataset/rba-dataset.csv"
show_statistics(dataset_path)