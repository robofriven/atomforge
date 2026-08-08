class MemoryExtractor:
    def extract(self, text: str):
        ...
        """
            1. Take in the response
            2. Ask the Model
                a. What facts/preferences/events are present
                b. Are they worth remembering and why?
                c. Confidence
                d. Importance
            """
