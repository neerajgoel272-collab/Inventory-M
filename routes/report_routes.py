"""
Reports & Analytics Routes
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from database import db, Product, Sale
from sqlalchemy import func
from datetime import date, timedelta

report_bp = Blueprint('reports', __name__)


@report_bp.route('/reports')
@login_required
def index():
    """Reports & analytics page."""
    return render_template('reports.html')


@report_bp.route('/api/reports/summary')
@login_required
def api_summary():
    """Overall business summary statistics."""
    uid   = current_user.id
    today = date.today()

    # Revenue totals
    total_revenue = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid).scalar() or 0

    # This month
    month_start = today.replace(day=1)
    monthly_rev = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid, Sale.sale_date >= month_start).scalar() or 0
    monthly_qty = db.session.query(func.sum(Sale.quantity_sold))\
        .filter(Sale.user_id == uid, Sale.sale_date >= month_start).scalar() or 0

    # Last month comparison
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_rev = db.session.query(func.sum(Sale.total_amount))\
        .filter(Sale.user_id == uid,
                Sale.sale_date >= last_month_start,
                Sale.sale_date <= last_month_end).scalar() or 0

    month_growth = ((monthly_rev - last_month_rev) / last_month_rev * 100) \
        if last_month_rev > 0 else 0

    # Total transactions
    total_tx = Sale.query.filter_by(user_id=uid).count()
    avg_tx   = total_revenue / total_tx if total_tx > 0 else 0

    return jsonify({
        'total_revenue': round(total_revenue, 2),
        'monthly_revenue': round(monthly_rev, 2),
        'monthly_qty': monthly_qty or 0,
        'last_month_revenue': round(last_month_rev, 2),
        'month_growth_pct': round(month_growth, 1),
        'total_transactions': total_tx,
        'avg_transaction_value': round(avg_tx, 2),
    })


@report_bp.route('/api/reports/monthly-trend')
@login_required
def api_monthly_trend():
    """Monthly revenue trend for last 12 months."""
    uid = current_user.id
    rows = db.session.query(
        func.strftime('%Y-%m', Sale.sale_date).label('month'),
        func.sum(Sale.total_amount).label('revenue'),
        func.sum(Sale.quantity_sold).label('qty'),
        func.count(Sale.id).label('transactions')
    ).filter(Sale.user_id == uid)\
     .group_by('month')\
     .order_by('month')\
     .all()

    return jsonify([{
        'month': r.month,
        'revenue': round(r.revenue, 2),
        'qty': r.qty,
        'transactions': r.transactions,
    } for r in rows])


@report_bp.route('/api/reports/category-sales')
@login_required
def api_category_sales():
    """Sales breakdown by product category."""
    uid = current_user.id
    rows = db.session.query(
        Product.category,
        func.sum(Sale.total_amount).label('revenue'),
        func.sum(Sale.quantity_sold).label('qty')
    ).join(Sale, Sale.product_id == Product.id)\
     .filter(Sale.user_id == uid)\
     .group_by(Product.category)\
     .order_by(func.sum(Sale.total_amount).desc()).all()

    return jsonify([{
        'category': r.category,
        'revenue': round(r.revenue, 2),
        'qty': r.qty
    } for r in rows])


@report_bp.route('/api/reports/top-products')
@login_required
def api_top_products():
    """Top 10 products by revenue."""
    uid = current_user.id
    limit = int(request.args.get('limit', 10))

    rows = db.session.query(
        Product.name,
        Product.category,
        func.sum(Sale.total_amount).label('revenue'),
        func.sum(Sale.quantity_sold).label('qty')
    ).join(Sale, Sale.product_id == Product.id)\
     .filter(Sale.user_id == uid)\
     .group_by(Product.id)\
     .order_by(func.sum(Sale.total_amount).desc())\
     .limit(limit).all()

    return jsonify([{
        'product': r.name,
        'category': r.category,
        'revenue': round(r.revenue, 2),
        'qty': r.qty
    } for r in rows])


@report_bp.route('/api/reports/daily-trend')
@login_required
def api_daily_trend():
    """Daily revenue for last 30 days."""
    uid   = current_user.id
    today = date.today()
    days  = int(request.args.get('days', 30))
    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        rev = db.session.query(func.sum(Sale.total_amount))\
            .filter(Sale.user_id == uid, Sale.sale_date == d).scalar() or 0
        result.append({'date': d.isoformat(), 'revenue': round(rev, 2)})
    return jsonify(result)
