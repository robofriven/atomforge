from dataclasses import dataclass, field


@dataclass
class WorkingMemory:
    atom_ids: set[str] = field(default_factory=set)

    def add(self, atom_id: str) -> None:
        self.atom_ids.add(atom_id)

    def remove(self, atom_id: str) -> None:
        self.atom_ids.discard(atom_id)

    def list(self) -> list[str]:
        return sorted(self.atom_ids)
