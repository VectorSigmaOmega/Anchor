"""Evaluation controls shared with the corrected production parser/packer.

The original pilot implementation is preserved in commit ce23896.
"""

from anchor.ingest.chunk import build_variant, split_block  # noqa: F401
from anchor.ingest.layout import layout_heading, parse_layout, table_text  # noqa: F401
