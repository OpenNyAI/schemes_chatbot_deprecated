from pydantic import BaseModel
from typing import Union


class ChatInput(BaseModel):
    chat_id: int
    phone_number: int
    message: str
    message_type: str
    platform: str


class ChatResponse(BaseModel):
    text: str
    audio_url: Union[str, None]
