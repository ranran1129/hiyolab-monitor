import os
import signal
import sys
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TARGET_URL = "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
STATE_FILE = "last_comment_id.txt"
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": SESSION_COOKIE,
}


def fetch_latest_comment(url: str) -> tuple[str, str] | tuple[None, None]:
    """最新コメントのID（数値）とテキストを返す"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # コメントは id="comment-body-XXXXXX" のpタグ、最後のliが最新
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


def load_last_id() -> str | None:
    if os.path.exists(STATE_FILE):
        return open(STATE_FILE).read().strip()
    return None


def save_id(comment_id: str) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(comment_id)


def send_line(text: str) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()


def handle_stop(sig, frame):
    print("\n停止中...")
    try:
        send_line("【監視停止】ひよりとーく の監視を停止しました。")
        print("停止通知をLINEに送信しました。")
    except Exception as e:
        print(f"停止通知の送信に失敗: {e}")
    sys.exit(0)


def check_once() -> None:
    try:
        comment_id, summary = fetch_latest_comment(TARGET_URL)
        if comment_id is None:
            print("コメントが見つかりませんでした（ログイン切れの可能性あり）")
            return

        last_id = load_last_id()

        if last_id is None:
            save_id(comment_id)
            print(f"初回実行: 最新コメントID={comment_id} を保存")
            return

        if int(comment_id) > int(last_id):
            save_id(comment_id)
            msg = f"【新着】ひよりとーく が更新されました！\n\n{summary}\n\n{TARGET_URL}"
            send_line(msg)
            print(f"新着検知 (ID:{comment_id}) → LINE送信完了")
        else:
            print(f"変化なし (最新ID:{comment_id})")

    except Exception as e:
        print(f"エラー: {e}")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    print("監視開始（1分間隔）。停止するには Ctrl+C を押してください。")
    try:
        send_line("【監視開始】ひよりとーく の監視を開始しました。\n新しいコメントが追加されたらお知らせします。")
        print("開始通知をLINEに送信しました。")
    except Exception as e:
        print(f"開始通知の送信に失敗: {e}")

    while True:
        check_once()
        time.sleep(60)
