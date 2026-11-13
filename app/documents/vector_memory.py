"""NEXUS AI - Persistent Document Vector Memory & Hybrid Search.
Stores document embeddings in local ChromaDB (0 MB VRAM) and catalog metadata in SQLite.
Enables grounded Q&A with specific source, page number, and chunk citations.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from app.documents.parser_extractor import parse_document

DEFAULT_VECTOR_DB_PATH = Path("./workspace/memory/doc_vectors")
DEFAULT_CATALOG_DB_PATH = Path("./workspace/memory/doc_catalog.db")


class DocumentVectorMemory:
    """Zero-GPU Vector Memory managing ChromaDB vector index and SQLite relational catalog."""

    def __init__(
        self,
        vector_db_path: Path = DEFAULT_VECTOR_DB_PATH,
        catalog_db_path: Path = DEFAULT_CATALOG_DB_PATH,
    ):
        self.vector_db_path = Path(vector_db_path)
        self.catalog_db_path = Path(catalog_db_path)

        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        self.catalog_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB persistent client (local on disk)
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.vector_db_path.resolve()),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="nexus_documents",
            metadata={"description": "NEXUS AI Document Intelligence Chunks"},
        )

        self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialize the SQLite document catalog schema."""
        with sqlite3.connect(str(self.catalog_db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    file_name TEXT,
                    file_path TEXT UNIQUE,
                    file_size INTEGER,
                    extension TEXT,
                    page_count INTEGER,
                    word_count INTEGER,
                    sha256_hash TEXT,
                    category TEXT,
                    tags TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    page_number INTEGER,
                    chunk_index INTEGER,
                    content TEXT,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
                )
            """)
            conn.commit()

    def chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        """Split text into overlapping chunks without breaking mid-word when possible."""
        words = text.split()
        if not words:
            return []

        chunks = []
        i = 0
        while i < len(words):
            chunk_words = words[i : i + chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + chunk_size >= len(words):
                break
            i += max(1, chunk_size - overlap)
        return chunks

    def ingest_document(
        self,
        file_path: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Parse, catalog, chunk, and embed a document into ChromaDB and SQLite."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        parsed = parse_document(str(path))
        doc_id = str(uuid.uuid4())
        tag_str = ",".join(tags) if tags else ""

        # Compute hash
        import hashlib
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()

        # Update SQLite catalog
        with sqlite3.connect(str(self.catalog_db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (doc_id, file_name, file_path, file_size, extension, page_count, word_count, sha256_hash, category, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                path.name,
                str(path.resolve()),
                parsed["metadata"].get("file_size", 0),
                parsed["metadata"].get("extension", ""),
                parsed["metadata"].get("page_count", len(parsed["pages"])),
                parsed["word_count"],
                file_hash,
                category,
                tag_str,
            ))
            conn.commit()

        # Chunk and push into ChromaDB
        all_chunk_ids = []
        all_chunks = []
        all_metadatas = []

        chunk_counter = 0
        with sqlite3.connect(str(self.catalog_db_path)) as conn:
            cursor = conn.cursor()
            for page in parsed["pages"]:
                p_num = page["page_number"]
                p_chunks = self.chunk_text(page["text"])
                for p_idx, text_chunk in enumerate(p_chunks):
                    if not text_chunk.strip():
                        continue
                    chunk_id = f"{doc_id}_c{chunk_counter}"
                    all_chunk_ids.append(chunk_id)
                    all_chunks.append(text_chunk)
                    all_metadatas.append({
                        "doc_id": doc_id,
                        "file_name": path.name,
                        "file_path": str(path.resolve()),
                        "page_number": p_num,
                        "chunk_index": p_idx,
                        "category": category,
                    })
                    cursor.execute("""
                        INSERT INTO chunks (chunk_id, doc_id, page_number, chunk_index, content)
                        VALUES (?, ?, ?, ?, ?)
                    """, (chunk_id, doc_id, p_num, p_idx, text_chunk))
                    chunk_counter += 1
            conn.commit()

        if all_chunks:
            # Batch upsert to ChromaDB
            self.collection.upsert(
                ids=all_chunk_ids,
                documents=all_chunks,
                metadatas=all_metadatas,
            )

        return {
            "doc_id": doc_id,
            "file_name": path.name,
            "total_chunks": len(all_chunks),
            "word_count": parsed["word_count"],
            "category": category,
            "hash": file_hash,
        }

    def batch_ingest_directory(
        self,
        dir_path: str,
        category: str = "general",
        recursive: bool = True,
    ) -> List[Dict[str, Any]]:
        """Batch ingest all supported documents in a folder."""
        folder = Path(dir_path)
        if not folder.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        supported_exts = {".pdf", ".docx", ".xlsx", ".csv", ".pptx", ".md", ".txt"}
        pattern = "**/*" if recursive else "*"
        results = []

        for p in folder.glob(pattern):
            if p.is_file() and p.suffix.lower() in supported_exts:
                try:
                    res = self.ingest_document(str(p), category=category)
                    results.append(res)
                except Exception as e:
                    results.append({"file_name": p.name, "error": str(e)})

        return results

    def search_documents(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve most relevant document snippets with grounded citations."""
        if not query.strip():
            return []

        search_kwargs: Dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, max(1, self.collection.count() or 1)),
        }
        if filter_metadata:
            search_kwargs["where"] = filter_metadata

        try:
            results = self.collection.query(**search_kwargs)
        except Exception:
            return []

        hits = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []

            for i in range(len(docs)):
                meta = metas[i] if i < len(metas) else {}
                hits.append({
                    "content": docs[i],
                    "file_name": meta.get("file_name", "Unknown"),
                    "file_path": meta.get("file_path", ""),
                    "page_number": meta.get("page_number", 1),
                    "chunk_index": meta.get("chunk_index", 0),
                    "distance": dists[i] if i < len(dists) else 0.0,
                    "citation": f"{meta.get('file_name', 'Doc')} (Page {meta.get('page_number', 1)})",
                })
        return hits

    def answer_from_documents(self, query: str, n_context: int = 4) -> Dict[str, Any]:
        """Synthesize an answer backed by cited document passages."""
        snippets = self.search_documents(query=query, n_results=n_context)
        if not snippets:
            return {
                "query": query,
                "answer": "No relevant document passages were found in the document memory catalog.",
                "citations": [],
            }

        citations = []
        context_parts = []
        for idx, s in enumerate(snippets, 1):
            context_parts.append(f"[{idx}] (Source: {s['citation']}):\n{s['content']}")
            citations.append({
                "index": idx,
                "file_name": s["file_name"],
                "page": s["page_number"],
                "citation": s["citation"],
            })

        context_block = "\n\n".join(context_parts)
        answer = f"Based on the indexed documents:\n\n{context_block}"

        return {
            "query": query,
            "answer": answer,
            "citations": citations,
            "raw_snippets": snippets,
        }


# Singleton accessor
_vector_memory_instance: Optional[DocumentVectorMemory] = None

def get_vector_memory() -> DocumentVectorMemory:
    global _vector_memory_instance
    if _vector_memory_instance is None:
        _vector_memory_instance = DocumentVectorMemory()
    return _vector_memory_instance

def ingest_document(file_path: str, category: str = "general") -> Dict[str, Any]:
    return get_vector_memory().ingest_document(file_path, category=category)

def batch_ingest_directory(dir_path: str, category: str = "general") -> List[Dict[str, Any]]:
    return get_vector_memory().batch_ingest_directory(dir_path, category=category)

def search_documents(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    return get_vector_memory().search_documents(query, n_results=n_results)

def answer_from_documents(query: str, n_context: int = 4) -> Dict[str, Any]:
    return get_vector_memory().answer_from_documents(query, n_context=n_context)

