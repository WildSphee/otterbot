from typing import Dict, List

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

def call_openai(history: List[Dict[str, str]], query: str, tools: List = []) -> str:
    """
    Call the OpenAI API to generate a response based on chat history and a user query.

    Args:
        history (List[Dict[str, str]]): The conversation history.
        query (str): The user's query.

    Returns:
        str: The generated response from OpenAI.
    """
    messages = history + [
        {"role": "system", "content": query},
    ]

    completion = client.chat.completions.create(
        model="gpt-4o", messages=messages, tools=tools
    )

    res: str = completion.choices[0].message.content
    print(f"LLM output: \n {res}")
    return res
