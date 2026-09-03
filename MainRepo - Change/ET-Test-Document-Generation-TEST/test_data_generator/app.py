import io
import json
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
from ai_doc_generator.registry import (
    DOC_TYPES,
    LAYOUT_AXIS,
    PACKET_REGISTRY,
    SCENARIO_REGISTRY,
    US_STATES,
)
from claim_context import claim_narrative, claim_to_fields, extract_claim_id, fetch_claim_context
from guidewire import GuidewireClient
from jurisdiction import resolve_issuer, resolve_jurisdiction
from pdf_manager import combine_pdfs, replace_text_in_pdf
from renderers.layouts import all_layouts
from renderers.state_forms import STATE_FORMS
from scanner_simulator import simulate_scan

app = FastAPI(title="PDF Test Data Generator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

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


@app.post("/api/ai-generate")
async def ai_generate_document(
    doc_type: str = Form(...),
    mode: str = Form("generate"),
    scenario: str = Form("general"),
    jurisdiction: Optional[str] = Form(None),
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

    fields = json.loads(custom_fields)
    claim = None

    if claim_id := extract_claim_id(user_input):
        try:
            claim = await run_in_threadpool(fetch_claim_context, _guidewire, claim_id)
            fields = {**claim_to_fields(claim), **fields}

            if narrative := claim_narrative(claim):
                user_input = f"{user_input}\n\n{narrative}" if user_input else narrative

            if claim.description:
                fields["_claim_description"] = claim.description
            if claim.excerpts:
                fields["_document_excerpts"] = claim.excerpts
        except Exception:
            claim = None

    jurisdiction = (resolve_jurisdiction(doc_type, jurisdiction, claim, user_input)
                    or resolve_issuer(doc_type, jurisdiction, claim, user_input))

    req = GenerationRequest(
        doc_type=doc_type,
        mode=mode,
        scenario=scenario,
        jurisdiction=jurisdiction,
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

        result = run_generation(
            agent, prompt, req.reference_bytes,
            custom_fields=req.custom_fields,
            anchor_date=req.custom_fields.get("loss_date"),
            jurisdiction=req.jurisdiction,
        )

        if result.artifact:
            content, kind = result.artifact
            suffix = f"_{jurisdiction}" if jurisdiction else ""
            return kind, content, f"{doc_type}_{scenario}{suffix}.{kind}"

        if result.packet:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for comp in result.packet:
                    safe_label = comp["label"].replace(" ", "_").replace("/", "-")
                    zf.writestr(f"{safe_label}.{comp['kind']}", comp["bytes"])
            return "zip", buf.getvalue(), f"{doc_type}_packet.zip"

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
        raise HTTPException(status_code=500, detail=str(e))

    media_types = {"pdf": "application/pdf", "zip": "application/zip"}
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
        "layout_axis": LAYOUT_AXIS,
        "states": US_STATES,
        "layouts": all_layouts(),
        "state_fidelity": {code: entry[3] for code, entry in STATE_FORMS.items()},
    })


class NoCacheStaticFiles(StaticFiles):

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", NoCacheStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
