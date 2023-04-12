from database import PostgresDatabase
import re

async def load_specific_scheme_prompt(interested_scheme_name, scheme_chatbot_prompt, engine) -> (str, str):
    """
    Returns the details of the input specific scheme which can be used as prompt for that scheme
    """
    db_obj = PostgresDatabase(engine)
    interested_scheme_details = await db_obj.get_specific_scheme_details(scheme_name=interested_scheme_name)
    if interested_scheme_details:
        prompt = scheme_chatbot_prompt
        if interested_scheme_details['eligibility_criteria'] != '':
            eligibility = interested_scheme_details['eligibility_criteria']
            prompt = prompt + 'Scheme Name: ' + interested_scheme_name + "\n Start of scheme details\nEligibility:\n" + eligibility

        if interested_scheme_details['documents_required'] != '':
            documents = interested_scheme_details['documents_required']
            prompt = prompt + "Documents Required:\n" + documents + '\n\n'

        summary = interested_scheme_details['summary']

        prompt = prompt + '\n End of scheme details.\n\n'
    else:
        prompt = 'Not Found'
        summary = 'Not Found'
    return prompt, summary


def mask_sensitive_info(user_input):
    # Regular expressions to match Aadhaar card number, bank account number, IFSC code, and address
    aadhaar_regex = re.compile(r'\d{4}\s\d{4}\s\d{4}')
    aadhaar_regex2 = re.compile(r'\d{12}')
    bank_regex = re.compile(r'[A-Za-z]{4}\d{7}')
    ifsc_regex = re.compile(r'[A-Z]{4}\d{7}')
    # address_regex = re.compile(r'\d{1,3}\s\w+\s\w+')
    # Mask the sensitive information with 'X' characters
    user_input = aadhaar_regex.sub('XXXX XXXX XXXX', user_input)
    user_input = aadhaar_regex2.sub('XXXXXXXXXXXX', user_input)
    user_input = bank_regex.sub('XXXXXXX', user_input)
    user_input = ifsc_regex.sub('XXXXXXX', user_input)
    # user_input = address_regex.sub('XXX XXX', user_input)
    # Return the masked string
    return user_input