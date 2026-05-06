"""
Inventory Management Routes — CRUD for products
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from database import db, Product
from services.stock_service import MovementInput, apply_movement

inventory_bp = Blueprint('inventory', __name__)


@inventory_bp.route('/inventory')
@login_required
def index():
    """List all products with search/filter support."""
    search   = request.args.get('search', '')
    category = request.args.get('category', '')
    status   = request.args.get('status', '')

    query = Product.query.filter_by(user_id=current_user.id)

    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)

    products = query.order_by(Product.name).all()

    # Filter by stock status
    if status == 'low':
        products = [p for p in products if p.is_low_stock and p.quantity > 0]
    elif status == 'out':
        products = [p for p in products if p.quantity == 0]
    elif status == 'ok':
        products = [p for p in products if not p.is_low_stock]

    # All categories for dropdown
    categories = db.session.query(Product.category)\
        .filter_by(user_id=current_user.id)\
        .distinct().all()
    categories = [c[0] for c in categories]

    return render_template('inventory.html',
        products=products,
        categories=categories,
        search=search,
        selected_category=category,
        selected_status=status,
    )


@inventory_bp.route('/inventory/add', methods=['GET', 'POST'])
@login_required
def add_product():
    """Add a new product."""
    if request.method == 'POST':
        name      = request.form.get('name', '').strip()
        category  = request.form.get('category', 'General').strip()
        price     = float(request.form.get('price', 0))
        quantity  = int(request.form.get('quantity', 0))
        threshold = int(request.form.get('threshold', 10))
        desc      = request.form.get('description', '').strip()

        if not name or price <= 0:
            flash('Product name and valid price are required.', 'danger')
            return redirect(url_for('inventory.add_product'))

        product = Product(
            name=name, category=category, price=price,
            quantity=quantity, low_stock_threshold=threshold,
            description=desc, user_id=current_user.id
        )
        db.session.add(product)
        db.session.commit()
        flash(f'Product "{name}" added successfully!', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory.html', mode='add')


@inventory_bp.route('/inventory/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
def edit_product(pid):
    """Edit an existing product."""
    product = Product.query.filter_by(id=pid, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        product.name                = request.form.get('name', product.name).strip()
        product.category            = request.form.get('category', product.category).strip()
        product.price               = float(request.form.get('price', product.price))
        product.quantity            = int(request.form.get('quantity', product.quantity))
        product.low_stock_threshold = int(request.form.get('threshold', product.low_stock_threshold))
        product.description         = request.form.get('description', product.description).strip()

        db.session.commit()
        flash(f'Product "{product.name}" updated.', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory.html', mode='edit', product=product)


@inventory_bp.route('/inventory/delete/<int:pid>', methods=['POST'])
@login_required
def delete_product(pid):
    """Delete a product and its sales history."""
    product = Product.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f'Product "{name}" deleted.', 'success')
    return redirect(url_for('inventory.index'))


# ── REST API Endpoints (used by JS fetch) ────────────────────────────────────

@inventory_bp.route('/api/products')
@login_required
def api_products():
    """Return all products as JSON."""
    products = Product.query.filter_by(user_id=current_user.id).all()
    return jsonify([p.to_dict() for p in products])


@inventory_bp.route('/api/products/<int:pid>')
@login_required
def api_product(pid):
    """Return a single product as JSON."""
    product = Product.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    return jsonify(product.to_dict())


@inventory_bp.route('/api/products/<int:pid>/restock', methods=['POST'])
@login_required
def api_restock(pid):
    """Restock a product by adding quantity."""
    product = Product.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    data = request.get_json()
    qty = int(data.get('quantity', 0))
    if qty > 0:
        try:
            apply_movement(MovementInput(
                user_id=current_user.id,
                product_id=product.id,
                movement_type="restock",
                quantity_delta=+qty,
                reference_type="manual",
                reference_id=None,
                note="API restock",
            ))
            db.session.commit()
            return jsonify({'success': True, 'new_quantity': product.quantity})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'error': 'Invalid quantity'}), 400
