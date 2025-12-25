from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# ===== 카테고리 전체 =====
CATEGORIES = {
    "전체": "https://www.smu.ac.kr/kor/life/notice.do",
    "메인공지": {
        "글로벌": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=190",
        "진로취업": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=162",
        "등록/장학": "https://www.smu.ac.kr/kor/life/notice.do?mode=list&srCategoryId1=22",
        # ✅ 추가
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
        # ✅ 추가 3개
        "가족복지학과": "https://www.smu.ac.kr/smfamily/community/notice.do",
        "화공신소재전공": "https://icee.smu.ac.kr/ichemistry/community/notice.do",
        "국어교육과": "https://www.smu.ac.kr/koredu/community/notice.do",
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

NOTICE_SELECTORS = [
    "table.board_list tbody tr",
    "table.boardList tbody tr",
    "tbody tr",
    "ul.board-list li",
    "ul.board-thumb-wrap li",
    "table.board-table tbody tr",
]

def parse_notice_list(html, base):
    soup = BeautifulSoup(html, "html.parser")

    rows = []
    for sel in NOTICE_SELECTORS:
        rows = soup.select(sel)
        if rows:
            break

    items = []
    for r in rows[:30]:
        a = r.find("a")
        if not a:
            continue

        title = a.get_text(strip=True)
        href = a.get("href", "").strip()
        url = urljoin(base, href)

        date = ""
        # 흔한 날짜 위치들
        date_el = r.select_one(".date") or r.select_one("td.date") or r.select_one("span.date")
        if date_el:
            date = date_el.get_text(strip=True)

        items.append({"title": title, "url": url, "date": date})
    return items

def fetch_one(url):
    if not url:
        return []
    try:
        r = SESSION.get(url, headers=HEADERS, timeout=7)
        r.raise_for_status()
        return parse_notice_list(r.text, url)
    except Exception as e:
        app.logger.warning(f"fetch_one failed: {url} / {e}")
        return []

@app.route("/fetch")
def fetch():
    group = request.args.get("group", "")
    sub = request.args.get("sub", "")

    if group in CATEGORIES:
        val = CATEGORIES[group]
        if isinstance(val, dict) and sub:
            url = val.get(sub, "")
            return jsonify({"items": fetch_one(url)})
        if isinstance(val, dict) and not sub:
            # 하위 모두 합치기
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
