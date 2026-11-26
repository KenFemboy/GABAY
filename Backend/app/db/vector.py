"""Embedding column that is a pgvector ``vector(n)`` on PostgreSQL.

On PostgreSQL the column uses the pgvector extension (enabled by migration
0008), so similarity search runs in SQL with the ``<=>`` cosine-distance
operator. On SQLite (the test database) the same column stores float32 bytes
and search falls back to numpy. Python code always sees ``numpy`` arrays.
"""

import numpy as np
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Float, LargeBinary, bindparam
from sqlalchemy.types import TypeDecorator

# Dimension of the chosen embedding model (docs/decisions/0001-embedding-model.md).
EMBEDDING_DIMS = 384


class EmbeddingVector(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def __init__(self, dims: int) -> None:
        super().__init__()
        self.dims = dims

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(VECTOR(self.dims))
        return dialect.type_descriptor(LargeBinary())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        array = np.asarray(value, dtype=np.float32).reshape(-1)
        if array.shape[0] != self.dims:
            raise ValueError(f"Expected a {self.dims}-dimensional vector, got {array.shape[0]}.")
        if dialect.name == "postgresql":
            return array  # pgvector's bind processor serialises numpy arrays
        return array.tobytes()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return np.asarray(value, dtype=np.float32)
        return np.frombuffer(value, dtype=np.float32)


def cosine_distance(column, query: np.ndarray, dims: int):
    """SQL expression ``column <=> :query`` (PostgreSQL + pgvector only)."""
    param = bindparam("query_vector", value=np.asarray(query, dtype=np.float32), type_=EmbeddingVector(dims))
    return column.op("<=>", return_type=Float)(param)
