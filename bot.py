# -*- coding: utf-8 -*-
"""Bot node botnet: xác định IP công outbound, ghi ips.log, commit, báo Telegram."""
import base64
import datetime
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, Optional


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    """GET JSON từ URL, trả về object đã parse."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", "replace")
        return json.loads(body) if body else {}


def http_post(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> int:
    """POST JSON, trả về HTTP status code."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def main() -> None:
    """Chạy 1 chu kỳ bot node: in IP + ghi log + commit + báo Telegram."""
    # Bước 1: lấy IP công outbound của runner
    ip = urllib.request.urlopen("https://api.ipify.org", timeout=30).read().decode().strip()
    info: Dict[str, str] = {}
    try:
        info = http_get_json("https://ipinfo.io/" + ip + "/json")
    except Exception as e:  # geo thất bại không làm hỏng bot
        print("WARN: không lấy được geo:", e)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    org = info.get("org", "?")
    place = f"{info.get('city', '?')}, {info.get('country', '?')}"
    line = f"{stamp} | {ip} | {org} | {place}\n"
    print("NODE_IP:", line.strip())

    # Bước 2: append vào ips.log (giữ tối đa ~5KB)
    old = ""
    try:
        with open("ips.log", encoding="utf-8") as f:
            old = f.read()
    except FileNotFoundError:
        pass
    content = (old + line)[-5000:]

    # Bước 3: commit ips.log về repo bằng Contents API (token do workflow cấp)
    token = os.environ.get("GH_PUSH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if token and repo:
        try:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "botnet-node"}
            sha: Optional[str] = None
            try:
                cur = http_get_json(f"https://api.github.com/repos/{repo}/contents/ips.log?ref=main", headers)
                sha = cur.get("sha")
            except urllib.error.HTTPError:
                pass  # file chưa tồn tại, PUT sẽ tạo mới
            payload: Dict[str, Any] = {
                "message": f"node: {ip}",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": "main",
            }
            if sha:
                payload["sha"] = sha
            status = http_post(f"https://api.github.com/repos/{repo}/contents/ips.log", payload, headers)
            print("COMMIT_IPS_LOG:", status)
        except Exception as e:
            print("WARN: commit ips.log lỗi:", e)

    # Bước 4: gửi IP về Telegram cho Sếp
    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg and chat:
        try:
            msg = (
                f"\U0001F916 BOTNET NODE [{repo.split('/')[-1]}]\n"
                f"IP cong: {ip}\nOrg: {org}\nVi tri: {place}\n{stamp}"
            )
            status = http_post(
                f"https://api.telegram.org/bot{tg}/sendMessage",
                {"chat_id": chat, "text": msg},
            )
            print("TELEGRAM:", status)
        except Exception as e:
            print("WARN: telegram loi:", e)


if __name__ == "__main__":
    main()
