from anchor.ingest.parse import serialize_table


def test_serialize_table_ignores_empty_pdf_cells() -> None:
    rows = [["Header", None], [None, "Value"]]

    assert serialize_table(rows) == "Header\nValue"
