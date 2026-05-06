"""
AI Copilot (optional) — safe, read-only insights.

This implementation is local-only and does not call any external LLM.
It supports a small set of intents and returns data-driven answers.
"""

from datetime import date, timedelta

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from database import db, Product, Sale


copilot_bp = Blueprint("copilot", __name__)


@copilot_bp.route("/copilot")
@login_required
def copilot_page():
    return render_template("copilot.html")


def _kpis(uid: int):
    today = date.today()
    month_start = today.replace(day=1)
    total_revenue = db.session.query(func.sum(Sale.total_amount)).filter(Sale.user_id == uid).scalar() or 0
    monthly_revenue = db.session.query(func.sum(Sale.total_amount)).filter(Sale.user_id == uid, Sale.sale_date >= month_start).scalar() or 0
    low_stock = Product.query.filter(Product.user_id == uid, Product.quantity <= Product.low_stock_threshold).count()
    return {
        "total_revenue": round(float(total_revenue), 2),
        "monthly_revenue": round(float(monthly_revenue), 2),
        "low_stock_count": int(low_stock),
    }


@copilot_bp.route("/api/copilot/ask", methods=["POST"])
@login_required
def ask():
    uid = current_user.id
    q = (request.get_json() or {}).get("q", "")
    qn = (q or "").strip().lower()

    if not qn:
        return jsonify({"answer": "Try: 'kpis', 'sales last 7 days', 'top products', 'top categories', 'reorder today', 'forecast <product name>'."})

    # Intent: KPIs
    if "kpi" in qn or "revenue" in qn or "sales" in qn and "today" in qn:
        k = _kpis(uid)
        return jsonify({"answer": f"Total revenue: ₹{k['total_revenue']}, this month: ₹{k['monthly_revenue']}, low-stock items: {k['low_stock_count']}."})

    # Intent: reorder suggestions (simple heuristic)
    if "reorder" in qn or "restock" in qn:
        products = Product.query.filter_by(user_id=uid).order_by(Product.quantity.asc()).limit(10).all()
        picks = [p for p in products if p.quantity <= p.low_stock_threshold]
        if not picks:
            return jsonify({"answer": "Nothing urgent. All products are above their low-stock thresholds."})
        lines = [f"- {p.name}: {p.quantity} left (threshold {p.low_stock_threshold})" for p in picks[:8]]
        return jsonify({"answer": "Reorder these items:\n" + "\n".join(lines)})

    # Intent: expiring stock
    if "expiry" in qn or "expiring" in qn:
        return jsonify({"answer": "Expiry/batch tracking is disabled in this build."})

    # Intent: sales last N days
    if "sales last" in qn and "day" in qn:
        # parse a small integer like "sales last 7 days"
        n = 7
        parts = qn.replace(",", " ").split()
        for i, tok in enumerate(parts):
            if tok.isdigit() and i + 1 < len(parts) and parts[i + 1].startswith("day"):
                n = max(1, min(365, int(tok)))
                break
        today = date.today()
        start = today - timedelta(days=n - 1)
        rows = db.session.query(
            Sale.sale_date,
            func.sum(Sale.total_amount).label("revenue"),
            func.sum(Sale.quantity_sold).label("qty"),
        ).filter(Sale.user_id == uid, Sale.sale_date >= start, Sale.sale_date <= today)\
         .group_by(Sale.sale_date).order_by(Sale.sale_date).all()
        total_rev = sum(float(r.revenue or 0) for r in rows)
        total_qty = sum(int(r.qty or 0) for r in rows)
        lines = [f"- {r.sale_date}: ₹{round(float(r.revenue or 0), 2)} ({int(r.qty or 0)} units)" for r in rows[-14:]]
        return jsonify({"answer": f"Sales last {n} days: ₹{round(total_rev,2)} revenue, {total_qty} units.\n" + ("\n".join(lines) if lines else "No sales in this period.")})

    # Intent: top categories
    if "top" in qn and ("category" in qn or "categories" in qn):
        rows = db.session.query(
            Product.category,
            func.sum(Sale.total_amount).label("revenue"),
        ).join(Sale, Sale.product_id == Product.id)\
         .filter(Sale.user_id == uid)\
         .group_by(Product.category)\
         .order_by(func.sum(Sale.total_amount).desc()).limit(5).all()
        if not rows:
            return jsonify({"answer": "No sales yet, so I can’t rank top categories."})
        lines = [f"- {r.category}: ₹{round(float(r.revenue), 2)}" for r in rows]
        return jsonify({"answer": "Top categories by revenue:\n" + "\n".join(lines)})

    # Intent: forecast by product name (uses Forecast v2)
    if qn.startswith("forecast"):
        name = qn.replace("forecast", "", 1).strip()
        if not name:
            return jsonify({"answer": "Use: forecast <product name>. Example: forecast rice"})
        product = Product.query.filter(Product.user_id == uid, Product.name.ilike(f"%{name}%")).order_by(Product.name.asc()).first()
        if not product:
            return jsonify({"answer": f"I couldn't find a product matching '{name}'."})

        sales_rows = db.session.query(
            Sale.sale_date,
            func.sum(Sale.quantity_sold).label("qty")
        ).filter(Sale.user_id == uid, Sale.product_id == product.id)\
         .group_by(Sale.sale_date).order_by(Sale.sale_date).all()
        if len(sales_rows) < 7:
            return jsonify({"answer": f"Not enough history to forecast {product.name} (need 7+ days)."})

        from ml.forecasting import best_forecast
        history = {str(r.sale_date): float(r.qty) for r in sales_rows}
        res = best_forecast(history, horizon=14)
        total = sum(float(x["predicted_qty"]) for x in res["forecast"])
        avg = total / 14.0
        return jsonify({"answer": f"Forecast for {product.name} (14 days): {round(total,1)} units total (~{round(avg,2)}/day). Model: {res.get('model_used')}."})

    # Intent: top products
    if "top" in qn and ("product" in qn or "products" in qn):
        rows = db.session.query(
            Product.name,
            func.sum(Sale.total_amount).label("revenue"),
            func.sum(Sale.quantity_sold).label("qty"),
        ).join(Sale, Sale.product_id == Product.id).filter(Sale.user_id == uid)\
         .group_by(Product.id).order_by(func.sum(Sale.total_amount).desc()).limit(5).all()
        if not rows:
            return jsonify({"answer": "No sales yet, so I can’t rank top products."})
        lines = [f"- {r.name}: ₹{round(float(r.revenue), 2)} ({int(r.qty)} units)" for r in rows]
        return jsonify({"answer": "Top products by revenue:\n" + "\n".join(lines)})

    return jsonify({"answer": "I didn't understand that. Try one of these:\n\n  kpis\n  sales last 7 days\n  top products\n  top categories\n  reorder\n  forecast <product name>\n\nExample: 'forecast rice' or 'sales last 30 days'"})

