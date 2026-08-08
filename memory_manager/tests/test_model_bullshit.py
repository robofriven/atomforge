from memory_manager.model_bullshit import ModelBullshit


def test_model_bullshit_local_model_response():
    model = ModelBullshit()

    response = model.ask("Reply with exactly the word PINEAPPLE.")

    assert "pineapple" in response.lower()
