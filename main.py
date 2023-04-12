import uvicorn
from fastapi import FastAPI, Request, Security, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security.api_key import APIKey, APIKeyHeader

from models.register_user import RegisterUser, RegisterUserResponse
from models.change_language import ChangeLanguage, ChangeLanguageResponse
from models.clear_memory import ClearMemoryResponse, ClearMemory
from models.greetings import GreetingsInput, GreetingsResponse
from models.chat import ChatResponse, ChatInput
from chat import chatbot_flow
from database import create_engine, PostgresDatabase
from wasabi import msg

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title='JugalBandi API')
language_options = {'English': 'en', 'हिन्दी': 'hi', 'বাংলা': 'bn', 'தமிழ்': 'ta', 'తెలుగు': 'te', 'ਪੰਜਾਬੀ': 'pa'}
greeting_messages = {'en': "Now please ask your question either by typing it or by recording it in a voice note",
                     'hi': "अब कृपया अपना प्रश्न टाइप करके या ध्वनि नोट में रिकॉर्ड करके पूछें",
                     'bn': "এখন টাইপ করে অথবা ভয়েস নোটে রেকর্ড করে আপনার প্রশ্ন জিজ্ঞাসা করুন",
                     'ta': "இப்போது உங்கள் கேள்வியை தட்டச்சு செய்வதன் மூலமாகவோ அல்லது குரல் குறிப்பில் பதிவு செய்வதன் மூலமாகவோ கேட்கவும்",
                     'te': "ఇప్పుడు దయచేసి మీ ప్రశ్నను టైప్ చేయడం ద్వారా లేదా వాయిస్ నోట్‌లో రికార్డ్ చేయడం ద్వారా అడగండి",
                     'pa': "ਹੁਣ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਸਵਾਲ ਜਾਂ ਤਾਂ ਇਸਨੂੰ ਟਾਈਪ ਕਰਕੇ ਜਾਂ ਵੌਇਸ ਨੋਟ ਵਿੱਚ ਰਿਕਾਰਡ ਕਰਕੇ ਪੁੱਛੋ"}
acknowledgement = {'en': '👆We have recieved your question:\n',
                   'hi': '👆हमें आपका प्रश्न प्राप्त हो गया है:\n',
                   'bn': "👆আমরা আপনার প্রশ্ন পেয়েছি:\n",
                   'ta': "👆உங்கள் கேள்வியை நாங்கள் பெற்றுள்ளோம்:\n",
                   'te': "👆మేము మీ ప్రశ్నను స్వీకరించాము:\n",
                   'pa': "👆ਸਾਨੂੰ ਤੁਹਾਡਾ ਸਵਾਲ ਪ੍ਰਾਪਤ ਹੋਇਆ ਹੈ:\n"}
"""
Adding description for JugalBandi docs
"""

description = """ JugalBandi a interactive API hosting chatbot services and document QA service. 
"""


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="JugalBandi API",
        version="0.0.1",
        description=description,
        routes=app.routes
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://i.ibb.co/XSn7BDW/Open-Ny-AI-Logo-final.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    db_engine = await create_engine()
    db_object = PostgresDatabase(engine=db_engine)
    api_key = api_key.strip() if isinstance(api_key, str) else None
    if api_key and await db_object.check_api_key(api_key=api_key):
        await db_engine.close()
        return api_key
    else:
        await db_engine.close()
        raise HTTPException(
            status_code=403, detail="Could not validate API KEY"
        )


@app.post("/register_user/", response_model=RegisterUserResponse)
async def register_user(data: RegisterUser, request: Request, api_key: APIKey = Depends(get_api_key)):
    db_engine = await create_engine()
    db_object = PostgresDatabase(engine=db_engine)
    client_ip_address = request.headers.get('x-forwarded-for')
    msg.info(f'{client_ip_address}  :: Register request received :: {str(data)}')

    first_name = None if data.first_name == 'None' else data.first_name
    if len(first_name.split()) != 1:
        first_name = str(first_name).split()[0]
    last_name = None if data.last_name == 'None' else data.last_name
    if len(last_name.split()) != 1:
        last_name = ' '.join(str(last_name).split()[1:])
    chat_id = data.chat_id
    phone_number = None if data.phone_number == 'None' else data.phone_number
    telegram_username = None if data.telegram_username == 'None' else data.telegram_username
    bot_preference = None if data.bot_preference == 'None' else data.bot_preference
    language_preference = 'en' if data.language_preference not in language_options.keys() else language_options[
        data.language_preference]
    response = await db_object.insert_user(first_name, last_name, chat_id, phone_number, telegram_username,
                                           bot_preference,
                                           language_preference)
    await db_engine.close()
    return response


@app.post("/change_language/", response_model=ChangeLanguageResponse)
async def change_language(data: ChangeLanguage, request: Request, api_key: APIKey = Depends(get_api_key)):
    db_engine = await create_engine()
    db_object = PostgresDatabase(engine=db_engine)
    client_ip_address = request.headers.get('x-forwarded-for')
    msg.info(f'{client_ip_address}  :: Language change request received :: {str(data)}')

    chat_id = data.chat_id
    language_preference = language_options[data.language_preference]
    response = await db_object.update_language_preference(chat_id=chat_id, language_preference=language_preference)
    await db_engine.close()
    return response


@app.post("/clear_memory/", response_model=ClearMemoryResponse)
async def clear_memory(data: ClearMemory, request: Request, api_key: APIKey = Depends(get_api_key)):
    db_engine = await create_engine()
    db_object = PostgresDatabase(engine=db_engine)
    client_ip_address = request.headers.get('x-forwarded-for')
    msg.info(f'{client_ip_address}  :: Clear Memory request received :: {str(data)}')

    chat_id = data.chat_id
    response = await db_object.clear_memory(chat_id=chat_id)
    await db_engine.close()
    return response


@app.post("/greetings/",
          response_model=GreetingsResponse)
async def greetings(data: GreetingsInput, request: Request,
                    api_key: APIKey = Depends(get_api_key)):
    """
    This is chat API that take input message. Message can either be audio or string
    """
    db_engine = await create_engine()
    db_object = PostgresDatabase(engine=db_engine)
    client_ip_address = request.headers.get('x-forwarded-for')
    msg.info(f'{client_ip_address}  :: Greetings request received :: {str(data)}')
    chat_id = data.chat_id
    language_preference = await db_object.get_language_preference(chat_id=chat_id)
    message = greeting_messages[language_preference]
    response = {"response": message}
    await db_engine.close()
    return response


@app.post("/chat/",
          response_model=ChatResponse)
async def chat(data: ChatInput, request: Request,
               api_key: APIKey = Depends(get_api_key)):
    """
    This is chat API that take input message. Message can either be audio or string
    """
    db_engine = await create_engine(timeout=600)
    db_object = PostgresDatabase(engine=db_engine)
    client_ip_address = request.headers.get('x-forwarded-for')
    msg.info(f'{client_ip_address}  :: Chat request received :: {str(data)}')
    message = data.message
    message_type = data.message_type
    chat_id = data.chat_id
    phone_number = data.phone_number
    platform = data.platform
    response, audio_url = await chatbot_flow(db_object=db_object, chat_id=chat_id, message=message,
                                             message_type=message_type, acknowledgements=acknowledgement)
    await db_object.update_api_quota(api_key=api_key)
    await db_engine.close()
    response = {"text": response, "audio_url": audio_url}
    return response


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8080)
