import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler

load_dotenv()

# Initialize Langfuse handler (automatically picks up credentials from .env)
langfuse_handler = CallbackHandler()

# Initialize the chat model with Langfuse tracing
llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "Qwen 3.8 27B"),
    temperature=0.7,
    max_completion_tokens=256,
    callbacks=[langfuse_handler],
)

# Run inference (traces are automatically captured)
response = llm.invoke("Explain quantum computing in one sentence.")
print(response.content)

# Flush any background traces to the local Langfuse server before exit
get_client().flush()
