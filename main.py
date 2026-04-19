import sqlite3
import secrets
import hashlib
import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB_PATH = os.environ.get("DB_PATH", "poop.db")

BRISTOL_TYPES = list(range(1, 9))  # 1-8

EFFORT_ICONS = {
    1: "",   # easy
    2: "😐",   # normal
    3: "😣",   # hard
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS poops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    # Migrate: add bristol_type and effort columns
    try:
        conn.execute("ALTER TABLE poops ADD COLUMN bristol_type INTEGER DEFAULT 4")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE poops ADD COLUMN effort INTEGER DEFAULT 2")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, key_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return key.hex() == key_hex


@app.on_event("startup")
def startup():
    init_db()


def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT u.id, u.username FROM users u "
        "JOIN sessions s ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "username": row["username"]}
    return None


# --- Auth routes ---


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not row or not verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Неверное имя пользователя или пароль"},
        )

    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, row["id"])
    )
    conn.commit()
    conn.close()

    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=10 * 365 * 24 * 3600)
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "register.html", {"error": None})


@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        conn.close()
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Пользователь уже существует"},
        )

    pw_hash = hash_password(password)
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, pw_hash),
    )
    user_id = cursor.lastrowid
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id)
    )
    conn.commit()
    conn.close()

    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=10 * 365 * 24 * 3600)
    return response


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# --- App routes ---


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    success = request.query_params.get("success")
    return templates.TemplateResponse(
        request, "home.html", {"user": user, "just_pooped": success == "1"}
    )


@app.post("/poop")
def record_poop(
    request: Request,
    bristol_type: int = Form(...),
    effort: int = Form(...),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    bristol_type = max(1, min(8, bristol_type))
    effort = max(1, min(3, effort))

    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO poops (user_id, timestamp, bristol_type, effort) VALUES (?, ?, ?, ?)",
        (user["id"], now, bristol_type, effort),
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/?success=1", status_code=303)


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    since = (datetime.now() - timedelta(days=13)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    conn = get_db()
    rows = conn.execute(
        "SELECT timestamp, bristol_type, effort FROM poops WHERE user_id = ? AND timestamp >= ? "
        "ORDER BY timestamp DESC",
        (user["id"], since.isoformat()),
    ).fetchall()
    conn.close()

    # Build day buckets
    days_map: dict[str, list] = {}
    for i in range(14):
        day = (datetime.now() - timedelta(days=i)).date()
        days_map[day.isoformat()] = []

    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"])
        day_key = ts.date().isoformat()
        if day_key in days_map:
            position = (ts.hour * 60 + ts.minute) / (24 * 60) * 100
            bt = row["bristol_type"] or 4
            ef = row["effort"] or 2
            days_map[day_key].append({
                "time": ts.strftime("%H:%M"),
                "position": position,
                "bristol_type": bt,
                "effort_icon": EFFORT_ICONS.get(ef, "😐"),
            })

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    calendar_days = []
    for i in range(14):
        day = (datetime.now() - timedelta(days=i)).date()
        calendar_days.append(
            {
                "date_str": day.strftime("%d.%m.%Y"),
                "weekday": weekdays[day.weekday()],
                "poops": days_map[day.isoformat()],
            }
        )

    return templates.TemplateResponse(
        request, "calendar.html", {"user": user, "days": calendar_days}
    )
