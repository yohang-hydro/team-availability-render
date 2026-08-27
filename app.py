import os
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort

load_dotenv()


def running_in_production():
    return os.environ.get("RENDER") == "true" or os.environ.get("FLASK_ENV") == "production"


if running_in_production():
    if not os.environ.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is required in production.")
    if not os.environ.get("ADMIN_PASSWORD"):
        raise RuntimeError("ADMIN_PASSWORD is required in production.")
    if not os.environ.get("TEAM_ACCESS_CODE"):
        raise RuntimeError("TEAM_ACCESS_CODE is required in production.")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
TEAM_ACCESS_CODE = os.environ.get("TEAM_ACCESS_CODE", "team")

OPEN_ENDPOINTS = {
    "access",
    "static",
    "health",
    "admin",
    "admin_settings",
    "admin_add",
    "admin_delete",
    "admin_reset",
}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
# Half-hour availability blocks from 09:00–09:30 through 16:30–17:00.
SLOTS = [f"{h:02d}:{m:02d}" for h in range(9, 17) for m in (0, 30)]


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Add your PostgreSQL connection string as an environment variable.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with db() as con:
        with con.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS participants (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    submitted_at TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS availability (
                    participant_id BIGINT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                    day TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    PRIMARY KEY (participant_id, day, slot)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            defaults = {
                "title": "Find a Meeting Time",
                "description": "Select all times that work for you. We will combine everyone’s availability to find the best overlap.",
            }
            for key, value in defaults.items():
                cur.execute(
                    "INSERT INTO settings(key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (key, value),
                )


def get_settings():
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        rows = cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


def overlap_data():
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT id, name, submitted_at FROM participants ORDER BY name")
        people = cur.fetchall()
        submitted = [p for p in people if p["submitted_at"] is not None]
        cur.execute("SELECT participant_id, day, slot FROM availability")
        rows = cur.fetchall()

    selected = {(r["participant_id"], r["day"], r["slot"]) for r in rows}
    counts = {d: {s: 0 for s in SLOTS} for d in DAYS}
    names = {d: {s: [] for s in SLOTS} for d in DAYS}

    for p in submitted:
        for d in DAYS:
            for s in SLOTS:
                if (p["id"], d, s) in selected:
                    counts[d][s] += 1
                    names[d][s].append(p["name"])
    return people, submitted, counts, names


@app.route("/access", methods=["GET", "POST"])
def access():
    if session.get("team_access") and request.method == "GET":
        return redirect(url_for("index"))

    if request.method == "POST":
        code = request.form.get("access_code", "")
        if secrets.compare_digest(code, TEAM_ACCESS_CODE):
            session["team_access"] = True
            return redirect(url_for("index"))
        return render_template("access.html", error="Incorrect access code.")

    return render_template("access.html", error=None)


@app.before_request
def require_team_access():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if not session.get("team_access"):
        return redirect(url_for("access"))


@app.get("/")
def index():
    settings = get_settings()
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT name, submitted_at FROM participants ORDER BY name")
        people = cur.fetchall()
    return render_template("index.html", days=DAYS, slots=SLOTS, settings=settings, people=people)


@app.get("/api/person/<path:name>")
def person(name):
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT id, submitted_at FROM participants WHERE name = %s", (name.strip(),))
        p = cur.fetchone()
        if not p:
            return jsonify({"name": name, "selected": [], "submitted": False})
        cur.execute("SELECT day, slot FROM availability WHERE participant_id = %s", (p["id"],))
        rows = cur.fetchall()
    return jsonify(
        {
            "name": name,
            "selected": [[r["day"], r["slot"]] for r in rows],
            "submitted": bool(p["submitted_at"]),
        }
    )


@app.post("/api/save")
def save():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    selected = data.get("selected") or []
    if not name or len(name) > 80:
        return jsonify({"error": "Please enter your name."}), 400

    clean = {(d, s) for d, s in selected if d in DAYS and s in SLOTS}
    with db() as con, con.cursor() as cur:
        cur.execute(
            "INSERT INTO participants(name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (name,),
        )
        cur.execute("SELECT id FROM participants WHERE name = %s", (name,))
        p = cur.fetchone()
        cur.execute("DELETE FROM availability WHERE participant_id = %s", (p["id"],))
        cur.executemany(
            "INSERT INTO availability(participant_id, day, slot) VALUES (%s, %s, %s)",
            [(p["id"], d, s) for d, s in sorted(clean)],
        )
        cur.execute(
            "UPDATE participants SET submitted_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), p["id"]),
        )
    return jsonify({"ok": True})


@app.get("/api/overlap")
def overlap():
    people, submitted, counts, names = overlap_data()
    return jsonify(
        {
            "total_people": len(people),
            "responses": len(submitted),
            "pending": [p["name"] for p in people if p["submitted_at"] is None],
            "counts": counts,
            "names": names,
        }
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and "password" in request.form:
        if secrets.compare_digest(request.form["password"], ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="Incorrect password")

    if not session.get("admin"):
        return render_template("admin_login.html", error=None)

    with db() as con, con.cursor() as cur:
        cur.execute("SELECT id, name, submitted_at FROM participants ORDER BY name")
        people = cur.fetchall()
    return render_template("admin.html", people=people, settings=get_settings())


@app.post("/admin/settings")
def admin_settings():
    if not session.get("admin"):
        abort(403)
    allowed = {"title", "description"}
    with db() as con, con.cursor() as cur:
        for key in allowed:
            if key in request.form:
                cur.execute(
                    """
                    INSERT INTO settings(key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (key, request.form[key]),
                )
    return redirect(url_for("admin"))


@app.post("/admin/add")
def admin_add():
    if not session.get("admin"):
        abort(403)
    names = request.form.get("names", "").replace(",", "\n").splitlines()
    with db() as con, con.cursor() as cur:
        for name in names:
            name = name.strip()
            if name:
                cur.execute(
                    "INSERT INTO participants(name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                    (name,),
                )
    return redirect(url_for("admin"))


@app.post("/admin/delete/<int:pid>")
def admin_delete(pid):
    if not session.get("admin"):
        abort(403)
    with db() as con, con.cursor() as cur:
        cur.execute("DELETE FROM participants WHERE id = %s", (pid,))
    return redirect(url_for("admin"))


@app.post("/admin/reset")
def admin_reset():
    if not session.get("admin"):
        abort(403)
    with db() as con, con.cursor() as cur:
        cur.execute("DELETE FROM availability")
        cur.execute("UPDATE participants SET submitted_at = NULL")
    return redirect(url_for("admin"))


@app.get("/health")
def health():
    try:
        with db() as con, con.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return {"ok": True}
    except Exception:
        return {"ok": False}, 503


# Gunicorn imports the module rather than executing __main__, so initialise here.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
