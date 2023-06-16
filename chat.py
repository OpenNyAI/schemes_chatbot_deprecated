import datetime
import os.path
import re
from io import BytesIO

import requests

import pytz

from utils import mask_sensitive_info
from bot_preference import scheme_v1
from cloud_filestorage import upload_file_and_get_public_url
from io_processing import process_incoming_voice, process_outgoing_voice, process_outgoing_text, process_incoming_text
from translator import translator


async def chatbot_flow(db_object, chat_id, message, message_type, acknowledgements):
    date = datetime.datetime.now(pytz.UTC)
    user_regional_lang_text = None
    response = 'We are facing some issues, we will fix it soon'
    stt_success = False
    davinci_success = False
    bot_success = False
    stt_api_name = None
    english_to_vernacular_translation_success = False
    english_to_vernacular_translation_api_name = None
    vernacular_to_english_translation_success = False
    vernacular_to_english_translation_api_name = None
    tts_success = False
    tts_service_name = None
    user_audio_file_link = None
    bot_audio_file_link = None
    inbound_audio_file_name = 'temp.mp3'
    outbound_audio_file_name = 'temp.mp3'

    # create translator object based on user language preference
    language_preference = await db_object.get_language_preference(chat_id=chat_id)
    translate = translator(input_language=language_preference)

    bot_preference = await db_object.get_bot_preference(chat_id=chat_id)

    # add default row for failure
    if not await db_object.check_failure_exist(chat_id=chat_id):
        await db_object.insert_user_prompt(chat_id=chat_id, conversation_chunk_id='FAILURE' + str(chat_id),
                                           scheme_name=None,
                                           conversation_summary=None,
                                           bot_preference=None,
                                           prompt_type=None)

    if message_type == 'text':
        if not re.search(r'[\.\?\!]$', message):
            message = message + '.'
        message, user_regional_lang_text, vernacular_to_english_translation_success, vernacular_to_english_translation_api_name = process_incoming_text(
            message, translate)
    else:
        # audio processing pending
        audio_link = message
        audio_response = requests.get(audio_link)
        if 'audio/ogg' in audio_response.headers.get('Content-Type'):
            audio_data = audio_response.content
            inbound_audio_file_name = str(chat_id) + '-Inbound-' + str(datetime.datetime.now()).replace(' ',
                                                                                                        '-') + '.ogg'
            with open(inbound_audio_file_name, 'wb') as f:
                f.write(audio_data)
            audio_file = BytesIO(audio_data)
            message, user_regional_lang_text, stt_success, stt_api_name, vernacular_to_english_translation_success, vernacular_to_english_translation_api_name = process_incoming_voice(
                audio_file,
                language_preference,
                translate=translate)
            user_audio_file_link = await upload_file_and_get_public_url(filename=inbound_audio_file_name,
                                                                        phone_number=chat_id,
                                                                        remote_filename=inbound_audio_file_name)
        else:
            response = 'We only support audio or text input, please provide your query in one of these'

    if (stt_success and vernacular_to_english_translation_success) or (
            message_type == 'text' and vernacular_to_english_translation_success):
        # Acknowledge the request
        if message_type != 'text':
            temp_response = acknowledgements[language_preference] + user_regional_lang_text
        message = mask_sensitive_info(message)
        if bot_preference == 'scheme_v1' or bot_preference is None:
            current_conversation_chunk_id, current_scheme_conversation_summary, current_scheme_name, davinci_response, new_conversation_chunk_id, current_prompt, next_prompt_name, next_prompt, llm_output = await scheme_v1(
                db_object, message, chat_id)
        else:
            current_conversation_chunk_id, current_scheme_conversation_summary, current_scheme_name, davinci_response, new_conversation_chunk_id, current_prompt, next_prompt_name, next_prompt, llm_output = '', '', '', '', '', '', '', '', ''

        if davinci_response == 'Because Server is overloaded, I am unable to answer you at the moment. Please retry.':
            davinci_success = False
        else:
            davinci_success = True
        if davinci_response == 'Sorry, I could not understand that information. Please answer in different wording.':
            bot_success = False
        else:
            bot_success = True

        davinci_response = davinci_response.split("Bot:")[-1].lstrip().strip()
        davinci_response = davinci_response.replace('"', '').replace("'", '')
        # if message_type != 'text':
        _, regional_lang_text, english_to_vernacular_translation_success, english_to_vernacular_translation_api_name = process_outgoing_text(
            message=davinci_response,
            translate=translate)
        response = regional_lang_text
        # else:
        #     regional_lang_text = davinci_response
        #
        #     response = regional_lang_text

        # update the db user prompts with prompts history and chat memory
        current_scheme_conversation_summary = current_scheme_conversation_summary.replace("'", "")

        await db_object.update_user_prompt(conversation_summary=current_scheme_conversation_summary,
                                           chunk_id=new_conversation_chunk_id)

        if message_type != 'text':
            # perform TTS
            audio, duration_seconds, tts_service_name = process_outgoing_voice(message=regional_lang_text,
                                                                               translate=translate)

            if audio:
                tts_success = True
                # send the audio response to user
                outbound_audio_file_name = str(chat_id) + '-Outbound-' \
                                           + str(datetime.datetime.now()).replace(' ', '-') + '.mp3'
                with open(outbound_audio_file_name, 'wb') as f:
                    f.write(audio.getvalue())
                bot_audio_file_link = await upload_file_and_get_public_url(filename=outbound_audio_file_name,
                                                                           phone_number=chat_id,
                                                                           remote_filename=outbound_audio_file_name)
            else:
                tts_success = False

        # Log the conversation event
        await db_object.insert_conversation(chat_id=chat_id, user_audio_file_link=user_audio_file_link,
                                            bot_audio_file_link=bot_audio_file_link,
                                            conversation_chunk_id=new_conversation_chunk_id,
                                            bot_preference=bot_preference,
                                            scheme_name=current_scheme_name, user_message=message,
                                            bot_response=davinci_response,
                                            user_message_translated=user_regional_lang_text,
                                            bot_response_translated=regional_lang_text,
                                            date=date, language_preference=language_preference,
                                            current_prompt=current_prompt,
                                            next_prompt_name=next_prompt_name, next_prompt=next_prompt,
                                            llm_output=llm_output)
        # insert service log
        await db_object.insert_service_logs(chat_id=chat_id, conversation_chunk_id=new_conversation_chunk_id,
                                            created_at=date, message_type=message_type,
                                            bot_preference=bot_preference,
                                            davinci_success=davinci_success, bot_success=bot_success,
                                            vernacular_to_english_translation_api_success=vernacular_to_english_translation_success,
                                            vernacular_to_english_translation_api_name=vernacular_to_english_translation_api_name,
                                            english_to_vernacular_translation_api_success=english_to_vernacular_translation_success,
                                            english_to_vernacular_translation_api_name=english_to_vernacular_translation_api_name,
                                            stt_api_success=stt_success, stt_api_name=stt_api_name,
                                            tts_api_success=tts_success,
                                            tts_api_name=tts_service_name)
    else:
        # send the text response to user
        new_conversation_chunk_id = 'FAILURE' + str(chat_id)
        current_scheme_name = None
        bot_preference = None
        current_prompt = None
        await db_object.insert_conversation(chat_id=chat_id, user_audio_file_link=user_audio_file_link,
                                            bot_audio_file_link=bot_audio_file_link,
                                            conversation_chunk_id=new_conversation_chunk_id,
                                            bot_preference=bot_preference,
                                            scheme_name=current_scheme_name, user_message=message,
                                            bot_response=response,
                                            user_message_translated=user_regional_lang_text,
                                            bot_response_translated=response,
                                            date=date, language_preference=language_preference,
                                            current_prompt=current_prompt,
                                            next_prompt_name=None, next_prompt=None, llm_output=None)
        # insert service log
        await db_object.insert_service_logs(chat_id=chat_id, conversation_chunk_id=new_conversation_chunk_id,
                                            created_at=date, message_type=message_type, bot_preference=bot_preference,
                                            davinci_success=davinci_success, bot_success=bot_success,
                                            vernacular_to_english_translation_api_success=vernacular_to_english_translation_success,
                                            vernacular_to_english_translation_api_name=vernacular_to_english_translation_api_name,
                                            english_to_vernacular_translation_api_success=english_to_vernacular_translation_success,
                                            english_to_vernacular_translation_api_name=english_to_vernacular_translation_api_name,
                                            stt_api_success=stt_success, stt_api_name=stt_api_name,
                                            tts_api_success=tts_success,
                                            tts_api_name=tts_service_name)

    # clean up
    if os.path.isfile(inbound_audio_file_name):
        os.remove(inbound_audio_file_name)
    if os.path.isfile(outbound_audio_file_name):
        os.remove(outbound_audio_file_name)
    return response, bot_audio_file_link
