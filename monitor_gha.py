"""GitHub Actions 用監視スクリプト（状態はファイルで管理）"""
import os
import sys
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
STATE_FILE = "last_comment_id.txt"
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": SESSION_COOKIE,
}


def fetch_latest_comment():
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    comments = soup.select("ul.list--comment li.replies")
    if not comments:
        return None, None
    latest = comments[0]
    txt_el = latest.select_one("p.txt[id^='comment-body-']")
    if not txt_el:
        return None, None
    comment_id = txt_el["id"].replace("comment-body-", "")
    nick_el = latest.select_one("p.nick")
    nick = nick_el.get_text(strip=True) if nick_el else "？"
    text = txt_el.get_text(strip=True)
    return comment_id, f"{nick}：{text}"


def load_last_id():
    if os.path.exists(STATE_FILE):
        return open(STATE_FILE).read().strip()
    return None


def save_id(comment_id):
    with open(STATE_FILE, "w") as f:
        f.write(comment_id)


def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()


# ハートビート（毎日9時の確認通知）
if os.environ.get("HEARTBEAT") == "true":
    send_line("【監視中】ひよりとーく を正常に監視しています。")
    print("ハートビート通知を送信しました")
    sys.exit(0)

comment_id, summary = fetch_latest_comment()
if comment_id is None:
    print("コメント取得失敗（ログイン切れの可能性あり）")
    send_line("【警告】ひよりとーく の取得に失敗しました。\nCookieが期限切れの可能性があります。")
    sys.exit(0)

last_id = load_last_id()

if last_id is None:
    save_id(comment_id)
    print(f"初回実行: ID={comment_id} を保存")
elif int(comment_id) > int(last_id):
    save_id(comment_id)
    msg = f"【新着】ひよりとーく が更新されました！\n\n{summary}\n\n{TARGET_URL}"
    send_line(msg)
    print(f"新着検知 (ID:{comment_id}) → LINE送信完了")
else:
    print(f"変化なし (最新ID:{comment_id})")
