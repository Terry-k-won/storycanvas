#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 키워드 분석기 — 브라우저 UI 버전

실행: python naver_gui.py
→ 브라우저가 자동으로 열립니다 (http://localhost:5050)
외부 패키지 불필요 (표준 라이브러리만 사용)

제공 기능:
  - 월간 검색량 PC / 모바일 / 합계
  - 월간 블로그 발행량 (최근 30일)
  - 키워드 경쟁률 점수 및 등급
  - 연관 키워드 분석 (검색량 + 경쟁률)
  - 도전 추천 키워드 자동 선별

필요한 API 키:
  1) 네이버 검색 API  → developers.naver.com
  2) 네이버 검색광고 API → searchad.naver.com
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naver_config.json")
PORT = 5050

API_BLOG = "https://openapi.naver.com/v1/search/blog.json"
SEARCHAD_BASE = "https://api.searchad.naver.com"
KEYWORDSTOOL_URI = "/keywordstool"
DISPLAY = 100
MAX_START = 1000


# ── 검색광고 API ──────────────────────────────────────────
def _sign(timestamp, method, uri, secret):
    msg = f"{timestamp}.{method}.{uri}"
    d = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.b64encode(d).decode()

def get_keywords(keyword, api_key, secret_key, customer_id):
    ts = str(round(time.time() * 1000))
    sig = _sign(ts, "GET", KEYWORDSTOOL_URI, secret_key)
    params = urllib.parse.urlencode({"hintKeywords": keyword.replace(" ", ""), "showDetail": 1})
    req = urllib.request.Request(f"{SEARCHAD_BASE}{KEYWORDSTOOL_URI}?{params}")
    req.add_header("X-Timestamp", ts)
    req.add_header("X-API-KEY", api_key)
    req.add_header("X-Customer", str(customer_id))
    req.add_header("X-Signature", sig)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def parse_cnt(v):
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace(",", "").strip()
    if "<" in s:
        return 10
    try:
        return int(s)
    except ValueError:
        return 0


# ── 검색 API (블로그 발행량) ─────────────────────────────
def blog_search(query, cid, secret, start):
    params = urllib.parse.urlencode(
        {"query": query, "display": DISPLAY, "start": start, "sort": "date"}
    )
    req = urllib.request.Request(f"{API_BLOG}?{params}")
    req.add_header("X-Naver-Client-Id", cid)
    req.add_header("X-Naver-Client-Secret", secret)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def get_blog_monthly(query, cid, secret):
    today = dt.date.today()
    s30 = today - dt.timedelta(days=30)
    count, total, capped, start = 0, None, False, 1
    while start <= MAX_START:
        data = blog_search(query, cid, secret, start)
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
            if d < s30:
                stop = True
                break
            count += 1
        if stop:
            break
        start += DISPLAY
        if start > MAX_START and len(items) == DISPLAY:
            capped = True
        time.sleep(0.08)
    return count, (total or 0), capped


# ── 경쟁률 계산 ──────────────────────────────────────────
def competition_grade(blog30, search_total):
    if search_total <= 0:
        return None, "데이터 없음", "#888"
    ratio = blog30 / search_total * 100
    if ratio < 3:
        grade, color = "낮음 😊", "#22c55e"
    elif ratio < 10:
        grade, color = "보통 😐", "#f59e0b"
    else:
        grade, color = "높음 😰", "#ef4444"
    return round(ratio, 2), grade, color


# ── 설정 저장/불러오기 ────────────────────────────────────
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 분석 메인 로직 ───────────────────────────────────────
def analyze(payload):
    kw = payload.get("keyword", "").strip()
    cid = payload.get("cid", "").strip()
    sec = payload.get("secret", "").strip()
    ak = payload.get("ad_key", "").strip()
    asec = payload.get("ad_secret", "").strip()
    cust = payload.get("customer", "").strip()

    if payload.get("save_keys"):
        save_config({"cid": cid, "secret": sec, "ad_key": ak, "ad_secret": asec, "customer": cust})

    result = {"keyword": kw, "search": None, "blog": None, "related": [], "recommend": [], "errors": []}

    # 검색량
    if ak and asec and cust:
        try:
            data = get_keywords(kw, ak, asec, cust)
            kwlist = data.get("keywordList", [])
            target = kw.replace(" ", "")
            row = next((r for r in kwlist if r.get("relKeyword", "").replace(" ", "") == target), None)
            if row is None and kwlist:
                row = kwlist[0]
            if row:
                pc = parse_cnt(row.get("monthlyPcQcCnt", 0))
                mo = parse_cnt(row.get("monthlyMobileQcCnt", 0))
                result["search"] = {"pc": pc, "mobile": mo, "total": pc + mo}

            # 연관 키워드
            related = []
            for r in kwlist[:20]:
                rk = r.get("relKeyword", "")
                rpc = parse_cnt(r.get("monthlyPcQcCnt", 0))
                rmo = parse_cnt(r.get("monthlyMobileQcCnt", 0))
                rtotal = rpc + rmo
                if rtotal < 50:
                    continue
                related.append({"keyword": rk, "pc": rpc, "mobile": rmo, "total": rtotal})
            result["related"] = related
        except Exception as e:
            result["errors"].append(f"검색광고 API: {e}")

    # 블로그 발행량 (메인 키워드)
    blog30_main = 0
    if cid and sec:
        try:
            cnt, total, capped = get_blog_monthly(kw, cid, sec)
            blog30_main = cnt
            ratio, grade, color = competition_grade(cnt, result["search"]["total"] if result["search"] else 0)
            result["blog"] = {
                "monthly": cnt, "capped": capped, "total": total,
                "ratio": ratio, "grade": grade, "color": color
            }
        except Exception as e:
            result["errors"].append(f"검색 API: {e}")

    # 연관 키워드 경쟁률 + 추천 선별
    if cid and sec and result["related"]:
        for r in result["related"]:
            try:
                cnt30, _, _ = get_blog_monthly(r["keyword"], cid, sec)
                r["blog30"] = cnt30
                ratio, grade, color = competition_grade(cnt30, r["total"])
                r["ratio"] = ratio
                r["grade"] = grade
                r["color"] = color
                time.sleep(0.05)
            except Exception:
                r["blog30"] = None
                r["ratio"] = None
                r["grade"] = "조회 실패"
                r["color"] = "#888"

        # 추천: 검색량 충분 + 경쟁률 낮음 + 메인 키워드와 유사
        result["recommend"] = [
            r for r in result["related"]
            if r.get("ratio") is not None and r["ratio"] < 5 and r["total"] >= 200
        ]
        result["recommend"].sort(key=lambda x: x["total"], reverse=True)
        result["recommend"] = result["recommend"][:5]

    return result


# ── HTML 템플릿 ───────────────────────────────────────────
def build_html(config):
    c = config
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>네이버 키워드 분석기</title>
<style>
  :root {{
    --bg: #0f172a; --card: #1e293b; --card2: #263045;
    --border: #334155; --accent: #6366f1; --accent2: #818cf8;
    --text: #f1f5f9; --sub: #94a3b8; --green: #22c55e;
    --yellow: #f59e0b; --red: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif; min-height: 100vh; }}
  .header {{ background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 28px 32px; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -0.5px; }}
  .header p {{ color: #c4b5fd; font-size: 0.85rem; margin-top: 4px; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 24px 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px 24px; margin-bottom: 16px; }}
  .card-title {{ font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--sub); margin-bottom: 14px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  label {{ display: block; font-size: 0.8rem; color: var(--sub); margin-bottom: 5px; font-weight: 500; }}
  input[type=text], input[type=password] {{
    width: 100%; background: var(--card2); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 13px; color: var(--text); font-size: 0.9rem; outline: none;
    transition: border-color .2s;
  }}
  input:focus {{ border-color: var(--accent); }}
  .keyword-row {{ display: flex; gap: 10px; align-items: flex-end; }}
  .keyword-row input {{ flex: 1; font-size: 1rem; padding: 11px 14px; }}
  .btn {{
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff; border: none; border-radius: 8px; padding: 11px 28px;
    font-size: 0.95rem; font-weight: 600; cursor: pointer; white-space: nowrap;
    transition: opacity .2s, transform .1s;
  }}
  .btn:hover {{ opacity: .9; }}
  .btn:active {{ transform: scale(.97); }}
  .btn:disabled {{ opacity: .5; cursor: default; }}
  .save-row {{ display: flex; align-items: center; gap: 8px; margin-top: 12px; }}
  .save-row input {{ width: auto; }}
  .save-row label {{ margin: 0; color: var(--sub); font-size: 0.82rem; }}
  .result-area {{ display: none; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .stat-box {{ background: var(--card2); border-radius: 10px; padding: 16px; text-align: center; border: 1px solid var(--border); }}
  .stat-box .num {{ font-size: 1.8rem; font-weight: 700; color: var(--accent2); }}
  .stat-box .lbl {{ font-size: 0.78rem; color: var(--sub); margin-top: 4px; }}
  .competition-bar-wrap {{ margin-top: 14px; }}
  .competition-bar-wrap .label-row {{ display: flex; justify-content: space-between; font-size: 0.82rem; color: var(--sub); margin-bottom: 6px; }}
  .bar-bg {{ background: var(--card2); border-radius: 999px; height: 8px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 999px; transition: width 1s ease; }}
  .grade-badge {{ display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 0.82rem; font-weight: 600; margin-top: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ color: var(--sub); font-weight: 600; padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); }}
  th:first-child {{ text-align: left; }}
  td {{ padding: 9px 10px; text-align: right; border-bottom: 1px solid #1e293b; }}
  td:first-child {{ text-align: left; font-weight: 500; }}
  tr:hover td {{ background: rgba(99,102,241,.06); }}
  .pill {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
  .recommend-list {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }}
  .recommend-chip {{
    background: rgba(99,102,241,.18); border: 1px solid rgba(99,102,241,.4);
    border-radius: 999px; padding: 6px 14px; font-size: 0.85rem; font-weight: 500;
    cursor: pointer; transition: background .2s;
  }}
  .recommend-chip:hover {{ background: rgba(99,102,241,.35); }}
  .error-box {{ background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.3); border-radius: 8px; padding: 10px 14px; color: #fca5a5; font-size: 0.85rem; margin-top: 8px; }}
  .spinner {{ display: none; width: 20px; height: 20px; border: 3px solid rgba(255,255,255,.2); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .loading .spinner {{ display: inline-block; }}
  .loading .btn-text {{ display: none; }}
  .section-divider {{ display: flex; align-items: center; gap: 10px; margin: 6px 0 14px; }}
  .section-divider span {{ color: var(--sub); font-size: 0.78rem; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; white-space: nowrap; }}
  .section-divider::before, .section-divider::after {{ content:''; flex:1; height:1px; background: var(--border); }}
  .toggle-btn {{ background: none; border: 1px solid var(--border); color: var(--sub); border-radius: 6px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; float: right; }}
  .toggle-btn:hover {{ border-color: var(--accent); color: var(--accent2); }}
  .api-section {{ overflow: hidden; transition: max-height .35s ease; }}
  @media(max-width:600px) {{
    .stat-grid {{ grid-template-columns: 1fr 1fr; }}
    .grid2 {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="header">
  <h1>🔍 네이버 키워드 분석기</h1>
  <p>월간 검색량 · 콘텐츠 발행량 · 경쟁률 · 추천 키워드</p>
</div>

<div class="container">

  <!-- API 키 입력 -->
  <div class="card" id="api-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <span class="card-title" style="margin:0">API 키 설정</span>
      <button class="toggle-btn" onclick="toggleApi()">접기 ▲</button>
    </div>
    <div id="api-section" class="api-section">
      <div style="margin-bottom:10px; padding:10px 14px; background:rgba(99,102,241,.1); border-radius:8px; font-size:0.82rem; color:#a5b4fc; line-height:1.6;">
        ① <b>검색 API</b>: <a href="https://developers.naver.com" target="_blank" style="color:#818cf8;">developers.naver.com</a> → 애플리케이션 등록 → <b>검색</b> 체크<br>
        ② <b>검색광고 API</b>: <a href="https://searchad.naver.com" target="_blank" style="color:#818cf8;">searchad.naver.com</a> → 도구 → API 사용관리
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:14px;">
        <div>
          <div class="card-title">① 검색 API</div>
          <div style="margin-bottom:10px">
            <label>Client ID</label>
            <input type="text" id="cid" value="{c.get('cid','')}">
          </div>
          <div>
            <label>Client Secret</label>
            <input type="password" id="secret" value="{c.get('secret','')}">
          </div>
        </div>
        <div>
          <div class="card-title">② 검색광고 API</div>
          <div style="margin-bottom:10px">
            <label>API Key</label>
            <input type="text" id="ad_key" value="{c.get('ad_key','')}">
          </div>
          <div style="margin-bottom:10px">
            <label>Secret Key</label>
            <input type="password" id="ad_secret" value="{c.get('ad_secret','')}">
          </div>
          <div>
            <label>Customer ID</label>
            <input type="text" id="customer" value="{c.get('customer','')}">
          </div>
        </div>
      </div>
      <div class="save-row">
        <input type="checkbox" id="save_keys" checked>
        <label for="save_keys">이 PC에 키 저장 (naver_config.json — .gitignore 적용됨)</label>
      </div>
    </div>
  </div>

  <!-- 키워드 입력 -->
  <div class="card">
    <div class="card-title">키워드 입력</div>
    <div class="keyword-row">
      <input type="text" id="keyword" placeholder="분석할 키워드를 입력하세요" onkeydown="if(event.key==='Enter')analyze()">
      <button class="btn" id="analyze-btn" onclick="analyze()">
        <span class="btn-text">분석하기</span>
        <div class="spinner"></div>
      </button>
    </div>
  </div>

  <!-- 결과 -->
  <div id="result-area" class="result-area">

    <div class="section-divider"><span>📊 분석 결과</span></div>

    <!-- 검색량 -->
    <div class="card" id="card-search" style="display:none">
      <div class="card-title">월간 검색량</div>
      <div class="stat-grid">
        <div class="stat-box">
          <div class="num" id="s-pc">-</div>
          <div class="lbl">PC 검색량</div>
        </div>
        <div class="stat-box">
          <div class="num" id="s-mo">-</div>
          <div class="lbl">모바일 검색량</div>
        </div>
        <div class="stat-box">
          <div class="num" id="s-tot">-</div>
          <div class="lbl">PC + 모바일</div>
        </div>
      </div>
    </div>

    <!-- 발행량 + 경쟁률 -->
    <div class="card" id="card-blog" style="display:none">
      <div class="card-title">월간 콘텐츠 발행량 (최근 30일)</div>
      <div class="stat-grid" style="grid-template-columns:1fr 1fr 1fr">
        <div class="stat-box">
          <div class="num" id="b-monthly">-</div>
          <div class="lbl">블로그 발행 (30일)</div>
        </div>
        <div class="stat-box">
          <div class="num" id="b-total">-</div>
          <div class="lbl">블로그 누적</div>
        </div>
        <div class="stat-box">
          <div class="num" id="b-ratio">-</div>
          <div class="lbl">발행/검색 비율</div>
        </div>
      </div>
      <div class="competition-bar-wrap">
        <div class="label-row">
          <span>경쟁률</span>
          <span id="b-grade-text">-</span>
        </div>
        <div class="bar-bg">
          <div class="bar-fill" id="b-bar" style="width:0%;background:#22c55e"></div>
        </div>
        <div>
          <span class="grade-badge" id="b-badge" style="background:rgba(34,197,94,.15);color:#22c55e">-</span>
        </div>
      </div>
    </div>

    <!-- 추천 키워드 -->
    <div class="card" id="card-recommend" style="display:none">
      <div class="card-title">🎯 도전 추천 키워드</div>
      <p style="font-size:0.82rem; color:var(--sub); margin-bottom:12px;">검색량 충분 + 경쟁률 낮음 기준 자동 선별 · 클릭하면 바로 분석</p>
      <div class="recommend-list" id="recommend-list"></div>
    </div>

    <!-- 연관 키워드 테이블 -->
    <div class="card" id="card-related" style="display:none">
      <div class="card-title">연관 키워드 분석</div>
      <div style="overflow-x:auto">
        <table id="related-table">
          <thead>
            <tr>
              <th>키워드</th>
              <th>PC</th>
              <th>모바일</th>
              <th>합계</th>
              <th>블로그 30일</th>
              <th>경쟁률</th>
              <th>등급</th>
            </tr>
          </thead>
          <tbody id="related-body"></tbody>
        </table>
      </div>
    </div>

    <!-- 에러 -->
    <div id="error-area"></div>

  </div>
</div>

<script>
let apiVisible = true;
function toggleApi() {{
  const sec = document.getElementById('api-section');
  const btn = document.querySelector('.toggle-btn');
  apiVisible = !apiVisible;
  sec.style.maxHeight = apiVisible ? '600px' : '0';
  btn.textContent = apiVisible ? '접기 ▲' : '펼치기 ▼';
}}
document.getElementById('api-section').style.maxHeight = '600px';

function fmt(n) {{
  if (n === null || n === undefined) return '-';
  return Number(n).toLocaleString('ko-KR');
}}

function analyze() {{
  const kw = document.getElementById('keyword').value.trim();
  if (!kw) {{ alert('키워드를 입력하세요.'); return; }}
  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.classList.add('loading');
  document.getElementById('result-area').style.display = 'none';
  document.getElementById('error-area').innerHTML = '';

  const payload = {{
    keyword: kw,
    cid: document.getElementById('cid').value.trim(),
    secret: document.getElementById('secret').value.trim(),
    ad_key: document.getElementById('ad_key').value.trim(),
    ad_secret: document.getElementById('ad_secret').value.trim(),
    customer: document.getElementById('customer').value.trim(),
    save_keys: document.getElementById('save_keys').checked,
  }};

  fetch('/api/analyze', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload)
  }})
  .then(r => r.json())
  .then(data => renderResult(data))
  .catch(e => {{
    document.getElementById('error-area').innerHTML =
      `<div class="error-box">서버 오류: ${{e.message}}</div>`;
    document.getElementById('result-area').style.display = 'block';
  }})
  .finally(() => {{
    btn.disabled = false;
    btn.classList.remove('loading');
    // API 키 섹션 자동 접기
    if (apiVisible) toggleApi();
  }});
}}

function renderResult(d) {{
  document.getElementById('result-area').style.display = 'block';

  // 검색량
  if (d.search) {{
    document.getElementById('card-search').style.display = 'block';
    document.getElementById('s-pc').textContent = fmt(d.search.pc);
    document.getElementById('s-mo').textContent = fmt(d.search.mobile);
    document.getElementById('s-tot').textContent = fmt(d.search.total);
  }}

  // 블로그 발행량 + 경쟁률
  if (d.blog) {{
    document.getElementById('card-blog').style.display = 'block';
    document.getElementById('b-monthly').textContent =
      d.blog.capped ? '1,000+' : fmt(d.blog.monthly);
    document.getElementById('b-total').textContent = fmt(d.blog.total);
    if (d.blog.ratio !== null) {{
      document.getElementById('b-ratio').textContent = d.blog.ratio + '%';
      const pct = Math.min(d.blog.ratio, 30) / 30 * 100;
      document.getElementById('b-bar').style.width = pct + '%';
      document.getElementById('b-bar').style.background = d.blog.color;
      document.getElementById('b-grade-text').textContent = d.blog.ratio + '%';
      document.getElementById('b-badge').textContent = d.blog.grade;
      document.getElementById('b-badge').style.color = d.blog.color;
      document.getElementById('b-badge').style.background = d.blog.color + '22';
    }}
  }}

  // 추천 키워드
  if (d.recommend && d.recommend.length > 0) {{
    document.getElementById('card-recommend').style.display = 'block';
    const list = document.getElementById('recommend-list');
    list.innerHTML = d.recommend.map(r =>
      `<span class="recommend-chip" onclick="setKeyword('${{r.keyword}}')">${{r.keyword}}<br>
      <small style="color:var(--sub)">검색 ${{fmt(r.total)}} · 경쟁 ${{r.ratio}}%</small></span>`
    ).join('');
  }}

  // 연관 키워드 테이블
  if (d.related && d.related.length > 0) {{
    document.getElementById('card-related').style.display = 'block';
    const tbody = document.getElementById('related-body');
    tbody.innerHTML = d.related.map(r => `
      <tr>
        <td><span style="cursor:pointer;color:var(--accent2)" onclick="setKeyword('${{r.keyword}}')">${{r.keyword}}</span></td>
        <td>${{fmt(r.pc)}}</td>
        <td>${{fmt(r.mobile)}}</td>
        <td><b>${{fmt(r.total)}}</b></td>
        <td>${{r.blog30 !== null ? fmt(r.blog30) : '-'}}</td>
        <td>${{r.ratio !== null ? r.ratio + '%' : '-'}}</td>
        <td><span class="pill" style="background:${{r.color}}22;color:${{r.color}}">${{r.grade}}</span></td>
      </tr>`).join('');
  }}

  // 에러
  if (d.errors && d.errors.length > 0) {{
    document.getElementById('error-area').innerHTML =
      d.errors.map(e => `<div class="error-box">⚠️ ${{e}}</div>`).join('');
  }}
}}

function setKeyword(kw) {{
  document.getElementById('keyword').value = kw;
  analyze();
}}
</script>
</body>
</html>"""


# ── HTTP 서버 ─────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    config = {}

    def log_message(self, fmt, *args):
        pass  # 서버 로그 숨김

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = build_html(self.config).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/analyze":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode())
            try:
                result = analyze(payload)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    cfg = load_config()
    Handler.config = cfg

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"서버 시작: http://localhost:{PORT}")
    print("종료하려면 Ctrl+C 를 누르세요.")

    def open_browser():
        time.sleep(0.6)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.shutdown()


if __name__ == "__main__":
    main()
