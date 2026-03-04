"""
Reusable pagination utility for all list endpoints.

Usage:
    from src.utils.pagination import PaginationParams, paginate

    @router.get("/items")
    async def list_items(
        pagination: PaginationParams = Depends(),
        db: Session = Depends(get_db),
    ):
        query = db.query(Item).order_by(Item.created_at.desc())
        return paginate(query, pagination)
"""
from fastapi import Depends, Query


class PaginationParams:
    """FastAPI dependency — provides page/page_size with validation."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


def paginate(query, params: PaginationParams) -> dict:
    """Apply pagination to a SQLAlchemy query.

    Returns a dict matching PaginatedResponse shape:
        items, total, page, page_size, pages, has_next, has_prev
    """
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    pages = max(1, (total + params.page_size - 1) // params.page_size)
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "pages": pages,
        "has_next": params.page < pages,
        "has_prev": params.page > 1,
    }
