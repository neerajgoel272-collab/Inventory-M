"""
AI-Driven Smart Inventory and Sales Forecasting System
Main Flask Application Entry Point
"""

from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from database import db, User
from config import Config
from flask_migrate import Migrate

def create_app():
    load_dotenv()
    app = Flask(__name__)

    # ─── Configuration ───────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = Config.secret_key()
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS

    # ─── Initialize Extensions ────────────────────────────────────────────────────
    db.init_app(app)
    Migrate(app, db)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ─── Register Blueprints ──────────────────────────────────────────────────────
    from routes.auth_routes import auth_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.inventory_routes import inventory_bp
    from routes.sales_routes import sales_bp
    from routes.forecast_routes import forecast_bp
    from routes.report_routes import report_bp
    from routes.copilot_routes import copilot_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(sales_bp)
    from routes.purchase_routes import purchase_bp
    app.register_blueprint(purchase_bp)
    # Forecasting is optional (can require heavy ML deps)
    if Config.enable_forecasting():
        app.register_blueprint(forecast_bp)
    app.register_blueprint(report_bp)

    if Config.enable_copilot():
        app.register_blueprint(copilot_bp)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.cli.command("seed-demo")
    def seed_demo():
        """Seed the database with demo user/products/sales (if empty)."""
        with app.app_context():
            seed_sample_data(app)

    return app


def seed_sample_data(app):
    """Seed the database with sample products and sales data for demo."""
    from database import db, Product, Sale, User
    from werkzeug.security import generate_password_hash
    from datetime import date, timedelta
    import random

    # Only seed if empty
    if User.query.first():
        return

    # Create demo user
    demo_user = User(
        username='demo',
        email='demo@store.com',
        password_hash=generate_password_hash('demo123'),
        business_name='Neeraj General Store'
    )
    db.session.add(demo_user)
    db.session.flush()

    # Sample products
    products_data = [
        ('Rice (5kg)', 'Grocery', 250.0, 120, 20),
        ('Wheat Flour (1kg)', 'Grocery', 45.0, 200, 30),
        ('Sugar (1kg)', 'Grocery', 42.0, 150, 25),
        ('Cooking Oil (1L)', 'Grocery', 130.0, 80, 15),
        ('Dal (500g)', 'Grocery', 65.0, 100, 20),
        ('Biscuits (Pack)', 'Snacks', 25.0, 250, 50),
        ('Chips (Pack)', 'Snacks', 20.0, 300, 60),
        ('Shampoo (200ml)', 'Personal Care', 120.0, 60, 10),
        ('Soap (100g)', 'Personal Care', 35.0, 180, 30),
        ('Toothpaste (100g)', 'Personal Care', 55.0, 90, 15),
        ('Detergent (500g)', 'Household', 95.0, 70, 12),
        ('Tea (250g)', 'Beverages', 85.0, 110, 20),
        ('Coffee (100g)', 'Beverages', 150.0, 50, 10),
        ('Cold Drink (500ml)', 'Beverages', 30.0, 200, 40),
        ('Notebook (200pg)', 'Stationery', 55.0, 80, 15),
    ]

    products = []
    for name, cat, price, qty, threshold in products_data:
        p = Product(
            name=name, category=cat, price=price,
            quantity=qty, low_stock_threshold=threshold,
            user_id=demo_user.id
        )
        db.session.add(p)
        products.append(p)
    db.session.flush()

    # Generate 90 days of historical sales
    base_date = date.today() - timedelta(days=90)
    for i in range(90):
        sale_date = base_date + timedelta(days=i)
        # Each day, record sales for 5–10 random products
        for p in random.sample(products, k=random.randint(5, 10)):
            qty_sold = random.randint(1, 15)
            sale = Sale(
                product_id=p.id,
                quantity_sold=qty_sold,
                sale_price=p.price,
                total_amount=qty_sold * p.price,
                sale_date=sale_date,
                user_id=demo_user.id
            )
            db.session.add(sale)

    db.session.commit()
    print("Sample data seeded successfully.")


if __name__ == '__main__':
    app = create_app()
    import os
    port = int(os.environ.get('PORT', Config.port()))
    app.run(debug=False, host='0.0.0.0', port=port)
