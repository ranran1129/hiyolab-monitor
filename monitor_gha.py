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
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    resp.raise_for_status()


# 通常監視
comment_id, summary = fetch_latest_comment()
if comment_id is None:
    print("コメント取得失敗（ログイン切れの可能性あり）")
    send_line(
        "【警告】ひよりとーく の取得に失敗しました。\n"
        "Cookieが期限切れの可能性があります。\n\n"
        "iPhoneから更新する場合：\n"
        "GitHub → hiyolab-monitor → Actions → Cookie更新 → Run workflow"
    )
    sys.exit(1)

last_id = load_last_id()

if last_id is None:
    save_id(comment_id)
    print(f"初回実行: ID={comment_id} を保存")
elif int(comment_id) > int(last_id):
    save_id(comment_id)
    send_line(f"【新着】ひよりとーく が更新されました！\n\n{summary}\n\n{TARGET_URL}")
    print(f"新着検知 (ID:{comment_id}) → LINE送信完了")
else:
    print(f"変化なし (最新ID:{comment_id})")
