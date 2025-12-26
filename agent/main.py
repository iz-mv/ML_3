import os
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain.agents import create_agent

from langfuse.langchain import CallbackHandler
from tools import today_date, estimate_trip_cost


SYSTEM_PROMPT = (
    "You are a helpful AI agent. "
    "Use tools when they help. "
    "If you are not sure about a fact, say you are not sure. "
    "Keep answers short and clear."
)


def main() -> None:
    load_dotenv()

    handler = CallbackHandler()

    llm = ChatOllama(
        model=os.getenv("MODEL_NAME", "llama3.2"),
        temperature=float(os.getenv("TEMPERATURE", "0")),
    )

    agent = create_agent(
        model=llm,
        tools=[today_date, estimate_trip_cost],
        system_prompt=SYSTEM_PROMPT,
    )

    print("Agent is running. Type 'exit' to stop.")

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break

        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"callbacks": [handler]},
        )

        messages = result.get("messages", [])
        if messages:
            last_msg = messages[-1]
            final = getattr(last_msg, "content", str(last_msg))
        else:
            final = str(result)

        print(f"Agent: {final}")


if __name__ == "__main__":
    main()
