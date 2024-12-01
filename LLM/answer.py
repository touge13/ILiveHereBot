import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import json
from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from config import GigaChat_API
import requests 
import csv
import chromadb
from config import ADDRESSES_FILE, CLASSIFICATOR_NAME, GIGACHAT_VERSION
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.docstore.document import Document

logging.basicConfig(level=logging.INFO)

model = GigaChat(
    credentials=GigaChat_API,
    scope="GIGACHAT_API_PERS",
    model=GIGACHAT_VERSION, 
    temperature=0.7,
    max_tokens=1000,
    verify_ssl_certs=False
)

message = """
Вопрос пользователя:
{question}

Учитывая все важные аспекты, сгенерируй ответ пользователю, основываясь на следующем контексте:
(ОБЯЗАТЕЛЬНО ИСПОЛЬЗУЙ НОМЕРА ИЗ КОНТЕКСТА И ПРОЧУЮ ДРУГУЮ ИНФОРМАЦИЮ ИЗ КОНТЕКСТА ЕСЛИ ЕСТЬ)
КОНТЕКСТ:
{context}
КОНЕЦ КОНТЕКСТА

Пример структуры ответа:
Здравствуйте!
(тут подробно ответ на вопрос, избегая упоминания источников данных)

Ты — AI помощник, будь внимателен и обеспечь полезный и качественный ответ.
Ответ должен быть вежливым, подробным и профессиональным, с ясными рекомендациями или информацией.
"""

prompt = ChatPromptTemplate.from_messages([("human", message)])

def get_building_id(address): 
    url = "https://geo.hack-it.yazzh.ru/api/v2/geo/buildings/search/" 
    response = requests.get(url, params={"query": address}).json() 
    if response.get("success") and response["data"]: 
        return response["data"][0]["id"]  
    return None 
 
def get_building_details(building_id): 
    url = f"https://geo.hack-it.yazzh.ru/api/v2/geo/buildings/{building_id}" 
    response = requests.get(url).json() 
    if response.get("data"): 
        return response["data"]  
    return None 
 
def get_vehicles_around(latitude, longitude): 
    url = "https://hack-it.yazzh.ru/api/v2/external/dus/get-vehicles-around" 
    response = requests.get(url, params={"latitude": latitude, "longitude": longitude}).json() 
    if response.get("success") and response.get("data"): 
        return response["data"]  
    return [] 
 
def get_dispatcher_phones(building_id, dist): 
    url = f"https://hack-it.yazzh.ru/districts-info/building-id/{building_id}" 
    response = requests.get(url, params={"query": dist}).json()[0] 
    ans = [] 
    for item in response['data']: 
        ans.append(item) 
    return ans 
 
def get_json(input_class: str, user_address) -> str: 
    try: 
        if input_class == 'Благоустройство, ЖКХ и уборка дорог': 
            building_id = get_building_id(user_address) 
            if not building_id: 
                print("Не удалось найти здание по адресу.") 
                return 
            dispatcher_phones = get_dispatcher_phones(building_id, user_address) 
            details = get_building_details(building_id) 
            latitude = details['latitude'] 
            longtitude = details['longitude'] 
            vechicle = get_vehicles_around(latitude, longtitude) 
            vechicle.extend(dispatcher_phones) 
            combined_json_str = json.dumps(vechicle, ensure_ascii=False, indent=4) 
            return combined_json_str 
        elif input_class == 'Поиск контактов, основанный на Базе Контактов Санкт-Петербурга': 
            building_id = get_building_id(user_address) 
            response = requests.get("https://hack-it.yazzh.ru/districts-info/building-id/{building_id}").json()[0] 
            contacts = [] 
            for item in response['data']: 
                contacts.append({ 
                    'name': item['name'], 
                    'phones': item['phones'] 
                }) 
            message = "" 
            for contact in contacts: 
                message += f"Название службы: {contact['name']} \n" 
                message += f"Телефоны: {', '.join(contact['phones'])} \n" 
            item_to_message = contacts.copy() 
            data = { 
                "message": message, 
                "contacts": item_to_message 
            } 
        elif input_class == 'Раздельный сбор мусора': 
            building_id = get_building_id(user_address) 
            if not building_id: 
                print("Не удалось найти здание по адресу.") 
                return 
            details = get_building_details(building_id) 
            latitude = details['latitude'] 
            longtitude = details['longitude'] 
            recycling_response = requests.get( 
                f"https://yazzh.gate.petersburg.ru/api/v2/recycling/map/?category=Все&location_latitude={latitude}&location_longitude={longtitude}&location_radius=3" 
            ).json() 
            data = [] 
            count = 0 # мы оставляем только первые 5 объектов из-за проблем со стороны предоставленного api
            for item in recycling_response['data']:
                if count == 5:
                    break 
                data.append({ 
                    'title': item['title'], 
                    'location': item['location'] 
                })
                count += 1
        else: 
            return "[]"
        return json.dumps(data, ensure_ascii=False) 
    except Exception as e: 
        logging.error(f"Ошибка при получении JSON: {e}") 
        return "[]"

class typeDefiner():
    def __init__(self):
        client = chromadb.Client()
        embeddings = HuggingFaceEmbeddings(model_name=CLASSIFICATOR_NAME)
        self.vector_store_themes = Chroma(embedding_function=embeddings)
        self.vector_store_themes.add_documents([Document('Поиск контактов, основанный на Базе Контактов Санкт-Петербурга'), 
                                        Document('Раздельный сбор мусора'), 
                                        Document('Благоустройство, ЖКХ и уборка дорог'),
                                        ])
    def define_type(self, query: str):
        self.retriever_2 = self.vector_store_themes.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 1})
        return self.retriever_2.invoke(query)[0].page_content

def find_address_by_user_id(user_id: int) -> str:
    try:
        with open(ADDRESSES_FILE, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)
            for row in reader:
                if int(row[0]) == user_id:
                    return row[2]  
        return "Адрес не найден."
    except FileNotFoundError:
        return "CSV-файл не найден."
    except Exception as e:
        return f"Произошла ошибка: {e}"

def generate_response(question: str, user_context: str, user_id) -> str:
    try:
        definer = typeDefiner()
        class_question = definer.define_type(question)
        user_address = find_address_by_user_id(user_id)
        json_context = get_json(class_question, user_address=user_address)
        rag_chain = {"context": RunnablePassthrough(), "question": RunnablePassthrough()} | prompt | model
        response = rag_chain.invoke({
            "вопрос пользователя:": question,
            "json файл, по которому ты должен составить ответ пользователю:": json_context,
            "текущий контекст": user_context
        })
        return response.content
    except Exception as e:
        logging.error(f"Ошибка при обращении к GigaChat: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."
