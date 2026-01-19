from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import re  # ✅ 작성일/날짜 텍스트 추출용

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
    "공학교육인증센터": "https://icee.smu.ac.kr/icee/community/notice.do"
}

SESSION = requests.Session()
HEADERS = {"User-Agent": "Mozilla/5.0"}

NOTICE_SELECTORS = [
    "table.board_list tbody tr",
    "table.boardList tbody tr",
    "tbody tr",
    "ul.board-list li",
    "ul.board-thumb-wrap li",
    "table.board-table tbody tr",
]

# ✅ 날짜 텍스트에서 잡아낼 정규식들
RE_DATE_WRITTEN = re.compile(r"작성일\s*[:：]?\s*(20\d{2}[./-]\d{2}[./-]\d{2})")
RE_DATE_ANY = re.compile(r"\b(20\d{2}[./-]\d{2}[./-]\d{2})\b")

def parse_notice_list(html, base):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    elems = []

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

        title = a.get_text(strip=True)
        link = urljoin(base, a.get("href") or "")

        # ===== 작성자 =====
        author = ""
        w = el.find(class_="writer") or el.find("td", {"data-role": "writer"})
        if not w:
            w = el.find("td", class_="writer")
        if w:
            author = w.get_text(strip=True)

        # ===== 날짜(작성일) =====
        date = ""
        d = el.find(class_="date") or el.find("td", {"data-role": "date"})
        if not d:
            d = el.find("td", class_="date")
        if d:
            date = d.get_text(strip=True)

        # ✅ (추가) class로 못 찾으면 텍스트에서 "작성일 YYYY-MM-DD" 또는 날짜 패턴 추출
        if not date:
            text_all = " ".join(el.stripped_strings)
            m = RE_DATE_WRITTEN.search(text_all) or RE_DATE_ANY.search(text_all)
            if m:
                date = m.group(1).replace(".", "-").replace("/", "-")

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
    # 하위 카테고리 key 목록만 뽑아서 JS로 전달
    groups = {g: (list(v.keys()) if isinstance(v, dict) else []) for g, v in CATEGORIES.items()}
    return render_template("index.html", groups=groups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)

