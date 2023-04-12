FROM continuumio/anaconda3
WORKDIR /root
COPY ./requirements.txt /root/
RUN apt-get -y update
RUN apt-get -y upgrade
RUN apt-get install -y ffmpeg
RUN pip3 install fastapi
RUN pip3 install pydantic
RUN pip3 install wasabi
RUN pip3 install "uvicorn[standard]"
RUN pip3 install asyncpg
RUN pip3 install -r requirements.txt
RUN apt-get update
COPY ./data /root/data
COPY ./gupshup /root/gupshup
COPY ./models /root/models
COPY ./openai_utility /root/openai_utility
COPY ./a0ae7026506d.json /root/
COPY ./*.py /root/
EXPOSE 8080
COPY script.sh /root/
ENTRYPOINT ["bash","script.sh"]