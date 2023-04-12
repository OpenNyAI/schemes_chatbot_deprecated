from langchain.vectorstores.faiss import FAISS
from langchain.docstore.document import Document
import pickle
from langchain.embeddings.openai import OpenAIEmbeddings
import json
from openai_utils import call_chatgpt_api
from dotenv import load_dotenv
from tqdm import tqdm
load_dotenv()


def create_scheme_embeddings(scheme_data):
    max_characters = 8000 * 4  #### max token limit for OpenAI is 8191 and roughly 4 characters per token
    scheme_summaries = []
    for scheme in scheme_data:
        scheme_summary = scheme['scheme_name'] + '\n' + scheme['details'] + '\n' + scheme['eligibility']
        if len(scheme_summary) > max_characters:
            print('Summarized ' + scheme['scheme_name'])
            scheme_summary_prompt = 'Summarize the text below in less than 6000 words: \n\n' + scheme['details']
            scheme_summary = scheme['scheme_name'] + '\n' + call_openAI_api(scheme_summary_prompt)
        scheme_summaries.append(Document(page_content=scheme_summary, metadata={"source": scheme['scheme_name']}))

    with open("../data/scheme_indices_eligibility.pickle", "wb") as f:
        pickle.dump(FAISS.from_documents(scheme_summaries, OpenAIEmbeddings()), f)

def create_scheme_summary(scheme_data):
    max_characters = 4000 * 4  #### max token limit for OpenAI is 4096 and roughly 4 characters per token
    for scheme in tqdm(scheme_data):
        if scheme.get('summary') is None or scheme.get('summary') == 'Because Server is overloaded, I am unable to answer you at the moment. Please retry.':
            scheme_info = scheme['scheme_name'] + '\n' + scheme['details'] + '\n' + scheme['benefits']
            if scheme.get('original_eligibility'):
                scheme_info = scheme_info + '\n' + scheme['original_eligibility']
            if len(scheme_info) > max_characters:
                scheme_info = scheme_info[:max_characters] ## truncate long scheme informations

            scheme_summary_prompt = 'Create summary of following text in 2 lines. Summary should cover target audience of scheme and benefits. it is important to be factually correct and only use the information given below.\n\n' + scheme_info
            try:
                scheme_summary = call_chatgpt_api(scheme_summary_prompt).strip()
            except:
                scheme_summary = ''
            scheme['summary'] = scheme_summary

if __name__=="__main__":
    data = json.load(open('myschemes_scraped_combined.json'))
    create_scheme_summary(data)
    json.dump(data,open('myschemes_scraped_combined.json','w'))