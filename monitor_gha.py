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


def fetch_artist_comments() -> list[tuple[str, str, str]]:
    """アーティストのコメント一覧を (id, nick, text) で返す（新しい順）"""
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for li in soup.select("ul.list--comment li.replies"):
        txt_el = li.select_one("p.txt[id^='comment-body-']")
        if not txt_el:
            continue
        comment_id = txt_el["id"].replace("comment-body-", "")
        nick_el = li.select_one("p.nick")
        nick = nick_el.get_text(strip=True) if nick_el else "？"
        text = txt_el.get_text(strip=True)
        results.append((comment_id, nick, text))
    return results


def load_last_id() -> str | None:
    if os.path.exists(STATE_FILE):
        val = open(STATE_FILE).read().strip()
        return val if val else None
    return None


def save_id(comment_id: str) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(comment_id)


def send_line(text: str) -> None:
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


# コメント取得
comments = fetch_artist_comments()
if not comments:
    print("コメント取得失敗（ログイン切れの可能性あり）")
    send_line(
        "【警告】ひよりとーく の取得に失敗しました。\n"
        "Cookieが期限切れの可能性があります。\n\n"
        "iPhoneから更新する場合：\n"
        "GitHub → hiyolab-monitor → Actions → Cookie更新 → Run workflow"
    )
    sys.exit(1)

last_id = load_last_id()
latest_id = comments[0][0]  # 最新のID

# 初回実行
if last_id is None:
    save_id(latest_id)
    print(f"初回実行: ID={latest_id} を保存")
    sys.exit(0)

# last_id より新しいコメントを古い順に並べる
new_comments = [c for c in comments if int(c[0]) > int(last_id)]
new_comments.sort(key=lambda c: int(c[0]))  # 古い順に並べ替え

if not new_comments:
    print(f"変化なし (最新ID:{latest_id})")
    sys.exit(0)

# 新しいコメントを1件ずつ通知
for comment_id, nick, text in new_comments:
    msg = f"【新着】ひよりとーく\n\n{nick}：{text}\n\n{TARGET_URL}"
    send_line(msg)
    print(f"新着通知送信: ID={comment_id} / {nick}：{text[:30]}")

# 最新IDを保存
save_id(latest_id)
print(f"ID更新: {last_id} → {latest_id}")
