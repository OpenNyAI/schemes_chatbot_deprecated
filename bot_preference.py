from scheme_v1_prompt_engineering import get_scheme_fsm_bot_response


async def scheme_v1(db_obj, message, user_id, bot_preference='scheme_v1'):
    current_scheme_conversation_summary, current_scheme_name, current_prompt, current_conversation_chunk_id, current_prompt_type = await db_obj.get_prompts_v1(
        user_id)
    # process and fetch response from openAI model
    davinci_response, current_prompt, new_conversation_chunk_id, scheme_name, current_scheme_conversation_summary, next_prompt_type, next_prompt, llm_output = await get_scheme_fsm_bot_response(
        current_prompt=current_prompt,
        current_state=current_prompt_type,
        current_scheme_conversation_summary=current_scheme_conversation_summary,
        user_input=message,
        db_obj=db_obj,
        current_conversation_chunk_id=current_conversation_chunk_id,
        current_scheme_name=current_scheme_name,
        user_id=user_id,
        bot_preference=bot_preference)
    return current_conversation_chunk_id, current_scheme_conversation_summary, current_scheme_name, davinci_response, new_conversation_chunk_id, current_prompt, next_prompt_type, next_prompt, llm_output
