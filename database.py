import datetime
import json
import os

import asyncpg
import pytz

all_prompts = json.load(open('./data/prompts.json'))
all_scheme_info = json.load(open('./data/myschemes_scraped_combined.json'))
all_scheme_info_dict = {i['scheme_name']: i for i in all_scheme_info}


async def create_engine(timeout=5):
    engine = await asyncpg.create_pool(
        host=os.getenv('DATABASE_IP'),
        port=5432,
        user=os.getenv('DATABASE_USERNAME'),
        password=os.getenv('DATABASE_PASSWORD'),
        database=os.getenv('DATABASE_NAME'), max_inactive_connection_lifetime=timeout
    )
    await create_schema(engine)
    return engine


async def create_schema(engine):
    async with engine.acquire() as connection:
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS jugalbandi_users (
                id SERIAL PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                chat_id BIGINT UNIQUE NOT NULL,
                phone_number BIGINT UNIQUE,
                telegram_username TEXT,
                language_preference TEXT DEFAULT 'en',
                bot_preference TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS jugalbandi_tokens (
                id SERIAL PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                phone_number BIGINT UNIQUE,
                email TEXT,
                api_key TEXT UNIQUE NOT NULL,
                desciption TEXT,
                available_quota BIGINT NOT NULL,
                used_quota BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS jugalbandi_user_prompts (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES jugalbandi_users(chat_id),
                conversation_chunk_id TEXT UNIQUE,
                scheme_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                conversation_summary TEXT,
                prompt_type TEXT,
                bot_preference TEXT
            );
            CREATE TABLE IF NOT EXISTS jugalbandi_service_logs (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES jugalbandi_users(chat_id),
                conversation_chunk_id TEXT,
                FOREIGN KEY (conversation_chunk_id) REFERENCES jugalbandi_user_prompts(conversation_chunk_id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                message_type TEXT,
                bot_preference TEXT,
                davinci_success BOOL,
                bot_success BOOL,
                vernacular_to_english_translation_api_success BOOL,
                vernacular_to_english_translation_api_name TEXT,
                english_to_vernacular_translation_api_success BOOL,
                english_to_vernacular_translation_api_name TEXT,
                stt_api_success BOOL,
                stt_api_name TEXT,
                tts_api_success BOOL,
                tts_api_name TEXT
            );
            CREATE TABLE IF NOT EXISTS jugalbandi_users_conversation_history (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES jugalbandi_users(chat_id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                language_preference TEXT DEFAULT 'hi',
                user_audio_file_link TEXT,
                bot_audio_file_link TEXT,
                conversation_chunk_id TEXT,
                FOREIGN KEY (conversation_chunk_id) REFERENCES jugalbandi_user_prompts(conversation_chunk_id),
                bot_preference TEXT,
                scheme_name TEXT,
                user_message TEXT,
                bot_response TEXT,
                user_message_translated TEXT,
                bot_response_translated TEXT,
                current_prompt TEXT,
                next_prompt_name TEXT,
                next_prompt TEXT,
                llm_output TEXT
                
            );
            CREATE INDEX IF NOT EXISTS user_chat_id_idx ON jugalbandi_users(chat_id);
            CREATE INDEX IF NOT EXISTS token_key_idx ON jugalbandi_tokens(api_key);
            CREATE INDEX IF NOT EXISTS prompts_chat_id_idx ON jugalbandi_user_prompts(chat_id);
            CREATE INDEX IF NOT EXISTS chat_id_idx ON jugalbandi_users_conversation_history(chat_id);
            CREATE INDEX IF NOT EXISTS user_chat_id_idx ON jugalbandi_service_logs(chat_id);
        ''')


class PostgresDatabase:
    def __init__(self, engine):
        self.engine = engine

    async def update_api_quota(self, api_key):
        async with self.engine.acquire() as connection:
            # Check if user with given chat_id already exists
            existing_user = await connection.fetchrow(
                'SELECT * FROM jugalbandi_tokens WHERE api_key = $1', api_key
            )
            await connection.execute('Update jugalbandi_tokens set used_quota = $1 WHERE api_key = $2',
                                     existing_user['used_quota'] + 1, api_key)

    async def check_user(self, chat_id):
        async with self.engine.acquire() as connection:
            # Check if user with given chat_id already exists
            existing_user = await connection.fetchrow(
                'SELECT * FROM jugalbandi_users WHERE chat_id = $1', chat_id
            )
        if existing_user:
            return True
        else:
            return False

    async def insert_user(self, first_name, last_name, chat_id, phone_number, telegram_username, bot_preference,
                          language_preference='en'):
        existing_user = await self.check_user(chat_id)
        # If user with given chat_id don't exist, insert the user's details
        if not existing_user:
            async with self.engine.acquire() as connection:
                await connection.execute(
                    '''
                    INSERT INTO jugalbandi_users 
                    (first_name, last_name, chat_id, phone_number, telegram_username, language_preference, bot_preference, created_at) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''',
                    first_name, last_name, chat_id, phone_number, telegram_username, language_preference,
                    bot_preference,
                    datetime.datetime.now(pytz.UTC)
                )
            return {'success': True}
        else:
            return {'success': False}

    async def update_language_preference(self, chat_id, language_preference):
        async with self.engine.acquire() as connection:
            await connection.execute(
                'UPDATE jugalbandi_users SET language_preference = $1 WHERE chat_id = $2',
                language_preference, chat_id
            )
        return {'success': True}

    async def check_api_key(self, api_key):
        async with self.engine.acquire() as connection:
            # Check if user with given chat_id already exists
            existing_user = await connection.fetchrow(
                'SELECT * FROM jugalbandi_tokens WHERE api_key = $1', api_key
            )
        if existing_user and existing_user['available_quota'] > existing_user['used_quota']:
            return True
        else:
            return False

    async def clear_memory(self, chat_id):
        async with self.engine.acquire() as connection:
            await connection.execute(
                '''UPDATE jugalbandi_user_prompts SET conversation_summary= '',
                prompt_type ='user_information_extraction', scheme_name='' WHERE chat_id = $1''',
                chat_id
            )
        return {'success': True}

    async def insert_service_logs(self, chat_id, conversation_chunk_id, created_at, message_type, bot_preference,
                                  davinci_success, bot_success, vernacular_to_english_translation_api_success,
                                  vernacular_to_english_translation_api_name,
                                  english_to_vernacular_translation_api_success,
                                  english_to_vernacular_translation_api_name,
                                  stt_api_success,
                                  stt_api_name, tts_api_success, tts_api_name):
        async with self.engine.acquire() as connection:
            await connection.execute('''
                        INSERT INTO jugalbandi_service_logs (chat_id, conversation_chunk_id,created_at, message_type, 
                        bot_preference, davinci_success, bot_success, vernacular_to_english_translation_api_success,
                                  vernacular_to_english_translation_api_name,english_to_vernacular_translation_api_success,
                                  english_to_vernacular_translation_api_name, 
                        stt_api_success, stt_api_name, tts_api_success, tts_api_name)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ''', chat_id, conversation_chunk_id, created_at, message_type, bot_preference, davinci_success,
                                     bot_success, vernacular_to_english_translation_api_success,
                                     vernacular_to_english_translation_api_name,
                                     english_to_vernacular_translation_api_success,
                                     english_to_vernacular_translation_api_name, stt_api_success,
                                     stt_api_name, tts_api_success, tts_api_name)

        return {'success': True}

    async def get_bot_preference(self, chat_id):
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(
                'SELECT bot_preference FROM jugalbandi_users WHERE chat_id = $1', chat_id
            )
        return result['bot_preference']

    async def update_bot_preference(self, chat_id, bot_preference):
        async with self.engine.acquire() as connection:
            await connection.execute(
                'UPDATE jugalbandi_users SET bot_preference = $1 WHERE chat_id = $2',
                bot_preference, chat_id
            )

    async def get_language_preference(self, chat_id):
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(
                'SELECT language_preference FROM jugalbandi_users WHERE chat_id = $1', chat_id
            )
        return result['language_preference']

    async def insert_conversation(self, chat_id, user_audio_file_link, bot_audio_file_link, conversation_chunk_id,
                                  bot_preference, scheme_name,
                                  user_message, bot_response, user_message_translated, bot_response_translated,
                                  date, language_preference, current_prompt, next_prompt_name, next_prompt, llm_output):
        async with self.engine.acquire() as connection:
            await connection.execute(
                '''INSERT INTO jugalbandi_users_conversation_history 
                (chat_id, created_at, language_preference, user_audio_file_link, bot_audio_file_link, conversation_chunk_id, bot_preference, scheme_name, user_message, bot_response, user_message_translated, bot_response_translated, current_prompt, next_prompt_name, next_prompt, llm_output) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)''',
                chat_id, date, language_preference, user_audio_file_link, bot_audio_file_link, conversation_chunk_id,
                bot_preference, scheme_name,
                user_message, bot_response, user_message_translated, bot_response_translated, current_prompt,
                next_prompt_name, next_prompt, str(llm_output)
            )

    async def insert_user_prompt(self, chat_id, conversation_chunk_id='',
                                 scheme_name='',
                                 created_at=datetime.datetime.now(pytz.UTC),
                                 updated_at=datetime.datetime.now(pytz.UTC),
                                 conversation_summary='',
                                 bot_preference=None,
                                 prompt_type=None):
        async with self.engine.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO jugalbandi_user_prompts
                (chat_id, conversation_chunk_id, scheme_name, created_at, updated_at, conversation_summary,prompt_type,bot_preference)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
                ''',
                chat_id, conversation_chunk_id, scheme_name, created_at, updated_at, conversation_summary, prompt_type,
                bot_preference)

    async def check_failure_exist(self, chat_id):
        async with self.engine.acquire() as connection:
            # Check if user with given chat_id already exists
            existing_user = await connection.fetchrow(
                '''
                SELECT * FROM jugalbandi_user_prompts WHERE chat_id = $1 and conversation_chunk_id=$2
                ''', chat_id, 'FAILURE' + str(chat_id)
            )
        if existing_user:
            return True
        else:
            return False

    async def update_user_prompt(self, conversation_summary, chunk_id):
        async with self.engine.acquire() as conn:
            await conn.execute(
                '''
                UPDATE jugalbandi_user_prompts
                SET updated_at = $1 ,conversation_summary= $2 WHERE conversation_chunk_id = $3;
                ''', datetime.datetime.now(pytz.UTC), conversation_summary, chunk_id
            )

    async def update_user_prompt_with_new_scheme(self, chunk_id, scheme_name, prompt_type):
        async with self.engine.acquire() as conn:
            await conn.execute(
                '''
                UPDATE jugalbandi_user_prompts
                SET updated_at = $1 ,scheme_name= $2, prompt_type= $3 WHERE conversation_chunk_id = $4;
                ''', datetime.datetime.now(pytz.UTC), scheme_name, prompt_type, chunk_id
            )

    async def get_all_scheme_names(self) -> str:
        """reads all the scheme names"""
        async with self.engine.acquire() as connection:
            result = await connection.fetch(f'SELECT scheme_name FROM schemes_details')
        all_scheme_names = '\n'.join([i['scheme_name'] for i in result])
        return all_scheme_names

    async def get_all_scheme_names_myscheme(self) -> str:
        """reads all the scheme names"""
        async with self.engine.acquire() as connection:
            result = await connection.fetch(f'SELECT scheme_name FROM myschemes_info')
        all_scheme_names = '\n'.join([i['scheme_name'] for i in result])
        return all_scheme_names

    async def get_specific_scheme_details(self, scheme_name) -> dict:
        specific_scheme_details = dict()
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(f"SELECT * FROM schemes_details where scheme_name='{scheme_name}'")
        if result is not None:
            specific_scheme_details['scheme_name'] = result['scheme_name']
            specific_scheme_details['summary'] = result['summary']
            specific_scheme_details['eligibility_criteria'] = result['eligibility_criteria']
            specific_scheme_details['benefits'] = result['benefits']
            specific_scheme_details['documents_required'] = result['documents_required']
        return specific_scheme_details

    async def get_specific_scheme_details_myscheme(self, scheme_name) -> dict:
        specific_scheme_details = dict()
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(f"SELECT * FROM myschemes_info where scheme_name='{scheme_name}'")
        if result is not None:
            specific_scheme_details['scheme_name'] = result['scheme_name']
            specific_scheme_details['tags'] = result['tags']
            specific_scheme_details['details'] = result['details']
            specific_scheme_details['eligibility_criteria'] = result['eligibility_criteria']
            specific_scheme_details['benefits'] = result['benefits']
            specific_scheme_details['application_process'] = result['application_process']
            specific_scheme_details['documents_required'] = result['documents_required']
            specific_scheme_details['scheme_short_title'] = result['scheme_short_title']
            specific_scheme_details['scheme_category'] = result['scheme_category']
            specific_scheme_details['scheme_subcategory'] = result['scheme_subcategory']
        return specific_scheme_details

    async def get_prompts(self, chat_id):
        from utils import load_specific_scheme_prompt
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(
                '''
                SELECT conversation_chunk_id, scheme_name, conversation_summary FROM jugalbandi_user_prompts 
                WHERE chat_id = $1 order by created_at desc limit 1''',
                chat_id
            )
        if result is None:
            return '', '', '', ''
        else:
            current_scheme_conversation_summary = result['conversation_summary']
            current_scheme_name = result['scheme_name']
            scheme_chatbot_prompt = json.load(open('data/prompts.json'))['scheme_chatbot_prompt']
            current_prompt, current_scheme_summary = await load_specific_scheme_prompt(current_scheme_name,
                                                                                       scheme_chatbot_prompt,
                                                                                       self.engine)
            current_conversation_chunk_id = result['conversation_chunk_id']
            return current_scheme_conversation_summary, current_scheme_name, current_prompt, current_conversation_chunk_id

    async def get_prompts_v1(self, chat_id):
        from scheme_v1_prompt_engineering import load_specific_scheme_prompt
        async with self.engine.acquire() as connection:
            result = await connection.fetchrow(
                '''
                SELECT * FROM jugalbandi_user_prompts 
                WHERE chat_id = $1 and bot_preference = 'scheme_v1' order by updated_at desc limit 1''',
                chat_id
            )
        if result is None or 'FAILURE' in result['conversation_chunk_id']:
            return '', '', '', '', 'user_information_extraction'
        else:
            current_prompt_type = result['prompt_type']
            current_scheme_conversation_summary = result['conversation_summary']
            current_scheme_name = result['scheme_name']
            current_conversation_chunk_id = result['conversation_chunk_id']

            if current_prompt_type == 'specific_scheme_conversation':
                scheme_chatbot_prompt = all_prompts['scheme_chatbot_prompt']
                current_prompt, scheme_summary = load_specific_scheme_prompt(current_scheme_name,
                                                                             scheme_chatbot_prompt)
            elif current_prompt_type == 'user_information_extraction':
                current_prompt = all_prompts['user_information_extraction']
            elif current_prompt_type == 'specific_scheme_name_disambiguation':
                current_prompt = all_prompts['scheme_name_disambiguation_filtered_schemes'] + '\n' + '\n'.join(
                    current_scheme_name.split('||'))
            else:
                current_prompt = ''

            return current_scheme_conversation_summary, current_scheme_name, current_prompt, current_conversation_chunk_id, current_prompt_type
