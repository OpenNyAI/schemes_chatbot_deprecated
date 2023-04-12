from pydantic import BaseModel


class ChangeLanguage(BaseModel):
    chat_id: int
    language_preference: str


class ChangeLanguageResponse(BaseModel):
    success: bool
