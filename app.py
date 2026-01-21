from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import re  # ✅ 날짜/작성자 텍스트 추출용(추가)

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

    # ✅ (추가) 학술정보관(도서관) 공지
    # 기존 카테고리/링크는 절대 건드리지 않고, 새 그룹만 추가
    "학술정보관": {
        "서울캠퍼스": "https://lib.smu.ac.kr/Board?n=notice",
        "천안캠퍼스": "http://libnt.smuc.ac.kr/Board?n=notice"
    }
}

SESSION = requests.Session()
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ===== 공지 목록 구조 셀렉터 =====
# ✅ 기존 셀렉터는 그대로 두고, 학술정보관(dl.onroad-board)만 맨 앞에 "추가"
NOTICE_SELECTORS = [
    "dl.onroad-board",  # ✅ (추가) 학술정보관 공지 구조

    "table.board_list tbody tr",
    "table.boardList tbody tr",
    "tbody tr",
    "ul.board-list li",
    "ul.board-thumb-wrap li",
    "table.board-table tbody tr",
]

# ✅ 날짜 텍스트에서 잡아낼 정규식들(추가: 기존 사이트 영향 없음, 못 찾을 때만 fallback)
RE_DATE_WRITTEN = re.compile(r"작성일\s*[:：]?\s*(20\d{2}[./-]\d{2}[./-]\d{2})")
RE_DATE_PUBLISHED = re.compile(r"게시일\s*[:：]?\s*(20\d{2}[./-]\d{2}[./-]\d{2})")
RE_DATE_ANY = re.compile(r"\b(20\d{2}[./-]\d{2}[./-]\d{2})\b")

# ✅ 작성자(글쓴이) 추출용(추가: 기존 사이트 영향 없음, 못 찾을 때만 fallback)
RE_AUTHOR = re.compile(r"글쓴이\s*([^\s/]+)")

def parse_notice_list(html, base):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    elems = []

    # 1) 기존 방식 유지: 셀렉터를 순서대로 탐색해 첫 매칭을 사용
    for sel in NOTICE_SELECTORS:
        elems = soup.select(sel)
        if elems:
            break
    if not elems:
        return items

    # 2) 각 공지 항목 파싱 (기존 로직 유지 + 학술정보관 케이스만 안전하게 추가 대응)
    for el in elems[:60]:
        a = el.find("a")
        if not a:
            continue

        # 제목
        # (학술정보관은 <span class="btn btn-xs">일반</span> 같은 태그가 제목 앞에 붙어 있어서 제거)
        raw_title = a.get_text(" ", strip=True)
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

        # ✅ (추가) 학술정보관처럼 class로 날짜가 없으면 텍스트에서 "작성일/게시일/날짜패턴" 추출
        # 기존 사이트는 date가 이미 잡히므로, 기존 동작에 영향 없음
        if not date:
            text_all = " ".join(el.stripped_strings)
            m = RE_DATE_WRITTEN.search(text_all) or RE_DATE_PUBLISHED.search(text_all) or RE_DATE_ANY.search(text_all)
            if m:
                date = m.group(1).replace(".", "-").replace("/", "-")

        # ✅ (추가) 학술정보관: "글쓴이 홍길동 / 조회수 ..." 형태면 정규식으로 작성자 추출
        # 기존 사이트는 author가 이미 잡히므로, 기존 동작에 영향 없음
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
    try:
        r = SESSION.get(url, headers=HEADERS, timeout=7)
        r.raise_for_status()
        return parse_notice_list(r.text, url)
    except:
        return []

@app.route("/fetch")
def fetch_api():
    group = request.args.get("group")
    sub = request.args.get("sub")

    # 기존 방식 유지: 하위카테고리는 flat으로 합쳐 sub로 직접 요청 가능
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
            with ThreadPoolExecutor(max_workers=10) as ex:
                tasks = [ex.submit(fetch_one, u) for u in val.values()]
                for f in as_completed(tasks):
                    results.extend(f.result())
            return jsonify({"items": results})
        return jsonify({"items": fetch_one(val)})

    return jsonify({"items": []})

@app.route("/")
def index():
    # 기존 방식 유지: 하위 카테고리 key 목록만 뽑아서 JS로 전달
    groups = {g: (list(v.keys()) if isinstance(v, dict) else []) for g, v in CATEGORIES.items()}
    return render_template("index.html", groups=groups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
