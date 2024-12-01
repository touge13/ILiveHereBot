import pandas as pd
import csv

def parse_contacts_to_csv(input_file: str, output_file: str):
    df = pd.read_excel(input_file, header=0)
    df['id'] = df['id'].astype(str)
    if 'phones' in df.columns:
        df['phones'] = df['phones'].str.replace(r'[{}]', '', regex=True)
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL)
parse_contacts_to_csv("contacts.xlsx", "contacts.csv")

def parse_questions_to_csv_no_headers(input_file, output_file):
    df = pd.read_excel(input_file)
    parsed_data = []
    for index, row in df.iterrows():
        for column in df.columns[1:]:
            if pd.notna(row[column]):
                question_block = row[column].split("Ответ:")
                if len(question_block) == 2:
                    question = question_block[0].strip()
                    answer_format, full_answer = question_block[1].strip().split("\n", 1)
                    parsed_data.append({
                        "type_question": column.strip(),
                        "question": question,
                        "format_answer": answer_format.strip(),
                        "full_answer": full_answer.strip()
                    })
    parsed_df = pd.DataFrame(parsed_data)
    parsed_df.to_csv(output_file, index=False, encoding='utf-8-sig')

input_file = "questions.xlsx"
output_file = "questions.csv"
# parse_questions_to_csv_no_headers(input_file, output_file)
