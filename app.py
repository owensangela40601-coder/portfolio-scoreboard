from flask import Flask, request, render_template, redirect, url_for
import pytesseract
from PIL import Image
import re
import json
import os
from werkzeug.utils import secure_filename

# Optional local Tesseract path for Windows users.
# On Render/Linux, Tesseract is provided by the deploy image if installed.
WINDOWS_TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(WINDOWS_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = WINDOWS_TESSERACT

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

DATA_FILE = "pods.json"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def load_pods():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"A": [], "B": [], "C": []}


def save_pods(pods):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(pods, f, indent=2)


pods = load_pods()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_name(name):
    junk = {
        "becca", "rend", "inc", "com", "usd", "co", "corp", "ltd",
        "class", "fund", "tr", "etf", "ord", "npv", "holdings", "holding"
    }
    words = name.lower().split()
    cleaned = [w for w in words if w not in junk and len(w) > 1]
    return " ".join(cleaned).upper()


def extract_results(image_path):
    text = pytesseract.image_to_string(Image.open(image_path))
    print("\n--- OCR RAW TEXT ---\n")
    print(text)

    lines = text.split("\n")
    results = []

    for line in lines:
        if "%" not in line or not any(c.isalpha() for c in line):
            continue

        percents = re.findall(r'[-+]?\d{1,3}\.\d{1,2}%', line)
        if not percents:
            continue

        percent = float(percents[0].replace('%', ''))
        words = line.split()
        raw_name = " ".join(words[:5])
        name = clean_name(raw_name)

        if not name:
            continue

        if abs(percent) > 1 and "MONEY MARKET" not in name:
            results.append((name, percent))

    # dedupe by stock name, keep highest absolute value if OCR duplicates
    deduped = {}
    for name, pct in results:
        if name not in deduped or abs(pct) > abs(deduped[name]):
            deduped[name] = pct

    return [(name, pct) for name, pct in deduped.items()]


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


def generate_teacher_analysis(results, scoreboard):
    if not results or not scoreboard:
        return []

    analysis = []
    avg = scoreboard["average"]
    best = scoreboard["best"]
    worst = scoreboard["worst"]
    market = scoreboard["market"]
    teacher = scoreboard["teacher"]

    if avg > teacher:
        analysis.append("🔥 Strong: Beat the Teacher.")
    elif avg > market:
        analysis.append("👍 Good: Beat the market, but not the Teacher.")
    else:
        analysis.append("⚠️ ETF strategy would have done better.")

    if best[1] > avg * 2:
        analysis.append("⚠️ One holding is driving most of the gains. That can mean concentration risk.")

    if worst[1] < 0:
        analysis.append("❌ A losing position is pulling results down.")

    if scoreboard["win_rate"] == 100:
        analysis.append("💪 Excellent consistency: all detected positions are positive.")

    if len(results) < 3:
        analysis.append("⚠️ Very small basket: not much diversification.")

    return analysis


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
            error = "Please enter a student name."
            return render_template("index.html", pods=pods, error=error)

        if pod not in {"A", "B", "C"}:
            error = "Please choose Pod A, B, or C."
            return render_template("index.html", pods=pods, error=error)

        if not file or file.filename == "":
            error = "Please upload a screenshot."
            return render_template("index.html", pods=pods, error=error)

        if not allowed_file(file.filename):
            error = "Please upload a PNG, JPG, JPEG, or WEBP image."
            return render_template("index.html", pods=pods, error=error)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        try:
            results = extract_results(filepath)
            scoreboard = create_scoreboard(results)

            if not scoreboard:
                error = "I couldn't find enough usable portfolio data in that screenshot."
                return render_template("index.html", pods=pods, error=error)

            analysis = generate_teacher_analysis(results, scoreboard)

            pods[pod] = [p for p in pods[pod] if p["name"].lower() != name.lower()]

            if len(pods[pod]) < 10 or any(p["name"].lower() == name.lower() for p in pods[pod]):
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
            else:
                error = f"Pod {pod} already has 10 students."

        except Exception as e:
            print("ERROR:", e)
            error = "Could not read that image. Try a cleaner screenshot of the positions table."

    return render_template(
        "index.html",
        scoreboard=scoreboard,
        pods=pods,
        analysis=analysis,
        error=error,
        selected_player=selected_player,
    )


@app.route("/child/<pod>/<name>")
def view_child(pod, name):
    global pods

    if pod not in pods:
        return "Pod not found", 404

    player = None
    for p in pods[pod]:
        if p["name"].lower() == name.lower():
            player = p
            break

    if not player:
        return "Student not found", 404

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


@app.route("/reset")
def reset():
    global pods
    pods = {"A": [], "B": [], "C": []}
    save_pods(pods)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False)
