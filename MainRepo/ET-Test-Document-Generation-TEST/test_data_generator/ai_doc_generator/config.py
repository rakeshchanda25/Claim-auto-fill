from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):
    """One document-generation request, as assembled from the /api/ai-generate form."""

    doc_type: str
    mode: Literal["generate", "recreate", "packet"]
    scenario: str = "general"
    seed: Optional[int] = None

    # recreate mode only - the uploaded file the new document is based on.
    reference_bytes: Optional[bytes] = None
    reference_file_type: Optional[str] = None

    # Structured field:value overrides. Live Guidewire claim facts are merged in
    # here (see app.py), so these take priority over generated values.
    custom_fields: dict = Field(default_factory=dict)

    # Free-form guidance typed by the user, plus any claim narrative/notes.
    user_input: str = ""
