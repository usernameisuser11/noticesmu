from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# ===== 카테고리 (그대로 유지) =====
CATEGORIES = { ... }  # 기존 CATEGORIES 그대로 사용

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
    items = []
    elems = []
    for sel in NOTICE_SELECTORS:
        elems = soup.select(sel)
        if elems: break
    if not elems: return items
    for el in elems[:60]:
        a = el.find("a")
        if not a: continue
        title = a.get_text(strip=True)
        link = urljoin(base, a.get("href") or "")
        # 작성자
        author = ""
        w = el.find(class_="writer") or el.find("td", {"data-role": "writer"})
        if not w: w = el.find("td", class_="writer")
        if w: author = w.get_text(strip=True)
        # 날짜
        date = ""
        d = el.find(class_="date") or el.find("td", {"data-role": "date"})
        if not d: d = el.find("td", class_="date")
        if d: date = d.get_text(strip=True)
        items.append({"title": title, "link": link, "author": author, "date": date})
    return items

def fetch_one(url):
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
    for g,v in CATEGORIES.items():
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
    groups = {g:(list(v.keys()) if isinstance(v, dict) else []) for g,v in CATEGORIES.items()}
    return render_template("index.html", groups=groups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
