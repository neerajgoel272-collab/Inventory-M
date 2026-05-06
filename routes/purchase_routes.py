"""
Purchase Management Routes — Record stock purchases from suppliers
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database import db, Product, Purchase
from datetime import date, timedelta
from collections import defaultdict

purchase_bp = Blueprint('purchase', __name__)


@purchase_bp.route('/purchases')
@login_required
def index():
    start_date = request.args.get('start', (date.today() - timedelta(days=30)).isoformat())
    end_date   = request.args.get('end', date.today().isoformat())

    purchases = Purchase.query.filter(
        Purchase.user_id == current_user.id,
        Purchase.purchase_date >= start_date,
        Purchase.purchase_date <= end_date
    ).order_by(Purchase.purchase_date.desc(), Purchase.created_at.desc()).all()

    period_total     = sum(p.total_amount for p in purchases)
    period_gst_total = sum(p.gst_amount or 0 for p in purchases)

    # Group into bills by minute of creation
    bill_map = defaultdict(list)
    for p in purchases:
        minute_key = p.created_at.strftime('%Y%m%d%H%M') if p.created_at else p.purchase_date.isoformat()
        key = (p.purchase_date.isoformat(), p.party_name or '', minute_key)
        bill_map[key].append(p)

    bills = []
    for (pdate, party, _), items in sorted(bill_map.items(), key=lambda x: x[0][2], reverse=True):
        try:
            from datetime import datetime as dt
            d = dt.strptime(pdate, '%Y-%m-%d').strftime('%d %b %Y')
        except Exception:
            d = pdate
        bills.append({
            'date': d,
            'party_name': party,
            'notes': items[0].notes or '',
            'lines': items,
            'total': sum(i.total_amount for i in items),
            'gst_total': sum(i.gst_amount or 0 for i in items),
        })

    products = Product.query.filter_by(user_id=current_user.id).order_by(Product.name).all()

    return render_template('purchases.html',
        bills=bills,
        products=products,
        start_date=start_date,
        end_date=end_date,
        period_total=round(period_total, 2),
        period_gst_total=round(period_gst_total, 2),
    )


@purchase_bp.route('/purchases/record-bulk', methods=['POST'])
@login_required
def record_bulk_purchase():
    purchase_date_s = request.form.get('purchase_date', date.today().isoformat())
    party_name      = request.form.get('party_name', '').strip()
    notes           = request.form.get('notes', '').strip()
    product_ids     = request.form.getlist('product_id[]')
    quantities      = request.form.getlist('quantity[]')
    prices          = request.form.getlist('purchase_price[]')
    gst_rates       = request.form.getlist('gst_rate[]')
    new_names       = request.form.getlist('new_product_name[]')
    new_categories  = request.form.getlist('new_product_category[]')
    new_prices      = request.form.getlist('new_product_price[]')
    new_thresholds  = request.form.getlist('new_product_threshold[]')

    if not product_ids:
        flash('No items to record.', 'danger')
        return redirect(url_for('purchase.index'))

    recorded, errors = 0, []
    new_idx = 0  # index into new_product fields

    for pid_str, qty_str, price_str, gst_str in zip(
        product_ids, quantities, prices, gst_rates or ['0']*len(product_ids)
    ):
        try:
            qty      = int(qty_str)
            price    = float(price_str)
            gst_rate = float(gst_str or 0)
        except (ValueError, TypeError):
            new_idx += 1
            continue

        # Handle new product creation
        if pid_str == '__new__':
            name      = new_names[new_idx].strip()      if new_idx < len(new_names)      else ''
            category  = new_categories[new_idx].strip() if new_idx < len(new_categories) else 'General'
            sell_price= float(new_prices[new_idx])      if new_idx < len(new_prices) and new_prices[new_idx] else price
            threshold = int(new_thresholds[new_idx])    if new_idx < len(new_thresholds) and new_thresholds[new_idx] else 10
            new_idx += 1
            if not name:
                errors.append('New product name is required.')
                continue
            from database import Product as Prod
            product = Prod(name=name, category=category, price=sell_price,
                           quantity=0, low_stock_threshold=threshold, user_id=current_user.id)
            db.session.add(product)
            db.session.flush()
        else:
            new_idx += 1
            try:
                pid = int(pid_str)
            except (ValueError, TypeError):
                continue
            if not pid or qty <= 0 or price < 0:
                continue
            product = Product.query.filter_by(id=pid, user_id=current_user.id).first()
            if not product:
                errors.append(f'Product #{pid} not found.')
                continue

        subtotal   = qty * price
        gst_amount = round(subtotal * gst_rate / 100, 2)
        total      = round(subtotal + gst_amount, 2)

        purchase = Purchase(
            product_id=product.id,
            quantity=qty,
            purchase_price=price,
            total_amount=total,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            party_name=party_name,
            notes=notes,
            purchase_date=date.fromisoformat(purchase_date_s),
            user_id=current_user.id
        )
        db.session.add(purchase)

        # Auto-increase stock
        product.quantity += qty
        recorded += 1

    if errors:
        db.session.rollback()
        for err in errors:
            flash(err, 'danger')
    else:
        db.session.commit()
        flash(f'{recorded} purchase(s) recorded. Stock updated.', 'success')

    return redirect(url_for('purchase.index'))


@purchase_bp.route('/purchases/delete/<int:pid>', methods=['POST'])
@login_required
def delete_purchase(pid):
    purchase = Purchase.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    product  = Product.query.get(purchase.product_id)
    if product:
        product.quantity = max(0, product.quantity - purchase.quantity)
    db.session.delete(purchase)
    db.session.commit()
    flash('Purchase deleted and stock adjusted.', 'info')
    return redirect(url_for('purchase.index'))
