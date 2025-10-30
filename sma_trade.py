import yfinance as yf
import pandas as pd
import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime

# --- 환경 변수 로드 (GitHub Secrets에서 가져옴) ---
EMAIL_SENDER = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_TO_1") # 수동 실행 시 빈 문자열("")이 됨

# --- 기본 설정 ---
Ticker = "QLD"
my_strategy = {
    # 정배열 (강세)
    "SMA5 > EMA20 > SMA180": .7,
    "EMA20 > SMA5 > SMA180": 1,
    # 혼조세 (180일선이 중간)
    "SMA5 > SMA180 > EMA20": 0.4,
    "EMA20 > SMA180 > SMA5": 0,
    # 역배열 (약세)
    "SMA180 > SMA5 > EMA20": 0.4,
    "SMA180 > EMA20 > SMA5": 0.1
}

# --- 헬퍼 함수 1: SMA 상태 계산 ---
def get_sma_state(row):
    if pd.isna(row['SMA5']) or pd.isna(row['EMA20']) or pd.isna(row['SMA180']):
        return None
    smas = {
        'SMA5': row['SMA5'],
        'EMA20': row['EMA20'],
        'SMA180': row['SMA180']
    }
    sorted_state = tuple(k for k, v in sorted(smas.items(), key=lambda item: item[1], reverse=True))
    return sorted_state

# --- 헬퍼 함수 2: 현재 상태만 가져오기 ---
def get_current_recommendation(ticker, strategy_map_config):
    print(f"[{ticker}] 최신 데이터 다운로드 중...")
    # SMA180 계산을 위해 1년치 데이터를 여유있게 가져옴
    data = yf.download(ticker, period="1y", auto_adjust=True, progress=False)
    
    if data.empty:
        print("데이터 다운로드 실패")
        return "데이터 다운로드 실패", 0.0, datetime.now().strftime('%Y-%m-%d')

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

    data['SMA5'] = data['Close'].rolling(5).mean()
    data['EMA20'] = data['Close'].ewm(com=20, adjust=False).mean()
    data['SMA180'] = data['Close'].rolling(180).mean()

    last_valid_row = data.dropna().iloc[-1]
    last_date = last_valid_row.name.strftime('%Y-%m-%d')
    current_state = get_sma_state(last_valid_row)

    if current_state is None:
        print("SMA 계산 불가 (데이터 부족)")
        return "SMA 계산 불가 (데이터 부족)", 0.0, last_date

    strategy_map = {}
    for k_str, allocation in strategy_map_config.items():
        key_tuple = tuple(k_str.split(' > '))
        strategy_map[key_tuple] = allocation

    current_state_str = ' > '.join(current_state)
    current_alloc = strategy_map.get(current_state, 0.0) 

    return current_state_str, current_alloc, last_date


# --- 헬퍼 함수 3: 이메일 전송 (수정됨) ---
def send_email(subject, body, sender, password, receiver):
    
    # [수정 1] 수신자(receiver)가 비어있는지(None 또는 "") 먼저 확인
    if not receiver: 
        print("\n[이메일] 수신자(EMAIL_TO_1)가 지정되지 않았습니다 (수동 실행).")
        print("콘솔 로그만 출력하고 이메일 발송은 건너뜁니다.")
        return # 함수 종료
        
    # [수정 2] 수신자가 있을 경우에만 발신자 정보 확인
    if not all([sender, password]):
        print("\n[이메일] 발신자 정보(EMAIL_ADDRESS, EMAIL_PASSWORD)가 없습니다.")
        return # 함수 종료

    print(f"\n[이메일 전송] {receiver}(으)로 알림 발송 시도...")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.set_content(body) 

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("[이메일 전송] 성공!")
    except Exception as e:
        print(f"[이메일 전송] 실패: {e}")


# --- 메인 로직 (변경 없음) ---
if __name__ == "__main__":
    
    # 1. 현재 상태 및 비중 가져오기
    current_state_str, current_alloc, last_date = get_current_recommendation(Ticker, my_strategy)

    # 2. 이메일 제목 및 본문 생성
    email_subject = f"주간 {Ticker} 리밸런싱 알림 ({last_date})"
    
    email_body = f"""
안녕하세요,

{last_date} 기준 {Ticker}의 현재 상태 및 권장 비중입니다.

■ 현재 SMA 상태
-> {current_state_str}

■ 권장 비중 (전략 기준)
-> {current_alloc * 100:.0f}%

---
[참고: 전체 전략 맵]
"""
    #for state_str, alloc in my_strategy.items():
    #    email_body += f"- {state_str:<25}: {alloc * 100:.0f}%\n"

    # (GitHub Actions 로그 확인을 위해 콘솔에는 항상 출력)
    print("--- 분석 결과 (콘솔 로그) ---")
    print(email_body.strip())
    print("-" * 25)

    # 3. 이메일 전송 실행
    # (EMAIL_RECEIVER가 비어있으면 send_email 함수 내부에서 알아서 중단됨)
    send_email(
        subject=email_subject,
        body=email_body.strip(),
        sender=EMAIL_SENDER,
        password=EMAIL_PASSWORD,
        receiver=EMAIL_RECEIVER
    )
