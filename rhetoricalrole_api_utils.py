import json
import urllib
from typing import Union

from fastapi import HTTPException
from pydantic import BaseModel
from wasabi import msg

from api_utils import check_api_health
from api_utils import check_indiankanoon_url, IndiaKannonScrape, get_sha, get_ik_html


class Data(BaseModel):
    text: str
    preamble_text: str
    judgement_text: str


class Value(BaseModel):
    id: int
    end: int
    text: str
    start: int
    labels: list[str]


class Result(BaseModel):
    value: Value


class Annotations(BaseModel):
    result: list[Result]


class RhetoricalRoleInput(BaseModel):
    judgement_text: Union[str, None]
    indiakannon_url: Union[str, None]


class RhetoricalRoleOutput(BaseModel):
    id: str
    data: Data
    annotations: list[Annotations]


rhetorical_role_responses = \
    {418: {"description": "Error from Indiakannon scrapper"},
     419: {"description": "API not ready"},
     420: {"description": "Authentication token not passed"},
     421: {"description": "Token reached maximum usability, contact support!!"},
     403: {"description": "Wrong Inference token, Please provide valid token to use service"},
     423: {"description": "Missing text in input for processing"},
     424: {"description": "Judgement too big to process"},
     425: {"description": "No valid input passed"}
     }

remote_api_legacy_error_code_dict = {515: 424, 516: 423, 520: 421, 519: 403}


def check_rhetoricalrole_request_validity(data: RhetoricalRoleInput):
    judgement_text = data.judgement_text
    indiakannon_url = data.indiakannon_url
    if judgement_text is None and indiakannon_url is None:
        raise HTTPException(detail="No valid input passed", status_code=425)


def get_response_from_remote_rhetoricalrole_api(body):
    if not check_api_health():
        msg.fail("API not ready: 419")
        raise HTTPException(detail="API not ready", status_code=419)
    rr_api_url = f'http://35.202.36.80:8080/predictions/RhetorcalRolePredictor/'
    req = urllib.request.Request(rr_api_url)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    jsondata = json.dumps(body)
    jsondataasbytes = jsondata.encode('utf-8')
    try:
        response = urllib.request.urlopen(req, jsondataasbytes).read()
        json_data = json.loads(response)
        return json_data
    except urllib.error.URLError as e:
        error_code = e.code
        error_code = remote_api_legacy_error_code_dict[error_code]
        detail = rhetorical_role_responses[error_code]['description']
        msg.fail(f"RhetoricalRole: Error {detail}:{error_code}")
        raise HTTPException(detail=detail, status_code=error_code)


def process_rhetorical_role_request(data: RhetoricalRoleInput, db_obj, api_key):
    RECIEVED_FROM_CACHE = False
    judgement_text = data.judgement_text
    indiakannon_url = data.indiakannon_url
    inference_token = api_key
    if indiakannon_url is not None and check_indiankanoon_url(indiakannon_url):
        if indiakannon_url[-1] == '/':
            indiakannon_url = indiakannon_url[:-1]
        # check cache for Rhetorical Role result for a doc
        result_from_db = db_obj.fetch(indiakanoon_url=indiakannon_url)
        if result_from_db:
            if result_from_db[0][4]:
                RECIEVED_FROM_CACHE = True
                sha = result_from_db[0][1]
                response = result_from_db[0][4]
                msg.info(f"RhetoricalRole: Fetched from cache")
                if response[0].get('api_call') is not None:
                    response[0].pop('api_call')
                if response[0].get('inference_token') is not None:
                    response[0].pop('inference_token')
                return sha, response
        if not result_from_db or not result_from_db[0][4]:
            tid = indiakannon_url.split('/')[-1]
            fetched_html, error_code_ik = get_ik_html(indiakannon_url, tid)
            if fetched_html is not None:
                judgement_text = IndiaKannonScrape(fetched_html)
                sha = get_sha(judgement_text)
                result_from_db = db_obj.fetch(judgement_sha=sha)
                if result_from_db:
                    if result_from_db[0][4]:
                        RECIEVED_FROM_CACHE = True
                        response = result_from_db[0][4]
                        msg.info(f"RhetoricalRole: Fetched from cache")
                        if response[0].get('api_call') is not None:
                            response[0].pop('api_call')
                        if response[0].get('inference_token') is not None:
                            response[0].pop('inference_token')
                        return sha, response
            else:
                if error_code_ik is not None:
                    msg.fail(f"Error from SCRAPPER CODE: {error_code_ik}")
                else:
                    msg.fail("Error from SCRAPPER CODE")
                raise HTTPException(detail="Error from Indiakannon scrapper", status_code=418)
    elif judgement_text:
        sha = get_sha(judgement_text)
        result_from_db = db_obj.fetch(judgement_sha=sha)
        if result_from_db:
            if result_from_db[0][4]:
                RECIEVED_FROM_CACHE = True
                response = result_from_db[0][4]
                msg.info(f"RhetoricalRole: Fetched from cache")
                if response[0].get('api_call') is not None:
                    response[0].pop('api_call')
                if response[0].get('inference_token') is not None:
                    response[0].pop('inference_token')
                return sha, response

    if not RECIEVED_FROM_CACHE:
        sha = get_sha(judgement_text)
        response = get_response_from_remote_rhetoricalrole_api(
            {'text': judgement_text, 'inference_token': inference_token})
        result_from_db = db_obj.fetch(judgement_sha=sha)
        if not result_from_db:
            db_obj.insert(indiakanoon_url=indiakannon_url, judgement_sha=sha)
        msg.info("RhetoricalRole: Added new judgement to cache")
        db_obj.update(json_data=response, column_name='rhetorical_role_result', indiakanoon_url=None,
                      judgement_sha=sha)
        if response[0].get('api_call') is not None:
            response[0].pop('api_call')
        if response[0].get('inference_token') is not None:
            response[0].pop('inference_token')
        return sha, response
