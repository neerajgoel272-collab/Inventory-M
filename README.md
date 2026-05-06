# 🤖 AI-Driven Smart Inventory & Sales Forecasting System
### Final Year Major Project — Python Flask + ML + SQLite

---

## 📁 Project Folder Structure

```
smart_inventory/
│
├── app.py                     # Main Flask application (entry point)
├── database.py                # SQLAlchemy ORM models (all tables)
├── requirements.txt           # Python dependencies
│
├── routes/                    # Flask Blueprints (one per feature)
│   ├── __init__.py
│   ├── auth_routes.py         # Login, Register, Logout
│   ├── dashboard_routes.py    # Dashboard KPIs & charts
│   ├── inventory_routes.py    # Product CRUD + REST API
│   ├── sales_routes.py        # Sales recording + REST API
│   ├── forecast_routes.py     # AI forecasting endpoints
│   └── report_routes.py       # Analytics & reporting
│
├── models/                    # AI/ML Models
│   ├── __init__.py
│   └── forecaster.py          # SalesForecaster (LinearRegression + ES)
│
├── templates/                 # Jinja2 HTML templates
│   ├── base.html              # Base layout (sidebar + topbar)
│   ├── home.html              # Landing page
│   ├── login.html             # Login page
│   ├── register.html          # Registration page
│   ├── dashboard.html         # Dashboard overview
│   ├── inventory.html         # Inventory management
│   ├── sales.html             # Sales management
│   ├── forecast.html          # AI forecasting page
│   └── reports.html           # Reports & analytics
│
├── static/                    # CSS, JS, Images (served by Flask)
│   ├── css/
│   ├── js/
│   └── img/
│
└── data/
    └── sample_sales.csv       # Sample dataset for reference
```

---

## 🗄️ Database Schema

### Table: `users`
| Column        | Type    | Description                     |
|---------------|---------|---------------------------------|
| id            | INTEGER | Primary key                     |
| username      | TEXT    | Unique username                 |
| email         | TEXT    | Unique email                    |
| password_hash | TEXT    | Bcrypt hashed password          |
| business_name | TEXT    | Store / business name           |
| created_at    | DATETIME| Account creation timestamp      |

### Table: `products`
| Column              | Type    | Description                    |
|---------------------|---------|--------------------------------|
| id                  | INTEGER | Primary key                    |
| name                | TEXT    | Product name                   |
| category            | TEXT    | Product category               |
| price               | FLOAT   | Selling price (₹)              |
| quantity            | INTEGER | Current stock quantity         |
| low_stock_threshold | INTEGER | Alert threshold                |
| description         | TEXT    | Optional description           |
| user_id             | INTEGER | FK → users.id                  |
| created_at          | DATETIME|                                |
| updated_at          | DATETIME|                                |

### Table: `sales`
| Column        | Type    | Description                     |
|---------------|---------|---------------------------------|
| id            | INTEGER | Primary key                     |
| product_id    | INTEGER | FK → products.id                |
| quantity_sold | INTEGER | Units sold                      |
| sale_price    | FLOAT   | Price at time of sale           |
| total_amount  | FLOAT   | quantity_sold × sale_price      |
| sale_date     | DATE    | Date of sale                    |
| notes         | TEXT    | Optional notes                  |
| user_id       | INTEGER | FK → users.id                   |
| created_at    | DATETIME|                                 |

### Table: `forecasts`
| Column        | Type    | Description                     |
|---------------|---------|---------------------------------|
| id            | INTEGER | Primary key                     |
| product_id    | INTEGER | FK → products.id                |
| forecast_date | DATE    | Predicted date                  |
| predicted_qty | FLOAT   | ML-predicted units              |
| lower_bound   | FLOAT   | 95% CI lower                    |
| upper_bound   | FLOAT   | 95% CI upper                    |
| model_used    | TEXT    | Model name                      |
| user_id       | INTEGER | FK → users.id                   |
| created_at    | DATETIME|                                 |

---

## 🚀 Setup & Run Instructions

### Step 1 — Prerequisites
- Python 3.9 or higher
- pip (Python package manager)
- Git (optional)

### Step 2 — Clone / Extract Project
```bash
cd Desktop
# If using git:
git clone <repo-url> smart_inventory
# OR extract the ZIP and cd into it
cd smart_inventory
```

### Step 3 — Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 4 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5 — Run the Application
```bash
python app.py
```

### Step 6 — Open in Browser
```
http://127.0.0.1:5000
```

### Demo Login
- **Username:** `demo`
- **Password:** `demo123`

The demo account includes:
- 15 pre-loaded products (groceries, snacks, beverages, etc.)
- 90 days of random historical sales data
- Ready for AI forecasting immediately

---

## 🧠 AI Forecasting — How It Works

### Overview
The `SalesForecaster` class in `models/forecaster.py` implements a production-grade ML pipeline:

### Algorithm: Linear Regression with Feature Engineering

**Step 1 — Data Preparation**
- Converts sparse sales history dict into a complete daily time series
- Fills missing days with 0 (no sale = 0 units)

**Step 2 — Feature Engineering**
The model creates these input features from each date:
| Feature         | Description                          |
|-----------------|--------------------------------------|
| `t`             | Time index (day number)              |
| `day_of_week`   | 0=Monday … 6=Sunday                  |
| `day_of_month`  | 1–31                                 |
| `week_of_year`  | 1–52                                 |
| `month`         | 1–12                                 |
| `lag_1`         | Previous day's sales                 |
| `lag_7`         | Sales 7 days ago (same-day effect)   |
| `lag_14`        | Sales 14 days ago                    |
| `rolling_7_mean`| 7-day rolling average                |
| `rolling_14_mean`| 14-day rolling average              |

**Step 3 — Model Training**
- `StandardScaler` normalises features
- `LinearRegression` (scikit-learn) fits on available history
- Residuals used to compute prediction confidence interval (±1.96σ)

**Step 4 — Multi-Step Forecasting**
- Iteratively predicts each future day
- Uses previous predictions as lag features for next step

**Step 5 — Fallback (< 21 days data)**
- Uses Exponential Smoothing with trend correction

### Why AI Improves Inventory Decisions

| Traditional Approach        | AI-Powered Approach                           |
|-----------------------------|-----------------------------------------------|
| Reorder when stock runs out | Reorder before stockout based on forecast     |
| Fixed reorder quantities    | Demand-calibrated reorder quantities          |
| Manual monitoring           | Automated low-stock urgency scoring           |
| Ignores seasonality         | Learns weekly & monthly demand patterns       |
| Reactive decisions          | Proactive, data-driven decisions              |

### Example AI Output
```
Product: Rice (5kg)
Current Stock: 40 units
Predicted demand (next 14 days): 68 units
Days of stock remaining: 8 days
Suggested restock: 28 units
Urgency: HIGH
```

---

## 🌐 REST API Reference

| Method | Endpoint                      | Description                        |
|--------|-------------------------------|------------------------------------|
| GET    | `/api/products`               | List all products (JSON)           |
| GET    | `/api/products/<id>`          | Single product details             |
| POST   | `/api/products/<id>/restock`  | Add stock quantity                 |
| GET    | `/api/sales/daily`            | Daily sales totals (last N days)   |
| GET    | `/api/sales/monthly`          | Monthly sales totals               |
| GET    | `/api/sales/by-product`       | Sales grouped by product           |
| GET    | `/api/forecast/<product_id>`  | AI forecast for a product          |
| GET    | `/api/forecast/all`           | Forecast overview for all products |
| GET    | `/api/reports/summary`        | Business KPI summary               |
| GET    | `/api/reports/monthly-trend`  | Monthly revenue trend              |
| GET    | `/api/reports/category-sales` | Sales by category                  |
| GET    | `/api/reports/top-products`   | Top products by revenue            |
| GET    | `/api/dashboard/kpis`         | Live dashboard KPI refresh         |

---

## 📚 Technology Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Backend    | Python 3.9+, Flask 3.0            |
| Database   | SQLite (via SQLAlchemy ORM)       |
| Auth       | Flask-Login, Werkzeug password    |
| AI/ML      | scikit-learn, pandas, numpy       |
| Frontend   | HTML5, CSS3, JavaScript (ES6+)    |
| UI Library | Bootstrap 5.3                     |
| Charts     | Chart.js 4.4                      |
| Icons      | Bootstrap Icons 1.11              |
| Fonts      | Google Fonts (Plus Jakarta Sans)  |

---

## 📝 Project Features Checklist

- [x] User Registration & Login (hashed passwords)
- [x] Product CRUD (Add / Edit / Delete / Restock)
- [x] Stock quantity tracking with low-stock alerts
- [x] Daily sales recording with auto inventory deduction
- [x] Sales history with date/product filters
- [x] AI forecasting (Linear Regression + Exponential Smoothing)
- [x] 30-day demand prediction with confidence intervals
- [x] Restock quantity suggestions per product
- [x] Urgency scoring (High / Medium / Low)
- [x] Dashboard with KPI cards and charts
- [x] Monthly revenue trend (Chart.js)
- [x] Category distribution chart
- [x] Top products analysis
- [x] REST API endpoints for all data
- [x] 8 complete HTML pages
- [x] Responsive Bootstrap UI
- [x] Auto-seeded demo data (15 products, 90-day history)

---

*Project by: [Your Name] | Final Year B.E./B.Tech | [College Name] | 2024*
