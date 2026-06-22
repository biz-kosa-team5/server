from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Neighbor:
  index: int
  score: float


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
  if not left or not right:
    return 0.0
  if len(left) != len(right):
    raise ValueError("Vectors must have the same dimensions")

  dot_product = sum(a * b for a, b in zip(left, right, strict=True))
  left_norm = math.sqrt(sum(value * value for value in left))
  right_norm = math.sqrt(sum(value * value for value in right))
  if left_norm == 0.0 or right_norm == 0.0:
    return 0.0
  return dot_product / (left_norm * right_norm)


def top_k_nearest_neighbors(
  query: Sequence[float],
  vectors: Sequence[Sequence[float]],
  k: int,
) -> list[Neighbor]:
  if k <= 0 or not vectors:
    return []

  neighbors = [
    Neighbor(index=index, score=cosine_similarity(query, vector))
    for index, vector in enumerate(vectors)
  ]
  return sorted(neighbors, key=lambda neighbor: (-neighbor.score, neighbor.index))[:k]
