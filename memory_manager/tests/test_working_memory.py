from memory_manager.working_memory import WorkingMemory


def test_add_remove_and_deduplicate_atoms():
    memory = WorkingMemory()

    memory.add("atom-1")
    memory.add("atom-2")
    memory.add("atom-1")

    assert memory.list() == ["atom-1", "atom-2"]

    memory.remove("atom-1")

    assert memory.list() == ["atom-2"]
