"""File parsers, layer 1 beside ``api/``: one module per file kind (conventions §2, ADR-0020).

Each module has one function, ``parse_<file_kind>(path) -> list[Model]``; a parser's
library is this package's dependency, declared in ``pyproject.toml``, never core's.
``wasde_xml`` reads a release's XML file with the standard library's
``xml.etree.ElementTree``; ``wasde_xls`` the narrative of its XLS file, sheet ``WASDE
Text``, with xlrd; ``wasde_pdf`` the narrative pages of its PDF file with pypdf, text only
(ADR-0020 decision 4).
"""

from xippios.usda.wasde.parse.wasde_pdf import parse_wasde_pdf
from xippios.usda.wasde.parse.wasde_xls import parse_wasde_xls
from xippios.usda.wasde.parse.wasde_xml import parse_wasde_xml

__all__ = ["parse_wasde_pdf", "parse_wasde_xls", "parse_wasde_xml"]
