from pydantic import BaseModel


class GreetingsInput(BaseModel):
    chat_id: int


class GreetingsResponse(BaseModel):
    response: str
