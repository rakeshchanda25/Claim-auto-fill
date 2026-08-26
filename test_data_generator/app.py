from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
import base64
import io
import json
import zipfile
import uvicorn
from pathlib import Path
from typing import List, Optional
from pdf_manager import replace_text_in_pdf, combine_pdfs
from scanner_simulator import simulate_scan
from ai_doc_generator.config import GenerationRequest
from ai_doc_generator.prompt_builder import build_generation_prompt
from ai_doc_generator.packets import PACKET_REGISTRY, SCENARIO_REGISTRY


app = FastAPI(title="PDF Test Data Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
):
    ref_bytes = None
    ref_ext = None
    if reference_file and reference_file.filename:
        ref_bytes = await reference_file.read()
        ref_ext = Path(reference_file.filename).suffix.lstrip(".").lower()

    req = GenerationRequest(
        doc_type=doc_type,
        mode=mode,
        scenario=scenario,
        count=count,
        seed=seed,
        reference_bytes=ref_bytes,
        reference_file_type=ref_ext,
        custom_fields=json.loads(custom_fields),
    )

    def _run():
        import re
        from ai_doc_generator.agent_factory import create_doc_generator_agent

        with create_doc_generator_agent() as agent:
            prompt = build_generation_prompt(req)
            result_str = agent.run(prompt)
            if hasattr(result_str, "content"):
                result_str = result_str.content
            elif hasattr(result_str, "output"):
                result_str = result_str.output

        print("\n" + "=" * 40 + " RAW AGENT RESPONSE START " + "=" * 40)
        print(f"TYPE: {type(result_str)}")
        print(f"REPR: {repr(result_str)}")
        print("CONTENT:")
        print(result_str)
        print("=" * 40 + " RAW AGENT RESPONSE END " + "=" * 40 + "\n")

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
            raise HTTPException(
                status_code=500,
                detail=f"Raw LLM Response [{type(result_str).__name__}]: {repr(result_str)}"
            )

        if "components" in result:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for comp in result["components"]:
                    pdf_data = base64.b64decode(comp["pdf_bytes_b64"])
                    safe_label = comp["label"].replace(" ", "_").replace("/", "-")
                    zf.writestr(f"{safe_label}.pdf", pdf_data)
            return ("zip", buf.getvalue(), f"{doc_type}_packet.zip")

        if "pdf_bytes_b64" not in result:
            raise HTTPException(
                status_code=500,
                detail=f"Missing 'pdf_bytes_b64' in keys: {list(result.keys())}. Raw response: {repr(result_str)}"
            )

        pdf_bytes = base64.b64decode(result["pdf_bytes_b64"])
        return ("pdf", pdf_bytes, f"{doc_type}_{scenario}.pdf")




    try:
        file_type, content, filename = await run_in_threadpool(_run)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if file_type == "zip":
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/ai-analyze-reference")
async def ai_analyze_reference(file: UploadFile = File(...)):
    file_bytes = await file.read()
    file_ext = Path(file.filename).suffix.lstrip(".").lower()

    from ai_doc_generator.tools import analyze_reference_document
    try:
        result = analyze_reference_document.invoke({"file_bytes": file_bytes, "file_type": file_ext})
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


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8011, reload=True)
