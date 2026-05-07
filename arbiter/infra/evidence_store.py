import base64
import csv
import hashlib
import html
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib import error, request
from uuid import uuid4

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from arbiter.models.evidence import EvidenceBundle, EvidenceChunk, EvidenceSource


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = str(data or "").strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


class EvidenceStore:
    SUPPORTED_TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".htm",
        ".css",
        ".json",
        ".csv",
        ".sql",
        ".yaml",
        ".yml",
        ".xml",
        ".log",
        ".rst",
    }

    def __init__(self):
        self._material_cache: dict[str, tuple[str, list[str], str]] = {}
        self._url_cache: dict[str, tuple[str, list[str], str]] = {}

    def ingest(
        self,
        *,
        query: str,
        materials: Optional[list[dict]] = None,
        urls: Optional[list[str]] = None,
    ) -> EvidenceBundle:
        materials = list(materials or [])
        urls = [str(item or "").strip() for item in (urls or []) if str(item or "").strip()]
        sources: list[EvidenceSource] = []
        warnings: list[str] = []

        for item in materials:
            source, source_warnings = self._ingest_material(item)
            warnings.extend(source_warnings)
            if source is not None:
                sources.append(source)

        for url in urls:
            source, source_warnings = self._ingest_url(url)
            warnings.extend(source_warnings)
            if source is not None:
                sources.append(source)

        chunks = self._chunk_sources(sources)
        retrieved = self._retrieve(query, chunks)
        deduped_warnings = []
        for warning in warnings:
            clean = str(warning or "").strip()
            if clean and clean not in deduped_warnings:
                deduped_warnings.append(clean)

        return EvidenceBundle(
            query=str(query or ""),
            sources=sources,
            retrieved_chunks=retrieved,
            warnings=deduped_warnings[:8],
            rag_used=bool(retrieved),
        )

    def _ingest_material(self, material: dict) -> tuple[Optional[EvidenceSource], list[str]]:
        name = str(material.get("name", "") or "attachment").strip() or "attachment"
        media_type = str(material.get("media_type", "") or "").strip()
        source_type = str(material.get("source_type", "") or "file").strip() or "file"
        warnings: list[str] = []

        raw_bytes = material.get("bytes")
        if raw_bytes is None and material.get("content_base64"):
            try:
                raw_bytes = base64.b64decode(str(material.get("content_base64") or ""), validate=False)
            except Exception:
                warnings.append(f"{name}: base64 decoding failed.")
                raw_bytes = b""
        if raw_bytes is None and material.get("content") is not None:
            raw_bytes = str(material.get("content") or "").encode("utf-8")
        if raw_bytes is None:
            warnings.append(f"{name}: no readable file content was provided.")
            return None, warnings

        cache_key = self._material_cache_key(name, media_type, raw_bytes)
        cached = self._material_cache.get(cache_key)
        if cached is None:
            extracted_text, extract_warnings = self._extract_text(
                name=name,
                raw_bytes=raw_bytes,
                media_type=media_type,
            )
            cached_media_type = media_type or self._infer_media_type(name)
            self._material_cache[cache_key] = (extracted_text, list(extract_warnings or []), cached_media_type)
        else:
            extracted_text, extract_warnings, media_type = cached
        warnings.extend(extract_warnings)
        if not extracted_text.strip():
            warnings.append(f"{name}: no readable text could be extracted.")
            return None, warnings

        source = EvidenceSource(
            source_id=f"src-{uuid4().hex[:10]}",
            name=name,
            source_type=source_type,
            media_type=media_type or self._infer_media_type(name),
            extracted_text=extracted_text,
            char_count=len(extracted_text),
            warnings=extract_warnings[:4],
            metadata={"extension": Path(name).suffix.lower()},
        )
        return source, warnings

    def _ingest_url(self, url: str) -> tuple[Optional[EvidenceSource], list[str]]:
        warnings: list[str] = []
        cached = self._url_cache.get(url)
        if cached is not None:
            extracted_text, cached_warnings, media_type = cached
            warnings.extend(cached_warnings)
            if not extracted_text.strip():
                warnings.append(f"{url}: no readable text could be extracted.")
                return None, warnings
            source = EvidenceSource(
                source_id=f"url-{uuid4().hex[:10]}",
                name=url,
                source_type="url",
                media_type=media_type or self._infer_media_type(url),
                extracted_text=extracted_text,
                char_count=len(extracted_text),
                warnings=list(cached_warnings or [])[:4],
                metadata={"extension": Path(url).suffix.lower()},
            )
            return source, warnings
        try:
            req = request.Request(
                url,
                headers={"User-Agent": "TheArbiter/0.1"},
                method="GET",
            )
            with request.urlopen(req, timeout=15) as response:
                body = response.read()
                media_type = str(response.headers.get_content_type() or "")
        except error.URLError as exc:
            warnings.append(f"{url}: could not be fetched ({exc.reason}).")
            return None, warnings
        except Exception as exc:
            warnings.append(f"{url}: fetch failed ({str(exc).strip() or 'unknown error'}).")
            return None, warnings

        name = url
        extracted_text, extract_warnings = self._extract_text(
            name=name,
            raw_bytes=body,
            media_type=media_type,
        )
        warnings.extend(extract_warnings)
        if not extracted_text.strip():
            warnings.append(f"{url}: no readable text could be extracted.")
            return None, warnings
        self._url_cache[url] = (extracted_text, list(extract_warnings or []), media_type or self._infer_media_type(name))

        source = EvidenceSource(
            source_id=f"url-{uuid4().hex[:10]}",
            name=url,
            source_type="url",
            media_type=media_type or self._infer_media_type(name),
            extracted_text=extracted_text,
            char_count=len(extracted_text),
            warnings=extract_warnings[:4],
            metadata={"extension": Path(url).suffix.lower()},
        )
        return source, warnings

    def _extract_text(self, *, name: str, raw_bytes: bytes, media_type: str) -> tuple[str, list[str]]:
        path = Path(str(name or "attachment"))
        suffix = path.suffix.lower()
        warnings: list[str] = []
        media_type = str(media_type or "").lower()

        if suffix == ".pdf" or "pdf" in media_type:
            if PdfReader is None:
                return "", [f"{name}: PDF extraction requires the optional `pypdf` dependency."]
            try:
                reader = PdfReader(io.BytesIO(raw_bytes))
                parts = []
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        parts.append(page_text)
                return self._normalize_text("\n\n".join(parts)), warnings
            except Exception as exc:
                return "", [f"{name}: PDF extraction failed ({str(exc).strip() or 'unknown error'})."]

        if suffix == ".docx" or "wordprocessingml" in media_type:
            try:
                return self._extract_docx_text(raw_bytes), warnings
            except Exception as exc:
                return "", [f"{name}: DOCX extraction failed ({str(exc).strip() or 'unknown error'})."]

        if suffix in {".json"} or "json" in media_type:
            try:
                payload = json.loads(raw_bytes.decode("utf-8"))
                pretty = json.dumps(payload, ensure_ascii=True, indent=2)
                return self._normalize_text(pretty), warnings
            except Exception:
                warnings.append(f"{name}: JSON parsing failed, falling back to raw text decoding.")

        if suffix in {".csv"} or "csv" in media_type:
            try:
                decoded = raw_bytes.decode("utf-8")
                reader = csv.reader(io.StringIO(decoded))
                rows = []
                for row in reader:
                    rows.append(" | ".join(str(cell).strip() for cell in row))
                return self._normalize_text("\n".join(rows)), warnings
            except Exception:
                warnings.append(f"{name}: CSV parsing failed, falling back to raw text decoding.")

        if suffix in {".html", ".htm"} or media_type == "text/html":
            decoded = self._decode_text_bytes(raw_bytes)
            parser = _HTMLTextExtractor()
            parser.feed(decoded)
            return self._normalize_text(parser.get_text()), warnings

        if suffix in self.SUPPORTED_TEXT_EXTENSIONS or media_type.startswith("text/") or not suffix:
            return self._normalize_text(self._decode_text_bytes(raw_bytes)), warnings

        warnings.append(f"{name}: unsupported attachment type; used best-effort text decoding.")
        return self._normalize_text(self._decode_text_bytes(raw_bytes)), warnings

    @staticmethod
    def _material_cache_key(name: str, media_type: str, raw_bytes: bytes) -> str:
        digest = hashlib.sha1(raw_bytes).hexdigest()
        return f"{name}:{media_type}:{digest}"

    @staticmethod
    def _extract_docx_text(raw_bytes: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ET.fromstring(document_xml)
        text_parts = []
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                text_parts.append(node.text)
        return EvidenceStore._normalize_text("\n".join(text_parts))

    @staticmethod
    def _decode_text_bytes(raw_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw_bytes.decode(encoding)
            except Exception:
                continue
        return raw_bytes.decode("utf-8", errors="ignore")

    @staticmethod
    def _normalize_text(text: str) -> str:
        value = html.unescape(str(text or ""))
        value = re.sub(r"\r\n?", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()

    @staticmethod
    def _infer_media_type(name: str) -> str:
        suffix = Path(str(name or "")).suffix.lower()
        mapping = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".htm": "text/html",
            ".json": "application/json",
            ".csv": "text/csv",
        }
        return mapping.get(suffix, "application/octet-stream")

    def _chunk_sources(self, sources: list[EvidenceSource], *, size: int = 900, overlap: int = 120) -> list[EvidenceChunk]:
        chunks: list[EvidenceChunk] = []
        for source in sources:
            text = str(source.extracted_text or "").strip()
            if not text:
                continue
            start = 0
            chunk_index = 0
            while start < len(text):
                end = min(len(text), start + size)
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append(
                        EvidenceChunk(
                            chunk_id=f"{source.source_id}-chunk-{chunk_index}",
                            source_id=source.source_id,
                            source_name=source.name,
                            source_type=source.source_type,
                            text=chunk_text,
                            index=chunk_index,
                            locator=f"chars {start}-{end}",
                            metadata={"source_name": source.name},
                        )
                    )
                if end >= len(text):
                    break
                start = max(0, end - overlap)
                chunk_index += 1
        return chunks

    def _retrieve(self, query: str, chunks: list[EvidenceChunk], limit: int = 6) -> list[EvidenceChunk]:
        query_tokens = self._tokenize(query)
        query_vector = self._embed(query_tokens)
        scored: list[tuple[float, EvidenceChunk]] = []
        for chunk in chunks:
            chunk_tokens = self._tokenize(chunk.text)
            lexical_overlap = self._jaccard(query_tokens, chunk_tokens)
            phrase_hits = self._phrase_hits(query, chunk.text)
            vector_score = self._cosine(query_vector, self._embed(chunk_tokens))
            score = round((0.5 * vector_score) + (0.35 * lexical_overlap) + (0.15 * phrase_hits), 4)
            if score <= 0.01:
                continue
            chunk.score = score
            scored.append((score, chunk))

        if not scored:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "into", "your", "when",
            "then", "than", "have", "will", "what", "where", "which", "should", "could",
            "would", "there", "their", "about", "after", "before", "only", "also", "just",
            "does", "did", "not", "are", "was", "were", "been", "being", "them", "they",
            "build", "create", "write", "make", "need", "task", "user", "request",
        }
        words = re.findall(r"[a-zA-Z0-9_]+", str(text or "").lower())
        return {word for word in words if len(word) > 2 and word not in stopwords}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    @staticmethod
    def _phrase_hits(query: str, text: str) -> float:
        phrases = [part.strip().lower() for part in re.split(r"[,\n]", str(query or "")) if part.strip()]
        if not phrases:
            return 0.0
        lowered = str(text or "").lower()
        hits = 0
        for phrase in phrases[:6]:
            if len(phrase) < 8:
                continue
            if phrase in lowered:
                hits += 1
        return min(1.0, hits / max(1, len(phrases[:6])))

    @staticmethod
    def _embed(tokens: set[str], dimensions: int = 192) -> list[float]:
        vector = [0.0] * dimensions
        if not tokens:
            return vector
        for token in tokens:
            slot = hash(token) % dimensions
            vector[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        return sum(a * b for a, b in zip(left, right))


_EVIDENCE_STORE: Optional[EvidenceStore] = None


def get_evidence_store() -> EvidenceStore:
    global _EVIDENCE_STORE
    if _EVIDENCE_STORE is None:
        _EVIDENCE_STORE = EvidenceStore()
    return _EVIDENCE_STORE
