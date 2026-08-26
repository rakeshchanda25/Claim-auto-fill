#!/usr/bin/env python3
"""
================================================================================
 AUTOFILL  --  blank PDF in, filled PDF out. One command, any AcroForm.
================================================================================

    python autofill.py blank_form.pdf filled.pdf

With semantic LLM classification:

    python autofill.py blank_form.pdf filled.pdf --llm

The LLM is configured through:

    GEN_MODEL = "qwen3.6:27b"
    PROVIDER = "litellm"

and initialized with:

    get_genai_llm()

No Anthropic API key is required.

Pipeline:

    blueprint_builder.build_draft()   structure  (universal, deterministic)
              |
              v
    classify() / classify_llm()       label text -> concept + dtype
              |
              v
    generate()                        persona-seeded synthetic values
              |
              v
    claim_filler.PypdfBackend         layout, render, read-back verify

WHAT IS HONEST ABOUT THIS
-------------------------
Structure detection is exact.

Without --llm, classification is keyword-based, so it is good on conventional
labels ("Postcode", "Date", "Amount") and mediocre on prose questions.

With --llm, semantic classification is delegated to the configured chat model.
If the LLM fails or returns an invalid classification, the code automatically
falls back to the deterministic keyword classifier.

Everything here is template-agnostic.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys

import pdfplumber

from blueprint_builder import build_draft, harvest_text
from claim_filler import PypdfBackend, flow, fit_cell, money

# ---------------------------------------------------------------------------
# LLM imports
# ---------------------------------------------------------------------------
# Replace this import with the actual module where ModelConfig and
# get_chat_model are defined in your project.
#
# Example:
# from genai import ModelConfig, get_chat_model
#
# Or:
# from your_llm_module import ModelConfig, get_chat_model
# ---------------------------------------------------------------------------

from andromeda.config import ModelConfig, AgentConfig
from andromeda.utils import get_chat_model


# =============================================================================
# LLM CONFIGURATION
# =============================================================================

GEN_MODEL = "qwen3.6:27b"
# GEN_MODEL = "llama3.2:3b"

PROVIDER = "litellm"
# PROVIDER = "ollama"


def get_genai_llm():
    return get_chat_model(
        model_config=ModelConfig(
            name=GEN_MODEL,
            provider=PROVIDER,
            temperature=0,
        )
    )


# =============================================================================
# 1. CLASSIFY -- label text to (dtype, concept)
# =============================================================================

# Ordered most-specific first; the first pattern that matches wins.

RULES: list[tuple[str, str]] = [
    (r"post\s*code|zip", "postcode"),
    (r"e-?mail", "email"),
    (r"\bmobile\b", "mobile"),

    # "Vat No & %" must beat the percent rule.
    # Bare "Office" is a phone label on most forms.
    (r"\bvat\b", "vat"),
    (
        r"\btel\b|telephone|phone|\bfax\b|^office$|\boffice\b",
        "phone",
    ),

    (r"signature|signed by", "signature"),
    (r"percent|percentage|\bgross profit\b", "percent"),

    # Narrative answer, not a date.
    (r"by whom|who discovered|discovered", "prose"),

    (r"date and time", "date"),
    (r"\btime\b", "time"),
    (r"\bdate\b|\bwhen\b|acquired|expiry|d\.o\.b|birth", "date"),

    (
        r"£|\bamount\b|\bcost\b|\bvalue\b|\bsum\b|estimate|claimed|"
        r"salvage|deduction|\bprice\b|\btotal\b",
        "money",
    ),

    (
        r"policy number|claim no|reference|crime ref|\bno\.\b|number",
        "identifier",
    ),

    (r"occupation|trade|business type|profession", "occupation"),

    (
        r"name of insured|policyholder|insured name|^name\b|full name",
        "org_name",
    ),

    (r"address", "address"),
    (r"\bage\b", "age"),

    (
        r"description|specify|articles|particulars of (goods|items)",
        "item",
    ),

    (
        r"from whom|obtained|supplier|purchased from",
        "supplier",
    ),
]


VALID_DTYPES = {
    "postcode",
    "email",
    "mobile",
    "phone",
    "signature",
    "percent",
    "vat",
    "date",
    "time",
    "money",
    "identifier",
    "occupation",
    "org_name",
    "address",
    "age",
    "item",
    "supplier",
    "short_text",
    "prose",
}


def classify(label: str, multiline: bool, capacity: int) -> str:
    """
    Deterministic keyword classifier.

    This is always available as the fallback if the LLM is unavailable.
    """

    lab = " ".join((label or "").lower().split())

    for pattern, dtype in RULES:
        if re.search(pattern, lab):
            return dtype

    # A question mark or long/multiline label usually expects prose.
    if "?" in lab or capacity > 120 or multiline:
        return "prose"

    return "short_text"


# =============================================================================
# 1B. LLM CLASSIFIER
# =============================================================================

def _extract_llm_text(response) -> str:
    """
    Extract text from common chat-model response formats.

    Supports:
      - response.content
      - plain string responses
    """

    if isinstance(response, str):
        return response.strip()

    content = getattr(response, "content", None)

    if content is None:
        return str(response).strip()

    if isinstance(content, str):
        return content.strip()

    # Some providers may return a list of content blocks.
    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            text = getattr(item, "text", None)

            if text:
                parts.append(str(text))

        if parts:
            return " ".join(parts).strip()

    return str(content).strip()


def _clean_llm_dtype(text: str) -> str | None:
    """
    Normalize an LLM response into one of VALID_DTYPES.

    The model is instructed to return only a dtype, but this function is
    deliberately defensive against responses such as:

        "The answer is prose."
        "prose."
        "`prose`"
        "dtype: prose"
    """

    if not text:
        return None

    value = text.strip().lower()

    # Remove markdown/code formatting.
    value = value.replace("```text", "")
    value = value.replace("```", "")
    value = value.strip("` \n\t:.-")

    # Direct match.
    if value in VALID_DTYPES:
        return value

    # Look for an exact valid dtype as a standalone token.
    for dtype in sorted(VALID_DTYPES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(dtype)}\b", value):
            return dtype

    return None


def classify_llm(
    llm,
    label: str,
    multiline: bool,
    capacity: int,
) -> str:
    """
    Semantic classification using the configured GenAI chat model.

    If the LLM fails or returns an invalid dtype, deterministic classification
    is used instead.
    """

    prompt = f"""
You classify fields from arbitrary PDF forms.

Classify the following form field into exactly ONE dtype.

Allowed dtypes:
{", ".join(sorted(VALID_DTYPES))}

Field label:
{label!r}

Multiline:
{multiline}

Character capacity:
{capacity}

Definitions:

postcode
  Postal/ZIP/post code.

email
  Email address.

mobile
  Mobile/cell phone number.

phone
  Telephone, office phone, landline or fax.

signature
  Signature or signed-by field.

percent
  Percentage, rate or percentage-based value.

vat
  VAT/tax registration information.

date
  Calendar date, including date of birth, acquisition date,
  expiry date, incident date, etc.

time
  Time of day.

money
  Monetary amount, cost, value, price, claim amount, total,
  estimate, deduction, etc.

identifier
  Policy number, claim number, reference number, crime reference,
  account/reference identifier, etc.

occupation
  Occupation, trade, profession or business type.

org_name
  Name of insured, policyholder, person, company or organization.

address
  Postal/address information.

age
  Age or age/duration of an item.

item
  Description of goods, articles, property or items.

supplier
  Supplier, vendor, seller or purchased-from party.

short_text
  Short non-narrative text where another specific dtype does not apply.

prose
  A sentence/paragraph/narrative answer, especially a question asking
  for circumstances, cause, explanation, details, evidence, witnesses,
  mitigation, responsibility, etc.

Important:
- Choose based on the meaning of the label, not just individual keywords.
- "Who discovered the loss?" is prose.
- "Date discovered" is date.
- "Who is the supplier?" is supplier.
- "Telephone number of police station" is phone.
- "Estimated value" is money.
- "Policy number" is identifier.
- Return ONLY the dtype.
- Do not explain your answer.
""".strip()

    try:
        response = llm.invoke(prompt)
        raw = _extract_llm_text(response)
        dtype = _clean_llm_dtype(raw)

        if dtype is not None:
            return dtype

        print(
            f"    warn  LLM returned invalid dtype {raw!r} "
            f"for label {label!r}; using keyword classifier",
            file=sys.stderr,
        )

    except Exception as exc:
        print(
            f"    warn  LLM classification failed for {label!r}: {exc}; "
            f"using keyword classifier",
            file=sys.stderr,
        )

    return classify(label, multiline, capacity)


# =============================================================================
# 2. GENERATE -- persona-seeded values
# =============================================================================

# ONE coherent entity drives every field.
# Independent per-field generation is what makes a filled form look
# machine-produced.

class Persona:
    def __init__(self, seed: int = 7):
        r = random.Random(seed)

        self.company = "Whitaker Plumbing & Heating Ltd"
        self.person = "M. J. Whitaker"
        self.role = "Director"

        self.street = "Unit 7, Kirkstall Trade Park"
        self.street2 = "Bridgewater Road"
        self.city = "Leeds"
        self.postcode = "LS9 8AR"

        self.occupation = "Plumbing & heating contractor"

        self.email = "accounts@whitakerplumbing.co.uk"
        self.mobile = "07784 220513"
        self.phone = "0113 288 4417"

        self.vat = "GB 412 8834 07"
        self.policy = "CPM/4471902/07"

        self.event_date = "14/08/2026"
        self.event_time = "02:35"
        self.today = "26/08/2026"

        self._n = r

    def value(
        self,
        dtype: str,
        label: str,
        capacity: int,
    ) -> str:

        lab = (label or "").lower()

        gen = {
            "postcode": lambda: self.postcode,

            "email": lambda: self.email,

            "mobile": lambda: self.mobile,

            "phone": lambda: self.phone,

            "signature": lambda: f"{self.person} ({self.role})",

            "percent": lambda: "42%",

            "vat": lambda: (
                f"VAT No. {self.vat} - 100% recoverable"
            ),

            "date": lambda: (
                self.today
                if "sign" in lab or "declar" in lab
                else self.event_date
            ),

            "time": lambda: self.event_time,

            "money": lambda: money(self._amount(lab)),

            "identifier": lambda: (
                self.policy
                if "policy" in lab
                else "PRP/2026/0884127"
            ),

            "occupation": lambda: self.occupation,

            "org_name": lambda: self.company,

            "address": lambda: (
                f"{self.street}, {self.street2}, {self.city}"
            ),

            "age": lambda: "12 years",

            "item": lambda: "Hilti TE 6-A22 drill x2",

            "supplier": lambda: (
                f"City Plumbing, {self.city}"
            ),

            "short_text": lambda: self._short(lab),

            "prose": lambda: self._prose(lab),
        }[dtype]()

        return gen

    def _amount(self, lab: str) -> float:
        for key, val in (
            ("building", 285000.0),
            ("content", 96500.0),
            ("stock", 42000.0),
            ("salvage", 0.0),
            ("wear", 262.0),
            ("deduction", 262.0),
            ("original", 1190.0),
            ("replacement", 1310.0),
            ("estimate", 2340.0),
        ):
            if key in lab:
                return val

        return 1048.00

    def _short(self, lab: str) -> str:
        if "name" in lab:
            return self.company

        if "who" in lab or "by whom" in lab:
            return f"{self.person}, {self.role}"

        return "N/A"

    def _prose(self, lab: str) -> str:
        """
        Answer shaped by the question.

        Deliberately conservative -- a wrong confident answer is worse
        than a plainly generic one.
        """

        if (
            "cause" in lab
            or "circumstance" in lab
            or ("detail" in lab and "loss" in lab)
        ):
            return (
                "Forced entry overnight through the rear fire exit door. "
                "Tools, test equipment and stock were removed. CCTV shows "
                "two persons on site for approximately 18 minutes. No fire "
                "or water damage."
            )

        if "police" in lab and (
            "station" in lab or "telephone" in lab
        ):
            return (
                "Elland Road Police Station, Leeds LS11 8BU - "
                "0113 241 5000"
            )

        if "crime" in lab or "officer" in lab:
            return (
                "Crime reference 13260814/26, allocated to PC 4412 "
                "Hardisty, West Yorkshire Police."
            )

        if "mitigat" in lab or "action" in lab:
            return (
                "Emergency board-up and locksmith attended same day. "
                "Locks replaced, alarm re-coded, police and insurers "
                "notified."
            )

        if "third party" in lab or "responsible" in lab:
            return (
                "Sentinel Alarm Monitoring Ltd, 22 Cross Green Way, "
                "Leeds LS9 0SE. Tel 0113 245 9911."
            )

        if (
            "witness" in lab
            or "evidence" in lab
            or "photograph" in lab
        ):
            return (
                "Enclosed: photographs of the damage, CCTV footage, "
                "alarm activation log, and purchase invoices for stolen "
                "items."
            )

        if (
            "interested part" in lab
            or "landlord" in lab
            or "lease" in lab
        ):
            return (
                "Kirkstall Estates Ltd (freeholder), Bridgewater House, "
                "Leeds LS4 2QE."
            )

        if "trade" in lab or "trading" in lab or "how long" in lab:
            return (
                "Partially suspended. Only maintenance call-outs can be "
                "serviced for approximately 10 working days."
            )

        if "losing" in lab or "each day" in lab:
            return (
                "Approximately GBP 1,450 of turnover per working day"
            )

        if "previous" in lab or "particulars" in lab:
            return (
                "Escape of water, March 2023, insured with Aviva. "
                "Settled at GBP 4,180.00. No other claims in the last "
                "5 years."
            )

        return "N/A"


# =============================================================================
# 3. COLUMN HEADERS FOR DETECTED GRIDS
# =============================================================================

def column_headers(pdf_path: str, grid: dict) -> list[str]:
    """
    Harvest the printed header sitting above each detected column.
    """

    words = harvest_text(pdf_path)[grid["page"]]

    heads = []

    for rect in grid["column_rects"]:
        x0, _, x1, y1 = rect

        above = [
            t
            for t in words
            if (
                t["x1"] > x0 - 4
                and t["x0"] < x1 + 4
                and 0 <= t["y0"] - y1 < 70
            )
        ]

        above.sort(
            key=lambda t: (-t["y0"], t["x0"])
        )

        heads.append(
            " ".join(t["text"] for t in above[:8])
        )

    return heads


# =============================================================================
# 4. BOOLEAN ANSWERS
# =============================================================================

def answer_bool(question: str) -> bool:
    """
    Choose an answer that keeps the form internally coherent.

    Say Yes where the follow-up field is one we can populate.
    Say No where the honest answer for a single-incident claim is No.
    """

    q = " ".join(
        (question or "").lower().split()
    )

    for pattern, ans in [
        (
            r"other insurance|any other insurances|any other person",
            False,
        ),
        (
            r"sole owner",
            False,
        ),
        (
            r"still able to trade",
            False,
        ),
        (
            r"registered under the vat",
            True,
        ),
        (
            r"previously made",
            True,
        ),
        (
            r"another party responsible",
            True,
        ),
        (
            r"responsible under the terms",
            True,
        ),
    ]:
        if re.search(pattern, q):
            return ans

    return True


# =============================================================================
# 5. PIPELINE
# =============================================================================

def run(
    template: str,
    output: str,
    rows: int,
    seed: int,
    watermark: bool,
    dump: str | None,
    use_llm: bool,
) -> int:

    print(
        f"[1] structure   : analysing {template}"
    )

    draft = build_draft(template)

    s = draft["stats"]

    print(
        f"    {s['widgets']} widgets, {s['runs']} runs, "
        f"{s['bool_pairs']} yes/no pairs, {s['grids']} grids, "
        f"{s['structural_coverage_pct']}% coverage"
    )

    # ---------------------------------------------------------------------
    # Initialize backend
    # ---------------------------------------------------------------------

    backend = PypdfBackend()

    index = {
        w.name: w
        for w in backend.introspect(template)
    }

    persona = Persona(seed)

    # ---------------------------------------------------------------------
    # Initialize LLM ONCE
    # ---------------------------------------------------------------------

    llm = None

    if use_llm:
        print(
            f"[LLM] model={GEN_MODEL}, provider={PROVIDER}"
        )

        try:
            llm = get_genai_llm()

            print(
                "[LLM] semantic classification enabled"
            )

        except Exception as exc:
            print(
                f"[LLM] initialization failed: {exc}",
                file=sys.stderr,
            )

            print(
                "[LLM] falling back to keyword classification",
                file=sys.stderr,
            )

            llm = None

    # ---------------------------------------------------------------------
    # Storage
    # ---------------------------------------------------------------------

    values: dict[str, str] = {}
    fonts: dict[str, float] = {}

    warns: list[str] = []
    audit: list[dict] = []

    seen_labels: dict[str, str] = {}

    # =========================================================================
    # RUNS
    # =========================================================================

    for i, r in enumerate(draft["runs"]):

        # -----------------------------------------------------------------
        # Classify
        # -----------------------------------------------------------------

        if llm is not None:
            dtype = classify_llm(
                llm,
                r["label"],
                r["multiline_box"],
                r["total_capacity"],
            )
        else:
            dtype = classify(
                r["label"],
                r["multiline_box"],
                r["total_capacity"],
            )

        # -----------------------------------------------------------------
        # "Date and Time" can sit over TWO adjacent widgets.
        # Keep second occurrence as time.
        # -----------------------------------------------------------------

        if (
            dtype == "date"
            and seen_labels.get(r["label"]) == "date"
        ):
            dtype = "time"

        seen_labels[r["label"]] = dtype

        # -----------------------------------------------------------------
        # Generate value
        # -----------------------------------------------------------------

        val = persona.value(
            dtype,
            r["label"],
            r["total_capacity"],
        )

        if not val:
            continue

        # -----------------------------------------------------------------
        # Resolve widgets
        # -----------------------------------------------------------------

        ws = [
            index[n]
            for n in r["widgets"]
            if n in index
        ]

        if not ws:
            continue

        # -----------------------------------------------------------------
        # Determine font
        # -----------------------------------------------------------------

        font = (
            9.0
            if len(ws) == 1 and not r["multiline_box"]
            else 8.5
        )

        # -----------------------------------------------------------------
        # Flow into PDF widgets
        # -----------------------------------------------------------------

        v, f, w = flow(
            val,
            ws,
            font,
        )

        values.update(v)
        fonts.update(f)
        warns.extend(w)

        # -----------------------------------------------------------------
        # Audit
        # -----------------------------------------------------------------

        audit.append(
            {
                "run": i,
                "label": r["label"],
                "dtype": dtype,
                "value": val,
                "widgets": r["widgets"],
                "classification": (
                    "llm"
                    if llm is not None
                    else "keyword"
                ),
            }
        )

    # =========================================================================
    # YES/NO PAIRS
    # =========================================================================

    for p in draft["bool_pairs"]:

        ans = answer_bool(
            p["question_text"]
        )

        on = (
            p["on_state"]
            or "/Yes"
        )

        values[p["yes_widget"]] = (
            on
            if ans
            else "/Off"
        )

        values[p["no_widget"]] = (
            "/Off"
            if ans
            else on
        )

        audit.append(
            {
                "pair": p["question_text"][:60],
                "answer": ans,
            }
        )

    # =========================================================================
    # GRIDS
    # =========================================================================

    for gi, g in enumerate(draft["grids"]):

        heads = column_headers(
            template,
            g,
        )

        n = min(
            rows,
            g["rows"],
        )

        print(
            f"    grid[{gi}] {g['rows']}x{g['cols']} "
            f"[{g['section']}] -> filling {n} rows"
        )

        for r_i in range(n):

            cells = []

            for c_i, head in enumerate(heads):

                name = g["widget_matrix"][r_i][c_i]

                wg = index.get(name)

                if not wg:
                    continue

                capacity = wg.capacity(7.0)

                # ---------------------------------------------------------
                # Classify grid column
                # ---------------------------------------------------------

                if llm is not None:
                    dtype = classify_llm(
                        llm,
                        head,
                        False,
                        capacity,
                    )
                else:
                    dtype = classify(
                        head,
                        False,
                        capacity,
                    )

                # ---------------------------------------------------------
                # Generate value
                # ---------------------------------------------------------

                val = persona.value(
                    dtype,
                    head,
                    capacity,
                )

                # ---------------------------------------------------------
                # Special money handling
                # ---------------------------------------------------------

                if dtype == "money":
                    val = money(
                        persona._amount(
                            head.lower()
                        )
                        * (1 + 0.13 * r_i)
                    )

                # ---------------------------------------------------------
                # Special item handling
                # ---------------------------------------------------------

                if dtype == "item":
                    val = [
                        "Hilti TE 6-A22 drill x2",
                        "Rothenberger press kit",
                        "Copper tube 15/22mm",
                    ][r_i % 3]

                # ---------------------------------------------------------
                # Don't put N/A in grids
                # ---------------------------------------------------------

                if val in ("N/A", ""):
                    val = "-"

                cells.append(
                    (
                        name,
                        wg,
                        val,
                    )
                )

            # -----------------------------------------------------------------
            # Calculate smallest fitting font for this row
            # -----------------------------------------------------------------

            size = min(
                [
                    fit_cell(
                        v,
                        w,
                        7.0,
                    )[0]
                    for _, w, v in cells
                ]
                or [7.0]
            )

            # -----------------------------------------------------------------
            # Store values
            # -----------------------------------------------------------------

            for name, wg, val in cells:
                values[name] = val
                fonts[name] = round(
                    size,
                    1,
                )

    # =========================================================================
    # GENERATION COMPLETE
    # =========================================================================

    print(
        f"[2] generate    : {len(values)} widget values "
        f"({len(audit)} decisions)"
    )

    # =========================================================================
    # FILL PDF
    # =========================================================================

    backend.fill(
        template,
        output,
        values,
        fonts,
        (
            "SPECIMEN - SYNTHETIC DATA"
            if watermark
            else None
        ),
    )

    print(
        f"[3] render      : {output}"
    )

    # =========================================================================
    # READ-BACK VERIFICATION
    # =========================================================================

    back = backend.read_back(output)

    bad = [
        k
        for k in values
        if back.get(k) != values[k]
    ]

    print(
        f"[4] verify      : "
        f"{len(values) - len(bad)}/{len(values)} "
        f"read back identical"
        + (
            f", {len(bad)} MISMATCH"
            if bad
            else ""
        )
    )

    # =========================================================================
    # WARNINGS
    # =========================================================================

    for w in warns[:6]:
        print(
            f"    warn  {w}"
        )

    # =========================================================================
    # AUDIT OUTPUT
    # =========================================================================

    if dump:

        with open(
            dump,
            "w",
            encoding="utf-8",
        ) as fh:

            json.dump(
                {
                    "blueprint_stats": s,
                    "model": (
                        GEN_MODEL
                        if llm is not None
                        else None
                    ),
                    "provider": (
                        PROVIDER
                        if llm is not None
                        else None
                    ),
                    "classification_mode": (
                        "llm"
                        if llm is not None
                        else "keyword"
                    ),
                    "decisions": audit,
                    "widget_values": values,
                    "warnings": warns,
                },
                fh,
                indent=2,
            )

        print(
            f"[+] audit       : {dump}"
        )

    return 0


# =============================================================================
# 6. CLI
# =============================================================================

def main() -> int:

    ap = argparse.ArgumentParser(
        description="Blank AcroForm PDF in, filled PDF out."
    )

    ap.add_argument(
        "template"
    )

    ap.add_argument(
        "output"
    )

    ap.add_argument(
        "--rows",
        type=int,
        default=3,
        help="line items per detected table (default 3)",
    )

    ap.add_argument(
        "--seed",
        type=int,
        default=7,
    )

    ap.add_argument(
        "--watermark",
        action="store_true",
    )

    ap.add_argument(
        "--audit",
        help="write the decision log here",
    )

    ap.add_argument(
        "--llm",
        action="store_true",
        help=(
            "use semantic classification through "
            f"{GEN_MODEL} via {PROVIDER}"
        ),
    )

    a = ap.parse_args()

    return run(
        template=a.template,
        output=a.output,
        rows=a.rows,
        seed=a.seed,
        watermark=a.watermark,
        dump=a.audit,
        use_llm=a.llm,
    )


if __name__ == "__main__":
    sys.exit(main())
