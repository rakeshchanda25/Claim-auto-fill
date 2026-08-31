import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Import your GuidewireClient class
from guidewire import GuidewireClient


# ============================================================
# Configuration
# ============================================================

GUIDEWIRE_BASE_URL = os.getenv(
    "GUIDEWIRE_BASE_URL",
    "https://cc-dev-gwcpdev.valuemom.zeta1-andromeda.guidewire.net:443"
)

GUIDEWIRE_USERNAME = os.getenv(
    "GUIDEWIRE_USERNAME",
    "su"
)

GUIDEWIRE_PASSWORD = os.getenv(
    "GUIDEWIRE_PASSWORD",
    "gw"
)

GUIDEWIRE_TIMEOUT = int(
    os.getenv("GUIDEWIRE_TIMEOUT", "60")
)


# ============================================================
# FastAPI application
# ============================================================

app = FastAPI(
    title="Guidewire Claim API",
    description="API for retrieving Guidewire ClaimCenter claim information",
    version="1.0.0",
)


# ============================================================
# Guidewire client
# ============================================================

client = GuidewireClient(
    base_url=GUIDEWIRE_BASE_URL,
    username=GUIDEWIRE_USERNAME,
    password=GUIDEWIRE_PASSWORD,
    timeout_seconds=GUIDEWIRE_TIMEOUT,
)


# ============================================================
# Health check
# ============================================================

@app.get("/")
def root():
    return {
        "success": True,
        "service": "Guidewire Claim API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoint": "GET /claims/{claim_id}",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# ============================================================
# Get complete claim information
# ============================================================

@app.get("/claims/{claim_id}")
def get_claim(claim_id: str):
    """
    Get all claim-related information available through
    GuidewireClient.

    claim_id can be either:
      - Claim number, e.g. CC0001234
      - Guidewire public ID, e.g. cc:xxxxxxxx
    """

    if not claim_id or not claim_id.strip():
        raise HTTPException(
            status_code=400,
            detail="claim_id is required"
        )

    claim_id = claim_id.strip()

    try:
        # Resolve claim number -> Guidewire public ID
        resolved_claim_id = client.resolve_claim_id_by_number(
            claim_id
        )

        # Retrieve all available claim information
        result = client.get_claim_background_context(
            resolved_claim_id
        )

        # Check for errors returned by individual Guidewire calls
        errors = {}

        if isinstance(result, dict):
            for section, value in result.items():
                if isinstance(value, dict) and value.get("error"):
                    errors[section] = value

        response = {
            "success": len(errors) == 0,
            "requested_claim_id": claim_id,
            "resolved_claim_id": resolved_claim_id,
            "data": result,
        }

        # Return 502 if Guidewire returned errors
        if errors:
            response["errors"] = errors

            return JSONResponse(
                status_code=502,
                content=response
            )

        return response

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to retrieve claim information",
                "error": str(exc),
            },
        )


# ============================================================
# Run directly with:
#
# python main.py
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8019,
        reload=True,
    )
