FROM python:3.10-slim

WORKDIR /ILiveHereBot

COPY env /ILiveHereBot/.env
COPY Bot/app.py /ILiveHereBot/app.py
COPY Data /ILiveHereBot/Data
COPY DataSets /ILiveHereBot/DataSets
COPY LLM/answer.py /ILiveHereBot/LLM/answer.py
COPY requirements.txt /ILiveHereBot/requirements.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /ILiveHereBot/requirements.txt

EXPOSE 5000

CMD ["python3", "app.py"]
