# -*- coding: utf-8 -*-
"""텔레그램 발송.

토큰/chat id 는 secret_config.py (로컬) 또는 환경변수 (클라우드)에서 읽는다.
텔레그램 메시지 한도(4096자)를 넘으면 줄 단위로 자동 분할한다.
"""
import os, sys, time
import requests

TG_LIMIT = 3800   # 안전 마진


def _creds():
    try:
        import secret_config as s
        token, chat = s.TELEGRAM_TOKEN, str(s.TELEGRAM_CHAT_ID)
    except Exception:
        token = os.environ.get("TELEGRAM_TOKEN")
        chat = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat


def _chunks(text, size=TG_LIMIT):
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > size and buf:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf.strip():
        yield buf


def send_telegram(text, parse_mode="HTML"):
    token, chat = _creds()
    if not token or not chat:
        raise RuntimeError("텔레그램 토큰/chat id 없음 — secret_config.py 또는 환경변수 설정 필요")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(text):
        r = requests.post(url, data={
            "chat_id": chat, "text": chunk,
            "parse_mode": parse_mode, "disable_web_page_preview": True,
        }, timeout=20)
        if not r.ok:
            raise RuntimeError(f"텔레그램 발송 실패 {r.status_code}: {r.text[:200]}")
        time.sleep(0.4)
    return True


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    msg = sys.argv[1] if len(sys.argv) > 1 else "✅ 텔레그램 연결 테스트 — 주식 추천 봇 작동 중"
    send_telegram(msg)
    print("발송 완료")
