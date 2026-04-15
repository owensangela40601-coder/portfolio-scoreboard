from flask import Flask, request, render_template, redirect, url_for
import requests
import re
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

DATA_FILE = "pods.json"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# 🔥 OCR API KEY
OCR_API_KEY = "helloworld"


# -------------------------
# DATA STORAGE
# -------------------------
def load_pods():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"A": [], "B": [], "C": []}


def save_pods(pods):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(pods, f, indent=2)


pods = load_pods()


# -------------------------
# HELPERS
# -------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# -------------------------
# 🔥 OCR FUNCTION (TICKER-BASED)
# -------------------------
def extract_results(image_path):

    with open(image_path, 'rb') as f:
        response = requests.post(
            'https://api.ocr.space/parse/image',
            files={'file': f},
            data={
                'apikey': OCR_API_KEY,
                'language': 'eng',
            }
        )

    result = response.json()

    try:
        text = result['ParsedResults'][0]['ParsedText']
    except:
        return []

    print("\n--- OCR TEXT ---\n")
    print(text)

    lines = text.split("\n")
    results = []

    for line in lines:

        # find % values
        percents = re.findall(r'[-+]?\d+\.\d+%', line)

        # find ticker-like words (ALL CAPS)
        tickers = re.findall(r'\b[A-Z]{2,5}\b', line)

        if percents and tickers:

            percent = float(percents[0].replace('%',''))
            ticker = tickers[0]

            # ❌ FILTER OUT JUNK
            if ticker in ["USD", "FDIC", "CASH", "CORE", "SWEEP"]:
                continue

            if abs(percent) < 0.5:
                continue

            results.append((ticker, percent))

    return results


# -------------------------
# SCOREBOARD
# -------------------------
def create_scoreboard(results):
    if not results:
        return None

    numbers = [r[1] for r in results]

    avg = sum(numbers) / len(numbers)
    best = max(results, key=lambda x: x[1])
    worst = min(results, key=lambda x: x[1])
    win_rate = len([n for n in numbers if n > 0]) / len(numbers) * 100

    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
    top_3 = sorted_results[:3]

    losers = [r for r in results if r[1] < 0]
    bottom_3 = sorted(losers, key=lambda x: x[1])[:3]

    market_return = 6.0
    teacher_return = 7.0

    if avg > teacher_return and avg > market_return:
        grade = "A"
        message = "🔥 Beat the Teacher AND the Market"
    elif avg > teacher_return:
        grade = "B"
        message = "💪 Beat the Teacher"
    elif avg > market_return:
        grade = "C"
        message = "👍 Beat the Market"
    elif avg > 0:
        grade = "D"
        message = "⚠️ Positive but underperformed"
    else:
        grade = "F"
        message = "❌ Negative return"

    return {
        "average": round(avg, 2),
        "best": best,
        "worst": worst,
        "win_rate": round(win_rate, 1),
        "top_3": top_3,
        "bottom_3": bottom_3,
        "grade": grade,
        "message": message,
        "market": market_return,
        "teacher": teacher_return,
    }


# -------------------------
# TEACHER ANALYSIS
# -------------------------
def generate_teacher_analysis(results, scoreboard):
    if not results or not scoreboard:
        return []

    analysis = []

    avg = scoreboard["average"]

    if avg > scoreboard["teacher"]:
        analysis.append("🔥 Strong: Beat the Teacher.")
    elif avg > scoreboard["market"]:
        analysis.append("👍 Beat the market but not the Teacher.")
    else:
        analysis.append("⚠️ ETF strategy would have done better.")

    if scoreboard["best"][1] > avg * 2:
        analysis.append("⚠️ One stock is driving gains.")

    if scoreboard["worst"][1] < 0:
        analysis.append("❌ Losing positions hurting performance.")

    return analysis


# -------------------------
# MAIN ROUTE
# -------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    global pods

    scoreboard = None
    analysis = []
    error = None
    selected_player = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pod = request.form.get("pod", "").strip()
        file = request.files.get("file")

        if not name:
            error = "Enter a name."
            return render_template("index.html", pods=pods, error=error)

        if pod not in {"A", "B", "C"}:
            error = "Choose Pod A, B, or C."
            return render_template("index.html", pods=pods, error=error)

        if not file or file.filename == "":
            error = "Upload a screenshot."
            return render_template("index.html", pods=pods, error=error)

        if not allowed_file(file.filename):
            error = "Use PNG/JPG."
            return render_template("index.html", pods=pods, error=error)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        results = extract_results(filepath)
        scoreboard = create_scoreboard(results)

        if not scoreboard:
            error = "Could not read screenshot clearly."
            return render_template("index.html", pods=pods, error=error)

        analysis = generate_teacher_analysis(results, scoreboard)

        pods[pod] = [p for p in pods[pod] if p["name"].lower() != name.lower()]

        student_record = {
            "name": name,
            "average": scoreboard["average"],
            "stocks": results,
            "grade": scoreboard["grade"],
            "message": scoreboard["message"],
            "pod": pod,
        }

        pods[pod].append(student_record)
        pods[pod] = sorted(pods[pod], key=lambda x: x["average"], reverse=True)

        save_pods(pods)

        selected_player = student_record

    return render_template(
        "index.html",
        scoreboard=scoreboard,
        pods=pods,
        analysis=analysis,
        error=error,
        selected_player=selected_player,
    )


# -------------------------
# CHILD VIEW
# -------------------------
@app.route("/child/<pod>/<name>")
def view_child(pod, name):
    global pods

    player = None

    for p in pods.get(pod, []):
        if p["name"].lower() == name.lower():
            player = p
            break

    if not player:
        return "Not found"

    results = player["stocks"]
    scoreboard = create_scoreboard(results)
    analysis = generate_teacher_analysis(results, scoreboard)

    return render_template(
        "index.html",
        scoreboard=scoreboard,
        pods=pods,
        analysis=analysis,
        selected_player=player,
    )


# -------------------------
# RESET
# -------------------------
@app.route("/reset")
def reset():
    global pods
    pods = {"A": [], "B": [], "C": []}
    save_pods(pods)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False)
