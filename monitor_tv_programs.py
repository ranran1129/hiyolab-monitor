import json
import os
from functools import partial
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

STATE_FILE = "tv_program_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

TALENTS = [
    {"key": "hiyori", "name": "濱岸ひより"},
    {"key": "kawada", "name": "河田陽菜"},
]


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


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_bangumi(name: str) -> dict[str, str]:
    """番組表.Gガイド（bangumi.org）の検索結果を programId -> 表示テキスト で返す"""
    resp = requests.get(
        "https://bangumi.org/fetch_search_content/",
        params={"q": name, "type": "tv"},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = {}
    for li in soup.select("#tv-content li.block"):
        link = li.select_one("a[href^='/tv_events/']")
        if not link:
            continue
        program_id = link["href"].split("/tv_events/")[1].split("?")[0]
        ps = li.select("p.repletion")
        title = ps[0].get_text(strip=True) if len(ps) > 0 else "?"
        schedule = ps[1].get_text(strip=True) if len(ps) > 1 else "?"
        results[program_id] = f"{title}\n{schedule}"
    return results


def fetch_jcom(name: str) -> dict[str, str]:
    """J:COMテレビ番組ガイドの検索結果を cid -> 表示テキスト で返す"""
    resp = requests.post(
        "https://tvguide.myjcom.jp/api/mypage/get_searchresult/",
        data={"keyword": name, "offset": 0},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    results = {}
    if data.get("status") != "success":
        return results

    for item in data.get("body", {}).get("value", []):
        cid = item["cid"]
        title = item.get("title", "?")
        date = item.get("date", "")
        dow = item.get("day_of_week", "")
        start = item.get("start_time", "")
        channel = item.get("channel_name", "")
        results[cid] = f"{title}\n{date}{dow} {start}　{channel}"
    return results


def check_source(state: dict, state_key: str, fetch_fn, name: str, source_label: str, link: str) -> None:
    error_flags = state.setdefault("_error_flags", {})

    try:
        current = fetch_fn()
    except Exception as e:
        print(f"[{state_key}] 取得エラー: {e}")
        if not error_flags.get(state_key):
            send_line(
                f"【エラー】{name}（{source_label}）の番組情報取得に失敗しました。\n"
                f"{e}\n\n"
                "復旧するまでこのソースの新着検知は止まっています。"
            )
            error_flags[state_key] = True
        return

    if error_flags.get(state_key):
        error_flags[state_key] = False

    known_ids = state.get(state_key)

    if known_ids is None:
        state[state_key] = list(current.keys())
        print(f"[{state_key}] 初回実行: {len(current)}件を保存")
        return

    known_ids = set(known_ids)
    new_ids = [pid for pid in current if pid not in known_ids]

    if not new_ids:
        print(f"[{state_key}] 変化なし ({len(current)}件)")
    else:
        for pid in new_ids:
            msg = f"【新着番組】{name}（{source_label}）\n\n{current[pid]}\n\n{link}"
            send_line(msg)
            print(f"[{state_key}] 新着通知送信: {pid}")

    state[state_key] = list(current.keys())


def main() -> None:
    state = load_state()

    for talent in TALENTS:
        key = talent["key"]
        name = talent["name"]
        encoded = quote(name)

        check_source(
            state,
            f"{key}_bangumi",
            partial(fetch_bangumi, name),
            name,
            "番組表.Gガイド",
            f"https://bangumi.org/search?q={encoded}&area_code=23",
        )
        check_source(
            state,
            f"{key}_jcom",
            partial(fetch_jcom, name),
            name,
            "J:COMテレビ番組ガイド",
            f"https://tvguide.myjcom.jp/search/event/?keyword={encoded}",
        )

    save_state(state)


if __name__ == "__main__":
    main()
