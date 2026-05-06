"""
Dashboard Routes — Main analytics overview
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from database import db, Product, Sale, Forecast
from sqlalchemy import func
from datetime import date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Main dashboard page."""
    uid = current_user.id
    today = date.today()
    month_start = today.replace(day=1)

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    total_products = Product.query.filter_by(user_id=uid).count()
    low_stock      = Product.query.filter(
        Product.user_id == uid,
        Product.quantity <= Product.low_stock_threshold
    ).count()
    out_of_stock   = Product.query.filter_by(user_id=uid, quantity=0).count()

    # Total sales revenue (all time)
    total_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid).scalar() or 0

    # Sales revenue this month
    monthly_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid, Sale.sale_date >= month_start).scalar() or 0

    # Today's sales
    today_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid, Sale.sale_date == today).scalar() or 0

    # ── Top 5 Products (by qty sold, all time) ────────────────────────────────
    top_products = db.session.query(
        Product.name,
        func.sum(Sale.quantity_sold).label('total_sold'),
        func.sum(Sale.total_amount).label('total_revenue')
    ).join(Sale, Sale.product_id == Product.id)\
     .filter(Sale.user_id == uid)\
     .group_by(Product.id)\
     .order_by(func.sum(Sale.quantity_sold).desc())\
     .limit(5).all()

    # ── Low Stock Products ────────────────────────────────────────────────────
    low_stock_products = Product.query.filter(
        Product.user_id == uid,
        Product.quantity <= Product.low_stock_threshold
    ).order_by(Product.quantity.asc()).limit(8).all()

    # ── Last 7 Days Sales Trend ───────────────────────────────────────────────
    seven_days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = db.session.query(func.sum(Sale.total_amount))\
            .filter(Sale.user_id == uid, Sale.sale_date == d).scalar() or 0
        seven_days.append({'date': d.strftime('%d %b'), 'revenue': round(rev, 2)})

    # ── Category Distribution ─────────────────────────────────────────────────
    cat_rows = db.session.query(
        Product.category,
        func.count(Product.id).label('count')
    ).filter(Product.user_id == uid)\
     .group_by(Product.category).all()

    # Convert to plain list of dicts (JSON serializable)
    cat_data = [{'category': row[0], 'count': row[1]} for row in cat_rows]

    # Convert top_products to plain dicts (JSON serializable)
    top_products_list = [
        {'name': r[0], 'total_sold': int(r[1]), 'total_revenue': float(r[2])}
        for r in top_products
    ]

    return render_template('dashboard.html',
        total_products=total_products,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        total_revenue=round(total_revenue, 2),
        monthly_revenue=round(monthly_revenue, 2),
        today_revenue=round(today_revenue, 2),
        top_products=top_products_list,
        low_stock_products=low_stock_products,
        seven_days=seven_days,
        cat_data=cat_data,
        now=today,
    )


@dashboard_bp.route('/api/dashboard/kpis')
@login_required
def api_kpis():
    """JSON endpoint for live KPI refresh."""
    uid = current_user.id
    today = date.today()

    total_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid).scalar() or 0
    today_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid, Sale.sale_date == today).scalar() or 0
    low_stock = Product.query.filter(
        Product.user_id == uid,
        Product.quantity <= Product.low_stock_threshold
    ).count()

    return jsonify({
        'total_revenue': round(total_revenue, 2),
        'today_revenue': round(today_revenue, 2),
        'low_stock_count': low_stock,
    })