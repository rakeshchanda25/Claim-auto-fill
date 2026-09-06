from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):

    # Required for generate/recreate. For packet mode this doubles as the
    # packet name, and may be omitted entirely - an empty doc_type in packet
    # mode means "let the model choose which documents this claim needs".
    doc_type: Optional[str] = None
    mode: Literal["generate", "recreate", "packet"]
    # "auto" (packet mode only) means "let the model choose the scenario too".
    scenario: str = "general"
    seed: Optional[int] = None

    reference_bytes: Optional[bytes] = None
    reference_file_type: Optional[str] = None

    custom_fields: dict = Field(default_factory=dict)

    user_input: str = ""
