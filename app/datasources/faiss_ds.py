import json
import os
from pathlib import Path
from typing import Dict, Iterator, List

import faiss
import numpy as np
import openai
from faiss import read_index

DATASOURCE_PATH = "datasources"

client = openai.OpenAI()


def get_embedding(text, model="text-embedding-ada-002"):
    text = text.replace("\n", " ")
    response = client.embeddings.create(input=[text], model=model)
    embedding: List[float] = response.data[0].embedding
    return np.array(embedding, dtype=np.float32)


def get_embeddings(texts, model="text-embedding-ada-002", batch_size=1000):
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_texts = [text.replace("\n", " ") for text in batch_texts]
        response = client.embeddings.create(input=batch_texts, model=model)
        batch_embeddings = [
            np.array(data.embedding, dtype=np.float32) for data in response.data
        ]
        embeddings.extend(batch_embeddings)
    return embeddings


class FAISSDS:
    """A datasource model that uses FAISS as a vector store with OpenAI embeddings."""

    def __init__(self, index_name):
        super().__init__()
        self.index_name = index_name
        self.documents = []
        self.index = None

        # Read the documents from data.jsonl
        json_name = "meta_data.jsonl"
        jsonpath = os.path.join(DATASOURCE_PATH, self.index_name, json_name)

        with open(jsonpath, "r") as fi:
            self.documents = [json.loads(line) for line in fi]

        # Load the FAISS index
        index_name = "faiss.index"
        index_path = os.path.join(DATASOURCE_PATH, self.index_name, index_name)
        self.index = read_index(index_path)

    def search_request(self, search_query: str, topk: int, skip: int = 0) -> List[Dict]:
        """
        Perform FAISS Similarity Search and return the top k vectors that match the query.

        Args:
            search_query (str): The search query.
            topk (int): The number of top most similar vectors to retrieve.
            skip (int): Number of initial results to skip.

        Returns:
            List[Dict]: The search results with the top k vectors.
        """
        query_embedding = get_embedding(search_query)
        vector = np.array(
            [query_embedding], dtype=np.float32
        )  # FAISS expects a 2D array
        scores, indices = self.index.search(vector, topk + skip)
        hits = []

        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if i < skip:
                continue

            if idx == -1:
                continue  # When not enough docs are returned

            result = self.documents[idx]

            # Process file URL
            file_loc = result.get("file_url", "")
            parts = file_loc.split("/")
            ds_name = parts[0] if len(parts) > 0 else ""
            filename = parts[1] if len(parts) > 1 else ""
            file_url = f"/datasource/{ds_name}/{filename}"

            hit = {
                "id": result["id"],
                "search_key": result["search_key"],
                "content": result["content"],
                "file_url": str(file_url),
                "score": float(score),
            }
            hits.append(hit)

        return hits

    @staticmethod
    def create(section: Iterator[Dict], index_name) -> Dict:
        """
        Create a FAISS index from sections.

        Args:
            section (Iterator[Dict]): An iterator of section dictionaries.

        Returns:
            Dict: A dictionary containing index creation info, e.g., {"index_name": index_name}
        """
        sections = list(section)
        keys = [entry["search_key"] for entry in sections]

        # Create directory for the index
        index_dir = Path(DATASOURCE_PATH) / index_name
        index_dir.mkdir(parents=True, exist_ok=True)

        # Save documents to data.jsonl
        data_jsonl_path = index_dir / "meta_data.jsonl"
        with open(data_jsonl_path, "w") as f:
            for entry in sections:
                json.dump(entry, f)
                f.write("\n")

        # Generate embeddings using OpenAI embeddings (batched)
        embeddings = get_embeddings(keys)
        embeddings = np.vstack(embeddings)

        # Create FAISS index
        embedding_dim = embeddings.shape[1]
        faiss_index = faiss.IndexFlatIP(embedding_dim)
        faiss_index.add(embeddings)

        # Save the FAISS index
        index_path = index_dir / "faiss.index"
        faiss.write_index(faiss_index, str(index_path))

        return {"index_name": index_name}
