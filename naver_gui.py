#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 키워드 분석기 (GUI)

창에서 API 키와 키워드를 입력하면 다음을 보여줍니다.
  - 월간 검색량 (PC / 모바일 / PC+모바일)   → 네이버 '검색광고 API' 필요
  - 월간 콘텐츠 발행량 (블로그)             → 네이버 '검색 API' 필요

필요한 키 2세트
  1) 검색 API (developers.naver.com, '검색' 사용 체크)
       - Client ID
       - Client Secret
  2) 검색광고 API (searchad.naver.com → 도구 → API 사용관리)
       - API Key (액세스 라이선스)
       - Secret Key (비밀키)
       - Customer ID (고객 ID)

실행:  python naver_gui.py
(추가 설치 불필요 — 표준 라이브러리 tkinter 사용)
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import tkinter as tk
from tkinter import ttk, messagebox

# ----- 검색 API (블로그 발행량) -----
API_BLOG = "https://openapi.naver.com/v1/search/blog.json"
DISPLAY = 100
MAX_START = 1000

# ----- 검색광고 API (검색량) -----
SEARCHAD_BASE = "https://api.searchad.naver.com"
KEYWORDSTOOL_URI = "/keywordstool"

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naver_config.json")


# =========================================================
# 검색량: 네이버 검색광고 API (키워드도구)
# =========================================================
def _signature(timestamp, method, uri, secret_key):
    msg = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _parse_cnt(v):
    """'< 10' 같은 값 처리. (수치, 표시문자열) 반환."""
    if isinstance(v, (int, float)):
        return int(v), f"{int(v):,}"
    s = str(v).replace(",", "").strip()
    if "<" in s:
        return 10, "10 미만"
    try:
        n = int(s)
        return n, f"{n:,}"
    except ValueError:
        return 0, str(v)


def get_search_volume(keyword, api_key, secret_key, customer_id):
    """월간 검색량 (pc, mobile) 반환. (각각 수치, 표시문자열)"""
    timestamp = str(round(time.time() * 1000))
    sig = _signature(timestamp, "GET", KEYWORDSTOOL_URI, secret_key)
    params = urllib.parse.urlencode({"hintKeywords": keyword.replace(" ", ""), "showDetail": 1})
    url = f"{SEARCHAD_BASE}{KEYWORDSTOOL_URI}?{params}"

    req = urllib.request.Request(url)
    req.add_header("X-Timestamp", timestamp)
    req.add_header("X-API-KEY", api_key)
    req.add_header("X-Customer", str(customer_id))
    req.add_header("X-Signature", sig)

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    kwlist = data.get("keywordList", [])
    target = keyword.replace(" ", "")
    row = next((r for r in kwlist if r.get("relKeyword", "").replace(" ", "") == target), None)
    if row is None and kwlist:
        row = kwlist[0]
    if row is None:
        return (0, "0"), (0, "0")

    pc = _parse_cnt(row.get("monthlyPcQcCnt", 0))
    mo = _parse_cnt(row.get("monthlyMobileQcCnt", 0))
    return pc, mo


# =========================================================
# 발행량: 네이버 검색 API (블로그)
# =========================================================
def _blog_get(query, cid, secret, start):
    params = urllib.parse.urlencode(
        {"query": query, "display": DISPLAY, "start": start, "sort": "date"}
    )
    req = urllib.request.Request(f"{API_BLOG}?{params}")
    req.add_header("X-Naver-Client-Id", cid)
    req.add_header("X-Naver-Client-Secret", secret)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_blog_monthly(query, cid, secret):
    """최근 30일 블로그 발행 글 수. (count, total, capped)"""
    today = dt.date.today()
    start_date = today - dt.timedelta(days=30)
    count, total, capped = 0, None, False
    start = 1
    while start <= MAX_START:
        data = _blog_get(query, cid, secret, start)
        if total is None:
            total = data.get("total", 0)
        items = data.get("items", [])
        if not items:
            break
        stop = False
        for it in items:
            pd = it.get("postdate", "")
            if len(pd) != 8:
                continue
            d = dt.date(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
            if d > today:
                continue
            if d < start_date:
                stop = True
                break
            count += 1
        if stop:
            break
        start += DISPLAY
        if start > MAX_START and len(items) == DISPLAY:
            capped = True
        time.sleep(0.1)
    return count, (total or 0), capped


# =========================================================
# GUI
# =========================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("네이버 키워드 분석기")
        root.geometry("560x640")

        pad = {"padx": 8, "pady": 4}

        # --- 검색 API ---
        f1 = ttk.LabelFrame(root, text="① 검색 API (블로그 발행량)")
        f1.pack(fill="x", **pad)
        self.cid = self._row(f1, "Client ID")
        self.secret = self._row(f1, "Client Secret", show="*")

        # --- 검색광고 API ---
        f2 = ttk.LabelFrame(root, text="② 검색광고 API (검색량 PC/모바일)")
        f2.pack(fill="x", **pad)
        self.ad_key = self._row(f2, "API Key")
        self.ad_secret = self._row(f2, "Secret Key", show="*")
        self.customer = self._row(f2, "Customer ID")

        # --- 키워드 ---
        f3 = ttk.Frame(root)
        f3.pack(fill="x", **pad)
        ttk.Label(f3, text="키워드", width=12).pack(side="left")
        self.keyword = ttk.Entry(f3)
        self.keyword.pack(side="left", fill="x", expand=True)
        self.keyword.bind("<Return>", lambda e: self.run())

        # --- 옵션 ---
        f4 = ttk.Frame(root)
        f4.pack(fill="x", **pad)
        self.save_keys = tk.BooleanVar(value=True)
        ttk.Checkbutton(f4, text="이 PC에 키 저장(평문)", variable=self.save_keys).pack(side="left")
        self.btn = ttk.Button(f4, text="조회", command=self.run)
        self.btn.pack(side="right")

        # --- 결과 ---
        self.out = tk.Text(root, height=18, wrap="word", state="disabled")
        self.out.pack(fill="both", expand=True, **pad)

        self._load_config()

    def _row(self, parent, label, show=None):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=6, pady=3)
        ttk.Label(f, text=label, width=14).pack(side="left")
        e = ttk.Entry(f, show=show)
        e.pack(side="left", fill="x", expand=True)
        return e

    def _log(self, text, clear=False):
        self.out.configure(state="normal")
        if clear:
            self.out.delete("1.0", "end")
        self.out.insert("end", text + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")

    # ---- 설정 저장/불러오기 ----
    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
        except Exception:
            return
        self.cid.insert(0, c.get("cid", ""))
        self.secret.insert(0, c.get("secret", ""))
        self.ad_key.insert(0, c.get("ad_key", ""))
        self.ad_secret.insert(0, c.get("ad_secret", ""))
        self.customer.insert(0, c.get("customer", ""))

    def _save_config(self):
        data = {
            "cid": self.cid.get().strip(),
            "secret": self.secret.get().strip(),
            "ad_key": self.ad_key.get().strip(),
            "ad_secret": self.ad_secret.get().strip(),
            "customer": self.customer.get().strip(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- 실행 ----
    def run(self):
        kw = self.keyword.get().strip()
        if not kw:
            messagebox.showwarning("입력 필요", "키워드를 입력하세요.")
            return
        if self.save_keys.get():
            self._save_config()
        self.btn.configure(state="disabled")
        self._log(f"'{kw}' 조회 중...", clear=True)
        threading.Thread(target=self._worker, args=(kw,), daemon=True).start()

    def _worker(self, kw):
        lines = []
        lines.append("=" * 46)
        lines.append(f"키워드: {kw}")
        lines.append("=" * 46)

        # 검색량
        ak, asec, cust = self.ad_key.get().strip(), self.ad_secret.get().strip(), self.customer.get().strip()
        if ak and asec and cust:
            try:
                (pc_n, pc_s), (mo_n, mo_s) = get_search_volume(kw, ak, asec, cust)
                lines.append("[월간 검색량]")
                lines.append(f"  PC        : {pc_s}")
                lines.append(f"  모바일    : {mo_s}")
                lines.append(f"  PC+모바일 : {pc_n + mo_n:,}")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                lines.append(f"[월간 검색량] 오류 HTTP {e.code}: {body[:200]}")
            except Exception as e:
                lines.append(f"[월간 검색량] 오류: {e}")
        else:
            lines.append("[월간 검색량] 검색광고 API 키 미입력 → 건너뜀")

        lines.append("")

        # 발행량
        cid, sec = self.cid.get().strip(), self.secret.get().strip()
        if cid and sec:
            try:
                cnt, total, capped = get_blog_monthly(kw, cid, sec)
                shown = "1000+ (한도초과)" if capped else f"{cnt:,}"
                lines.append("[월간 콘텐츠 발행량] (최근 30일)")
                lines.append(f"  블로그 발행 : {shown} 건")
                lines.append(f"  블로그 누적 : {total:,} 건")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                lines.append(f"[월간 발행량] 오류 HTTP {e.code}: {body[:200]}")
            except Exception as e:
                lines.append(f"[월간 발행량] 오류: {e}")
        else:
            lines.append("[월간 발행량] 검색 API 키 미입력 → 건너뜀")

        lines.append("=" * 46)
        self.root.after(0, self._done, "\n".join(lines))

    def _done(self, text):
        self._log(text, clear=True)
        self.btn.configure(state="normal")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
