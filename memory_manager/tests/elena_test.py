import sys
from pathlib import Path

from memory_manager.model_bullshit import ModelBullshit


EXTRACTION_PROMPT = """
You are analyzing a long roleplay conversation for a memory-management system.

Your task is to extract information that would be useful to remember later.

Do NOT:
- continue the roleplay
- reply to either participant
- write in character
- summarize every message
- preserve repetitive sexual/action narration merely because it appears often
- invent facts that are not supported by the conversation

Do extract potentially memorable information such as:
- people, identities, and relationships
- important personal facts
- preferences, dislikes, habits, and recurring behaviors
- meaningful events and experiences
- goals, plans, promises, decisions, and unresolved issues
- changes in relationships, beliefs, intentions, or circumstances
- locations and other persistent contextual facts
- emotionally significant information when it may affect future interactions

Prefer recall over aggressive filtering for this test.
If something might plausibly matter later, include it.
Extract everything that could support a future callback. Do not decide that jokes, anecdotes, one-off events, nicknames, shared phrases, embarrassing stories, or minor experiences are unimportant.

For each memory, output one line in this format:

MEMORY: <concise standalone statement>

The statement should make sense without needing the surrounding conversation.
Do not add commentary before or after the memory list.

CONVERSATION:
"""


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <input_file>")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    with input_path.open("r", encoding="utf-8") as file:
        text = file.read()

    prompt = EXTRACTION_PROMPT + "\n" + text

    model = ModelBullshit()
    response = model.ask(prompt)

    safe_model_name = model.model.replace("/", "_").replace(":", "_")

    output_path = input_path.with_name(
        f"{input_path.stem}_{safe_model_name}_memories.txt"
    )

    output_path.write_text(response, encoding="utf-8")
    print(response)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
