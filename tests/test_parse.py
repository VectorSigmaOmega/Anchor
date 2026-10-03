from anchor.ingest.parse import serialize_table


def test_serialize_table_preserves_empty_pdf_cell_positions() -> None:
    rows = [["Header", None], [None, "Value"]]

    assert serialize_table(rows) == "Header | \n | Value"
