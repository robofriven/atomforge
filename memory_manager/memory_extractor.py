from memory_manager.model_bullshit import ModelBullshit


class MemoryExtractor:
    def extract(self, text: str):
        model = ModelBullshit()


        instructions = f""" You are a memory extractor. You will be given a text and you will extract teh relevant facts/preferences/events from it. You will then determine if they are worth remembering and why. You will also provide a confidence level and an importance level for each fact/preference/event. You will return the extracted facts/preferences/events. Here is your text: {text}"""

        
        model.ask(instructions)

        """
            1. Take in the response
            2. Ask the Model
                a. What facts/preferences/events are present
                b. Are they worth remembering and why?
                c. Confidence
                d. Importance
            """
