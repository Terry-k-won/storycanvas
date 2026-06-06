#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 검색 API로 특정 키워드의 블로그 + 카페 '월간 발행량'을 조회하는 도구.

필요한 API 키 (네이버 개발자센터에서 애플리케이션 등록 후 '검색' API 사용 설정):
  - NAVER_CLIENT_ID      (X-Naver-Client-Id)
  - NAVER_CLIENT_SECRET  (X-Naver-Client-Secret)

키 입력 방법 (둘 중 하나):
  1) 환경변수로 지정
       export NAVER_CLIENT_ID=발급받은_아이디
       export NAVER_CLIENT_SECRET=발급받은_시크릿
  2) 같은 폴더에 .env 파일 작성 (.env.example 참고)

사용 예:
  python naver_volume.py "강남 맛집"
  python naver_volume.py "강남 맛집" --month 2026-05
  python naver_volume.py "강남 맛집" --keywords-file keywords.txt --csv out.csv

핵심 동작:
  - 블로그: search/blog API는 게시일(postdate)을 제공하므로, 최신순으로 페이지를
    훑으며 대상 월(또는 최근 30일)에 발행된 글 수를 실제로 카운트합니다.
    (API 한계상 최대 1000건까지 조회 가능 → 그 이상이면 '1000+ (한도초과)'로 표시)
  - 카페: search/cafearticle API는 발행일을 제공하지 않아 월간 발행량을 정확히
    셀 수 없습니다. 대신 전체 누적 검색결과(total)를 참고치로 표시합니다.
"""

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API_BLOG = "https://openapi.naver.com/v1/search/blog.json"
API_CAFE = "https://openapi.naver.com/v1/search/cafearticle.json"

DISPLAY = 100          # 한 번에 가져올 결과 수 (최대 100)
MAX_START = 1000       # 네이버 검색 API start 최댓값
REQUEST_PAUSE = 0.1    # 호출 간 간단한 대기 (rate limit 완화)


def load_env_file(path=".env"):
    """간단한 .env 로더 (외부 패키지 불필요)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def get_credentials():
    # 현재 디렉터리와 스크립트 디렉터리 둘 다 시도
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_env_file(".env")
    load_env_file(os.path.join(script_dir, ".env"))
    cid = os.environ.get("NAVER_CLIENT_ID")
    secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit(
            "오류: API 키가 없습니다.\n"
            "  환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 설정하거나\n"
            "  .env 파일(.env.example 참고)을 만들어 주세요."
        )
    return cid, secret


def api_get(url, query, cid, secret, start=1, sort="date"):
    """네이버 검색 API 호출 → 파싱된 dict 반환."""
    params = urllib.parse.urlencode(
        {"query": query, "display": DISPLAY, "start": start, "sort": sort}
    )
    req = urllib.request.Request(f"{url}?{params}")
    req.add_header("X-Naver-Client-Id", cid)
    req.add_header("X-Naver-Client-Secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"API 오류 (HTTP {e.code}): {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"네트워크 오류: {e.reason}")


def month_range(month_str):
    """'YYYY-MM' → (시작일, 끝일) inclusive. None이면 최근 30일."""
    if month_str is None:
        today = dt.date.today()
        return today - dt.timedelta(days=30), today
    year, mon = map(int, month_str.split("-"))
    start = dt.date(year, mon, 1)
    end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
    return start, end - dt.timedelta(days=1)


def count_blog_in_period(query, cid, secret, start_date, end_date):
    """대상 기간 내 블로그 발행 글 수를 최신순 페이징으로 카운트."""
    count = 0
    total = None
    capped = False
    start = 1
    while start <= MAX_START:
        data = api_get(API_BLOG, query, cid, secret, start=start, sort="date")
        if total is None:
            total = data.get("total", 0)
        items = data.get("items", [])
        if not items:
            break
        stop = False
        for it in items:
            pd = it.get("postdate", "")  # yyyyMMdd
            if len(pd) != 8:
                continue
            d = dt.date(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
            if d > end_date:
                continue            # 기간보다 미래 → 건너뜀
            if d < start_date:
                stop = True         # 최신순이므로 이 시점부터 모두 기간 이전
                break
            count += 1
        if stop:
            break
        start += DISPLAY
        if start > MAX_START and len(items) == DISPLAY:
            capped = True
        time.sleep(REQUEST_PAUSE)
    return count, total, capped


def cafe_total(query, cid, secret):
    """카페 누적 검색결과 수(total). (월간 발행일 정보는 API가 제공하지 않음)"""
    data = api_get(API_CAFE, query, cid, secret, start=1, sort="date")
    return data.get("total", 0)


def analyze(query, cid, secret, month_str):
    start_date, end_date = month_range(month_str)
    blog_count, blog_total, capped = count_blog_in_period(
        query, cid, secret, start_date, end_date
    )
    c_total = cafe_total(query, cid, secret)
    return {
        "keyword": query,
        "period": f"{start_date} ~ {end_date}",
        "blog_monthly": ("1000+ (한도초과)" if capped else blog_count),
        "blog_total": blog_total,
        "cafe_total": c_total,
    }


def print_result(r):
    print("=" * 52)
    print(f"키워드        : {r['keyword']}")
    print(f"집계 기간     : {r['period']}")
    print("-" * 52)
    print(f"블로그 월간 발행량 : {r['blog_monthly']} 건")
    print(f"블로그 누적(total) : {r['blog_total']:,} 건")
    print(f"카페 누적(total)   : {r['cafe_total']:,} 건  *발행일 미제공으로 월간 집계 불가")
    print("=" * 52)


def main():
    ap = argparse.ArgumentParser(
        description="네이버 키워드 블로그/카페 월간 발행량 조회"
    )
    ap.add_argument("keyword", nargs="?", help="검색 키워드")
    ap.add_argument("--month", help="대상 월 YYYY-MM (기본: 최근 30일)")
    ap.add_argument("--keywords-file", help="키워드 목록 파일(한 줄에 하나)")
    ap.add_argument("--csv", help="결과를 CSV로 저장할 경로")
    args = ap.parse_args()

    cid, secret = get_credentials()

    keywords = []
    if args.keywords_file:
        with open(args.keywords_file, "r", encoding="utf-8") as f:
            keywords = [ln.strip() for ln in f if ln.strip()]
    elif args.keyword:
        keywords = [args.keyword]
    else:
        ap.error("키워드 또는 --keywords-file 중 하나는 필요합니다.")

    results = []
    for kw in keywords:
        r = analyze(kw, cid, secret, args.month)
        print_result(r)
        results.append(r)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(
                f, fieldnames=["keyword", "period", "blog_monthly", "blog_total", "cafe_total"]
            )
            w.writeheader()
            w.writerows(results)
        print(f"\nCSV 저장 완료: {args.csv}")


if __name__ == "__main__":
    main()
