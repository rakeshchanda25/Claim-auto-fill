from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):

    doc_type: str
    mode: Literal["generate", "recreate", "packet"]
    scenario: str = "general"
    seed: Optional[int] = None

    reference_bytes: Optional[bytes] = None
    reference_file_type: Optional[str] = None

    custom_fields: dict = Field(default_factory=dict)

    user_input: str = ""
