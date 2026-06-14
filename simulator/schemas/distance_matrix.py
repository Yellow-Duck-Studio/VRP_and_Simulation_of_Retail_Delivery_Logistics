from typing import Dict, Tuple, Optional

class DistanceMatrix:
    def __init__(self, data: Dict[Tuple[str, str], float]):
        self._distances = data

    def get_distance(self, from_id: str, to_id: str) -> float:
        key = (from_id, to_id)
        if key in self._distances:
            return self._distances[key]
        key_rev = (to_id, from_id)
        if key_rev in self._distances:
            return self._distances[key_rev]
        raise KeyError(f"The distance between {from_id} and {to_id} was not found")

    @classmethod
    def from_dict(cls, data: Dict[Tuple[str, str], float]) -> "DistanceMatrix":
        return cls(data)