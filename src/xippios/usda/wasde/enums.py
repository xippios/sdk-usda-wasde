"""StrEnums for packaged value lists (conventions §3): none.

WASDE packages no value list: its four packaged lists (``params.PACKAGED_LISTS``) are
tables of several fields, read with ``PackagedList.load``, so nothing is generated here.
A value list packaged later renders here through core's ``render_enums``, called by
``scripts/refresh_reference.py``.
"""

__all__ = []
