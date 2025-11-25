from flask import Flask, render_template, request
import requests, json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# ===== 카테고리 (그대로 유지) =====
CATEGORIES = {
    "전체": "https://www.smu.ac.kr/kor/life/notice.do",
    "메인공지": {
        "글로벌": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=190",
        "진로취업": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=162",
        "등록/장학": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=22",
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
        "글로벌경영학과": "https://gbiz.smu.ac.kr/newmajoritb/board/notice.do"
    },
    "SW중심 사업단": "https://swai.smu.ac.kr/bbs/board.php?bo_table=07_01",
    "기숙사": {
        "상명 행복생활관": "https://dormitory.smu.ac.kr/dormi/happy/happy_notice.do",
        "스뮤하우스": "https://dormitory.smu.ac.kr/dormi/smu/smu_notice.do"
    },
    "대학원": "https://grad.smu.ac.kr/grad/board/notice.do",
    "공학교육인증센터": "https://icee.smu.ac.kr/icee/community/notice.do"
}

SESSION = requests.Session()
HEADERS = {"User-Agent": "Mozilla/5.0"}

# 공통 + 학술정보관까지 포함한 selector
NOTICE_SELECTORS = [
    "table.board_list tbody tr",
    "table.boardList tbody tr",
    "tbody tr",
    "ul.board-list li",
    "ul.board-thumb-wrap li",
    "table.board-table tbody tr",   # 학술정보관 전용
]

# --------------------- 공지 파싱 ---------------------
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

        author = ""
        w = el.find(class_="writer") or el.find("td", {"data-role": "writer"})
        if not w:
            w = el.find("td", class_="writer")
        if w:
            author = w.get_text(strip=True)

        date = ""
        d = el.find(class_="date") or el.find("td", {"data-role": "date"})
        if not d:
            d = el.find("td", class_="date")
        if d:
            date = d.get_text(strip=True)

        items.append({
            "title": title,
            "link": link,
            "author": author,
            "date": date
        })

    return items

# --------------------- 요청 ---------------------
def fetch_one(url):
    try:
        r = SESSION.get(url, headers=HEADERS, timeout=7)
        r.raise_for_status()
        return parse_notice_list(r.text, url)
    except:
        return []

# --------------------- API ---------------------
@app.route("/fetch")
def fetch_api():
    group = request.args.get("group")
    sub = request.args.get("sub")

    flat = {}
    for g,v in CATEGORIES.items():
        if isinstance(v, dict):
            flat.update(v)
        else:
            flat[g] = v

    if sub:
        return {"items": fetch_one(flat.get(sub, ""))}

    if group:
        val = CATEGORIES.get(group)

        if isinstance(val, dict):
            results = []
            with ThreadPoolExecutor(max_workers=10) as ex:
                tasks = [ex.submit(fetch_one, u) for u in val.values()]
                for f in as_completed(tasks):
                    results.extend(f.result())
            return {"items": results}

        return {"items": fetch_one(val)}

    return {"items": []}

# --------------------- UI 라우트 ---------------------
@app.route("/")
def index():
    groups = {g:(list(v.keys()) if isinstance(v, dict) else []) for g,v in CATEGORIES.items()}
    return render_template("index.html", groups=json.dumps(groups, ensure_ascii=False))

# --------------------- 서버 실행 ---------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
