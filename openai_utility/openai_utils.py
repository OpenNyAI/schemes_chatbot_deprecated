import os
import sys

import openai


def call_openAI_api(prompt, max_tokens=256,temperature=0):
    if os.getenv('OPENAI_API_KEY') is None:
        sys.exit('Missing OpenAI API key in environment variable "OPENAPI_KEY"')
    if os.getenv('OPEN_AI_MODEL') is None:
        sys.exit('Missing OpenAI model name in environment variable "OPEN_AI_MODEL"')
    openai.api_key = os.getenv('OPENAI_API_KEY')
    model_engine = os.getenv('OPEN_AI_MODEL')
    retry_limit = 2
    response_success = False
    response = "Because Server is overloaded, I am unable to answer you at the moment. Please retry."
    while retry_limit>0 and response_success == False:
        try:
            completions = openai.Completion.create(engine=model_engine, prompt=prompt,
                                                   max_tokens=max_tokens, n=1, stop=None, temperature=temperature, user="1",timeout=120)
            response = completions.choices[0].text
            response_success = True
        except:
            response_success = False
            retry_limit-=1

    return response

def call_chatgpt_api(messages, max_tokens=128,temperature=0):
    if os.getenv('OPENAI_API_KEY') is None:
        sys.exit('Missing OpenAI API key in environment variable "OPENAPI_KEY"')
    if os.getenv('OPEN_AI_MODEL') is None:
        sys.exit('Missing OpenAI model name in environment variable "OPEN_AI_MODEL"')
    openai.api_key = os.getenv('OPENAI_API_KEY')
    model_engine = 'gpt-3.5-turbo'

    try:
        completions = openai.ChatCompletion.create(model=model_engine, messages=messages,
                                               max_tokens=max_tokens, n=1, stop=None, temperature=temperature, user="1")
        response = completions.choices[0].message.content
    except:
        response = "Because Server is overloaded, I am unable to answer you at the moment. Please retry."
    return response