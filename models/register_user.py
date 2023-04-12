from typing import Union

from pydantic import BaseModel


class RegisterUser(BaseModel):
    first_name: Union[str, None]
    last_name: Union[str, None]
    chat_id: int
    phone_number: Union[int, None]
    telegram_username: Union[str, None]
    bot_preference: Union[str, None]
    language_preference: Union[str, None]


class RegisterUserResponse(BaseModel):
    success: bool
