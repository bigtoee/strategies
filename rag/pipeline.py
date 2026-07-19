# -*- coding: utf-8 -*-
"""
RAG 主流程：加载 -> 切分 -> 嵌入 -> 检索 -> 生成
"""
from .loader import load_document
from .splitter import recursive_char_splitter
from .embeddings import get_embedder
from .store import VectorStore
from .llm import get_llm


class RAGPipeline:
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        embedder_engine: str = "auto",
        embedder_kwargs: dict = None,
        llm_provider: str = "auto",
        llm_kwargs: dict = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedder = get_embedder(embedder_engine, **(embedder_kwargs or {}))
        self.llm = get_llm(llm_provider, **(llm_kwargs or {}))
        self.store = VectorStore()
        self.documents = []  # 原始文档信息

    def add_document(self, file_obj, filename: str = ""):
        """添加单个文档"""
        raw_text = load_document(file_obj, filename)
        chunks = recursive_char_splitter(raw_text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return 0

        vectors = self.embedder.embed(chunks)
        metadatas = [{"source": filename or "未知文件", "chunk_index": i} for i in range(len(chunks))]
        self.store.add(chunks, vectors, metadatas)
        self.documents.append({"filename": filename or "未知文件", "chunks": len(chunks)})
        return len(chunks)

    def add_text(self, text: str, source: str = "用户文本"):
        """直接添加一段文本"""
        chunks = recursive_char_splitter(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return 0
        vectors = self.embedder.embed(chunks)
        metadatas = [{"source": source, "chunk_index": i} for i in range(len(chunks))]
        self.store.add(chunks, vectors, metadatas)
        self.documents.append({"filename": source, "chunks": len(chunks)})
        return len(chunks)

    def retrieve(self, query: str, k: int = 4) -> list[dict]:
        """检索与 query 最相关的文档块"""
        qv = self.embedder.embed_query(query)
        return self.store.similarity_search(qv, k=k)

    def answer(self, query: str, k: int = 4, system_prompt: str = None) -> dict:
        """
        完整 RAG 流程：检索 + 生成。
        返回 {"answer": str, "contexts": list, "llm_used": bool}
        """
        contexts = self.retrieve(query, k=k)
        context_text = "\n\n---\n\n".join(
            f"[来源 {i+1}] {c['metadata']['source']}\n{c['text']}" for i, c in enumerate(contexts)
        )

        default_system = "你是一个严谨的问答助手，只能根据提供的参考资料回答问题。如果资料不足，请明确说明。"
        system = system_prompt or default_system

        user_prompt = f"""请参考以下资料回答问题：

{context_text}

---

问题：{query}
"""
        try:
            llm_answer = self.llm.chat(system, user_prompt)
            llm_used = bool(llm_answer.strip())
        except Exception as e:
            llm_answer = f""
            llm_used = False

        return {
            "answer": llm_answer,
            "contexts": contexts,
            "llm_used": llm_used,
        }

    def reset(self):
        self.store.clear()
        self.documents = []
