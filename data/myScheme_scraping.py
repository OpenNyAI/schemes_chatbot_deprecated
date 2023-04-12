# This code is for scraping the mySchemes website
import copy

from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver
import json
import os

class MySchemeScraper:
    def __init__(self):
        self.myscheme_url = 'https://rules.myscheme.in/'


    def get_scheme_links(self):
        driver = webdriver.Firefox()
        driver.get(self.myscheme_url)

        WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "__next")))
        result_elements = driver.find_element('id', '__next').find_element('tag name', 'tbody').find_elements('tag name', 'tr')
        scheme_links = []
        for result_element in result_elements:
            table_rows = result_element.find_elements('tag name','td')
            result_details_dict={}
            result_details_dict['sr_no'] = table_rows[0].text
            result_details_dict['scheme_name'] = table_rows[1].text.replace('\nCheck Eligibility','')
            result_details_dict['scheme_link'] = table_rows[2].find_element('tag name', 'a').get_attribute('href')
            scheme_links.append(result_details_dict)
        driver.close()
        return scheme_links

    def get_scheme_details(self,scheme_links):
        for scheme in scheme_links:
            driver = webdriver.Firefox()
            driver.get(scheme['scheme_link'])

            WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "__next")))
            scheme['tags'] = [i.text for i in driver.find_element('xpath','/html/body/div/main/div[3]/div[1]/div/div/div[2]/div/div[1]/div[2]/div[1]/div/div[2]/div[1]').find_elements('tag name','div')]
            scheme['details'] = driver.find_element('id', 'details').text
            scheme['benefits'] = driver.find_element('id', 'benefits').text
            scheme['eligibility'] = driver.find_element('id', 'eligibility').text
            scheme['application_process'] = driver.find_element('id', 'applicationProcess').text
            scheme['documents_required'] = driver.find_element('id', 'documentsRequired').text
            driver.close()


    def download(self):
        scheme_links = self.get_scheme_links()
        self.get_scheme_details(scheme_links)
        return scheme_links


    def combine_myscheme_provided_and_scraped_data(self,scraped_scheme_details):
        myscheme_structured_data = json.load(open('myScheme-data.json'))['hits']['hits']
        individual_beneficiary_types = ['Individual', 'Family', 'Sportsperson', 'Journalist']

        myscheme_structured_data = [scheme for scheme in myscheme_structured_data if any([i in individual_beneficiary_types for i in scheme['_source']['targetBeneficiaries']])]

        required_fields_from_structured_data = ['schemeShortTitle','schemeCategory','schemeSubCategory','gender','minority',
                                                'beneficiaryState','residence','caste','disability','occupation',
                                                'maritalStatus','education','age','isStudent','isBpl']

        myscheme_structured_data_dict = {i['_source']['schemeName'].lower().strip():i['_source'] for i in myscheme_structured_data}

        combined_schemes_data = []
        for scheme in scraped_scheme_details:
            structured_info = myscheme_structured_data_dict.get(scheme['scheme_name'].lower().strip())
            if structured_info is not None:
                structured_info = {k: v for k, v in structured_info.items() if k in required_fields_from_structured_data}
                scheme.update(structured_info)
            combined_schemes_data.append(copy.deepcopy(scheme))

        return combined_schemes_data


if __name__=='__main__':
    download_path = os.path.join(os.path.dirname(__file__),'myschemes_scraped_9feb.json')
    scraper = MySchemeScraper()
    scraped_scheme_details = scraper.download()
    json.dump(scraped_scheme_details,open(download_path,'w'))
    #scraped_scheme_details = json.load(open(download_path))
    combined_schemes_data = scraper.combine_myscheme_provided_and_scraped_data(scraped_scheme_details)

    output_path = os.path.join(os.path.dirname(__file__), 'myschemes_scraped_combined_9feb.json')
    json.dump(combined_schemes_data,open(output_path,'w'))
