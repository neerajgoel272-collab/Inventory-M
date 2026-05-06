"""
Database Models
SQLAlchemy ORM models for all tables
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────────────────────
# USER TABLE
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    """Business owner / user account."""
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    business_name = db.Column(db.String(120), default='My Store')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', backref='owner', lazy=True, cascade='all, delete-orphan')
    sales    = db.relationship('Sale',    backref='owner', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.username}>'


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT / INVENTORY TABLE
# ─────────────────────────────────────────────────────────────────────────────
class Product(db.Model):
    """Product in the inventory."""
    __tablename__ = 'products'

    id                  = db.Column(db.Integer, primary_key=True)
    name                = db.Column(db.String(120), nullable=False)
    category            = db.Column(db.String(80), default='General')
    price               = db.Column(db.Float, nullable=False)
    quantity            = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=10)
    description         = db.Column(db.Text, default='')
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relationships
    sales = db.relationship('Sale', backref='product', lazy=True)
    stock_movements = db.relationship(
        'StockMovement',
        backref='product',
        lazy=True,
        cascade='all, delete-orphan'
    )

    @property
    def is_low_stock(self):
        """Return True if current quantity is below the low-stock threshold."""
        return self.quantity <= self.low_stock_threshold

    @property
    def stock_status(self):
        if self.quantity == 0:
            return 'Out of Stock'
        elif self.is_low_stock:
            return 'Low Stock'
        return 'In Stock'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'price': self.price,
            'quantity': self.quantity,
            'low_stock_threshold': self.low_stock_threshold,
            'stock_status': self.stock_status,
            'is_low_stock': self.is_low_stock,
        }

    def __repr__(self):
        return f'<Product {self.name}>'


# ─────────────────────────────────────────────────────────────────────────────
# SALES TABLE
# ─────────────────────────────────────────────────────────────────────────────
class Sale(db.Model):
    """Individual sale transaction."""
    __tablename__ = 'sales'

    id           = db.Column(db.Integer, primary_key=True)
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_sold= db.Column(db.Integer, nullable=False)
    sale_price   = db.Column(db.Float, nullable=False)       # price at time of sale
    total_amount = db.Column(db.Float, nullable=False)
    sale_date    = db.Column(db.Date, nullable=False)
    notes        = db.Column(db.String(256), default='')
    party_name   = db.Column(db.String(200), default='')
    gst_rate     = db.Column(db.Float, default=0.0)
    gst_amount   = db.Column(db.Float, default=0.0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Link to inventory movement(s) that represent this sale
    stock_movements = db.relationship('StockMovement', backref='sale', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else '',
            'quantity_sold': self.quantity_sold,
            'sale_price': self.sale_price,
            'total_amount': self.total_amount,
            'sale_date': str(self.sale_date),
        }

    def __repr__(self):
        return f'<Sale product_id={self.product_id} qty={self.quantity_sold}>'


# ─────────────────────────────────────────────────────────────────────────────
# PURCHASE TABLE
# ─────────────────────────────────────────────────────────────────────────────
class Purchase(db.Model):
    """Purchase transaction — buying stock from a supplier/party."""
    __tablename__ = 'purchases'

    id            = db.Column(db.Integer, primary_key=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity      = db.Column(db.Integer, nullable=False)
    purchase_price= db.Column(db.Float, nullable=False)   # price per unit at purchase
    total_amount  = db.Column(db.Float, nullable=False)
    gst_rate      = db.Column(db.Float, default=0.0)
    gst_amount    = db.Column(db.Float, default=0.0)
    party_name    = db.Column(db.String(200), default='')
    notes         = db.Column(db.String(256), default='')
    purchase_date = db.Column(db.Date, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    product = db.relationship('Product', backref='purchases')

    def __repr__(self):
        return f'<Purchase product_id={self.product_id} qty={self.quantity}>'


# ─────────────────────────────────────────────────────────────────────────────
# FORECAST TABLE  (stores cached AI predictions)
# ─────────────────────────────────────────────────────────────────────────────
class Forecast(db.Model):
    """Cached sales forecasts generated by the AI model."""
    __tablename__ = 'forecasts'

    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    forecast_date  = db.Column(db.Date, nullable=False)
    predicted_qty  = db.Column(db.Float, nullable=False)
    lower_bound    = db.Column(db.Float, default=0)
    upper_bound    = db.Column(db.Float, default=0)
    model_used     = db.Column(db.String(50), default='LinearRegression')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    product = db.relationship('Product', backref='forecasts')

    def __repr__(self):
        return f'<Forecast product_id={self.product_id} date={self.forecast_date}>'


# ─────────────────────────────────────────────────────────────────────────────
# STOCK MOVEMENTS (single source of truth for inventory changes)
# ─────────────────────────────────────────────────────────────────────────────
class StockMovement(db.Model):
    """
    Immutable inventory ledger.
    quantity_delta: + for incoming stock, - for outgoing stock.
    """
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)

    movement_type = db.Column(db.String(32), nullable=False)  # sale, restock, adjustment, return, etc.
    quantity_delta = db.Column(db.Integer, nullable=False)

    reference_type = db.Column(db.String(32), default='')  # sale, po, manual
    reference_id = db.Column(db.Integer, nullable=True)

    note = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True, index=True)

    owner = db.relationship('User', backref=db.backref('stock_movements', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<StockMovement product_id={self.product_id} delta={self.quantity_delta} type={self.movement_type}>'
