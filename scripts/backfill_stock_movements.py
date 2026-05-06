import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database import db, Product, StockMovement


def main() -> int:
    app = create_app()
    with app.app_context():
        existing = StockMovement.query.filter_by(movement_type="initial_balance").first()
        if existing:
            print("Backfill already done")
            return 0

        products = Product.query.all()
        created = 0
        for p in products:
            qty = int(p.quantity or 0)
            if qty == 0:
                continue
            mv = StockMovement(
                user_id=p.user_id,
                product_id=p.id,
                movement_type="initial_balance",
                quantity_delta=qty,
                reference_type="system",
                reference_id=None,
                note="Backfilled from Product.quantity",
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(mv)
            created += 1
        db.session.commit()
        print(f"Backfilled {created} movements")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

