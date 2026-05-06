"""
Sales Management Routes — Record and view sales
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from database import db, Product, Sale
from sqlalchemy import func
from datetime import date, timedelta
from services.stock_service import MovementInput, apply_movement

sales_bp = Blueprint('sales', __name__)


@sales_bp.route('/sales')
@login_required
def index():
    """Sales history page with filters."""
    start_date = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date   = request.args.get('end', date.today().isoformat())
    product_id = request.args.get('product_id', '')

    query = Sale.query.filter(
        Sale.user_id == current_user.id,
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date
    )
    if product_id:
        query = query.filter_by(product_id=product_id)

    sales = query.order_by(Sale.sale_date.desc(), Sale.created_at.desc()).all()

    # Total for filter period
    period_total = sum(s.total_amount for s in sales)

    # Group into bills by (date, notes, created_at minute)
    from collections import defaultdict
    bill_map = defaultdict(list)
    for s in sales:
        # Group by date + notes + minute of creation (bulk sales share same minute)
        minute_key = s.created_at.strftime('%Y%m%d%H%M') if s.created_at else s.sale_date.isoformat()
        key = (s.sale_date.isoformat(), s.notes or '', minute_key)
        bill_map[key].append(s)

    bills = []
    for (sale_date, notes, _), items in sorted(bill_map.items(), key=lambda x: x[0][2], reverse=True):
        from datetime import datetime
        try:
            d = datetime.strptime(sale_date, '%Y-%m-%d').strftime('%d %b %Y')
        except Exception:
            d = sale_date
        bills.append({
            'date': d,
            'notes': notes,
            'party_name': items[0].party_name if hasattr(items[0], 'party_name') else '',
            'lines': items,
            'total': sum(i.total_amount for i in items),
        })

    # Products for dropdown
    products = Product.query.filter_by(user_id=current_user.id).order_by(Product.name).all()

    return render_template('sales.html',
        sales=sales,
        bills=bills,
        products=products,
        start_date=start_date,
        end_date=end_date,
        selected_product=product_id,
        period_total=round(period_total, 2),
    )


@sales_bp.route('/sales/record', methods=['POST'])
@login_required
def record_sale():
    """Record a new sale transaction."""
    product_id  = int(request.form.get('product_id', 0))
    qty_sold    = int(request.form.get('quantity_sold', 0))
    sale_date_s = request.form.get('sale_date', date.today().isoformat())
    notes       = request.form.get('notes', '').strip()

    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()

    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('sales.index'))

    if qty_sold <= 0:
        flash('Quantity must be greater than zero.', 'danger')
        return redirect(url_for('sales.index'))

    if product.quantity < qty_sold:
        flash(f'Insufficient stock! Available: {product.quantity}', 'danger')
        return redirect(url_for('sales.index'))

    sale = Sale(
        product_id=product_id,
        quantity_sold=qty_sold,
        sale_price=product.price,
        total_amount=qty_sold * product.price,
        sale_date=date.fromisoformat(sale_date_s),
        notes=notes,
        user_id=current_user.id
    )
    db.session.add(sale)
    db.session.flush()

    try:
        apply_movement(MovementInput(
            user_id=current_user.id,
            product_id=product_id,
            movement_type="sale",
            quantity_delta=-qty_sold,
            reference_type="sale",
            reference_id=sale.id,
            sale_id=sale.id,
            note=notes,
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Could not record sale: {str(e)}', 'danger')
        return redirect(url_for('sales.index'))

    flash(f'Sale recorded: {qty_sold} × {product.name} = ₹{sale.total_amount:.2f}', 'success')
    return redirect(url_for('sales.index'))


@sales_bp.route('/sales/record-bulk', methods=['POST'])
@login_required
def record_bulk_sale():
    """Record multiple sale items at once."""
    sale_date_s  = request.form.get('sale_date', date.today().isoformat())
    notes        = request.form.get('notes', '').strip()
    party_name   = request.form.get('party_name', '').strip()
    product_ids  = request.form.getlist('product_id[]')
    quantities   = request.form.getlist('quantity_sold[]')
    gst_rates    = request.form.getlist('gst_rate[]')

    if not product_ids:
        flash('No items to record.', 'danger')
        return redirect(url_for('sales.index'))

    recorded, errors = 0, []

    for pid_str, qty_str, gst_str in zip(product_ids, quantities, gst_rates or ['0']*len(product_ids)):
        try:
            pid      = int(pid_str)
            qty_sold = int(qty_str)
            gst_rate = float(gst_str or 0)
        except (ValueError, TypeError):
            continue

        if not pid or qty_sold <= 0:
            continue

        product = Product.query.filter_by(id=pid, user_id=current_user.id).first()
        if not product:
            errors.append(f'Product #{pid} not found.')
            continue
        if product.quantity < qty_sold:
            errors.append(f'{product.name}: insufficient stock (have {product.quantity}, need {qty_sold}).')
            continue

        subtotal   = qty_sold * product.price
        gst_amount = round(subtotal * gst_rate / 100, 2)
        sale = Sale(
            product_id=pid,
            quantity_sold=qty_sold,
            sale_price=product.price,
            total_amount=round(subtotal + gst_amount, 2),
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            sale_date=date.fromisoformat(sale_date_s),
            notes=notes,
            party_name=party_name,
            user_id=current_user.id
        )
        db.session.add(sale)
        db.session.flush()

        try:
            apply_movement(MovementInput(
                user_id=current_user.id,
                product_id=pid,
                movement_type="sale",
                quantity_delta=-qty_sold,
                reference_type="sale",
                reference_id=sale.id,
                sale_id=sale.id,
                note=notes,
            ))
            recorded += 1
        except Exception as e:
            errors.append(f'{product.name}: {str(e)}')

    if errors:
        db.session.rollback()
        for err in errors:
            flash(err, 'danger')
    else:
        db.session.commit()
        flash(f'{recorded} sale(s) recorded successfully.', 'success')

    return redirect(url_for('sales.index'))


@sales_bp.route('/sales/delete/<int:sid>', methods=['POST'])
@login_required
def delete_sale(sid):
    """Delete a sale and restore stock."""
    sale = Sale.query.filter_by(id=sid, user_id=current_user.id).first_or_404()
    try:
        apply_movement(MovementInput(
            user_id=current_user.id,
            product_id=sale.product_id,
            movement_type="sale_void",
            quantity_delta=+sale.quantity_sold,
            reference_type="sale",
            reference_id=sale.id,
            sale_id=sale.id,
            note="Sale deleted (stock restored)",
        ))
        db.session.delete(sale)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Could not delete sale: {str(e)}', 'danger')
        return redirect(url_for('sales.index'))
    flash('Sale record deleted and stock restored.', 'info')
    return redirect(url_for('sales.index'))


# ── REST API ─────────────────────────────────────────────────────────────────

@sales_bp.route('/api/sales/daily')
@login_required
def api_daily_sales():
    """Daily sales totals for the last N days (default 30)."""
    days = int(request.args.get('days', 30))
    uid  = current_user.id
    today = date.today()

    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        rev = db.session.query(func.sum(Sale.total_amount))\
            .filter(Sale.user_id == uid, Sale.sale_date == d).scalar() or 0
        qty = db.session.query(func.sum(Sale.quantity_sold))\
            .filter(Sale.user_id == uid, Sale.sale_date == d).scalar() or 0
        result.append({'date': d.isoformat(), 'revenue': round(rev, 2), 'qty': qty})

    return jsonify(result)


@sales_bp.route('/api/sales/monthly')
@login_required
def api_monthly_sales():
    """Monthly sales totals for the last 12 months."""
    uid = current_user.id
    rows = db.session.query(
        func.strftime('%Y-%m', Sale.sale_date).label('month'),
        func.sum(Sale.total_amount).label('revenue'),
        func.sum(Sale.quantity_sold).label('qty')
    ).filter(Sale.user_id == uid)\
     .group_by('month')\
     .order_by('month')\
     .limit(12).all()

    return jsonify([{'month': r.month, 'revenue': round(r.revenue, 2), 'qty': r.qty} for r in rows])


@sales_bp.route('/api/sales/by-product')
@login_required
def api_sales_by_product():
    """Total sales grouped by product (top 10)."""
    uid = current_user.id
    rows = db.session.query(
        Product.name,
        func.sum(Sale.quantity_sold).label('total_qty'),
        func.sum(Sale.total_amount).label('total_revenue')
    ).join(Sale, Sale.product_id == Product.id)\
     .filter(Sale.user_id == uid)\
     .group_by(Product.id)\
     .order_by(func.sum(Sale.total_amount).desc())\
     .limit(10).all()

    return jsonify([{
        'product': r.name,
        'total_qty': r.total_qty,
        'total_revenue': round(r.total_revenue, 2)
    } for r in rows])
