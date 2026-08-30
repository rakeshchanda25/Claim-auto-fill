from pydantic import BaseModel
from typing import Optional, Literal


class GenerationRequest(BaseModel):
    doc_type: str
    mode: Literal["generate", "recreate", "packet"]
    scenario: str = "general"
    count: int = 1
    seed: Optional[int] = None
    reference_bytes: Optional[bytes] = None
    reference_file_type: Optional[str] = None
    custom_fields: dict = {}

    class Config:
        arbitrary_types_allowed = True
