"""Azure Document Intelligence call plus pure helpers that turn a result dict into table rows."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentAnalysisFeature
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError


@dataclass(frozen=True)
class Model:
    label: str
    model_id: str
    blurb: str
    tabs: tuple[str, ...]
    features: tuple[str, ...] = ()


MODELS = [
    Model("OCR / Read", "prebuilt-read", "Plain text, line by line, with confidence.", ("Content", "JSON")),
    Model("Layout", "prebuilt-layout", "Text, tables, selection marks and structure.", ("Content", "Tables", "JSON")),
    Model("Invoices", "prebuilt-invoice", "Vendor, customer, totals, dates and line items.",
          ("Fields", "Tables", "Content", "JSON")),
    Model("Receipts", "prebuilt-receipt", "Merchant, date, totals, tax, tip and items.",
          ("Fields", "Tables", "Content", "JSON")),
    Model("General documents", "prebuilt-layout", "Key-value pairs found in any document, plus tables.",
          ("Key-value pairs", "Tables", "Content", "JSON"), ("keyValuePairs",)),
]
BY_LABEL = {m.label: m for m in MODELS}


class AnalyzeError(Exception):
    """A message that is safe to show to the user."""


def configured() -> bool:
    return bool(os.getenv("AZURE_DOCINTEL_ENDPOINT") and os.getenv("AZURE_DOCINTEL_KEY"))


def analyze(data: bytes, model: Model) -> dict:
    """Run one model over the bytes and return the result as a camelCase dict (the REST shape)."""
    if not configured():
        raise AnalyzeError("Set AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY in .env first.")
    client = DocumentIntelligenceClient(os.environ["AZURE_DOCINTEL_ENDPOINT"],
                                        AzureKeyCredential(os.environ["AZURE_DOCINTEL_KEY"]))
    features = [DocumentAnalysisFeature.KEY_VALUE_PAIRS] if model.features else None
    for attempt in range(4):
        try:
            poller = client.begin_analyze_document(model.model_id, AnalyzeDocumentRequest(bytes_source=data),
                                                   features=features)
            return poller.result().as_dict()
        except HttpResponseError as e:
            if e.status_code == 429 and attempt < 3:  # free tier: 20 calls a minute
                time.sleep(8 * (attempt + 1))
                continue
            if e.status_code == 400:
                raise AnalyzeError("Azure could not read this file. Try a PDF, JPG, PNG, TIFF or BMP.") from e
            raise AnalyzeError(f"Azure error: {e.message}"[:300]) from e
    raise AnalyzeError("Azure is rate limiting requests. Wait a minute and try again.")


# ---- result dict -> rows. Every row is {"page", "polygon", ...columns}; page/polygon feed the overlay. ----

def _region(item: dict) -> tuple[int | None, list[float]]:
    regions = item.get("boundingRegions") or []
    if regions:
        return regions[0].get("pageNumber"), regions[0].get("polygon") or []
    return None, []


def _value(field: dict):
    """The typed value of an invoice/receipt field, falling back to its raw text."""
    for k, v in field.items():
        if k.startswith("value") and v is not None:
            if isinstance(v, dict) and "amount" in v:
                return f"{v.get('currencySymbol', '')}{v['amount']}"
            if isinstance(v, (str, int, float)):
                return v
    return field.get("content")


def field_rows(result: dict) -> list[dict]:
    """Flatten invoice/receipt fields, expanding arrays and objects (Items[0].Amount)."""
    rows: list[dict] = []

    def walk(name: str, f: dict):
        if f.get("type") == "array":
            for i, sub in enumerate(f.get("valueArray") or []):
                walk(f"{name}[{i}]", sub)
        elif f.get("type") == "object":
            for k, sub in (f.get("valueObject") or {}).items():
                walk(f"{name}.{k}", sub)
        else:
            page, poly = _region(f)
            rows.append({"page": page, "polygon": poly, "Field": name, "Value": str(_value(f) or ""),
                         "Confidence": f.get("confidence")})

    for doc in result.get("documents") or []:
        for name, f in (doc.get("fields") or {}).items():
            walk(name, f)
    return rows


def kv_rows(result: dict) -> list[dict]:
    rows = []
    for kv in result.get("keyValuePairs") or []:
        page, poly = _region(kv.get("value") or kv.get("key") or {})
        rows.append({"page": page, "polygon": poly, "Key": (kv.get("key") or {}).get("content", ""),
                     "Value": (kv.get("value") or {}).get("content", ""), "Confidence": kv.get("confidence")})
    return rows


def line_rows(result: dict) -> list[dict]:
    """One row per line, with the average word confidence as the line confidence."""
    rows = []
    for p in result.get("pages") or []:
        words = p.get("words") or []
        for ln in p.get("lines") or []:
            spans = ln.get("spans") or [{}]
            lo, hi = spans[0].get("offset", 0), spans[0].get("offset", 0) + spans[0].get("length", 0)
            conf = [w["confidence"] for w in words
                    if w.get("confidence") is not None and lo <= (w.get("span") or {}).get("offset", -1) < hi]
            rows.append({"page": p.get("pageNumber"), "polygon": ln.get("polygon") or [], "Line": ln.get("content", ""),
                         "Confidence": sum(conf) / len(conf) if conf else None})
    return rows


def table_rows(result: dict) -> list[dict]:
    """One row per table cell; the viewer groups them back into a grid per table."""
    rows = []
    for t, table in enumerate(result.get("tables") or []):
        for c in table.get("cells") or []:
            page, poly = _region(c)
            rows.append({"page": page, "polygon": poly, "table": t + 1, "row": c.get("rowIndex", 0),
                         "col": c.get("columnIndex", 0), "text": c.get("content", ""), "kind": c.get("kind", "content")})
    return rows


def stats(result: dict) -> dict:
    return {
        "Pages": len(result.get("pages") or []),
        "Lines": sum(len(p.get("lines") or []) for p in result.get("pages") or []),
        "Tables": len(result.get("tables") or []),
        "Fields": len(field_rows(result)) or len(result.get("keyValuePairs") or []),
    }
