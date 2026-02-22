from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import re
import time

app = Flask(__name__)

# ===== 카테고리 전체 =====
CATEGORIES = {
    "전체": "https://www.smu.ac.kr/kor/life/notice.do",
    "메인공지": {
        "글로벌": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=190",
        "진로취업": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=162",
        "등록/장학": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=22",
        # 추가항목
        "사회 봉사": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=21&srCampus=&srSearchKey=&srSearchVal=",
        "비교과 일반": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=420"
    },
    "학부(과)/전공": {
        "컴퓨터과학전공": "https://cs.smu.ac.kr/cs/community/notice.do",
        "자유전공학부대학": "https://sls.smu.ac.kr/sls/community/notice.do",
        "역사콘텐츠전공": "https://www.smu.ac.kr/history/community/notice.do",
        "영어교육과": "https://www.smu.ac.kr/engedu/community/notice.do",
        "게임전공": "https://www.smu.ac.kr/game01/community/notice.do",
        "애니메이션전공": "https://animation.smu.ac.kr/animation/community/notice.do",
        "스포츠건강관리전공": "https://sports.smu.ac.kr/smpe/admission/notice.do",
        "경영학부": "https://smubiz.smu.ac.kr/smubiz/community/notice.do",
        "휴먼AI공학전공": "https://hi.smu.ac.kr/hi/community/notice.do",
        "식품영양학전공": "https://food.smu.ac.kr/foodnutrition/community/notice.do",
        "국가안보학과": "https://ns.smu.ac.kr/sdms/community/notice.do",
        # 추가항목
        "가족복지학과": "https://www.smu.ac.kr/smfamily/community/notice.do",
        "화공신소재전공": "https://icee.smu.ac.kr/ichemistry/community/notice.do",
        "국어교육과": "https://www.smu.ac.kr/koredu/community/notice.do",
        "글로벌경영학과": "https://gbiz.smu.ac.kr/newmajoritb/board/notice.do"
    },
    "기숙사": {
        "상명 행복생활관": "https://dormitory.smu.ac.kr/dormi/happy/happy_notice.do",
        "스뮤하우스": "https://dormitory.smu.ac.kr/dormi/smu/smu_notice.do"
    },
    "대학원": "https://grad.smu.ac.kr/grad/board/notice.do",
    "공학교육인증센터": "https://icee.smu.ac.kr/icee/community/notice.do",

    # ✅ (추가) 학술정보관
    "학술정보관": {
        "서울캠퍼스": "https://lib.smu.ac.kr/Board?n=notice",
        "천안캠퍼스": "http://libnt.smuc.ac.kr/Board?n=notice"
    },
}

SESSION = requests.Session()

# 기존 헤더(기존 사이트 영향 최소)
HEADERS_DEFAULT = {"User-Agent": "Mozilla/5.0"}

# 학술정보관 전용 헤더(차단/빈페이지 방지용) - 다른 사이트엔 적용 안 함
HEADERS_LIB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    "Connection": "keep-alive",
}

# ✅ 학술정보관(dl 구조)만 "추가" (기존 셀렉터 그대로 유지)
NOTICE_SELECTORS = [
    "dl.onroad-board",  # ✅ 학술정보관 공지 목록 구조

    "table.board_list tbody tr",
    "table.boardList tbody tr",
    "tbody tr",
    "ul.board-list li",
    "ul.board-thumb-wrap li",
    "table.board-table tbody tr",
]

# 날짜/작성자 텍스트 패턴(기존 영향 없음: 못 찾을 때만 fallback)
RE_DATE_WRITTEN = re.compile(r"작성일\s*[:：]?\s*(20\d{2}[./-]\d{2}[./-]\d{2})")
RE_DATE_PUBLISHED = re.compile(r"게시일\s*[:：]?\s*(20\d{2}[./-]\d{2}[./-]\d{2})")
RE_DATE_ANY = re.compile(r"\b(20\d{2}[./-]\d{2}[./-]\d{2})\b")
RE_AUTHOR = re.compile(r"글쓴이\s*([^\s/]+)")

def is_library_url(url: str) -> bool:
    return ("lib.smu.ac.kr" in (url or "")) or ("libnt.smuc.ac.kr" in (url or ""))

# ✅ 간단 캐시(속도용) - 30초만, 결과형태는 그대로
_CACHE = {}  # key: url, value: (expire_ts, items)

def cache_get(url: str):
    now = time.time()
    v = _CACHE.get(url)
    if not v:
        return None
    exp, items = v
    if now <= exp:
        return items
    _CACHE.pop(url, None)
    return None

def cache_set(url: str, items, ttl_sec: int = 300):
    _CACHE[url] = (time.time() + ttl_sec, items)

def parse_notice_list(html, base):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    elems = []

    # 1) 기존 방식 그대로: 먼저 매칭되는 구조 사용
    for sel in NOTICE_SELECTORS:
        elems = soup.select(sel)
        if elems:
            break
    if not elems:
        return items

    for el in elems[:60]:
        a = el.find("a")
        if not a:
            continue

        # 제목
        raw_title = a.get_text(" ", strip=True)

        # ✅ 학술정보관: <span class="btn btn-xs">일반</span> 같은 꼬리표 제거(있을 때만)
        tag = a.find("span", class_=re.compile(r"\bbtn\b"))
        if tag:
            tag_text = tag.get_text(" ", strip=True)
            title = raw_title[len(tag_text):].strip() if raw_title.startswith(tag_text) else raw_title
        else:
            title = raw_title

        link = urljoin(base, a.get("href") or "")

        # 작성자(기존 사이트용)
        author = ""
        w = el.find(class_="writer") or el.find("td", {"data-role": "writer"})
        if not w:
            w = el.find("td", class_="writer")
        if w:
            author = w.get_text(strip=True)

        # 날짜(기존 사이트용)
        date = ""
        d = el.find(class_="date") or el.find("td", {"data-role": "date"})
        if not d:
            d = el.find("td", class_="date")
        if d:
            date = d.get_text(strip=True)

        # ✅ class로 못 찾으면 텍스트에서 작성일/게시일/날짜패턴 추출 (기존 영향 없음)
        if not date:
            text_all = " ".join(el.stripped_strings)
            m = RE_DATE_WRITTEN.search(text_all) or RE_DATE_PUBLISHED.search(text_all) or RE_DATE_ANY.search(text_all)
            if m:
                date = m.group(1).replace(".", "-").replace("/", "-")

        # ✅ 학술정보관: 글쓴이 텍스트에서 추출(기존 영향 없음)
        if not author:
            text_all = " ".join(el.stripped_strings)
            ma = RE_AUTHOR.search(text_all)
            if ma:
                author = ma.group(1).strip()

        items.append({"title": title, "link": link, "author": author, "date": date})

    return items

def fetch_one(url):
    if not url:
        return []

    # 캐시 hit
    cached = cache_get(url)
    if cached is not None:
        return cached

    lib = is_library_url(url)
    headers = HEADERS_LIB if lib else HEADERS_DEFAULT
    timeout = 8 if lib else 6  # 학술정보관만 여유
    attempts = 2 if lib else 1  # 학술정보관만 재시도

    last_err = None
    for i in range(attempts):
        try:
            r = SESSION.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            # 403/500이어도 html은 받을 수 있으니, "raise_for_status"로 바로 죽이지 않음
            html = r.text or ""
            items = parse_notice_list(html, url)

            # 학술정보관인데 items 0이면 상태코드 로그(렌더 로그에서 확인 가능)
            if lib and not items:
                print(f"[LIB EMPTY] status={r.status_code} url={url}")

            cache_set(url, items, ttl_sec=30)
            return items
        except Exception as e:
            last_err = e
            if lib:
                print(f"[LIB ERR] try={i+1}/{attempts} url={url} err={e}")

    return []

@app.route("/fetch")
def fetch_api():
    group = request.args.get("group")
    sub = request.args.get("sub")

    flat = {}
    for g, v in CATEGORIES.items():
        if isinstance(v, dict):
            flat.update(v)
        else:
            flat[g] = v

    if sub:
        return jsonify({"items": fetch_one(flat.get(sub, ""))})

    if group:
        val = CATEGORIES.get(group)
        if isinstance(val, dict):
            results = []
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = [ex.submit(fetch_one, u) for u in val.values()]
    try:
        for f in as_completed(futures, timeout=5):  # ✅ 전체를 최대 5초만 기다림
            results.extend(f.result())
    except TimeoutError:
        pass  # ✅ 5초 넘는 애들은 일단 포기하고, 받은 것만 반환
return jsonify({"items": results})
            
        return jsonify({"items": fetch_one(val)})

    return jsonify({"items": []})

@app.route("/")
def index():
    groups = {g: (list(v.keys()) if isinstance(v, dict) else []) for g, v in CATEGORIES.items()}
    return render_template("index.html", groups=groups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)

