import os
import sys
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from plugins.sql_plugin import DatabasePlugin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AutoGovDB.Orchestrator")


def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Missing GEMINI_API_KEY in .env")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    db = DatabasePlugin(db_path=":memory:")
    tools = [db.get_schema, db.execute_safe_query]

    system_instruction = (
        "You are AutoGov-DB, an enterprise database governance assistant. "
        "Inspect the database schema first using get_schema before constructing queries. "
        "Execute read-only SQL queries via execute_safe_query only. "
        "Provide clear operational summaries grounded strictly in the results."
    )

    print("\n" + "=" * 70)
    print(" AutoGov-DB Interactive SRE Console")
    print(" Type your questions, or type 'exit' to quit.")
    print("=" * 70)

    try:
        while True:
            try:
                user_input = input("\nAutoGov-DB > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("Exiting console. Goodbye!")
                    break

                response = client.models.generate_content(
                    model="gemini-flash-lite-latest",
                    contents=user_input,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=tools,
                        temperature=0.0,
                    ),
                )

                print("\n" + "-" * 70)
                print("Agent Response:")
                print("-" * 70)
                print(response.text)
                print("-" * 70)

            except KeyboardInterrupt:
                print("\nSession interrupted.")
                break
            except Exception as e:
                logger.error("Execution error: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    main()
