import csv
import io
import json
import os
import uuid
from datetime import datetime

from flask import Flask, Response, redirect, render_template, request, url_for

app = Flask(__name__)
DATA_FILE = "data.json"


def default_data():
    today = datetime.now().strftime("%Y-%m-%d")
    month_prefix = datetime.now().strftime("%Y-%m")
    return {
        "currency": "$",
        "budget_alerts": True,
        "categories": [
            {"id": "food", "name": "Comida", "icon": "restaurant"},
            {"id": "leisure", "name": "Ocio", "icon": "sports_esports"},
            {"id": "bills", "name": "Facturas", "icon": "receipt_long"},
            {"id": "transport", "name": "Transporte", "icon": "directions_car"},
        ],
        "budgets": {
            "food": 600,
            "leisure": 250,
            "bills": 500,
            "transport": 180,
        },
        "goals": [
            {"id": "g1", "name": "Vacaciones", "target": 1200, "saved": 450},
            {"id": "g2", "name": "Nuevo Laptop", "target": 1800, "saved": 700},
        ],
        "transactions": [
            {
                "id": "t1",
                "description": "Salario",
                "amount": 2200,
                "kind": "income",
                "category_id": "bills",
                "date": f"{month_prefix}-01",
            },
            {
                "id": "t2",
                "description": "Blue Bottle Coffee",
                "amount": 6.5,
                "kind": "expense",
                "category_id": "food",
                "date": today,
            },
            {
                "id": "t3",
                "description": "Luigi's Pizzeria",
                "amount": 42,
                "kind": "expense",
                "category_id": "food",
                "date": f"{month_prefix}-02",
            },
            {
                "id": "t4",
                "description": "Internet",
                "amount": 45,
                "kind": "expense",
                "category_id": "bills",
                "date": f"{month_prefix}-03",
            },
        ],
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        data = default_data()
        save_data(data)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def category_map(data):
    return {c["id"]: c for c in data["categories"]}


def month_key(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m")


def dashboard_metrics(data):
    current_month = month_key()
    month_txs = [t for t in data["transactions"] if t["date"].startswith(current_month)]
    income_month = sum(t["amount"] for t in month_txs if t["kind"] == "income")
    expense_month = sum(t["amount"] for t in month_txs if t["kind"] == "expense")
    total_income = sum(t["amount"] for t in data["transactions"] if t["kind"] == "income")
    total_expense = sum(t["amount"] for t in data["transactions"] if t["kind"] == "expense")
    balance = total_income - total_expense

    c_map = category_map(data)
    category_spend = {}
    for t in month_txs:
        if t["kind"] != "expense":
            continue
        cid = t["category_id"]
        category_spend[cid] = category_spend.get(cid, 0) + t["amount"]

    chart_rows = []
    for cid, spent in sorted(category_spend.items(), key=lambda item: item[1], reverse=True):
        name = c_map.get(cid, {"name": cid})["name"]
        chart_rows.append({"category": name, "amount": spent})

    return {
        "balance": balance,
        "income_month": income_month,
        "expense_month": expense_month,
        "chart_rows": chart_rows,
    }


def budget_rows(data):
    c_map = category_map(data)
    current_month = month_key()
    spent_by_category = {}
    for t in data["transactions"]:
        if t["kind"] == "expense" and t["date"].startswith(current_month):
            cid = t["category_id"]
            spent_by_category[cid] = spent_by_category.get(cid, 0) + t["amount"]

    rows = []
    for c in data["categories"]:
        cid = c["id"]
        limit = float(data["budgets"].get(cid, 0))
        spent = float(spent_by_category.get(cid, 0))
        pct = (spent / limit * 100) if limit > 0 else 0
        status = "ok"
        if pct >= 100:
            status = "danger"
        elif pct >= 75:
            status = "warning"
        rows.append(
            {
                "id": cid,
                "name": c["name"],
                "icon": c["icon"],
                "limit": limit,
                "spent": spent,
                "pct": min(pct, 100) if limit > 0 else 0,
                "status": status,
            }
        )
    return rows


def trend_rows(data):
    now = datetime.now()
    months = []
    year = now.year
    month = now.month
    for _ in range(6):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()

    rows = []
    for m in months:
        expense = sum(
            t["amount"] for t in data["transactions"] if t["kind"] == "expense" and t["date"].startswith(m)
        )
        income = sum(
            t["amount"] for t in data["transactions"] if t["kind"] == "income" and t["date"].startswith(m)
        )
        rows.append({"month": m, "income": income, "expense": expense, "net": income - expense})
    return rows


@app.route("/")
def dashboard():
    data = load_data()
    metrics = dashboard_metrics(data)
    recent = sorted(data["transactions"], key=lambda t: t["date"], reverse=True)[:6]
    return render_template(
        "dashboard.html",
        data=data,
        metrics=metrics,
        recent=recent,
        category_map=category_map(data),
        budget_rows=budget_rows(data),
    )


@app.route("/expense", methods=["GET", "POST"])
def add_expense():
    data = load_data()
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        amount_raw = request.form.get("amount", "0").strip()
        kind = request.form.get("kind", "expense")
        category_id = request.form.get("category_id", "")
        tx_date = request.form.get("date", datetime.now().strftime("%Y-%m-%d"))

        if description and category_id:
            try:
                amount = float(amount_raw)
            except ValueError:
                amount = 0
            if amount > 0:
                data["transactions"].append(
                    {
                        "id": uuid.uuid4().hex[:8],
                        "description": description,
                        "amount": amount,
                        "kind": "income" if kind == "income" else "expense",
                        "category_id": category_id,
                        "date": tx_date,
                    }
                )
                save_data(data)
        return redirect(url_for("history"))

    return render_template("add_expense.html", data=data)


@app.route("/budgets", methods=["GET", "POST"])
def budgets():
    data = load_data()
    if request.method == "POST":
        category_id = request.form.get("category_id", "")
        limit_raw = request.form.get("limit", "0").strip()
        try:
            limit = float(limit_raw)
        except ValueError:
            limit = 0
        if category_id:
            data["budgets"][category_id] = max(0, limit)
            save_data(data)
        return redirect(url_for("budgets"))

    return render_template("budgets.html", data=data, rows=budget_rows(data))


@app.route("/goals", methods=["GET", "POST"])
def goals():
    data = load_data()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("name", "").strip()
            try:
                target = float(request.form.get("target", "0"))
            except ValueError:
                target = 0
            if name and target > 0:
                data["goals"].append(
                    {
                        "id": uuid.uuid4().hex[:8],
                        "name": name,
                        "target": target,
                        "saved": 0,
                    }
                )
                save_data(data)
        elif action == "contribute":
            goal_id = request.form.get("goal_id", "")
            try:
                amount = float(request.form.get("amount", "0"))
            except ValueError:
                amount = 0
            if amount > 0:
                for goal in data["goals"]:
                    if goal["id"] == goal_id:
                        goal["saved"] = min(goal["target"], goal["saved"] + amount)
                        break
                save_data(data)
        return redirect(url_for("goals"))

    return render_template("goals.html", data=data)


@app.route("/history")
def history():
    data = load_data()
    q = request.args.get("q", "").strip().lower()
    category_id = request.args.get("category_id", "")
    kind = request.args.get("kind", "")
    month = request.args.get("month", "")

    txs = list(data["transactions"])
    if q:
        txs = [t for t in txs if q in t["description"].lower()]
    if category_id:
        txs = [t for t in txs if t["category_id"] == category_id]
    if kind in ("income", "expense"):
        txs = [t for t in txs if t["kind"] == kind]
    if month:
        txs = [t for t in txs if t["date"].startswith(month)]

    txs.sort(key=lambda t: t["date"], reverse=True)
    return render_template(
        "history.html",
        data=data,
        transactions=txs,
        trends=trend_rows(data),
        category_map=category_map(data),
        filters={"q": q, "category_id": category_id, "kind": kind, "month": month},
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    data = load_data()
    if request.method == "POST":
        action = request.form.get("action", "general")
        if action == "general":
            currency = request.form.get("currency", "$").strip() or "$"
            data["currency"] = currency
            data["budget_alerts"] = request.form.get("budget_alerts") == "on"
        elif action == "category":
            name = request.form.get("name", "").strip()
            icon = request.form.get("icon", "category").strip() or "category"
            if name:
                slug = name.lower().replace(" ", "-")
                cid = f"{slug}-{uuid.uuid4().hex[:4]}"
                data["categories"].append({"id": cid, "name": name, "icon": icon})
                data["budgets"][cid] = 0
        save_data(data)
        return redirect(url_for("settings"))
    return render_template("settings.html", data=data)


@app.route("/export")
def export_csv():
    data = load_data()
    c_map = category_map(data)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "type", "description", "category", "amount"])
    for t in sorted(data["transactions"], key=lambda x: x["date"]):
        writer.writerow(
            [
                t["id"],
                t["date"],
                t["kind"],
                t["description"],
                c_map.get(t["category_id"], {"name": t["category_id"]})["name"],
                t["amount"],
            ]
        )
    csv_data = output.getvalue()
    filename = f"finanzas_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    app.run(debug=True)
