from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json
import os
import re
import uvicorn
from pathlib import Path
from typing import List, Optional
from pdf_manager import replace_text_in_pdf, combine_pdfs
from scanner_simulator import simulate_scan
from starlette.concurrency import run_in_threadpool
import base64
import io
import logging
import zipfile
from ai_doc_generator.config import GenerationRequest
from ai_doc_generator.prompt_builder import build_generation_prompt
from ai_doc_generator.packets import PACKET_REGISTRY, SCENARIO_REGISTRY
from guidewire import GuidewireClient

app = FastAPI(title="PDF Test Data Generator API")

# ============================================================
# Guidewire claim lookup (used by /api/ai-generate below)
#
# A claim ID/number typed into the frontend's free-text "User Input" box
# pulls live claim data from Guidewire via GuidewireClient (guidewire.py) -
# the same client main.py's now-removed standalone /claims/{claim_id}
# endpoint used, called in-process here instead of over HTTP to a second
# server. The returned facts are merged into custom_fields, which the LLM
# already treats as authoritative-but-partial (see prompt_builder.py's
# _custom_fields_block: "use verbatim wherever it fits, only invent the
# rest") - so any field Guidewire doesn't have still gets Faker-generated
# exactly as it does today.
# ============================================================

_GUIDEWIRE_BASE_URL = os.getenv(
    "GUIDEWIRE_BASE_URL",
    "https://cc-dev-gwcpdev.valuemom.zeta1-andromeda.guidewire.net:443",
)
_GUIDEWIRE_USERNAME = os.getenv("GUIDEWIRE_USERNAME", "su")
_GUIDEWIRE_PASSWORD = os.getenv("GUIDEWIRE_PASSWORD", "gw")
_GUIDEWIRE_TIMEOUT = int(os.getenv("GUIDEWIRE_TIMEOUT", "60"))

_guidewire_client = GuidewireClient(
    base_url=_GUIDEWIRE_BASE_URL,
    username=_GUIDEWIRE_USERNAME,
    password=_GUIDEWIRE_PASSWORD,
    timeout_seconds=_GUIDEWIRE_TIMEOUT,
)

# Checked in this order so an explicit Guidewire public ID or a labelled
# "claim id/number: X" is never shadowed by some other digit run in the text.
# The bare-number pattern matches the shape Guidewire's own claim_number
# field uses (see response.json: "000-00-053109").
_CLAIM_PUBLIC_ID_RE = re.compile(r"\bcc:[A-Za-z0-9_-]+\b")
_CLAIM_LABELLED_RE = re.compile(
    r"claim\s*(?:id|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9:_\-]{4,})", re.IGNORECASE
)
_CLAIM_BARE_NUMBER_RE = re.compile(r"\b\d{3}-\d{2}-\d{6}\b")


def extract_claim_id(text: str) -> Optional[str]:
    """Best-effort claim ID/number pulled out of free-form user text."""
    if not text:
        return None
    for pattern in (_CLAIM_PUBLIC_ID_RE, _CLAIM_LABELLED_RE, _CLAIM_BARE_NUMBER_RE):
        m = pattern.search(text)
        if m:
            return (m.group(1) if m.groups() else m.group(0)).strip().rstrip(".,;")
    return None


def fetch_claim_facts(claim_id_or_number: str) -> dict:
    """Fetches the claim from Guidewire and returns flat claim-level
    field:value pairs (claim_number, policy_number, insured_name, loss_date,
    etc.), named to match what these documents' skills already call fields
    by, so the value lands on the field it actually belongs to - never a
    generic "claim summary"/"claim description"/document-excerpt dump into
    every document regardless of whether it's relevant or even has a place
    to put it. Guidewire data takes priority wherever a document has a
    matching field; anything Guidewire doesn't have still gets Faker-
    generated exactly as it always did (see prompt_builder.py's
    _custom_fields_block and tools.py's build_packet/_sync_packet_component).

    Raises on failure - the caller decides whether that should block generation
    or just log a warning and fall back to pure Faker generation (see
    ai_generate_document below, which does the latter)."""
    resolved_id = _guidewire_client.resolve_claim_id_by_number(claim_id_or_number)
    data = _guidewire_client.get_claim_background_context(resolved_id)

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Guidewire lookup failed: {data}")
    if not isinstance(data, dict):
        data = {}

    claim = data.get("claim_details", {}) or {}
    policy = data.get("policy_details", {}) or {}

    facts = {
        "claim_number": claim.get("claim_number"),
        "policy_number": claim.get("policy_number") or policy.get("policy_number"),
        "claim_status": claim.get("status"),
        "loss_type": claim.get("loss_type"),
        "loss_cause": claim.get("loss_cause"),
        "loss_date": claim.get("loss_date"),
        "insured_name": claim.get("insured"),
        "reporter_name": claim.get("reporter"),
        "main_contact": claim.get("main_contact"),
        "how_reported": claim.get("how_reported"),
        "reported_date": claim.get("reported_date"),
        "adjuster_name": claim.get("assigned_adjuster"),
        "jurisdiction": claim.get("jurisdiction"),
        "line_of_business": claim.get("line_of_business"),
        "loss_location": claim.get("loss_location"),
        "policy_address": claim.get("policy_address"),
        "policy_type": policy.get("policy_type"),
        "policy_currency": policy.get("currency"),
        "policy_effective_date": policy.get("policy_effective_date"),
        "policy_expiration_date": policy.get("policy_expiration_date"),
        # The producing agent/broker - claim_details/policy_details don't carry this,
        # only the role-tagged contacts list does. Maps onto ACORD-25's producer_name,
        # the one real field this covers (a certificate of insurance's "producer" IS
        # the agent). Genuinely blank on plenty of real claims (confirmed: this
        # response.json sample's own Agent contact has display_name "") - falls
        # through to Faker exactly like any other field Guidewire doesn't have.
        "producer_name": _find_contact_name(data, role="Agent"),
    }
    return {k: v for k, v in facts.items() if v not in (None, "")}


def _find_contact_name(data: dict, *, role: str) -> str | None:
    for contact in (data.get("contacts", {}) or {}).get("contacts", []):
        if any(r.get("role") == role and r.get("active") for r in contact.get("roles", [])):
            name = contact.get("display_name") or " ".join(
                filter(None, [contact.get("first_name"), contact.get("last_name")])
            )
            if name:
                return name
    return None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
def _close_shared_agent():
    from ai_doc_generator.agent_factory import close_shared_agent
    close_shared_agent()

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/replace")
async def replace_pdf_text(
    file: UploadFile = File(...),
    replacements: str = Form(...)
):
    try:
        rep_dict = json.loads(replacements)
        pdf_bytes = await file.read()
        
        new_pdf_bytes = replace_text_in_pdf(pdf_bytes, rep_dict)
        
        return Response(
            content=new_pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=edited_{file.filename}"
            }
        )
    except Exception as e:
        # traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulate-scan")
async def api_simulate_scan(
    file: UploadFile = File(...),
    skew: bool = Form(False),
    blur: bool = Form(False),
    noise: bool = Form(False),
    low_dpi: bool = Form(False),
    skew_angle: float = Form(1.5),
    blur_strength: int = Form(5),
    noise_intensity: float = Form(15.0),
    overlay_image: UploadFile = File(None),
    rotation: bool = Form(False),
    rotation_rules: str = Form("[]")
):
    try:
        pdf_bytes = await file.read()
        
        overlay_bytes = None
        if overlay_image and overlay_image.filename:
            overlay_bytes = await overlay_image.read()
        
        new_pdf_bytes = simulate_scan(
            pdf_bytes, 
            skew, blur, noise, low_dpi,
            skew_angle=skew_angle,
            blur_strength=blur_strength,
            noise_intensity=noise_intensity,
            overlay_image_bytes=overlay_bytes,
            rotation=rotation,
            rotation_rules=rotation_rules
        )
        
        return Response(
            content=new_pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=scanned_{file.filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/combine")
async def api_combine(
    files: List[UploadFile] = File(...),
    page_specs: str = Form("[]"),
    file_order: str = Form("[]"),
    file_types: str = Form("[]")
):
    try:
        pdf_bytes_list = []
        for file in files:
            pdf_bytes_list.append(await file.read())

        specs  = json.loads(page_specs)
        order  = json.loads(file_order)
        types  = json.loads(file_types)

        if not specs:
            specs = ["all"] * len(pdf_bytes_list)
        if not order:
            order = list(range(len(pdf_bytes_list)))
        if not types:
            types = ["pdf"] * len(pdf_bytes_list)

        combined_pdf_bytes = combine_pdfs(
            pdf_bytes_list,
            page_specs=specs,
            file_order=order,
            file_types=types
        )
        
        return Response(
            content=combined_pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=combined_document.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ai-generate")
async def ai_generate_document(
    doc_type: str = Form(...),
    mode: str = Form("generate"),
    scenario: str = Form("general"),
    count: int = Form(1),
    seed: Optional[int] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    custom_fields: str = Form("{}"),
    user_input: str = Form(""),
):
    ref_bytes = None
    ref_ext = None
    if reference_file and reference_file.filename:
        ref_bytes = await reference_file.read()
        ref_ext = Path(reference_file.filename).suffix.lstrip(".").lower()

    logger.info(
        f"[1/6] request received: mode={mode} doc_type={doc_type} scenario={scenario!r} "
        f"count={count} seed={seed} reference={ref_ext or 'none'}"
        f"{f' ({len(ref_bytes)} bytes)' if ref_bytes else ''}"
        f"{f' user_input={len(user_input)} chars' if user_input else ''}"
    )

    custom_fields_dict = json.loads(custom_fields)

    # A claim ID/number typed into the free-text user_input box pulls live claim
    # data from Guidewire and merges it into custom_fields, which the LLM already
    # treats as authoritative-but-partial (see prompt_builder.py's
    # _custom_fields_block: "use verbatim wherever it fits, only invent the
    # rest") - so any field Guidewire doesn't have still gets Faker-generated
    # exactly as it does today. A lookup failure (unreachable Guidewire, unknown
    # claim ID) logs and falls through to plain generation rather than failing
    # the whole request - the claim data is an enrichment, not a requirement.
    claim_id = extract_claim_id(user_input)
    if claim_id:
        logger.info(f"[1/6] detected claim id/number {claim_id!r} in user input - looking up Guidewire")
        try:
            claim_facts = await run_in_threadpool(fetch_claim_facts, claim_id)
            logger.info(f"[1/6] Guidewire lookup ok: {len(claim_facts)} claim fact(s) retrieved")
            custom_fields_dict = {**claim_facts, **custom_fields_dict}
        except Exception as exc:
            logger.warning(f"[1/6] Guidewire lookup for {claim_id!r} failed, continuing without it: {exc}")

    req = GenerationRequest(
        doc_type=doc_type,
        mode=mode,
        scenario=scenario,
        count=count,
        seed=seed,
        reference_bytes=ref_bytes,
        reference_file_type=ref_ext,
        custom_fields=custom_fields_dict,
        user_input=user_input,
    )

    def _run():
        from ai_doc_generator.agent_factory import get_shared_agent, run_with_reference

        agent = get_shared_agent()
        prompt = build_generation_prompt(req)
        logger.info(f"[2/6] prompt built ({len(prompt)} chars) - handing off to agent")

        result_str, artifact_bytes, artifact_kind, packet_components = run_with_reference(
            agent, prompt, req.reference_bytes
        )
        if hasattr(result_str, "content"):
            result_str = result_str.content
        elif hasattr(result_str, "output"):
            result_str = result_str.output

        logger.info(
            f"[3/6] agent run returned: text_type={type(result_str).__name__} "
            f"text_len={len(result_str) if isinstance(result_str, str) else 'n/a'} "
            f"artifact={f'{artifact_kind} ({len(artifact_bytes)} bytes)' if artifact_bytes else 'none'} "
            f"packet={f'{len(packet_components)} component(s)' if packet_components else 'none'}"
        )
        logger.debug(f"[3/6] raw agent text: {result_str!r}")

        if artifact_bytes is not None:
            ext = artifact_kind or "pdf"
            logger.info(f"[4/6] using staged artifact directly (kind={ext}), skipping text-JSON parsing")
            logger.info(f"[6/6] responding with {ext} file, {len(artifact_bytes)} bytes")
            return (ext, artifact_bytes, f"{doc_type}_{scenario}.{ext}")

        if packet_components:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for comp in packet_components:
                    safe_label = comp["label"].replace(" ", "_").replace("/", "-")
                    ext = comp["kind"] or "pdf"
                    zf.writestr(f"{safe_label}.{ext}", comp["bytes"])
            logger.info("[4/6] using staged packet directly, skipping text-JSON parsing")
            logger.info(f"[6/6] responding with packet zip, {len(packet_components)} components")
            return ("zip", buf.getvalue(), f"{doc_type}_packet.zip")

        logger.info("[4/6] no staged artifact or packet - parsing agent text as JSON (legacy fallback path)")
        result = None
        if isinstance(result_str, dict):
            result = result_str
        elif isinstance(result_str, str) and result_str.strip():
            clean_str = re.sub(r"^```(?:json)?\s*", "", result_str.strip(), flags=re.IGNORECASE)
            clean_str = re.sub(r"\s*```$", "", clean_str)
            try:
                result = json.loads(clean_str)
            except Exception:
                match = re.search(r"\{.*\}", clean_str, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group(0))
                    except Exception:
                        pass

        if not result or not isinstance(result, dict):
            hint = (
                " Empty response from the agent - this usually means the model's final turn "
                "was a tool call with no follow-up text, or the model backend (Ollama) failed "
                "to produce a completion. Check the Ollama server is running and the configured "
                "model is available."
            ) if isinstance(result_str, str) and not result_str.strip() else ""
            logger.error(f"[5/6] could not parse a usable result from agent text: {result_str!r}")
            raise HTTPException(
                status_code=500,
                detail=f"Raw LLM Response [{type(result_str).__name__}]: {repr(result_str)}.{hint}"
            )
        logger.info(f"[5/6] parsed JSON result with keys: {list(result.keys())}")

        if "components" in result:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for comp in result["components"]:
                    pdf_data = base64.b64decode(comp["pdf_bytes_b64"])
                    safe_label = comp["label"].replace(" ", "_").replace("/", "-")
                    zf.writestr(f"{safe_label}.pdf", pdf_data)
            logger.info(f"[6/6] responding with packet zip, {len(result['components'])} components")
            return ("zip", buf.getvalue(), f"{doc_type}_packet.zip")

        if "docx_bytes_b64" in result:
            docx_bytes = base64.b64decode(result["docx_bytes_b64"])
            logger.info(f"[6/6] responding with docx file, {len(docx_bytes)} bytes")
            return ("docx", docx_bytes, f"{doc_type}_{scenario}.docx")

        if "pdf_bytes_b64" not in result:
            logger.error(f"[6/6] result JSON has no pdf_bytes_b64/docx_bytes_b64/components: keys={list(result.keys())}")
            raise HTTPException(
                status_code=500,
                detail=f"Missing 'pdf_bytes_b64' in keys: {list(result.keys())}. Raw response: {repr(result_str)}"
            )

        pdf_bytes = base64.b64decode(result["pdf_bytes_b64"])
        logger.info(f"[6/6] responding with pdf file, {len(pdf_bytes)} bytes")
        return ("pdf", pdf_bytes, f"{doc_type}_{scenario}.pdf")

    try:
        file_type, content, filename = await run_in_threadpool(_run)
    except HTTPException as e:
        logger.warning(f"ai-generate request failed: HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        logger.exception("ai-generate request failed with an unhandled exception")
        raise HTTPException(status_code=500, detail=str(e))

    media_types = {
        "zip": "application/zip",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    return Response(
        content=content,
        media_type=media_types[file_type],
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/ai-analyze-reference")
async def ai_analyze_reference(file: UploadFile = File(...)):
    file_bytes = await file.read()
    file_ext = Path(file.filename).suffix.lstrip(".").lower()

    from ai_doc_generator.tools import analyze_reference_document
    try:
        result = analyze_reference_document(file_bytes, file_ext)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai-doc-types")
async def get_ai_doc_types():
    doc_types = [
        {"id": "medical-record",        "label": "Medical Record",          "icon": "🏥", "category": "Clinical"},
        {"id": "medical-bill",          "label": "Medical Bill",            "icon": "💊", "category": "Billing"},
        {"id": "discharge-summary",     "label": "Discharge Summary",       "icon": "🏨", "category": "Clinical"},
        {"id": "cms-1500",              "label": "CMS-1500",                "icon": "📋", "category": "Billing"},
        {"id": "ub-04",                 "label": "UB-04",                   "icon": "🏦", "category": "Billing"},
        {"id": "eob-explanation",       "label": "EOB",                     "icon": "📄", "category": "Insurance"},
        {"id": "acord-25",              "label": "ACORD 25",                "icon": "📜", "category": "Insurance"},
        {"id": "police-report",         "label": "Police Report",           "icon": "🚔", "category": "Legal"},
        {"id": "demand-letter",         "label": "Demand Letter",           "icon": "⚖️", "category": "Legal"},
        {"id": "litigation-document",   "label": "Litigation Document",     "icon": "🏛️", "category": "Legal"},
        {"id": "pharmacy-invoice",      "label": "Pharmacy Invoice",        "icon": "💉", "category": "Billing"},
        {"id": "property-loss-notice",  "label": "Property Loss Notice",    "icon": "🏠", "category": "Property"},
        {"id": "auto-accident-report",  "label": "Auto Accident Report",    "icon": "🚗", "category": "Auto"},
    ]
    packets = [
        {"id": k, "label": v["display_name"], "description": v["description"], "icon": "📦"}
        for k, v in PACKET_REGISTRY.items()
    ]
    return JSONResponse({"document_types": doc_types, "packets": packets, "scenarios": SCENARIO_REGISTRY})


class NoCacheStaticFiles(StaticFiles):
    """Forces browsers to revalidate frontend assets on every load instead of
    silently reusing a stale main.js/index.html after an edit."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

app.mount("/", NoCacheStaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8015, reload=True)
