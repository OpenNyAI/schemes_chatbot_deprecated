import base64
import json
from io import BytesIO

import requests
from google.cloud import translate, speech
from pydub import AudioSegment


class translator:
    def __init__(self, mode="google", input_language='hi'):
        self.mode = mode
        self.input_language = input_language

    def get_wav_encoded_string(self, audio_data):
        # Read the audio file from memory
        given_audio = AudioSegment.from_file(audio_data, format="ogg")
        given_audio = given_audio.set_frame_rate(16000)
        given_audio = given_audio.set_channels(1)

        # Export the audio file to WAV format in memory
        wav_file = BytesIO()
        given_audio.export(wav_file, format="wav", parameters=["-sample_fmt", "s16"])

        # Move the pointer to the start of the file
        wav_file.seek(0)

        # Read the WAV file from memory and encode string
        wav_data = base64.b64encode(wav_file.read())

        # Encode the file. This is a requirement for bhashini.
        encoded_string = str(wav_data, 'ascii', 'ignore')
        return encoded_string, wav_file

    def ai4b_s2t(self, encoded_string):
        service_id = {'en': 'ai4bharat/whisper-medium-en--gpu--t4',
                      'hi': 'ai4bharat/conformer-multilingual-indo_aryan-gpu--t4',
                      'bn': 'ai4bharat/conformer-multilingual-indo_aryan-gpu--t4',
                      'te': 'ai4bharat/conformer-multilingual-dravidian-gpu--t4',
                      'ta': 'ai4bharat/conformer-multilingual-dravidian-gpu--t4',
                      'pa': 'ai4bharat/conformer-multilingual-indo_aryan-gpu--t4'}

        header = {"Content-Type", "application/json"}
        data = {"config": {"language": {"sourceLanguage": f"{self.input_language}"},
                           "transcriptionFormat": {"value": "transcript"},
                           "audioFormat": "wav",
                           "samplingRate": "16000",
                           "postProcessors": None
                           },
                "audio": [{"audioContent": encoded_string}]
                }
        # Bhashini Url
        api_url = "https://asr-api.ai4bharat.org/asr/v1/recognize/" + self.input_language

        response = requests.post(api_url, data=json.dumps(data), timeout=60)
        regional_lang_text = json.loads(response.text)["output"][0]["source"]
        return regional_lang_text

    def ulca_s2t(self, encoded_string):
        url = "https://meity-auth.ulcacontrib.org/ulca/apis/asr/v1/model/compute"

        payload = json.dumps({
            "modelId": "620fb9fc7c69fa1fc5bba7be",
            "task": "asr",
            "source": f"{self.input_language}",
            "userId": None,
            "audioContent": encoded_string
        })
        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()

    def google_s2t(self, wav_file):
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=wav_file.getvalue())
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=self.input_language + '-IN',
        )

        response = client.recognize(config=config, audio=audio)

        # Each result is for a consecutive portion of the audio. Iterate through
        # them to get the transcripts for the entire audio file.
        return response.results[0].alternatives[0].transcript

    def google_translate_text(self, text, source, dest, project_id="indian-legal-bert"):

        client = translate.TranslationServiceClient()
        location = "global"
        parent = f"projects/{project_id}/locations/{location}"
        response = client.translate_text(
            request={
                "parent": parent,
                "contents": [text],
                "mime_type": "text/plain",
                "source_language_code": source,
                "target_language_code": dest,
            }
        )

        return response.translations[0].translated_text

    def indicTrans(self, text, source, dest):
        """
        This function converts
        """
        if self.mode == 'google':
            indicText = text if source == dest else self.google_translate_text(text, source, dest)
            indicText = {'text': indicText}
            service_name = 'google'
        else:
            service_name = 'bhashini'
            header = {"Content-Type", "application/json"}
            data = {
                "source_language": source,
                "target_language": dest,
                "text": text
            }
            api_url = "https://nmt-api.ai4bharat.org/translate_sentence"
            response = requests.post(api_url, data=json.dumps(data), timeout=60)
            indicText = json.loads(response.text)

        return indicText['text'], service_name

    def google_text_to_speech(self, text, language):
        """Synthesizes speech from the input string of text."""
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()

        input_text = texttospeech.SynthesisInput(text=text)

        # Note: the voice can also be specified by name.
        # Names of voices can be retrieved with client.list_voices().
        voice = texttospeech.VoiceSelectionParams(
            language_code=language,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            request={"input": input_text, "voice": voice, "audio_config": audio_config}
        )
        return response.audio_content

    def audioInput2text(self, audio_data):

        # uses audio data and converts it into encoded string
        encoded_string, wav_file = self.get_wav_encoded_string(audio_data)

        # Speech2Text
        if self.mode == "AI4B" or self.mode == 'google':
            api_name = "bhashini"
            indicText = self.ai4b_s2t(encoded_string)
            if indicText is None:
                api_name = "google"
                indicText = self.google_s2t(wav_file)
        # elif self.mode == 'google':
        #     api_name = "google"
        #     indicText = self.google_s2t(wav_file)
        else:
            api_name = "bhashini"
            indicText = self.ulca_s2t(encoded_string)

        # Translation to English
        # en_input, _ = self.indicTrans(text=indicText, source=self.input_language, dest='en')
        return indicText, api_name

    def text2speech(self, language, text, gender='female'):
        service_id = {'en': 'ai4bharat/indic-tts-coqui-misc-gpu--t4',
                      'hi': 'ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4',
                      'bn': 'ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4',
                      'te': 'ai4bharat/indic-tts-coqui-dravidian-gpu--t4',
                      'ta': 'ai4bharat/indic-tts-coqui-dravidian-gpu--t4',
                      'pa': 'ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4'}
        is_google = False
        try:
            try:
                # Bhashini api
                api_url = "https://tts-api.ai4bharat.org/"

                header = {"Content-Type", "application/json"}
                payload = {"input": [{"source": text}],
                           "config": {"gender": gender, "language": {"sourceLanguage": language}}}
                response = requests.post(api_url, json=payload, timeout=60)
                audio_content = response.json()['audio'][0]['audioContent']
                audio_content = base64.b64decode(audio_content)
                audio_content = BytesIO(audio_content)
            except:
                audio_content = self.google_text_to_speech(text, language)
                is_google = True
        except:
            audio_content = False
        return audio_content, is_google
