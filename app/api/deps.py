"""Shared helpers for Milestone 3 routes."""
from app.models import User
from app.security import require_roles

staff = require_roles('admin', 'vendor')
admin = require_roles('admin')


def scope(user: User) -> int | None:
    """Vendors only ever see their own data; admins see the marketplace."""
    return user.vendor_id if user.role == 'vendor' else None


def with_meta(result: dict) -> dict:
    """Flatten a snapshot result: payload keys plus a ``meta`` block."""
    data = result['data']
    if isinstance(data, dict):
        return {**data, 'meta': result['meta']}
    return {'items': data, 'meta': result['meta']}
