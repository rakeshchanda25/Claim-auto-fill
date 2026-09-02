import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ai_doc_generator.config import GenerationRequest
from ai_doc_generator.prompt_builder import build_generation_prompt
from ai_doc_generator.registry import DOC_TYPES, PACKET_REGISTRY, SCENARIO_REGISTRY
from guidewire import ClaimContext, GuidewireClient
from pdf_manager import combine_pdfs, replace_text_in_pdf
from scanner_simulator import simulate_scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Test Data Generator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

# Guidewire ClaimCenter dev instance. Hardcoded deliberately - there is no .env
# file; change these here to point at a different environment.
GUIDEWIRE_BASE_URL = "https://cc-dev-gwcpdev.valuemom.zeta1-andromeda.guidewire.net:443"
GUIDEWIRE_USERNAME = "su"
GUIDEWIRE_PASSWORD = "gw"
GUIDEWIRE_TIMEOUT = 60

APP_HOST = "127.0.0.1"
APP_PORT = 8420

_guidewire = GuidewireClient(
    base_url=GUIDEWIRE_BASE_URL,
    username=GUIDEWIRE_USERNAME,
    password=GUIDEWIRE_PASSWORD,
    timeout_seconds=GUIDEWIRE_TIMEOUT,
)


@app.on_event("shutdown")
def _shutdown():
    from ai_doc_generator.agent_factory import close_shared_agent

    close_shared_agent()


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# ============================================================================
# PDF utilities
# ============================================================================

@app.post("/api/replace")
async def replace_pdf_text(file: UploadFile = File(...), replacements: str = Form(...)):
    try:
        pdf_bytes = await file.read()
        new_pdf_bytes = replace_text_in_pdf(pdf_bytes, json.loads(replacements))
        return Response(
            content=new_pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=edited_{file.filename}"},
        )
    except Exception as e:
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
    rotation_rules: str = Form("[]"),
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
            rotation_rules=rotation_rules,
        )
        return Response(
            content=new_pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=scanned_{file.filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/combine")
async def api_combine(
    files: List[UploadFile] = File(...),
    page_specs: str = Form("[]"),
    file_order: str = Form("[]"),
    file_types: str = Form("[]"),
):
    try:
        pdf_bytes_list = [await f.read() for f in files]
        specs = json.loads(page_specs) or ["all"] * len(pdf_bytes_list)
        order = json.loads(file_order) or list(range(len(pdf_bytes_list)))
        types = json.loads(file_types) or ["pdf"] * len(pdf_bytes_list)

        combined = combine_pdfs(pdf_bytes_list, page_specs=specs, file_order=order, file_types=types)
        return Response(
            content=combined,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=combined_document.pdf"},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Guidewire claim lookup
#
# A claim number typed into the free-text input pulls live claim data, which is
# merged into custom_fields and applied ahead of any generated value. A lookup
# failure is logged and generation continues with synthetic data only - real
# claim data is an enrichment, never a requirement.
# ============================================================================

# Checked in this order so an explicit public ID or a labelled "claim id: X" is
# never shadowed by some other run of digits in the text. The bare pattern is
# the shape Guidewire's own claim numbers use, e.g. 000-00-053109.
_CLAIM_PATTERNS = (
    re.compile(r"\bcc:[A-Za-z0-9_-]+\b"),
    re.compile(r"claim\s*(?:id|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9:_\-]{4,})", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{6}\b"),
)


def extract_claim_id(text: str) -> Optional[str]:
    """Best-effort claim ID or number pulled out of free-form user text."""
    for pattern in _CLAIM_PATTERNS:
        if m := pattern.search(text or ""):
            return (m.group(1) if m.groups() else m.group(0)).strip().rstrip(".,;")
    return None


def claim_to_fields(claim: ClaimContext) -> dict:
    """Maps a claim onto the field names these documents actually use, so each
    value lands on the field it belongs to. Empty values are dropped so they
    fall through to generated data rather than blanking a field."""
    fields = {
        "claim_number": claim.details.get("claim_number"),
        "policy_number": claim.details.get("policy_number") or claim.policy.get("policy_number"),
        "claim_status": claim.details.get("status"),
        "loss_type": claim.details.get("loss_type"),
        "loss_cause": claim.details.get("loss_cause"),
        "loss_date": claim.details.get("loss_date"),
        "reported_date": claim.details.get("reported_date"),
        "insured_name": claim.details.get("insured"),
        "reporter_name": claim.details.get("reporter"),
        "main_contact": claim.details.get("main_contact"),
        "adjuster_name": claim.details.get("assigned_adjuster"),
        "how_reported": claim.details.get("how_reported"),
        "jurisdiction": claim.details.get("jurisdiction"),
        "line_of_business": claim.details.get("line_of_business"),
        "loss_location": claim.details.get("loss_location"),
        "policy_address": claim.details.get("policy_address"),
        "policy_type": claim.policy.get("policy_type"),
        "policy_currency": claim.policy.get("currency"),
        "policy_effective_date": claim.policy.get("policy_effective_date"),
        "policy_expiration_date": claim.policy.get("policy_expiration_date"),
        # The producing agent - carried only by the role-tagged contacts list.
        # Maps onto ACORD-25's producer_name, the one field it applies to.
        "producer_name": claim.contact_name("Agent"),
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}


def claim_narrative(claim: ClaimContext) -> str:
    """The claim's prose - the adjuster's description and excerpts from attached
    documents - as free text for the model to apply with its own judgment."""
    lines = []
    if claim.description:
        lines.append(f"Adjuster's claim description: {claim.description}")
    if claim.excerpts:
        lines.append("Excerpts from documents already attached to this claim:")
        lines += [f'- [{e["category"]}] {e["source"]}: "{e["text"]}"' for e in claim.excerpts]
    return "\n".join(lines)


# ============================================================================
# AI document generation
# ============================================================================

@app.post("/api/ai-generate")
async def ai_generate_document(
    doc_type: str = Form(...),
    mode: str = Form("generate"),
    scenario: str = Form("general"),
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
        f"generate: mode={mode} doc_type={doc_type} scenario={scenario!r} seed={seed} "
        f"reference={ref_ext or 'none'}"
    )

    fields = json.loads(custom_fields)

    if claim_id := extract_claim_id(user_input):
        logger.info(f"looking up claim {claim_id!r} in Guidewire")
        try:
            claim = await run_in_threadpool(_guidewire.fetch_claim_context, claim_id)
            # User-supplied fields still win over the claim's.
            fields = {**claim_to_fields(claim), **fields}

            # generate/recreate: the model reads the narrative as free text and
            # decides where it belongs.
            if narrative := claim_narrative(claim):
                user_input = f"{user_input}\n\n{narrative}" if user_input else narrative

            # packet: there is no per-component model step, so this rides along
            # under reserved keys build_packet pops off and applies only to the
            # document types that have somewhere to put it.
            if claim.description:
                fields["_claim_description"] = claim.description
            if claim.excerpts:
                fields["_document_excerpts"] = claim.excerpts
        except Exception as exc:
            logger.warning(f"claim lookup for {claim_id!r} failed, continuing without it: {exc}")

    req = GenerationRequest(
        doc_type=doc_type,
        mode=mode,
        scenario=scenario,
        seed=seed,
        reference_bytes=ref_bytes,
        reference_file_type=ref_ext,
        custom_fields=fields,
        user_input=user_input,
    )

    def _run():
        from ai_doc_generator.agent_factory import get_shared_agent, run_generation

        agent = get_shared_agent()
        prompt = build_generation_prompt(req)
        logger.info(f"prompt built ({len(prompt)} chars) - running agent")

        result = run_generation(
            agent, prompt, req.reference_bytes,
            custom_fields=req.custom_fields,
            anchor_date=req.custom_fields.get("loss_date"),
        )

        if result.artifact:
            content, kind = result.artifact
            return kind, content, f"{doc_type}_{scenario}.{kind}"

        if result.packet:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for comp in result.packet:
                    safe_label = comp["label"].replace(" ", "_").replace("/", "-")
                    zf.writestr(f"{safe_label}.{comp['kind']}", comp["bytes"])
            return "zip", buf.getvalue(), f"{doc_type}_packet.zip"

        # Every mode stages its output, so reaching here means the agent never
        # completed one. Its final message is the only clue why.
        raise HTTPException(
            status_code=500,
            detail=(
                "The agent finished without producing a document. Its final message was: "
                f"{result.text!r}. This usually means the model stopped before calling "
                "render_document_to_pdf or render_packet - check the server log for the "
                "tool sequence, and that the model backend is reachable."
            ),
        )

    try:
        file_type, content, filename = await run_in_threadpool(_run)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ai-generate failed")
        raise HTTPException(status_code=500, detail=str(e))

    media_types = {"pdf": "application/pdf", "zip": "application/zip"}
    logger.info(f"responding with {filename} ({len(content)} bytes)")
    return Response(
        content=content,
        media_type=media_types.get(file_type, "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/ai-analyze-reference")
async def ai_analyze_reference(file: UploadFile = File(...)):
    from ai_doc_generator.tools import analyze_reference_document

    try:
        file_bytes = await file.read()
        file_ext = Path(file.filename).suffix.lstrip(".").lower()
        return JSONResponse(content=analyze_reference_document(file_bytes, file_ext))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai-doc-types")
async def get_ai_doc_types():
    return JSONResponse({
        "document_types": DOC_TYPES,
        "packets": [
            {"id": k, "label": v["display_name"], "description": v["description"], "icon": "📦"}
            for k, v in PACKET_REGISTRY.items()
        ],
        "scenarios": SCENARIO_REGISTRY,
    })


class NoCacheStaticFiles(StaticFiles):
    """Forces browsers to revalidate on every load instead of silently serving a
    stale main.js after an edit."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", NoCacheStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
