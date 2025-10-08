
import os
import csv
import sqlite3
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template, send_from_directory, flash, abort
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
ADMIN_KEY = os.environ.get("ADMIN_KEY", "letmein")  # simple guard for CSV import

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    con = sqlite3.connect("site.db")
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cur = con.cursor()
    # Who is eligible to vote (from spreadsheet import)
    # cur.execute("""
    # DROP TABLE IF EXISTS voter;
    # """)
    # cur.execute("""
    # DROP TABLE IF EXISTS contestant;
    # """)
    # cur.execute("""
    # DROP TABLE IF EXISTS vote;
    # """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS voter (
        email TEXT PRIMARY KEY,
        name  TEXT,
        created_at TEXT NOT NULL
    );
    """)
    # Photo submissions (contestants)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS contestant (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        caption TEXT,
        email TEXT NOT NULL,
        photo_path TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    # One vote per voter.email
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vote (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voter_email TEXT UNIQUE NOT NULL,
        voted_contestant_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (voter_email) REFERENCES voter(email),
        FOREIGN KEY (voted_contestant_id) REFERENCES contestant(id)
    );
    """)
    con.commit()
    con.close()

init_db()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB
@app.route("/upload", methods=["GET"])
def upload_page():
    return render_template("upload.html")

@app.route("/vote", methods=["GET"])
def vote_page():
    # simple login form; after submit it posts to /begin-vote (you already have it)
    return render_template("vote_login.html")

@app.route("/")
def home():
    con = get_db()
    contestants = con.execute("SELECT * FROM contestant ORDER BY id ASC").fetchall()
    voter = con.execute("SELECT * FROM voter").fetchall()
    con.close()
    return render_template("home.html", contestants=contestants,voter=voter)

@app.route("/upload", methods=["POST"])
def upload():
    name = (request.form.get("name")).strip() 
    caption = (request.form.get("caption") or "").strip() or None
    file = request.files.get("photo")
    email = (request.form.get("email")).strip()

    if not file or file.filename == "":
        flash("Please choose a photo.", "error") 
        return redirect(url_for("home"))
    if not allowed_file(file.filename):
        flash("Unsupported file type.", "error")
        return redirect(url_for("home"))
    if name is None:
        flash("Please enter your name.", "error")
        return redirect(url_for("home"))
    if email is None:
        flash("Please enter your email.", "error")
        return redirect(url_for("home"))

    ext = file.filename.rsplit(".", 1)[1].lower()
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{ts}.{ext}"
    save_path = os.path.join("static", "uploads", filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    con = get_db()
    try:
        is_voter = con.execute("SELECT * FROM voter WHERE email=?", (email,))
        has_uploaded = con.execute("SELECT * FROM contestant WHERE email=?", (email,)).fetchone()
        if (is_voter.fetchone() is None):
            flash("Email not found in participant list. Ask the host to add you.", "error")
            return redirect(url_for("home"))
        if (has_uploaded is not None):
            flash("You have already submitted a photo.", "error")
            return redirect(url_for("home"))
        con.execute(
            "INSERT INTO contestant (name, email,caption, photo_path, created_at) VALUES (?, ? , ?, ?, ?)",
            (name, email, caption, save_path, datetime.now().strftime("%Y%m%d%H%M%S%f")),
        )
        con.commit()
        flash("Upload successful! Share the vote page with your friends so they can vote with their email.", "info")
    except Exception as e:
        con.rollback()
        print(e)
        flash("Failed to insert into database.", "error")
    finally:
        con.close()

    return redirect(url_for("home"))

@app.route("/begin-vote", methods=["POST"])
def begin_vote():
    email = (request.form.get("email") or "").strip().lower()
    last4 = (request.form.get("last4") or "").strip()
    if not email:
        flash("Please enter your email.", "error")
        return redirect(url_for("home"))

    con = get_db()
    voter = con.execute("SELECT * FROM voter WHERE lower(email)=?", (email,)).fetchone()
    if not voter:
        con.close()
        flash("Email not found in participant list. Ask the host to add you.", "error")
        return redirect(url_for("home"))

    already = con.execute("SELECT voted_contestant_id FROM vote WHERE voter_email = ?", (voter["email"],)).fetchone()
    # Prepare list with vote counts
    contestants = con.execute("""
        SELECT c.*,
               COALESCE(v.cnt, 0) AS votes
        FROM contestant c
        LEFT JOIN (SELECT voted_contestant_id, COUNT(*) AS cnt FROM vote GROUP BY voted_contestant_id) v
        ON v.voted_contestant_id = c.id
        ORDER BY votes DESC, c.id ASC;
    """).fetchall()
    con.close()
    return render_template("vote.html", email=voter["email"], name=voter["name"], already=already, contestants=contestants)

@app.route("/cast_vote/<int:cid>", methods=["POST"])
def cast_vote(cid):
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        abort(400, "Missing email")
    con = get_db()
    voter = con.execute("SELECT 1 FROM voter WHERE lower(email)=?", (email,)).fetchone()
    if not voter:
        con.close()
        abort(403, "Unauthorized voter")
    target = con.execute("SELECT 1 FROM contestant WHERE id=?", (cid,)).fetchone()
    if not target:
        con.close()
        abort(404, "Contestant not found")
    try:
        con.execute(
            "INSERT INTO vote (voter_email, voted_contestant_id, created_at) VALUES (?, ?, ?)",
            (email, cid, datetime.now().strftime("%Y%m%d%H%M%S%f"))
        )
        con.commit()
        flash("Vote cast!","info")
    except sqlite3.IntegrityError:
        flash("You have already voted.", "error")
    finally:
        con.close()
    return redirect(url_for("home"))

@app.route("/rankings")
def rankings():
    con = get_db()
    rows = con.execute("""
        SELECT c.*, COALESCE(v.cnt, 0) AS votes
        FROM contestant c
        LEFT JOIN (SELECT voted_contestant_id, COUNT(*) AS cnt FROM vote GROUP BY voted_contestant_id) v
        ON v.voted_contestant_id = c.id
        ORDER BY votes DESC, c.id ASC
        LIMIT 10;
    """).fetchall()
    con.close()
    return render_template("rankings.html", top=rows)

@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    # Upload a CSV (columns: email, name) to load/refresh eligible voters
    key = request.args.get("key")
    if key != ADMIN_KEY:
        abort(403, "Invalid key")
    if request.method == "GET":
        return render_template("admin_import.html", key=key)
    file = request.files.get("csv")
    if not file or not file.filename.endswith(".csv"):
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("admin_import", key=key))

    added = 0
    reader = csv.DictReader((line.decode("utf-8-sig") for line in file.stream))
    con = get_db()
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        name  = (row.get("name")  or "").strip()
        if not email:
            continue
        con.execute("""
            INSERT INTO voter (email, name, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET name=excluded.name
        """, (email, name, datetime.utcnow().isoformat(timespec="seconds")))
        added += 1
    con.commit()
    con.close()
    flash(f"Imported/updated {added} voters.", "info")
    return redirect(url_for("admin_import", key=key))

@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(os.path.join("static", "uploads"), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
