#!/usr/bin/env python3
"""
================================================================================
 AI CLAIM EDITOR  --  single-file reference implementation
================================================================================

Fills an editable (AcroForm) PDF claim form from a canonical claim model.
Demonstrated against the Allianz "Property General Claim Form" (ACLM104/6F).

PIPELINE (mirrors the architecture discussed):

    A. INTROSPECT   walk page /Annots -> raw widget inventory
    B. BLUEPRINT    attach semantics to meaningless widget names
    C. RESOLVE      canonical claim model -> per-field values
                    (direct / derived / conditional-N-A / escalate)
    D. VALIDATE     syntactic + arithmetic + cross-field
    E. RENDER       write values into the ORIGINAL template, save a copy
    F. VERIFY       read values back out, diff against the fill plan

Run:
    python claim_filler.py <template.pdf> <output.pdf> [--watermark] [--json plan.json]

--------------------------------------------------------------------------------
NOTE ON "ANDROMEDA"
--------------------------------------------------------------------------------
I could not identify a PDF library named Andromeda, and I will not invent an API
for it. All PDF I/O is therefore isolated behind the PdfBackend interface below.
To swap engines, implement PdfBackend and change ONE line in main(). Nothing in
the blueprint, resolution, or validation layers touches the PDF library.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass, field as dc_field
from datetime import date
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject


# =============================================================================
# SECTION 0 -- PDF BACKEND (the only library-specific code; swap point)
# =============================================================================

@dataclass
class Widget:
    """One physical form control discovered in the template."""
    name: str
    page: int                 # 1-based
    rect: tuple               # (x0, y0, x1, y1) PDF pts, y=0 at page bottom
    ftype: str                # "text" | "checkbox" | "radio" | "choice"
    on_state: str | None = None      # checkbox/radio "checked" value, e.g. "/Yes"
    multiline: bool = False
    readonly: bool = False

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]

    def capacity(self, font_size: float) -> int:
        """Approx chars that fit on one line. Helvetica avg glyph ~0.5em."""
        return max(1, int(self.width / (0.5 * font_size)))


class PdfBackend:
    """Interface. Implement this to swap the PDF engine."""

    def introspect(self, path: str) -> list[Widget]: ...
    def fill(self, src: str, dst: str, values: dict[str, str],
             font_sizes: dict[str, float], watermark: str | None) -> None: ...
    def read_back(self, path: str) -> dict[str, str]: ...


class PypdfBackend(PdfBackend):
    """Reference implementation using pypdf."""

    # ---- A. INTROSPECT ------------------------------------------------------
    def introspect(self, path: str) -> list[Widget]:
        reader = PdfReader(path)
        widgets: list[Widget] = []

        for page_no, page in enumerate(reader.pages, start=1):
            for annot in (page.get("/Annots") or []):
                d = annot.get_object()
                if d.get("/Subtype") != "/Widget":
                    continue

                # Kid widgets carry no /T -- the name lives on the parent.
                # (This template has 61 such kids; a naive walk misses them
                #  entirely and silently loses both table grids.)
                name = d.get("/T")
                parent = d.get("/Parent")
                if name is None and parent is not None:
                    name = parent.get_object().get("/T")
                if name is None:
                    continue
                name = str(name)

                src = d if "/FT" in d else (parent.get_object() if parent else d)
                ft = src.get("/FT")
                flags = int(src.get("/Ff", 0) or 0)

                on_state = None
                if ft == "/Btn":
                    # The "checked" value is NOT "Yes"/True -- it is whatever key
                    # the author used in the appearance dictionary. Read it.
                    ap = d.get("/AP")
                    if ap and "/N" in ap:
                        keys = [str(k) for k in ap["/N"].get_object().keys()]
                        on = [k for k in keys if k != "/Off"]
                        on_state = on[0] if on else "/On"
                    ftype = "radio" if (flags & (1 << 15)) else "checkbox"
                elif ft == "/Ch":
                    ftype = "choice"
                else:
                    ftype = "text"

                widgets.append(Widget(
                    name=name,
                    page=page_no,
                    rect=tuple(round(float(v), 2) for v in d["/Rect"]),
                    ftype=ftype,
                    on_state=on_state,
                    multiline=bool(flags & (1 << 12)),
                    readonly=bool(flags & (1 << 0)),
                ))
        return widgets

    # ---- E. RENDER ----------------------------------------------------------
    def fill(self, src, dst, values, font_sizes, watermark=None):
        reader = PdfReader(src)
        writer = PdfWriter(clone_from=src)

        acro = writer._root_object["/AcroForm"]
        # Without this, values are stored in the file but many viewers render
        # nothing, because each widget caches its own appearance stream.
        acro[NameObject("/NeedAppearances")] = BooleanObject(True)

        # Per-field /DA. The template default is "/Helv 0 Tf" (auto-size), which
        # blows short strings up to fill tall boxes and shrinks long ones to
        # unreadable. Explicit sizes give predictable output.
        for page in writer.pages:
            for annot in (page.get("/Annots") or []):
                d = annot.get_object()
                nm = d.get("/T") or (d.get("/Parent").get_object().get("/T")
                                     if d.get("/Parent") else None)
                if nm is None:
                    continue
                size = font_sizes.get(str(nm))
                if size:
                    # Set /DA on the WIDGET, not the parent field. Kid widgets
                    # (this template has 61) inherit /FT from the parent but
                    # viewers resolve /DA from the widget first -- writing it to
                    # the parent silently leaves them on the auto-size default.
                    d[NameObject("/DA")] = TextStringObject(
                        f"/Helv {size} Tf 0 g")

        for page in writer.pages:
            page_names = set()
            for annot in (page.get("/Annots") or []):
                d = annot.get_object()
                nm = d.get("/T") or (d.get("/Parent").get_object().get("/T")
                                     if d.get("/Parent") else None)
                if nm:
                    page_names.add(str(nm))
            subset = {k: v for k, v in values.items() if k in page_names}
            if subset:
                writer.update_page_form_field_values(
                    page, subset, auto_regenerate=False)

        if watermark:
            self._stamp(writer, watermark)

        # Always tag provenance in metadata. Cheap now, awkward to retrofit.
        writer.add_metadata({
            "/Producer": "AI Claim Editor (reference implementation)",
            "/Subject": "SYNTHETIC / DEMONSTRATION DATA - not a submitted claim",
            "/Keywords": "synthetic;demo;not-a-real-claim",
        })

        with open(dst, "wb") as fh:
            writer.write(fh)

    def _stamp(self, writer, text: str) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import io
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.saveState()
        c.setFont("Helvetica-Bold", 46)
        c.setFillColorRGB(0.85, 0.15, 0.15, alpha=0.16)
        c.translate(A4[0] / 2, A4[1] / 2)
        c.rotate(38)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.save()
        buf.seek(0)
        stamp = PdfReader(buf).pages[0]
        for page in writer.pages:
            page.merge_page(stamp)

    # ---- F. VERIFY ----------------------------------------------------------
    def read_back(self, path: str) -> dict[str, str]:
        out = {}
        for name, f in (PdfReader(path).get_fields() or {}).items():
            v = f.get("/V")
            if v is not None:
                out[str(name)] = str(v)
        return out


# =============================================================================
# SECTION 1 -- BLUEPRINT
# =============================================================================
# The template's widget names are "Text Field0", "Check Box3" -- zero semantics.
# Everything meaningful lives here. In production this is LLM-drafted from
# nearby-text harvesting, then human-reviewed once, then cached by fingerprint.
# =============================================================================

@dataclass
class FieldSpec:
    key: str                          # canonical concept
    widgets: list[str]                # 1..n widgets; >1 = text flows across them
    kind: str = "text"                # text | money | date | bool | signature
    font: float = 9.0
    na_if_empty: bool = True          # form says: "if not applicable add N/A"
    required_if: Callable | None = None


@dataclass
class BoolSpec:
    key: str
    yes: str
    no: str


def T(n: int) -> str:
    return f"Text Field{n}"


def CB(n: int) -> str:
    return f"Check Box{n}"


# --- scalar / narrative fields ------------------------------------------------
FIELDS: list[FieldSpec] = [
    FieldSpec("claim_no",            [T(0)],  font=10),
    # Policyholder
    FieldSpec("insured_name",        [T(1)],  font=10),
    FieldSpec("policy_number",       [T(2)],  font=10),
    FieldSpec("address",             [T(3)],  font=8.5),
    FieldSpec("postcode",            [T(4)],  font=9),
    FieldSpec("occupation",          [T(5)]),
    FieldSpec("tel_home",            [T(6)]),
    FieldSpec("email",               [T(7)]),
    FieldSpec("mobile",              [T(8)]),
    FieldSpec("tel_office",          [T(9)]),
    FieldSpec("vat_details",         [T(10), T(11)], font=8.5),
    # Event
    FieldSpec("event_date",          [T(12)], kind="date"),
    FieldSpec("event_time",          [T(13)]),
    FieldSpec("discovered_by",       [T(14)], font=8.5),
    FieldSpec("loss_address",        [T(15)], font=8.5),
    FieldSpec("loss_postcode",       [T(16)]),
    # Property
    FieldSpec("interested_parties",  [T(17), T(18)], font=8.5),
    FieldSpec("sum_buildings",       [T(19)], kind="money"),
    FieldSpec("sum_contents",        [T(20)], kind="money"),
    FieldSpec("sum_stock",           [T(21)], kind="money"),
    FieldSpec("prev_claim_details",  [T(22), T(23)], font=8.5),
    FieldSpec("other_ins_details",   [T(24), T(25)], font=8.5),
    # Recovery
    FieldSpec("recovery_details",    [T(26), T(27)], font=8.5),
    FieldSpec("third_party",         [T(28), T(29), T(30)], font=8.5),
    FieldSpec("evidence",            [T(31), T(32), T(33)], font=8.5),
    # A. General
    FieldSpec("cause",               [T(34), T(35), T(36), T(37)], font=8.5),
    FieldSpec("crime_ref",           [T(38), T(39), T(40)], font=8.5),
    FieldSpec("police_station",      [T(41), T(42)], font=8.5),
    FieldSpec("trade_impact",        [T(43), T(44)], font=8.5),
    FieldSpec("daily_loss",          [T(45), T(46)], font=8.5),
    FieldSpec("gross_profit_pct",    [T(47), T(48)], font=8.5),
    FieldSpec("mitigation",          [T(49), T(50)], font=8.5),
    # Declaration
    FieldSpec("total_claimed",       [T(192)], kind="money", font=10),
    FieldSpec("signature",           [T(193)], kind="signature", font=11),
    FieldSpec("signed_date",         [T(194)], kind="date", font=10),
]

# --- paired Yes/No checkboxes -------------------------------------------------
# Each pair is two INDEPENDENT checkboxes, not a radio group -- so exactly one
# must be ticked and the other explicitly left /Off. A radio group would be set
# on the parent instead; the blueprint records which, so fill never guesses.
BOOLS: list[BoolSpec] = [
    BoolSpec("vat_registered",   CB(0),  CB(1)),
    BoolSpec("sole_owner",       CB(2),  CB(3)),
    BoolSpec("lease_repairs",    CB(4),  CB(5)),
    BoolSpec("previous_claim",   CB(6),  CB(7)),
    BoolSpec("other_insurance",  CB(8),  CB(9)),
    BoolSpec("third_party_resp", CB(10), CB(11)),
    BoolSpec("still_trading",    CB(12), CB(13)),
]

# --- repeating table regions --------------------------------------------------
# Both grids are regular and row-major in widget-name order. Detected by BOTH
# name pattern and rect clustering; either alone is unreliable.
BUILDINGS = dict(base=51, rows=9, cols=5, font=7.5,
                 columns=["description", "age", "last_maintained",
                          "estimate", "net_claimed"])
CONTENTS = dict(base=96, rows=12, cols=8, font=6.8,
                columns=["description", "date_acquired", "obtained_from",
                         "original_cost", "replacement_cost", "wear_tear",
                         "salvage", "amount_claimed"])


def table_widget(spec: dict, row: int, col: int) -> str:
    return T(spec["base"] + row * spec["cols"] + col)


# =============================================================================
# SECTION 2 -- CANONICAL CLAIM MODEL (form-agnostic dummy data)
# =============================================================================
# Persona-seeded: ONE coherent entity, every field derived from it. Independent
# per-field generation is what produces the uncanny "obviously fake" result.
# =============================================================================

CLAIM: dict[str, Any] = {
    "meta": {"claim_no": "PRP/2026/0884127", "synthetic": True},

    "policyholder": {
        "name": "Whitaker Plumbing & Heating Ltd",
        "policy_number": "CPM/4471902/07",
        "address": "Unit 7, Kirkstall Trade Park\nBridgewater Road\nLeeds",
        "postcode": "LS9 8AR",
        "occupation": "Plumbing & heating contractor",
        "tel_home": "0113 288 4417",
        "tel_office": "0113 288 4410",
        "mobile": "07784 220513",
        "email": "accounts@whitakerplumbing.co.uk",
        "vat_registered": True,
        "vat_number": "GB 412 8834 07",
        "vat_recovery_pct": 100,
    },

    "event": {
        "date": date(2026, 8, 14),
        "time": "02:35",
        "discovered": "07:10, 15/08/2026, by M. J. Whitaker, Director",
        "address": "Unit 7, Kirkstall Trade Park, Bridgewater Road, Leeds",
        "postcode": "LS9 8AR",
    },

    "property": {
        "sole_owner": False,
        "interested_parties": ("Kirkstall Estates Ltd (freeholder / landlord), "
                               "Bridgewater House, Leeds LS4 2QE. "
                               "Lombard North Central plc - finance agreement over plant."),
        "lease_repairs_responsibility": True,
        "sum_buildings": 285000,
        "sum_contents": 96500,
        "sum_stock": 42000,
        "previous_claim": True,
        "previous_claim_details": ("Escape of water from a failed washing machine hose, "
                                   "March 2023, insured with Aviva (policy 21/CM/889402). "
                                   "Settled at GBP 4,180.00. No other claims in the last 5 years."),
        "other_insurance": False,
    },

    "general": {
        "cause": ("Forced entry overnight. Offenders levered the rear fire exit door from the "
                  "service yard, splitting the frame and defeating the panic bar, then broke "
                  "through a stud partition into the stores. Power tools, test equipment and "
                  "copper tube stock were removed to a van. CCTV shows two persons on site for "
                  "18 minutes. No fire or water damage."),
        "crime_ref": ("Crime reference 13260814/26, allocated to PC 4412 Hardisty, "
                      "West Yorkshire Police. Scenes of crime attended 15/08/2026."),
        "police_station": "Elland Road Police Station, Leeds LS11 8BU - 0113 241 5000 (or 101)",
        "still_trading": False,
        "trade_impact": ("Partially suspended. Only maintenance call-outs can be serviced until "
                         "replacement tools arrive - approximately 10 working days."),
        "daily_loss": "Approximately GBP 1,450 of turnover per working day",
        "gross_profit_pct": "42% gross profit on turnover (year ended 31/03/2026)",
        "mitigation": ("Emergency board-up and locksmith attended 15/08/2026 (GBP 310, invoice "
                       "attached). Locks replaced, alarm re-coded, hire tools obtained. Police "
                       "and insurers notified same day."),
    },

    "recovery": {
        "third_party_responsible": True,
        "details": ("Alarm signal was received but not acted upon. Monitoring contract requires "
                    "keyholder notification within 10 minutes of activation; no contact was made."),
        "third_party": ("Sentinel Alarm Monitoring Ltd, 22 Cross Green Way, Leeds LS9 0SE. "
                        "Tel 0113 245 9911. Contract SM/WPH/2024-118. "
                        "Insurer understood to be QBE UK (broker: Marsh Commercial, Leeds)."),
        "evidence": ("Enclosed: 14 photographs of the damaged door, frame and partition; CCTV "
                     "footage 02:31-02:55 on USB; alarm activation log from Sentinel; locksmith "
                     "and board-up invoice; purchase invoices for stolen tools. Witness: "
                     "D. Osei, Kirkstall Motor Factors, Unit 9 (same estate), 07901 662214."),
    },

    # Buildings damage -- amounts drive the declaration total
    "buildings_items": [
        {"description": "Rear fire exit door, frame and panic bar",
         "age": "12 years", "last_maintained": "03/2025",
         "estimate": 2340.00, "net_claimed": 2340.00},
        {"description": "Internal stud partition to stores",
         "age": "12 years", "last_maintained": "03/2025",
         "estimate": 985.00, "net_claimed": 985.00},
    ],

    # Contents / stock -- amount_claimed is DERIVED, not stated
    "contents_items": [
        {"description": "Hilti TE 6-A22 drill x2",
         "date_acquired": "04/2023", "obtained_from": "City Plumbing, Leeds",
         "original_cost": 1190.00, "replacement_cost": 1310.00,
         "wear_tear": 262.00, "salvage": 0.00},
        {"description": "Rothenberger press kit",
         "date_acquired": "09/2024", "obtained_from": "Wolseley UK, Wakefield",
         "original_cost": 2050.00, "replacement_cost": 2185.00,
         "wear_tear": 218.50, "salvage": 0.00},
        {"description": "Copper tube 15/22mm",
         "date_acquired": "06/2026", "obtained_from": "Wolseley UK, Wakefield",
         "original_cost": 2480.00, "replacement_cost": 2610.00,
         "wear_tear": 0.00, "salvage": 0.00},
        {"description": "Testo 557 manifold",
         "date_acquired": "01/2025", "obtained_from": "BOSS Industrial, BD4",
         "original_cost": 1425.00, "replacement_cost": 1495.00,
         "wear_tear": 149.50, "salvage": 120.00},
    ],

    "declaration": {
        "signature": "M. J. Whitaker (Director)",
        "date": date(2026, 8, 26),
    },
}


# =============================================================================
# SECTION 3 -- RESOLUTION ENGINE
# =============================================================================
# Order matters: direct -> derived -> conditional N/A -> synthetic -> escalate.
# Running synthetic before derived is how you get a declaration total that does
# not equal the sum of the line items -- the single clearest tell of a fake form.
# =============================================================================

@dataclass
class Resolved:
    key: str
    value: str
    source: str          # direct | derived | conditional-na | unresolved
    note: str = ""


def money(v: float) -> str:
    return f"{v:,.2f}"


def gbdate(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class ResolutionEngine:
    def __init__(self, claim: dict):
        self.c = claim
        self.plan: dict[str, Resolved] = {}
        self.bools: dict[str, bool] = {}
        self.tables: dict[str, list[dict]] = {}

    def _put(self, key, value, source, note=""):
        self.plan[key] = Resolved(key, str(value), source, note)

    def run(self) -> "ResolutionEngine":
        p, e = self.c["policyholder"], self.c["event"]
        pr, g, r = self.c["property"], self.c["general"], self.c["recovery"]

        # ---- 1. DIRECT ------------------------------------------------------
        direct = {
            "claim_no": self.c["meta"]["claim_no"],
            "insured_name": p["name"], "policy_number": p["policy_number"],
            "address": p["address"], "postcode": p["postcode"],
            "occupation": p["occupation"], "tel_home": p["tel_home"],
            "tel_office": p["tel_office"], "mobile": p["mobile"],
            "email": p["email"],
            "event_date": gbdate(e["date"]), "event_time": e["time"],
            "discovered_by": e["discovered"],
            "loss_address": e["address"], "loss_postcode": e["postcode"],
            "sum_buildings": money(pr["sum_buildings"]),
            "sum_contents": money(pr["sum_contents"]),
            "sum_stock": money(pr["sum_stock"]),
            "cause": g["cause"], "crime_ref": g["crime_ref"],
            "police_station": g["police_station"],
            "mitigation": g["mitigation"],
            "third_party": r["third_party"], "evidence": r["evidence"],
            "signature": self.c["declaration"]["signature"],
            "signed_date": gbdate(self.c["declaration"]["date"]),
        }
        for k, v in direct.items():
            self._put(k, v, "direct")

        # ---- 2. BOOLEANS ----------------------------------------------------
        self.bools = {
            "vat_registered":   p["vat_registered"],
            "sole_owner":       pr["sole_owner"],
            "lease_repairs":    pr["lease_repairs_responsibility"],
            "previous_claim":   pr["previous_claim"],
            "other_insurance":  pr["other_insurance"],
            "third_party_resp": r["third_party_responsible"],
            "still_trading":    g["still_trading"],
        }

        # ---- 3. DERIVED -----------------------------------------------------
        b_items = self.c["buildings_items"]
        c_items = []
        for it in self.c["contents_items"]:
            it = dict(it)
            # amount claimed = replacement - wear/tear - salvage
            it["amount_claimed"] = round(
                it["replacement_cost"] - it["wear_tear"] - it["salvage"], 2)
            c_items.append(it)
        self.tables = {"buildings": b_items, "contents": c_items}

        total = sum(i["net_claimed"] for i in b_items) + \
                sum(i["amount_claimed"] for i in c_items)
        self._put("total_claimed", money(total), "derived",
                  "sum of buildings net + contents amount claimed")

        if p["vat_registered"]:
            self._put("vat_details",
                      f"VAT No. {p['vat_number']} - "
                      f"{p['vat_recovery_pct']}% recoverable",
                      "derived", "required because vat_registered = Yes")

        # ---- 4. CONDITIONAL (fill or N/A per the form's own rules) ----------
        self._conditional("interested_parties", not pr["sole_owner"],
                          pr["interested_parties"],
                          "required when sole_owner = No")
        self._conditional("prev_claim_details", pr["previous_claim"],
                          pr["previous_claim_details"],
                          "required when previous_claim = Yes")
        self._conditional("other_ins_details", pr["other_insurance"], None,
                          "not applicable: other_insurance = No")
        self._conditional("recovery_details", r["third_party_responsible"],
                          r["details"],
                          "required when third_party_responsible = Yes")
        for key, val in (("trade_impact", g["trade_impact"]),
                         ("daily_loss", g["daily_loss"]),
                         ("gross_profit_pct", g["gross_profit_pct"])):
            self._conditional(key, not g["still_trading"], val,
                              "required when still_trading = No")
        return self

    def _conditional(self, key, applies: bool, value, why: str):
        if applies and value:
            self._put(key, value, "direct", why)
        elif applies:
            self._put(key, "", "unresolved", f"REQUIRED but missing: {why}")
        else:
            # The form instructs: "If any are not applicable please add N/A"
            self._put(key, "N/A", "conditional-na", why)


# =============================================================================
# SECTION 4 -- VALIDATOR (cheapest tier first)
# =============================================================================

class Validator:
    def __init__(self, eng: ResolutionEngine):
        self.e = eng
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def run(self) -> "Validator":
        import re
        plan, tables = self.e.plan, self.e.tables

        # -- tier 1: syntactic ------------------------------------------------
        uk_pc = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$")
        for k in ("postcode", "loss_postcode"):
            v = plan[k].value
            if not uk_pc.match(v.upper()):
                self.errors.append(f"{k}: '{v}' is not a valid UK postcode")
        if "@" not in plan["email"].value:
            self.errors.append("email: malformed")
        try:
            from datetime import datetime
            datetime.strptime(plan["event_date"].value, "%d/%m/%Y")
        except ValueError:
            self.errors.append("event_date: not dd/mm/yyyy")

        # -- tier 2: arithmetic -----------------------------------------------
        for i, it in enumerate(tables["contents"], 1):
            expect = round(it["replacement_cost"] - it["wear_tear"]
                           - it["salvage"], 2)
            if abs(expect - it["amount_claimed"]) > 0.005:
                self.errors.append(
                    f"contents row {i}: col8 {it['amount_claimed']} != "
                    f"col5-col6-col7 ({expect})")

        total = sum(i["net_claimed"] for i in tables["buildings"]) + \
                sum(i["amount_claimed"] for i in tables["contents"])
        declared = float(plan["total_claimed"].value.replace(",", ""))
        if abs(total - declared) > 0.005:
            self.errors.append(
                f"declaration total {declared} != line-item sum {total}")

        # -- tier 3: cross-field (rules authored WITH the blueprint) ----------
        b = self.e.bools
        rules = [
            (not b["sole_owner"], "interested_parties",
             "sole_owner=No requires interested parties"),
            (b["previous_claim"], "prev_claim_details",
             "previous_claim=Yes requires particulars"),
            (b["third_party_resp"], "recovery_details",
             "third_party_responsible=Yes requires particulars"),
            (not b["still_trading"], "daily_loss",
             "still_trading=No requires daily loss figure"),
            (not b["still_trading"], "gross_profit_pct",
             "still_trading=No requires gross profit percentage"),
            (b["vat_registered"], "vat_details",
             "vat_registered=Yes requires VAT number and percentage"),
        ]
        for triggered, key, msg in rules:
            if triggered:
                v = plan.get(key)
                if v is None or not v.value or v.value == "N/A":
                    self.errors.append(f"cross-field: {msg}")

        # -- temporal coherence ----------------------------------------------
        ev = self.e.c["event"]["date"]
        sg = self.e.c["declaration"]["date"]
        if sg < ev:
            self.errors.append("signed_date precedes event date")

        # -- capacity warnings are raised later, once widths are known --------
        for k, r in plan.items():
            if r.source == "unresolved":
                self.warnings.append(f"unresolved -> needs human input: {k}")
        return self


# =============================================================================
# SECTION 5 -- LAYOUT: flow resolved text across the widgets available
# =============================================================================
# The template has no multi-line boxes for narrative answers -- it has runs of
# single-line widgets (the "cause" answer spans 4). Text must be wrapped to each
# widget's own character capacity, which differs because the first widget in a
# run starts after the printed label.
# =============================================================================

FONT_FLOOR = 5.4          # below this, output stops being legible


def _pack(words: list[str], widgets: list[Widget], font: float):
    """Greedy wrap into the run. Returns (per-widget lines, words_left)."""
    lines, idx = [], 0
    for w in widgets:
        cap = w.capacity(font)
        line, used = [], 0
        while idx < len(words):
            add = len(words[idx]) + (1 if line else 0)
            if used + add > cap:
                break
            line.append(words[idx]); used += add; idx += 1
        lines.append(" ".join(line))
    return lines, len(words) - idx


def flow(text: str, widgets: list[Widget], font: float):
    """Fit text into a run of widgets, shrinking the font before ever
    truncating. Returns (values, fonts, warnings)."""
    values, fonts, warns = {}, {}, []

    # Multi-line box: let the viewer wrap it; just shrink if clearly dense.
    if len(widgets) == 1 and widgets[0].multiline:
        w = widgets[0]
        size = font

        def needed(sz: float) -> int:
            """Rows required once explicit newlines AND wrapping are counted."""
            cap = w.capacity(sz)
            return sum(max(1, -(-len(ln) // cap)) for ln in text.split("\n"))

        # Reserve ~2pt of internal padding; viewers clip the last line otherwise.
        while size > FONT_FLOOR and \
                needed(size) * size * 1.18 > (w.height - 2):
            size -= 0.5
        if size < font:
            warns.append(f"{w.name}: auto-shrunk {font} -> {size}pt "
                         f"({needed(size)} lines into {w.height:.0f}pt box)")
        values[w.name] = text
        fonts[w.name] = size
        return values, fonts, warns

    words = " ".join(text.split()).split()
    size = font
    lines, left = _pack(words, widgets, size)
    while left > 0 and size > FONT_FLOOR:
        size -= 0.5
        lines, left = _pack(words, widgets, size)

    if left > 0:
        warns.append(f"{widgets[0].name} run: {left} words will not fit "
                     f"{len(widgets)} widget(s) even at {size}pt -- "
                     f"content needs a continuation sheet")
        # keep the text rather than silently dropping it mid-sentence
        lines[-1] = (lines[-1] + " " + " ".join(words[len(words)-left:]))
    elif size < font:
        warns.append(f"{widgets[0].name} run: auto-shrunk {font} -> {size}pt to fit")

    for w, line in zip(widgets, lines):
        if line:
            values[w.name] = line
            fonts[w.name] = size
    return values, fonts, warns


def fit_cell(text: str, w: Widget, font: float):
    """Shrink a single table cell's font until the string fits."""
    size = font
    while size > FONT_FLOOR and len(text) > w.capacity(size):
        size -= 0.3
    return size, (len(text) > w.capacity(size))


# =============================================================================
# SECTION 6 -- ORCHESTRATION
# =============================================================================

def build_values(eng: ResolutionEngine, index: dict[str, Widget]):
    values: dict[str, str] = {}
    fonts: dict[str, float] = {}
    warns: list[str] = []
    touched: set[str] = set()

    # ---- scalar + narrative fields -----------------------------------------
    for spec in FIELDS:
        res = eng.plan.get(spec.key)
        if res is None or res.value == "":
            continue
        ws = [index[n] for n in spec.widgets if n in index]
        if len(ws) != len(spec.widgets):
            warns.append(f"{spec.key}: widget(s) missing from template")
        if not ws:
            continue
        v, f2, w2 = flow(res.value, ws, spec.font)
        values.update(v); fonts.update(f2); warns.extend(w2)
        touched.update(v)

    # ---- Yes/No pairs: tick one, explicitly clear the other ----------------
    for bs in BOOLS:
        val = eng.bools.get(bs.key)
        if val is None:
            continue
        for name, on in ((bs.yes, val), (bs.no, not val)):
            w = index.get(name)
            if not w:
                warns.append(f"{bs.key}: checkbox {name} not in template")
                continue
            values[name] = (w.on_state or "/Yes") if on else "/Off"
            touched.add(name)

    # ---- repeating regions --------------------------------------------------
    for tname, spec in (("buildings", BUILDINGS), ("contents", CONTENTS)):
        items = eng.tables[tname]
        if len(items) > spec["rows"]:
            warns.append(f"{tname}: {len(items)} items but only "
                         f"{spec['rows']} rows -- continuation sheet needed")
        for r, item in enumerate(items[:spec["rows"]]):
            cells = []
            for c, col in enumerate(spec["columns"]):
                raw = item.get(col)
                if raw is None:
                    continue
                txt = money(raw) if isinstance(raw, (int, float)) else str(raw)
                name = table_widget(spec, r, c)
                w = index.get(name)
                if not w:
                    warns.append(f"{tname}[{r}][{col}]: {name} missing")
                    continue
                cells.append((name, w, col, txt))

            # One font size for the whole row. Sizing each cell independently
            # makes a row look like a ransom note -- the clearest visual tell
            # that a form was machine-filled.
            row_size, over = spec["font"], []
            for name, w, col, txt in cells:
                size, still = fit_cell(txt, w, spec["font"])
                row_size = min(row_size, size)
                if still:
                    over.append(col)
            for col in over:
                warns.append(f"{tname} row {r+1} ({col}): will not fit even at "
                             f"{row_size:.1f}pt -- shorten source text")
            for name, w, col, txt in cells:
                values[name] = txt
                fonts[name] = round(row_size, 1)
                touched.add(name)

    # ---- coverage: every widget consciously decided, none silently skipped --
    unmapped = sorted(set(index) - touched)
    return values, fonts, warns, unmapped


def main() -> int:
    ap = argparse.ArgumentParser(description="AI claim form filler")
    ap.add_argument("template")
    ap.add_argument("output")
    ap.add_argument("--watermark", action="store_true",
                    help="stamp SPECIMEN across every page")
    ap.add_argument("--json", help="write the fill plan to this path")
    ap.add_argument("--strict", action="store_true",
                    help="refuse to render if validation fails")
    args = ap.parse_args()

    backend: PdfBackend = PypdfBackend()   # <-- swap engine here, nowhere else

    # A. INTROSPECT
    widgets = backend.introspect(args.template)
    index = {w.name: w for w in widgets}
    print(f"[A] introspect  : {len(widgets)} widgets on "
          f"{len({w.page for w in widgets})} pages "
          f"({sum(w.ftype=='text' for w in widgets)} text, "
          f"{sum(w.ftype!='text' for w in widgets)} button)")

    on_states = {w.on_state for w in widgets if w.ftype != "text"}
    print(f"[A] checkbox on-states discovered: {on_states or '{}'}")

    # B/C. RESOLVE
    eng = ResolutionEngine(CLAIM).run()
    by_src: dict[str, int] = {}
    for r in eng.plan.values():
        by_src[r.source] = by_src.get(r.source, 0) + 1
    print(f"[C] resolve     : {len(eng.plan)} concepts {by_src}")

    # D. VALIDATE
    val = Validator(eng).run()
    values, fonts, warns, unmapped = build_values(eng, index)
    for w in warns:
        val.warnings.append(w)

    if val.errors:
        print("[D] validate    : FAILED")
        for e in val.errors:
            print(f"      ERROR  {e}")
        if args.strict:
            return 1
    else:
        print("[D] validate    : passed "
              "(syntactic, arithmetic, cross-field, temporal)")
    for w in val.warnings[:12]:
        print(f"      warn   {w}")
    if len(val.warnings) > 12:
        print(f"      warn   ... and {len(val.warnings)-12} more")

    # E. RENDER
    backend.fill(args.template, args.output, values, fonts,
                 "SPECIMEN - SYNTHETIC DATA" if args.watermark else None)
    print(f"[E] render      : wrote {len(values)} widget values -> {args.output}")
    print(f"[E] coverage    : {len(values)}/{len(index)} widgets filled, "
          f"{len(unmapped)} intentionally blank")

    # F. VERIFY -- read the saved file back and diff against the plan
    back = backend.read_back(args.output)
    mismatch = [(k, values[k], back.get(k, "<absent>"))
                for k in values if back.get(k) != values[k]]
    if mismatch:
        print(f"[F] verify      : {len(mismatch)} MISMATCH")
        for k, want, got in mismatch[:8]:
            print(f"      {k}: wanted {want!r} got {got!r}")
    else:
        print(f"[F] verify      : all {len(values)} values read back identical")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({
                "plan": {k: r.__dict__ for k, r in eng.plan.items()},
                "booleans": eng.bools,
                "tables": {k: [{kk: (str(vv)) for kk, vv in it.items()}
                               for it in v] for k, v in eng.tables.items()},
                "widget_values": values,
                "errors": val.errors,
                "warnings": val.warnings,
                "unmapped_widgets": unmapped,
            }, fh, indent=2, default=str)
        print(f"[+] fill plan   : {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())