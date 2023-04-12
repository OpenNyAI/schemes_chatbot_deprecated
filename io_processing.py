import logging
from io import BytesIO

from pydub import AudioSegment

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger('jugalbandi_telegram')


def process_incoming_voice(audio_bytes_data, language_preference, translate):
    try:
        regional_lang_text, api_name = translate.audioInput2text(audio_data=audio_bytes_data)
        s2t_success = True
        try:
            message, translation_api_name = \
                translate.indicTrans(text=regional_lang_text, source=language_preference, dest='en')
            translation_success = True
        except:
            message = None
            translation_success = False
            translation_api_name = None
    except:
        logger.info('Speech to text API failed')
        message, regional_lang_text = None, None
        s2t_success = False
        api_name = 'google' if translate.mode == 'google' else 'bhashini'
        translation_success = False
        translation_api_name = 'google' if translate.mode == 'google' else 'bhashini'
    return message, regional_lang_text, s2t_success, api_name, translation_success, translation_api_name


def process_outgoing_voice(message, translate):
    try:
        audio_content, is_google = translate.text2speech(text=message, language=translate.input_language)
        if audio_content and not is_google:
            audio = AudioSegment.from_file(audio_content, format="wav")
            audio_file = BytesIO()
            audio.export(audio_file, format='mp3')
            tts_service_name = 'bhashini'
            return audio_file, audio.duration_seconds, tts_service_name
        else:
            logger.debug('Used google t2s api')
            tts_service_name = 'google'
            audio_file = BytesIO(audio_content)
            return audio_file, None, tts_service_name
    except:
        tts_service_name = None
        return False, None, tts_service_name


def process_incoming_text(message, translate):
    regional_lang_text = message
    try:
        message, translation_api_name = translate.indicTrans(text=message, source=translate.input_language, dest='en')
        success = True
    except:
        logger.info("Translation API failed")
        success = False
        translation_api_name = 'google' if translate.mode == 'google' else 'bhashini'

    return message, regional_lang_text, success, translation_api_name


def process_outgoing_text(message, translate):
    try:
        regional_lang_text, translation_api_name = \
            translate.indicTrans(text=message, source='en', dest=translate.input_language)
        success = True
    except:
        success = False
        regional_lang_text = message
        translation_api_name = None
    return message, regional_lang_text, success, translation_api_name
