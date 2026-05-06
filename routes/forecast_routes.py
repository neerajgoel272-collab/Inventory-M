"""
AI Forecasting Routes — ML-powered sales prediction and restock suggestions
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from database import db, Product, Sale, Forecast
from sqlalchemy import func
from datetime import date

forecast_bp = Blueprint('forecast', __name__)

def _get_forecaster_or_error():
    """
    Lazily import ML dependencies so the web app can run
    even if pandas/numpy/scikit-learn aren't installed.
    """
    try:
        from models.forecaster import SalesForecaster  # local import (optional deps)
        return SalesForecaster(), None
    except Exception as e:
        return None, str(e)


def _get_v2_forecaster():
    from ml.forecasting import best_forecast
    return best_forecast


@forecast_bp.route('/forecast')
@login_required
def index():
    """Sales forecasting page."""
    products = Product.query.filter_by(user_id=current_user.id)\
        .order_by(Product.name).all()
    return render_template('forecast.html', products=products)


@forecast_bp.route('/api/forecast/<int:pid>')
@login_required
def api_forecast_product(pid):
    """
    Run AI forecast for a specific product.
    Returns 30-day prediction + restock recommendation.
    """
    product = Product.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    days    = int(request.args.get('days', 30))

    # Fetch historical sales for this product
    sales_rows = db.session.query(
        Sale.sale_date,
        func.sum(Sale.quantity_sold).label('qty')
    ).filter(Sale.product_id == pid, Sale.user_id == current_user.id)\
     .group_by(Sale.sale_date)\
     .order_by(Sale.sale_date).all()

    if len(sales_rows) < 7:
        return jsonify({'error': 'Not enough sales history (need at least 7 days).'}), 400

    # Build time-series dict
    history = {str(r.sale_date): float(r.qty) for r in sales_rows}

    # Run forecasting v2 (pure python baseline; always available)
    best_forecast = _get_v2_forecaster()
    result = best_forecast(history, horizon=days)

    if 'error' in result:
        return jsonify(result), 500

    # Save forecasts to DB (clear old, insert new)
    Forecast.query.filter_by(product_id=pid, user_id=current_user.id).delete()
    for item in result['forecast']:
        fc = Forecast(
            product_id=pid,
            forecast_date=date.fromisoformat(item['date']),
            predicted_qty=item['predicted_qty'],
            lower_bound=item.get('lower', 0),
            upper_bound=item.get('upper', 0),
            model_used=result.get('model_used', 'ForecastV2'),
            user_id=current_user.id
        )
        db.session.add(fc)
    db.session.commit()

    # Restock recommendation
    total_predicted = sum(f['predicted_qty'] for f in result['forecast'])
    restock_qty = max(0, round(total_predicted - product.quantity))

    result['product'] = product.to_dict()
    result['restock_recommendation'] = {
        'current_stock': product.quantity,
        'predicted_demand': round(total_predicted, 1),
        'suggested_restock': restock_qty,
        'days_of_stock_remaining': round(product.quantity / (total_predicted / days), 1)
            if total_predicted > 0 else 999,
    }

    return jsonify(result)


@forecast_bp.route('/api/forecast/all')
@login_required
def api_forecast_all():
    """
    Run AI forecast for ALL products with sufficient history.
    Used for the overview table on the forecast page.
    """
    uid      = current_user.id
    products = Product.query.filter_by(user_id=uid).all()
    results  = []

    best_forecast = _get_v2_forecaster()

    for product in products:
        sales_rows = db.session.query(
            Sale.sale_date,
            func.sum(Sale.quantity_sold).label('qty')
        ).filter(Sale.product_id == product.id, Sale.user_id == uid)\
         .group_by(Sale.sale_date)\
         .order_by(Sale.sale_date).all()

        if len(sales_rows) < 7:
            results.append({
                'product_id': product.id,
                'product_name': product.name,
                'status': 'insufficient_data',
                'current_stock': product.quantity,
            })
            continue

        history = {str(r.sale_date): float(r.qty) for r in sales_rows}
        res = best_forecast(history, horizon=14)

        if 'error' in res:
            continue

        predicted_14d = sum(float(f['predicted_qty']) for f in res['forecast'])
        days_remaining = round(product.quantity / (predicted_14d / 14), 1) \
            if predicted_14d > 0 else 999

        results.append({
            'product_id': product.id,
            'product_name': product.name,
            'category': product.category,
            'current_stock': product.quantity,
            'predicted_14d': round(predicted_14d, 1),
            'avg_daily_demand': round(predicted_14d / 14, 2),
            'days_remaining': min(days_remaining, 999),
            'restock_qty': max(0, round(predicted_14d - product.quantity)),
            'urgency': 'high' if days_remaining < 5 else ('medium' if days_remaining < 14 else 'low'),
            'model': res.get('model_used', 'LinearRegression'),
            'status': 'ok',
        })

    # Sort by urgency
    urgency_order = {'high': 0, 'medium': 1, 'low': 2}
    results.sort(key=lambda x: urgency_order.get(x.get('urgency', 'low'), 2))

    return jsonify(results)
