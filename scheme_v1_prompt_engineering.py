import ast
import copy
import datetime
import json
import os
import pickle
import re

import pytz
from transitions import Machine
from openai_utility.openai_utils import call_openAI_api, call_chatgpt_api

all_schemes_information = json.load(open('./data/myschemes_scraped_combined.json'))
all_schemes_information_dict = {i['scheme_name']: i for i in all_schemes_information}
prompts = json.load(open('data/prompts.json'))


async def load_scheme_name_disambiguation_prompt_myscheme(db_obj) -> str:
    """
    Loads the prompt for mapping the user query to  one of the supported scheme names
    """
    all_scheme_names = await db_obj.get_all_scheme_names_myscheme()
    scheme_name_disambiguation = prompts['scheme_name_disambiguation']
    scheme_name_disambiguation_prompt = all_scheme_names + scheme_name_disambiguation
    return scheme_name_disambiguation_prompt


async def load_information_extraction_prompt(db_obj) -> str:
    """
    Loads the prompt for mapping the user query to  one of the supported scheme names
    """
    user_information_extraction_prompt = prompts['user_information_extraction']
    return user_information_extraction_prompt


def load_specific_scheme_prompt(interested_scheme_name, scheme_chatbot_prompt) -> (str, str):
    """
    Returns the details of the input specific scheme which can be used as prompt for that scheme
    """
    # interested_scheme_details = await get_specific_scheme_details_myscheme(engine=engine, scheme_name=interested_scheme_name)
    interested_scheme_details = all_schemes_information_dict.get(interested_scheme_name)
    if interested_scheme_details:
        prompt = scheme_chatbot_prompt
        if interested_scheme_details['eligibility_criteria']:
            eligibility = interested_scheme_details['eligibility_criteria']

            prompt = prompt + '\n\nScheme Name: ' + interested_scheme_name + "\n\nStart of scheme " \
                                                                             "details\n\nEligibility_Criteria:\n\"\"\"\nApplicant may be eligible for " + interested_scheme_name + " if he/she meet the following criteria:\n" + str(
                eligibility) + "\"\"\""

        if interested_scheme_details['documents_required'] != '':
            documents = interested_scheme_details['documents_required']
            documents = re.sub('Documents Required\n', '', documents)
            prompt = prompt + "\n\nDocuments Required:\n" + documents

        if interested_scheme_details['benefits'] != '':
            benefits = interested_scheme_details['benefits']
            benefits = re.sub('Benefits\n', '', benefits)
            prompt = prompt + "\n\nBenefits:\n" + benefits

        summary = interested_scheme_details['details']

        prompt = prompt + '\nEnd of scheme details.\n\n'
    else:
        prompt = ''
        summary = ''
    return prompt, summary


with open("./data/scheme_indices_eligibility.pickle", "rb") as f:
    search_index = pickle.load(f)


def get_best_matching_scheme(question, user_need_scheme_category, do_scheme_category_filtering, k=10)->list[str]:
    exact_match_threshold = 0.3
    score_threshold = 0.5
    best_matching_schemes = []

    eligible_schemes_chunks = search_index.similarity_search_with_score(query=question, k=k)
    if eligible_schemes_chunks:

        exact_matches = [i.metadata['source'] for (i, score) in eligible_schemes_chunks if
                         score <= exact_match_threshold]

        if len(exact_matches) == 1:
            eligible_schemes = exact_matches
        else:
            eligible_schemes = [i.metadata['source'] for (i, score) in eligible_schemes_chunks if
                                score <= score_threshold]

        ######## check if the schemes returned by the search have same scheme category
        if do_scheme_category_filtering:
            for eligible_scheme in eligible_schemes:
                eligible_scheme_name = eligible_scheme
                if user_need_scheme_category in all_schemes_information_dict.get(eligible_scheme_name)[
                    'schemeCategory']:
                    best_matching_schemes.append(eligible_scheme_name)
        else:
            best_matching_schemes = eligible_schemes
    return best_matching_schemes


def create_user_response_for_best_matching_schemes(best_matching_schemes):
    max_schemes_to_show = 5
    if len(best_matching_schemes) > 0:
        user_response = 'I found following schemes which might be helpful. Which one would you like to know more about?'
        for i, scheme in enumerate(best_matching_schemes):
            user_response = user_response + '\n' + str(i + 1) + ") " + scheme
            if all_schemes_information_dict.get(scheme) is not None:
                user_response = user_response + ': ' + \
                            all_schemes_information_dict.get(scheme)['summary']
    else:
        user_response = 'Sorry, I cant find any schemes for you at this moment. Would you please explain your need in detail?'
    return user_response

def create_user_response_for_too_many_matching_schemes(best_matching_schemes):
    if len(best_matching_schemes) > 0:

        user_response = 'I found '+ str(len(best_matching_schemes))+' schemes that could be useful, but I need more information to find more relevant ones. Alternatively, please let me know which one of these schemes you would like to know more about.'
        for i, scheme in enumerate(best_matching_schemes):
            user_response = user_response + '\n' + str(i + 1) + ") " + scheme
    else:
        user_response = 'Sorry, I cant find any schemes for you at this moment. Would you please explain your need in detail?'
    return user_response

def create_prompt_for_filtered_scheme_name_disambiguation(best_matching_schemes):
    scheme_name_disambiguation_filtered_schemes_prompt = prompts[
        'scheme_name_disambiguation_filtered_schemes']

    concatenated_scheme_names = '\n'.join(best_matching_schemes)
    scheme_name_disambiguation_filtered_schemes_prompt = scheme_name_disambiguation_filtered_schemes_prompt + concatenated_scheme_names
    return scheme_name_disambiguation_filtered_schemes_prompt


user_information_extraction_prompt = prompts['user_information_extraction']


def get_trigger_event_based_on_llm_output(llm_output):
    if '{"Extracted_Info":' in llm_output:
        ###### this is output from user information extraction prompt
        trigger_condition = 'information_extraction'

    elif 'ChangingScheme' in llm_output:
        #### user is talking about different scheme, do need extraction
        trigger_condition = 'scheme_change'

    elif 'user_selected_filtered_scheme' in llm_output:
        ####### Need to disambiguate from multiple matching schemes given to user
        trigger_condition = 'user_selected_scheme_from_options'

    else:
        #### this is a specific scheme conversation
        trigger_condition = 'continue_scheme_conversation'
    return trigger_condition


class scheme_chatbot_fsm():
    states = ['user_information_extraction', 'specific_scheme_name_disambiguation', 'specific_scheme_conversation']

    def __init__(self, wake_up_state, current_scheme_name, llm_output, user_input, current_prompt,
                 current_scheme_conversation_summary):
        self.machine = Machine(model=self, states=scheme_chatbot_fsm.states, initial=wake_up_state)
        self.current_scheme_name = current_scheme_name
        self.user_response = ''
        self.scheme_search_result = None
        self.clarifying_question = None
        self.llm_output = llm_output
        self.llm_output_logging = llm_output
        self.user_information_dict = None
        self.user_input = user_input
        self.current_prompt = current_prompt
        self.current_scheme_conversation_summary = current_scheme_conversation_summary
        self.next_prompt = ''
        self.next_scheme_name = ''
        self.search_model = 'gpt3'

        self.machine.add_transition(trigger='information_extraction',
                                    source='user_information_extraction',
                                    dest='specific_scheme_name_disambiguation',
                                    conditions=['check_specific_need_or_specific_scheme',
                                                'check_if_multiple_schemes_less_than_5_found'],
                                    after=self.update_user_response_and_next_prompt_for_multiple_matching_schemes)

        self.machine.add_transition(trigger='information_extraction',
                                    source='user_information_extraction',
                                    dest='specific_scheme_conversation',
                                    conditions=['check_specific_need_or_specific_scheme',
                                                'check_if_single_scheme_found'],
                                    after=self.update_user_response_and_next_prompt_for_single_matching_schemes)

        self.machine.add_transition(trigger='information_extraction',
                                    source='user_information_extraction',
                                    dest='user_information_extraction',
                                    conditions=['check_specific_need_or_specific_scheme', 'check_if_no_schemes_found'],
                                    after=self.update_user_response_and_next_prompt_for_no_matching_schemes)

        self.machine.add_transition(trigger='information_extraction',
                                    source='user_information_extraction',
                                    dest='user_information_extraction',
                                    conditions=['check_specific_need_or_specific_scheme',
                                                'check_if_more_than_5_matching_scheme_found'],
                                    after=self.update_user_response_and_next_prompt_for_multiple_matching_schemes)

        self.machine.add_transition(trigger='user_selected_scheme_from_options',
                                    source='specific_scheme_name_disambiguation',
                                    dest='specific_scheme_conversation',
                                    conditions=['check_if_single_scheme_selected_from_options'],
                                    after=self.update_user_response_and_next_prompt_for_single_matching_schemes)

        self.machine.add_transition(trigger='user_selected_scheme_from_options',
                                    source='specific_scheme_name_disambiguation',
                                    dest='specific_scheme_name_disambiguation',
                                    conditions=['check_if_ambiguous_scheme_selected_from_options'],
                                    after=self.update_user_response_and_next_prompt_for_ambiguous_scheme_selection)

        self.machine.add_transition(trigger='scheme_change',
                                    source='specific_scheme_name_disambiguation',
                                    dest='user_information_extraction',
                                    after=self.perform_user_need_extraction_after_scheme_change)

        self.machine.add_transition(trigger='scheme_change',
                                    source='specific_scheme_conversation',
                                    dest='user_information_extraction',
                                    after=self.perform_user_need_extraction_after_scheme_change)

        self.machine.add_transition(trigger='continue_scheme_conversation',
                                    source='specific_scheme_conversation',
                                    dest='specific_scheme_conversation',
                                    after=self.update_user_response_and_next_prompt_for_specific_scheme_continuation)

    def check_specific_need_or_specific_scheme(self) -> bool:
        #### check if user has expressed a specific need or asking for specific scheme
        try:
            # output = output.replace("'", "\'")

            user_information_str = re.sub(r'(^.*)({\"Extracted_Info.*)', r'\2', self.llm_output, flags=re.DOTALL)
            # user_information_dict = json.loads(user_information_str)
            self.user_information_dict = ast.literal_eval(user_information_str)

            if self.user_information_dict['User_Message'] == '':
                ##### User has provided all the information needed for finding best scheme
                return True

            else:
                #### Need to ask more information from user
                self.user_response = self.user_information_dict['User_Message']
                return False

        except:
            self.user_response = 'Sorry, I could not understand that information. Please answer in different wording.'
            return False

    def check_if_multiple_schemes_less_than_5_found(self) -> bool:
        #### Return whether multiple schemes have been found for user need
        if not self.scheme_search_result:
            self.search_scheme_for_user_need()
        if len(self.scheme_search_result) > 1 and len(self.scheme_search_result) <= 5:
            return True
        else:
            return False

    def check_if_single_scheme_found(self) -> bool:
        #### Return whether unique scheme has been found for user need
        if not self.scheme_search_result:
            self.search_scheme_for_user_need()
        if len(self.scheme_search_result) == 1:
            self.next_scheme_name = self.scheme_search_result[0]
            return True
        else:
            return False

    def check_if_single_scheme_selected_from_options(self) -> bool:
        ###### this is response of user choosing one scheme from multiple recommendations
        try:
            output = self.llm_output.replace("'", "\'")
            user_information_str = re.sub(r'(^.*)({\'user_selected_filtered_scheme.*)', r'\2', output, flags=re.DOTALL)
            user_information_dict = ast.literal_eval(user_information_str)

            if user_information_dict['user_selected_filtered_scheme'] == 'MULTIPLE_MATCHES':
                return False

            else:
                self.next_scheme_name = user_information_dict['user_selected_filtered_scheme']
                return True

        except:
            return False

    def check_if_ambiguous_scheme_selected_from_options(self) -> bool:
        ###### this is response of user choosing one scheme from multiple recommendations
        try:
            output = self.llm_output.replace("'", "\'")
            user_information_str = re.sub(r'(^.*)({\'user_selected_filtered_scheme.*)', r'\2', output, flags=re.DOTALL)
            user_information_dict = ast.literal_eval(user_information_str)

            if user_information_dict['user_selected_filtered_scheme'] == 'MULTIPLE_MATCHES':
                return True

            else:
                self.scheme_name = user_information_dict['user_selected_filtered_scheme']
                return False

        except:
            return True

    def check_if_no_schemes_found(self) -> bool:
        #### Return whether multiple schemes have been found for user need
        if not self.scheme_search_result:
            self.search_scheme_for_user_need()
        if self.scheme_search_result is None:
            return True
        else:
            return False

    def check_if_more_than_5_matching_scheme_found(self) -> bool:
        if not self.scheme_search_result:
            self.search_scheme_for_user_need()
        if len(self.scheme_search_result) > 5:
            return True
        else:
            return False

    def perform_user_need_extraction_after_scheme_change(self):
        prompt = user_information_extraction_prompt
        prompt = prompt + "\nUser: " + self.user_input + "\nBot: "
        prompts_seperator = '\n\n' + '-' * 100 + '\n\n'
        self.current_prompt = '2 prompts were used.' + prompts_seperator + self.current_prompt + prompts_seperator + prompt
        output = call_openAI_api(prompt)
        self.llm_output = output
        self.llm_output_logging = self.llm_output + prompts_seperator + copy.deepcopy(output)
        self.current_scheme_conversation_summary = ''  ## clear memory as we are restarting the conversation
        trigger_condition = get_trigger_event_based_on_llm_output(output)
        self.trigger(trigger_condition)

    def get_scheme_summaries(self, scheme_names: list) -> str:
        summary_list = []
        for scheme in scheme_names:
            scheme_summary = '- ' + scheme + ' : ' + all_schemes_information_dict.get(scheme)['summary']
            summary_list.append(scheme_summary)
        return '\n'.join(summary_list)

    def get_user_inputs_from_conversation_history(self) -> str:
        if self.current_scheme_conversation_summary.strip() != '':
            user_inputs = re.findall(r'User\:(.*)(\nBot\:|$)', self.current_scheme_conversation_summary)
            concaternated_user_inputs = ' '.join([i[0] for i in user_inputs]).strip()
            return concaternated_user_inputs
        else:
            return ''

    def search_scheme_for_user_need(self):
        do_scheme_category_filtering = True
        k = 10
        score_threshold = 0.5
        if self.user_information_dict['Extracted_Info']['Specific_Scheme_Information'] == "Yes":
            do_scheme_category_filtering = False
            k = 1

        query = self.get_user_inputs_from_conversation_history() + self.user_input
        faiss_search_results = search_index.similarity_search_with_score(query=query, k=k)
        faiss_filtered_schemes = [i.metadata['source'] for (i, score) in faiss_search_results if
                                  score <= score_threshold]

        faiss_filtered_schemes_with_summary = self.get_scheme_summaries(faiss_filtered_schemes)
        if k == 1:
            self.scheme_search_result = faiss_filtered_schemes
        else:
            if os.environ.get('SCHEME_SEARCH_FILTERING') == 'cot_filtering':
                #### perform CoT filtering on filtered schemes
                prompts_seperator = '\n\n' + '-' * 100 + '\n\n'
                if self.search_model == 'chatgpt':
                    chatgpt_system_prompt = prompts[
                                                'scheme_filtering_chatgpt_prompt'] + faiss_filtered_schemes_with_summary
                    user_inputs = self.concatenate_user_inputs()
                    messages = [{"role": "system", "content": chatgpt_system_prompt},
                                {"role": "user", "content": user_inputs}]
                    self.current_prompt = '2 prompts were used.' + prompts_seperator + self.current_prompt + prompts_seperator + chatgpt_system_prompt
                    scheme_filtering_llm_response = call_chatgpt_api(messages, max_tokens=1024)
                else:

                    prompt_and_schemes = prompts[
                                             'scheme_filtering_prompt'] + faiss_filtered_schemes_with_summary + "\"\"\"\n"
                    prompt = prompt_and_schemes + "\nConversation History:\n\"\"\"" + \
                             self.current_scheme_conversation_summary.strip() + "\n\nUser: " + self.user_input + '''\n"""\n\nBot:'''

                    self.current_prompt = '2 prompts were used.' + prompts_seperator + self.current_prompt + prompts_seperator + prompt_and_schemes
                    scheme_filtering_llm_response = call_openAI_api(prompt, max_tokens=1024)


                self.llm_output_logging = self.llm_output + prompts_seperator + copy.deepcopy(
                    scheme_filtering_llm_response)
                self.parse_scheme_filtering_llm_output(scheme_filtering_llm_response)
            else:
                user_expressed_scheme_category = self.user_information_dict['Extracted_Info']['Scheme_Category']
                self.scheme_search_result = get_best_matching_scheme(self.user_input, user_expressed_scheme_category,
                                                                     do_scheme_category_filtering, k)

    def update_user_response_and_next_prompt_for_ambiguous_scheme_selection(self):
        ### user has not selected one name from options then ask user for more clarity
        bot_response = 'I could not select one scheme from previously displayed schme list based your response. Please select one name from previously shown scheme names. If you want search for a different need then please mention that you want to search for a different need and say your need.'
        self.user_response = bot_response
        best_matching_schemes = self.current_scheme_name.split('||')
        self.next_prompt = create_prompt_for_filtered_scheme_name_disambiguation(best_matching_schemes)
        self.next_scheme_name = self.current_scheme_name

    def update_user_response_and_next_prompt_for_multiple_matching_schemes(self):
        ##### multiple schemes found and hence ask user which scheme he/she wants

        best_matching_schemes = self.scheme_search_result
        if len(best_matching_schemes) <= 5:
            self.user_response = create_user_response_for_best_matching_schemes(best_matching_schemes)
            self.next_prompt = create_prompt_for_filtered_scheme_name_disambiguation(best_matching_schemes)
            self.next_scheme_name = '||'.join(best_matching_schemes)
        else:
            if self.clarifying_question:
                self.user_response = self.clarifying_question
                self.next_prompt = self.current_prompt
                self.next_scheme_name = self.current_scheme_name
            else:
                self.user_response = create_user_response_for_too_many_matching_schemes(best_matching_schemes)
                self.next_prompt = self.current_prompt
                self.next_scheme_name = self.current_scheme_name

    def update_user_response_and_next_prompt_for_single_matching_schemes(self):
        single_best_scheme = self.next_scheme_name
        bot_response = 'I think ' + single_best_scheme + ' best fits your needs.'
        scheme_summary = all_schemes_information_dict.get(single_best_scheme)['summary']
        self.user_response = bot_response + scheme_summary + '\nWhat would you like to know more about this scheme?'
        self.next_prompt, scheme_summary = load_specific_scheme_prompt(single_best_scheme,
                                                                       prompts['scheme_chatbot_prompt'])
        self.next_scheme_name = single_best_scheme

    def update_user_response_and_next_prompt_for_no_matching_schemes(self):

        self.user_response = create_user_response_for_best_matching_schemes([])
        self.next_prompt = self.current_prompt
        self.next_scheme_name = ''

    def update_user_response_and_next_prompt_for_single_selected_scheme(self):
        single_best_scheme = self.scheme_search_result[0][0]
        bot_response = 'I think ' + single_best_scheme + ' best fits your needs.'
        scheme_summary = all_schemes_information_dict.get(single_best_scheme)['summary']
        self.user_response = bot_response + scheme_summary + '\nWhat would you like to know more about this scheme?'
        self.next_prompt, scheme_summary = load_specific_scheme_prompt(single_best_scheme,
                                                                       prompts['scheme_chatbot_prompt'])
        self.next_scheme_name = single_best_scheme

    def update_user_response_and_next_prompt_for_specific_scheme_continuation(self):
        if "user_message" in self.llm_output:
            user_message_str = re.sub(r'(^.*)({\"user_message.*)', r'\2', self.llm_output, flags=re.DOTALL)
            try:
                user_messasge_dict = ast.literal_eval(user_message_str)
                bot_response = user_messasge_dict['user_message']
            except:
                bot_response = re.sub(r'{\"user_message\"\:\s+\"', '', user_message_str)
        elif "- Lets think step by step" in self.llm_output:
            bot_response = self.llm_output.split('\n-')[-1].strip()
        else:
            bot_response = self.llm_output
        self.user_response = bot_response
        self.next_prompt = self.current_prompt
        self.next_scheme_name = self.current_scheme_name

    def parse_scheme_filtering_llm_output(self, scheme_filtering_llm_response):
        clarifying_questions = re.findall(r'{\s*\'user_message\':.*}', scheme_filtering_llm_response, re.DOTALL)
        try:
            self.clarifying_question = ast.literal_eval(clarifying_questions[-1])['user_message']
        except:
            print("Error parsing scheme search LLM output")
            self.clarifying_question = None

        scheme_search_result_str = \
            re.search(r'relevant_schemes_list.*(\[.*\])', scheme_filtering_llm_response).groups()[0]
        try:
            scheme_search_result_str = re.sub(', “', ', "“', scheme_search_result_str)
            self.scheme_search_result = ast.literal_eval(scheme_search_result_str)
        except:
            print("Error parsing scheme search LLM output")
            self.scheme_search_result = None

    def concatenate_user_inputs(self):
        user_inputs = []
        all_inputs = self.current_scheme_conversation_summary.split('\n')
        for input in all_inputs:
            if input.startswith('User:'):
                user_inputs.append(re.sub('User:','',input))
        user_inputs.append(self.user_input)
        return ' '.join(user_inputs)


async def get_scheme_fsm_bot_response(current_prompt, current_state, current_scheme_conversation_summary, user_input,
                                      db_obj, current_conversation_chunk_id, current_scheme_name, user_id,
                                      bot_preference):
    """Gets response for user's input. It also returns updated prompt and updated conversation """

    if current_prompt == '':
        current_prompt = user_information_extraction_prompt
    end_of_conversation = '\n\"\"\"\n\nFinally,\n\n'
    conversation_history_prefix = "\nConversation History:\n\"\"\""
    prompt = current_prompt + "\nConversation History:\n\"\"\"" + current_scheme_conversation_summary.strip() + "\n\nUser: " + user_input + end_of_conversation + "Bot: "
    prompt = re.sub(r'\n{3,}', '\n\n', prompt)
    output = call_openAI_api(prompt.strip(), max_tokens=1024)

    machine_fsm = scheme_chatbot_fsm(wake_up_state=current_state, current_scheme_name=current_scheme_name,
                                     llm_output=output, user_input=user_input, current_prompt=current_prompt,
                                     current_scheme_conversation_summary=current_scheme_conversation_summary)

    try:
        trigger_condition = get_trigger_event_based_on_llm_output(output)
        machine_fsm.trigger(trigger_condition)
        bot_response = machine_fsm.user_response
        next_prompt_type = machine_fsm.state
        next_prompt = machine_fsm.next_prompt
        scheme_name = machine_fsm.next_scheme_name
        output = machine_fsm.llm_output_logging
        current_scheme_conversation_summary = machine_fsm.current_scheme_conversation_summary
        prompt = machine_fsm.current_prompt + conversation_history_prefix + current_scheme_conversation_summary.strip() + "\n\nUser: " + user_input + end_of_conversation + "Bot: "
        new_conversation_chunk_id = current_conversation_chunk_id
    except:
        bot_response = 'Sorry, I could not understand that information. Please answer in different wording.'
        next_prompt_type = current_state
        next_prompt = current_prompt
        scheme_name = current_scheme_name
        output = output
        current_scheme_conversation_summary = current_scheme_conversation_summary
        new_conversation_chunk_id = current_conversation_chunk_id

    window_size = 19
    current_scheme_conversation_summary = '\nUser:'.join(
        current_scheme_conversation_summary.split('\nUser:')[:window_size])

    current_scheme_conversation_summary = current_scheme_conversation_summary + "\n\nUser: " + user_input + "\nBot: " + bot_response

    if new_conversation_chunk_id == current_conversation_chunk_id and new_conversation_chunk_id != '':
        await db_obj.update_user_prompt_with_new_scheme(new_conversation_chunk_id, scheme_name, next_prompt_type)
    else:
        import uuid
        new_conversation_chunk_id = uuid.uuid4().hex
        await db_obj.insert_user_prompt(chat_id=user_id, conversation_chunk_id=new_conversation_chunk_id,
                                        scheme_name=scheme_name,
                                        created_at=datetime.datetime.now(pytz.UTC),
                                        updated_at=datetime.datetime.now(pytz.UTC),
                                        conversation_summary=current_scheme_conversation_summary,
                                        bot_preference=bot_preference,
                                        prompt_type=next_prompt_type
                                        )
    return bot_response, prompt, new_conversation_chunk_id, scheme_name, current_scheme_conversation_summary, next_prompt_type, next_prompt, output
