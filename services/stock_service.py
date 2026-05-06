from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database import db, Product, StockMovement


@dataclass(frozen=True)
class MovementInput:
    user_id: int
    product_id: int
    movement_type: str
    quantity_delta: int
    reference_type: str = ""
    reference_id: Optional[int] = None
    sale_id: Optional[int] = None
    note: str = ""


def apply_movement(inp: MovementInput) -> StockMovement:
    """
    Create a StockMovement row and apply its effect to Product.quantity.
    Product.quantity is a denormalized cache; StockMovement is the ledger.
    """
    if inp.quantity_delta == 0:
        raise ValueError("quantity_delta cannot be 0")

    product = Product.query.filter_by(id=inp.product_id, user_id=inp.user_id).first()
    if not product:
        raise ValueError("product not found")

    new_qty = (product.quantity or 0) + int(inp.quantity_delta)
    if new_qty < 0:
        raise ValueError("insufficient stock")

    mv = StockMovement(
        user_id=inp.user_id,
        product_id=inp.product_id,
        movement_type=inp.movement_type,
        quantity_delta=int(inp.quantity_delta),
        reference_type=inp.reference_type or "",
        reference_id=inp.reference_id,
        sale_id=inp.sale_id,
        note=inp.note or "",
    )
    db.session.add(mv)

    product.quantity = new_qty
    db.session.add(product)

    return mv

