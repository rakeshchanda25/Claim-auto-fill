from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
import io
import json
import zipfile
import uvicorn
from pathlib import Path
from typing import List, Optional
from pdf_manager import replace_text_in_pdf, combine_pdfs, handwrite_values_in_pdf
from scanner_simulator import simulate_scan
from ai_doc_generator.config import GenerationRequest
from ai_doc_generator.prompt_builder import build_generation_prompt
from ai_doc_generator.registry import DOC_TYPES, PACKET_REGISTRY, SCENARIO_REGISTRY
from claim_context import claim_narrative, claim_to_fields, extract_claim_id, fetch_claim_context
from guidewire import GuidewireClient

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
APP_PORT = 8025

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
    rotation_rules: str = Form("[]"),
    dark_background: bool = Form(False),
    dark_intensity: float = Form(0.55),
    dark_mode: str = Form("photo"),
    crop: bool = Form(False),
    crop_percent: float = Form(8.0),
    crop_edges: str = Form("right,bottom"),
    handwritten: bool = Form(False),
    annotation_count: int = Form(3),
    annotation_ink: str = Form("blue"),
    annotation_text: str = Form(""),
    handwrite_values: bool = Form(False),
    handwrite_ink: str = Form("blue"),
    handwrite_list: str = Form(""),
    handwrite_detect: str = Form("llm"),
    seed: Optional[int] = Form(None),
):
    try:
        pdf_bytes = await file.read()
        handwrite_report = None

        overlay_bytes = None
        if overlay_image and overlay_image.filename:
            overlay_bytes = await overlay_image.read()
        
        if handwrite_values:
            # Rewrites the filled-in values in handwriting before the page is
            # ever rasterised, so the printed template stays crisp and only
            # the values look hand-filled.
            supplied = [v.strip() for v in handwrite_list.replace("\n", ",").split(",")
                        if v.strip()]
            pdf_bytes, handwrite_report = handwrite_values_in_pdf(
                pdf_bytes, values=supplied or None, ink=handwrite_ink,
                seed=seed, detect=handwrite_detect)

        new_pdf_bytes = simulate_scan(
            pdf_bytes, 
            skew, blur, noise, low_dpi,
            skew_angle=skew_angle,
            blur_strength=blur_strength,
            noise_intensity=noise_intensity,
            overlay_image_bytes=overlay_bytes,
            rotation=rotation,
            rotation_rules=rotation_rules,
            dark_background=dark_background,
            dark_intensity=dark_intensity,
            dark_mode=dark_mode,
            crop=crop,
            crop_percent=crop_percent,
            crop_edges=crop_edges,
            handwritten=handwritten,
            annotation_count=annotation_count,
            annotation_ink=annotation_ink,
            annotation_text=annotation_text,
            seed=seed,
        )
        
        headers = {"Content-Disposition": f"attachment; filename=scanned_{file.filename}"}
        if handwrite_report:
            # So the caller can tell whether the model actually classified the
            # page or the rule fallback quietly took over.
            headers["X-Handwrite-Method"] = handwrite_report["method"]
            headers["X-Handwrite-Count"] = str(handwrite_report["written"])
            if handwrite_report.get("fallback_reason"):
                headers["X-Handwrite-Fallback"] = handwrite_report["fallback_reason"][:180]

        return Response(
            content=new_pdf_bytes,
            media_type="application/pdf",
            headers=headers,
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
    doc_type: Optional[str] = Form(None),
    mode: str = Form("generate"),
    scenario: str = Form("general"),
    seed: Optional[int] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    custom_fields: str = Form("{}"),
    user_input: str = Form(""),
):
    if not doc_type and mode != "packet":
        raise HTTPException(status_code=400,
                            detail="doc_type is required for generate/recreate mode.")

    ref_bytes = None
    ref_ext = None
    if reference_file and reference_file.filename:
        ref_bytes = await reference_file.read()
        ref_ext = Path(reference_file.filename).suffix.lstrip(".").lower()

    fields = json.loads(custom_fields)

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
            pass

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
            return "zip", buf.getvalue(), f"{doc_type or 'claim'}_packet.zip"

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
    })


class NoCacheStaticFiles(StaticFiles):

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

app.mount("/", NoCacheStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
