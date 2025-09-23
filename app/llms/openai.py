from typing import Dict, List, Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


def chat(messages: List[Dict[str, str]], model: str = "gpt-4o", tools: Optional[List] = None) -> str:
    """
    Minimal helper for Chat Completions.
    messages: list of {"role": "system"|"user"|"assistant", "content": "..."}
    """
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or [],
        temperature=0.2,
    )
    res: str = completion.choices[0].message.content or ""
    print(f"LLM output:\n{res}")
    return res


# Backward compatibility with your previous function signature
def call_openai(history: List[Dict[str, str]], query: str, tools: List = []) -> str:
    """
    Legacy shim. Interprets 'query' as a USER message appended after 'history'.
    """
    messages = history + [{"role": "user", "content": query}]
    return chat(messages=messages, tools=tools)
