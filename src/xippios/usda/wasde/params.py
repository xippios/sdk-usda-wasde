"""The packaged reference lists, read from ``reference/`` without a call (conventions §3).

``scripts/refresh_reference.py`` (``/refresh-reference-data``) writes them from the
latest release's files; ``PackagedList.load(PACKAGE, name)`` reads one, as the list
tasks in ``tasks.py`` do. Each is a table in core's ``PackagedList`` shape, named after
the parameter it serves: no value list is packaged, so no enum is generated
(``enums.py``).
"""

__all__ = ["PACKAGED_LISTS"]

PACKAGE = "xippios.usda.wasde"

PACKAGED_LISTS: tuple[str, ...] = ("table", "commodity", "region", "attribute")
"""The lists that ship inside the package, ``reference/<name>.json``; the refresh script
writes exactly these: the release's pages (``Table``), its supply-and-use matrices with
their commodities (``Commodity``), its region texts (``Region``) and its row labels by
matrix (``Attribute``)."""
