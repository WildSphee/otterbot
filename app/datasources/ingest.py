import itertools

from app.datasources.faiss_ds import FAISSDS

def ingest() -> str:
    # Combine all section generators
    combined_sections = itertools.chain(sections)

    # create FAISS index
    FAISSDS.create(section=combined_sections, index_name=game_name)
    return datasource_name
