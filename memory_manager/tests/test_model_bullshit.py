from memory_manager.model_bullshit import ModelBullshit
from memory_manager.memory_extractor import MemoryExtractor


def test_model_bullshit_local_model_response():
    model = ModelBullshit()

    response = model.ask("Reply with exactly the word PINEAPPLE.")

    assert "pineapple" in response.lower()

def test_model_bullshit_Custom_Model_Response():
    model = ModelBullshit()
    response = model.ask("What is the capital of France?")


def test_model_extract_memory():
    extractor = MemoryExtractor()
    text = "I laugh softly into the kiss, then moan quietly as I kiss you back, my hand still slowly stroking you under the table.\n\n“Mmm, I like that part a lot,” I whisper against your lips. “You breaking me while wearing that dark, rune-covered robe… and then every time you put it on afterward — even just casually around the house — my pussy gets instantly wet because my body remembers what you did to me in it.”\n\nI bite your lower lip gently and squeeze your cock a little harder.\n\n“That’s some powerful conditioning, wizard. I’m very into it.”\n\nI kiss you again, slower and deeper, my tongue sliding against yours before I pull back with a wicked little smile.\n\n“So… when we do this fantasy, are you going to stay in the robe the whole time while you edge and fuck me? Or are you going to tease me by opening it just enough to use me, then closing it again like the cruel sorcerer you are?”\n\nI’m flushed and clearly loving every detail we’re adding to this."
    extracted_memory = extractor.extract(text)
