from skydi import analyzer as a

SQ = [1, 1, 2, 1, 2, 2, 1, 2]
RESULT = {
    "pages": [{"pageNumber": 1, "width": 8.5, "height": 11, "unit": "inch",
               "words": [{"content": "hi", "confidence": 0.9, "span": {"offset": 0, "length": 2}},
                         {"content": "yo", "confidence": 0.7, "span": {"offset": 3, "length": 2}}],
               "lines": [{"content": "hi yo", "polygon": SQ, "spans": [{"offset": 0, "length": 5}]}]}],
    "documents": [{"fields": {
        "VendorName": {"type": "string", "valueString": "Contoso", "confidence": 0.99,
                       "boundingRegions": [{"pageNumber": 1, "polygon": SQ}]},
        "Items": {"type": "array", "valueArray": [{"type": "object", "valueObject": {
            "Amount": {"type": "currency", "valueCurrency": {"amount": 5, "currencySymbol": "$"}, "confidence": 0.8,
                       "boundingRegions": [{"pageNumber": 1, "polygon": SQ}]}}}]}}}],
    "keyValuePairs": [{"key": {"content": "Date"}, "value": {"content": "May 1", "boundingRegions": [
        {"pageNumber": 1, "polygon": SQ}]}, "confidence": 0.5}],
    "tables": [{"cells": [{"rowIndex": 0, "columnIndex": 1, "content": "x", "kind": "columnHeader",
                           "boundingRegions": [{"pageNumber": 1, "polygon": SQ}]}]}],
}


def test_field_rows_flatten_nested_fields():
    rows = a.field_rows(RESULT)
    assert [(r["Field"], r["Value"]) for r in rows] == [("VendorName", "Contoso"), ("Items[0].Amount", "$5")]
    assert rows[0]["page"] == 1 and rows[0]["polygon"] == SQ


def test_kv_rows():
    assert a.kv_rows(RESULT)[0]["Key"] == "Date"
    assert a.kv_rows(RESULT)[0]["Confidence"] == 0.5


def test_line_confidence_is_average_of_words():
    assert abs(a.line_rows(RESULT)[0]["Confidence"] - 0.8) < 1e-9


def test_table_rows_and_stats():
    assert a.table_rows(RESULT)[0]["table"] == 1
    assert a.stats(RESULT) == {"Pages": 1, "Lines": 1, "Tables": 1, "Fields": 2}


def test_general_documents_uses_layout_with_kv_feature():
    m = a.BY_LABEL["General documents"]
    assert m.model_id == "prebuilt-layout" and m.features
