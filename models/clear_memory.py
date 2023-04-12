from pydantic import BaseModel


class ClearMemory(BaseModel):
    chat_id: int


class ClearMemoryResponse(BaseModel):
    success: bool
