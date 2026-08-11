import sys

from memory_manager.model_bullshit import ModelBullshit


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]

    with open(input_file, "r", encoding="utf-8") as file:
        text = file.read()

    model = ModelBullshit()
    response = model.ask(text)

    print(response)


if __name__ == "__main__":
    main()
