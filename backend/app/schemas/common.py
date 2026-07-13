"""Common Pydantic schemas for unified API responses."""
from __future__ import annotations
from typing import Optional, Any, List, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response wrapper."""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class PaginatedData(BaseModel, Generic[T]):
    """Paginated data container."""
    items: List[T]
    total: int
    page: int
    page_size: int


class ErrorDetail(BaseModel):
    """Error response detail."""
    code: int
    message: str
    detail: Optional[str] = None
