"""Generate or refresh embeddings for all active goals.

    python -m app.scripts.reindex_goals

Safe to run any number of times: unchanged goals are skipped and no duplicate
vectors are created. The first run downloads the embedding model (~220 MB).
"""

import logging

from app.services.embedding_service import get_embedder, index_status, reindex


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from app.db.session import SessionLocal

    embedder = get_embedder()
    with SessionLocal() as db:
        result = reindex(db, embedder)
        status = index_status(db, embedder.model)
    print(
        f"created {result['created']}, updated {result['updated']}, unchanged {result['unchanged']}, "
        f"removed {result['removed']} - {status.indexed}/{status.active_goals} active goals indexed "
        f"({status.model})"
    )


if __name__ == "__main__":
    main()
