from pydantic import BaseModel, Field

class ConflictCheckRequest(BaseModel):
    requirement_a: str = Field(..., description="Description of the first requirement")
    requirement_b: str = Field(..., description="Description of the second requirement")

class ConflictCheckResponse(BaseModel):
    is_conflict: bool = Field(..., description="True if conflict is detected, False otherwise")
    raw_response: str = Field(..., description="The raw explanation or response from the model")
