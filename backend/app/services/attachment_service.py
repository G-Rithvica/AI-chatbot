from pathlib import Path
import base64
import re
import zipfile
import uuid
from collections import Counter
from typing import Any

import filetype
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import fitz  # PyMuPDF
except Exception:  # noqa: BLE001
    fitz = None

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None

from app.core.config import BASE_DIR, get_settings
from app.models.attachment import Attachment
from app.ai.llm import get_async_openai_client

settings = get_settings()
_MAX_CONTEXT_CHARS_PER_FILE = 4000
_MAX_TOTAL_CONTEXT_CHARS = 12000
_OCR_MAX_PAGES = 2
_VIDEO_MAX_KEYFRAMES = 8
_VIDEO_MAX_SIDE = 1280
_VIDEO_JPEG_QUALITY = 70
_VIDEO_MAX_INLINE_FRAMES = 4

ALLOWED_KINDS = {'image', 'video', 'table', 'formula', 'code', 'file'}

_KIND_BY_EXTENSION = {
    '.png': 'image',
    '.jpg': 'image',
    '.jpeg': 'image',
    '.jfif': 'image',
    '.heic': 'image',
    '.heif': 'image',
    '.avif': 'image',
    '.tif': 'image',
    '.tiff': 'image',
    '.gif': 'image',
    '.webp': 'image',
    '.bmp': 'image',
    '.svg': 'image',
    '.ico': 'image',
    '.raw': 'image',
    '.dng': 'image',
    '.cr2': 'image',
    '.nef': 'image',
    '.arw': 'image',
    '.orf': 'image',
    '.mp4': 'video',
    '.webm': 'video',
    '.mov': 'video',
    '.avi': 'video',
    '.mkv': 'video',
    '.csv': 'table',
    '.xls': 'table',
    '.xlsx': 'table',
    '.tsv': 'table',
    '.tex': 'formula',
    '.latex': 'formula',
    '.pdf': 'file',
    '.py': 'code',
    '.js': 'code',
    '.ts': 'code',
    '.tsx': 'code',
    '.jsx': 'code',
    '.java': 'code',
    '.cpp': 'code',
    '.c': 'code',
    '.cs': 'code',
    '.go': 'code',
    '.rs': 'code',
    '.md': 'code',
    '.txt': 'code',
    '.json': 'code',
    '.yaml': 'code',
    '.yml': 'code',
    '.sql': 'code',
    '.html': 'code',
    '.css': 'code',
}

_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.avi', '.mkv'}

_QUERY_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'how', 'i', 'in', 'is', 'it',
    'me', 'of', 'on', 'or', 'please', 'provide', 'show', 'tell', 'that', 'the', 'this', 'to',
    'what', 'when', 'where', 'which', 'who', 'why', 'with', 'about', 'information', 'details'
}

_PDF_SECTION_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _resolve_upload_root() -> Path:
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = BASE_DIR / upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _guess_kind(file_name: str, mime_type: str, content: bytes) -> str | None:
    suffix = Path(file_name).suffix.lower()
    kind = _KIND_BY_EXTENSION.get(suffix)
    if kind:
        return kind

    normalized_mime = (mime_type or '').lower()

    if normalized_mime.startswith('image/'):
        return 'image'
    if normalized_mime.startswith('video/'):
        return 'video'
    if normalized_mime in {
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }:
        return 'table'
    if normalized_mime in {'application/x-tex', 'text/x-tex', 'text/latex'}:
        return 'formula'
    if normalized_mime in {'application/pdf'}:
        return 'file'
    if normalized_mime.startswith('text/') or normalized_mime in {'application/json', 'application/xml'}:
        return 'code'

    # Browser/file picker may send generic application/octet-stream.
    if content:
        guessed = filetype.guess_mime(content)
        if guessed:
            if guessed.startswith('image/'):
                return 'image'
            if guessed.startswith('video/'):
                return 'video'
            if guessed == 'application/pdf':
                return 'file'

    # Fail-open fallback for real-world uploads where browser MIME is unreliable.
    # Keep attachment usable by treating unknown payloads as code-like files.
    if normalized_mime in {'', 'application/octet-stream'}:
        return 'file'

    return 'file'


def _build_public_url(storage_path: str) -> str:
    path = storage_path.replace('\\', '/')
    return f'/uploads/{path}'


def _read_text_excerpt(path: Path) -> str:
    try:
        text = path.read_text(encoding='utf-8', errors='ignore').strip()
    except Exception:  # noqa: BLE001
        return ''
    return text[:_MAX_CONTEXT_CHARS_PER_FILE]


def _strip_xml_tags(value: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', value)
    return ' '.join(text.split())


def _read_zip_text_excerpt(path: Path) -> str:
    # Many office formats (docx/xlsx/pptx/odt/ods/odp/epub) are zip containers.
    try:
        with zipfile.ZipFile(path) as zf:
            names = [
                name for name in zf.namelist()
                if name.lower().endswith(('.xml', '.txt', '.csv', '.json', '.md', '.html'))
            ]
            if not names:
                return ''

            parts: list[str] = []
            consumed = 0
            for name in names[:80]:
                if consumed >= _MAX_CONTEXT_CHARS_PER_FILE:
                    break
                try:
                    raw = zf.read(name)
                except Exception:  # noqa: BLE001
                    continue
                text = raw.decode('utf-8', errors='ignore')
                if not text.strip():
                    continue

                if name.lower().endswith('.xml') or text.lstrip().startswith('<'):
                    text = _strip_xml_tags(text)
                else:
                    text = ' '.join(text.split())
                if not text:
                    continue

                remaining = _MAX_CONTEXT_CHARS_PER_FILE - consumed
                chunk = text[:remaining]
                parts.append(chunk)
                consumed += len(chunk)

            return '\n'.join(parts)
    except Exception:  # noqa: BLE001
        return ''


def _read_binary_strings_excerpt(path: Path) -> str:
    try:
        raw = path.read_bytes()[:300_000]
    except Exception:  # noqa: BLE001
        return ''

    strings = re.findall(rb'[\x20-\x7e]{8,}', raw)
    if not strings:
        return ''

    text = ' '.join(chunk.decode('latin-1', errors='ignore') for chunk in strings)
    text = ' '.join(text.split())
    return text[:_MAX_CONTEXT_CHARS_PER_FILE]


def _read_pdf_excerpt(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return ''

    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            text = (page.extract_text() or '').strip()
        except Exception:  # noqa: BLE001
            text = ''
        if not text:
            continue
        remaining = _MAX_CONTEXT_CHARS_PER_FILE - total
        if remaining <= 0:
            break
        chunk = text[:remaining]
        parts.append(chunk)
        total += len(chunk)
    extracted = '\n'.join(parts)
    if extracted:
        return extracted

    # Secondary fallback: PyMuPDF often extracts text from PDFs that pypdf misses.
    if fitz is not None:
        try:
            doc = fitz.open(str(path))
            collected: list[str] = []
            total = 0
            for page in doc:
                text = (page.get_text('text') or '').strip()
                if not text:
                    continue
                remaining = _MAX_CONTEXT_CHARS_PER_FILE - total
                if remaining <= 0:
                    break
                chunk = text[:remaining]
                collected.append(chunk)
                total += len(chunk)
            doc.close()
            if collected:
                return '\n'.join(collected)
        except Exception:  # noqa: BLE001
            pass

    # Fallback for PDFs where page text extraction fails.
    try:
        raw = path.read_bytes()[:200_000]
    except Exception:  # noqa: BLE001
        return ''

    # Try extracting strings inside PDF text operators like ( ... ).
    paren_chunks = re.findall(rb'\(([^\)]{4,})\)', raw)
    if paren_chunks:
        joined = ' '.join(chunk.decode('latin-1', errors='ignore') for chunk in paren_chunks)
        joined = ' '.join(joined.split())
        if joined:
            return joined[:_MAX_CONTEXT_CHARS_PER_FILE]

    # Last-resort printable scan to recover visible text from encoded streams.
    printable = re.findall(rb'[\x20-\x7e]{20,}', raw)
    if printable:
        merged = ' '.join(chunk.decode('latin-1', errors='ignore') for chunk in printable)
        merged = ' '.join(merged.split())
        if merged:
            return merged[:_MAX_CONTEXT_CHARS_PER_FILE]

    return ''


def _normalize_heading(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r'\s+', ' ', lowered)
    return lowered


def _infer_heading_level(heading: str) -> int:
    text = heading.strip().lower()
    if text.startswith('demo'):
        return 1
    if text.startswith('epic'):
        return 2
    if text.startswith('user story') or text.startswith('story'):
        return 3

    number_match = re.match(r'^(\d+(?:\.\d+)*)\b', heading.strip())
    if number_match:
        return number_match.group(1).count('.') + 1
    return 4


def _looks_like_heading_line(line: str) -> bool:
    value = line.strip()
    if not value or len(value) > 140:
        return False

    if re.match(r'^(demo|epic|user\s*story|story|section)\s*[:#\-]?\s*[a-z0-9]+(?:\.[a-z0-9]+)*\b.*$', value, re.IGNORECASE):
        return True

    if re.match(r'^\d+(?:\.\d+){0,4}\s+[A-Za-z].{1,120}$', value):
        return True

    words = value.split()
    if len(words) <= 10 and not value.endswith('.'):
        title_like = sum(1 for word in words if word[:1].isupper())
        if title_like >= max(2, len(words) // 2):
            return True

    return False


def _extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return pages

    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or '').replace('\r', '\n')
        except Exception:  # noqa: BLE001
            text = ''
        if text.strip():
            pages.append((idx, text))

    if pages:
        return pages

    if fitz is None:
        return pages

    try:
        doc = fitz.open(str(path))
    except Exception:  # noqa: BLE001
        return pages

    try:
        for idx in range(len(doc)):
            text = (doc[idx].get_text('text') or '').replace('\r', '\n')
            if text.strip():
                pages.append((idx + 1, text))
    finally:
        doc.close()

    return pages


def _build_pdf_section_index(path: Path) -> list[dict[str, Any]]:
    try:
        mtime = path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return []

    cache_key = str(path)
    cached = _PDF_SECTION_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]

    pages = _extract_pdf_pages(path)
    if not pages:
        _PDF_SECTION_CACHE[cache_key] = (mtime, [])
        return []

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for page_number, page_text in pages:
        raw_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        normalized_lines = [re.sub(r'\s+', ' ', line) for line in raw_lines]
        if not normalized_lines:
            continue

        for line in normalized_lines:
            if _looks_like_heading_line(line):
                if current is not None:
                    sections.append(current)
                current = {
                    'heading': line,
                    'normalized_heading': _normalize_heading(line),
                    'level': _infer_heading_level(line),
                    'start_page': page_number,
                    'end_page': page_number,
                    'content_lines': [],
                }
                continue

            if current is None:
                current = {
                    'heading': f'Page {page_number} Overview',
                    'normalized_heading': _normalize_heading(f'Page {page_number} Overview'),
                    'level': 5,
                    'start_page': page_number,
                    'end_page': page_number,
                    'content_lines': [],
                }

            current['content_lines'].append(line)
            current['end_page'] = page_number

    if current is not None:
        sections.append(current)

    compacted: list[dict[str, Any]] = []
    for section in sections:
        body = '\n'.join(section.get('content_lines', [])).strip()
        compacted.append(
            {
                'heading': section['heading'],
                'normalized_heading': section['normalized_heading'],
                'level': int(section['level']),
                'start_page': int(section['start_page']),
                'end_page': int(section['end_page']),
                'body': body,
            }
        )

    _PDF_SECTION_CACHE[cache_key] = (mtime, compacted)
    return compacted


def _extract_query_targets(query: str) -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    patterns = [
        ('demo', 'demo', r'\b(demo)\s*[:#\-]?\s*([a-z0-9]+(?:\.[a-z0-9]+)*)\b'),
        ('epic', 'epic', r'\b(epic)\s*[:#\-]?\s*([a-z0-9]+(?:\.[a-z0-9]+)*)\b'),
        ('user story', 'user\\s*story|story', r'\b(user\s*story|story)\s*[:#\-]?\s*([a-z0-9]+(?:\.[a-z0-9]+)*)\b'),
        ('user', 'user', r'\b(user)\s*[:#\-]?\s*([a-z0-9]+(?:\.[a-z0-9]+)*)\b'),
    ]

    for label, label_regex, pattern in patterns:
        for match in re.finditer(pattern, query, flags=re.IGNORECASE):
            targets.append((label, label_regex, match.group(2).lower()))

    deduped: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, label_regex, identifier in targets:
        key = (label, identifier)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((label, label_regex, identifier))

    return deduped


def _is_title_lookup_query(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in ('title', 'heading', 'name'))


def _sanitize_section_title_tail(title: str) -> str:
    cleaned = re.sub(r'\s+', ' ', title).strip(' :-')
    # Some PDFs append audience labels on the same extracted heading line.
    cleaned = re.sub(
        r'\s+(?:mobile|web|desktop|admin|consumer|client)\s+users?\b.*$',
        '',
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(' :-')


def _derive_exact_heading_for_title_query(
    heading: str,
    query_targets: list[tuple[str, str, str]],
) -> str:
    normalized_heading = re.sub(r'\s+', ' ', heading).strip()

    for label, label_regex, identifier in query_targets:
        pattern = re.compile(
            rf'\b({label_regex})\s*[:#\-]?\s*({re.escape(identifier)})\b\s*[:\-]?\s*(.*)$',
            flags=re.IGNORECASE,
        )
        match = pattern.search(normalized_heading)
        if not match:
            continue

        normalized_label = label.title() if label != 'user story' else 'User Story'
        identifier_text = match.group(2)
        tail = _sanitize_section_title_tail(match.group(3))

        if tail:
            return f'{normalized_label} {identifier_text} : {tail}'
        return f'{normalized_label} {identifier_text}'

    return normalized_heading


def _build_section_heading_chain(sections: list[dict[str, Any]], index: int) -> list[str]:
    current = sections[index]
    current_level = int(current.get('level', 5))
    chain: list[str] = [str(current.get('heading', ''))]

    for cursor in range(index - 1, -1, -1):
        candidate = sections[cursor]
        candidate_level = int(candidate.get('level', 5))
        if candidate_level < current_level:
            chain.append(str(candidate.get('heading', '')))
            current_level = candidate_level
            if current_level <= 1:
                break

    return chain


def _heading_chain_satisfies_targets(
    heading_chain: list[str],
    targets: list[tuple[str, str, str]],
) -> tuple[bool, int]:
    if not targets:
        return False, 0

    score = 0
    matched_count = 0
    for _, label_regex, identifier in targets:
        exact_pattern = re.compile(
            rf'\b(?:{label_regex})\s*[:#\-]?\s*{re.escape(identifier)}\b',
            flags=re.IGNORECASE,
        )
        family_pattern = re.compile(rf'\b(?:{label_regex})\b', flags=re.IGNORECASE)

        exact_matched = any(exact_pattern.search(heading) for heading in heading_chain)
        if exact_matched:
            score += 150
            matched_count += 1
            continue

        # A family mention with a different identifier should rank lower.
        if any(family_pattern.search(heading) for heading in heading_chain):
            score -= 35

    return matched_count == len(targets), score


def _find_exact_pdf_section_index(sections: list[dict[str, Any]], query: str) -> int | None:
    targets = _extract_query_targets(query)
    if not targets:
        return None

    best_index: int | None = None
    best_score = -10_000
    query_keywords = _extract_query_keywords(query)

    for idx, section in enumerate(sections):
        heading = str(section.get('heading', ''))
        heading_lower = heading.lower()
        heading_chain = _build_section_heading_chain(sections, idx)
        chain_matches_all_targets, target_score = _heading_chain_satisfies_targets(heading_chain, targets)
        if not chain_matches_all_targets:
            continue

        score = target_score

        if query_keywords:
            heading_tokens = re.findall(r'[a-z0-9]{3,}', heading_lower)
            if heading_tokens:
                counts = Counter(heading_tokens)
                score += sum(counts[word] for word in query_keywords)

        if score > best_score:
            best_score = score
            best_index = idx

    return best_index


def _collect_section_with_children(sections: list[dict[str, Any]], start_index: int) -> list[dict[str, Any]]:
    root = sections[start_index]
    root_level = int(root.get('level', 5))
    collected = [root]

    for index in range(start_index + 1, len(sections)):
        candidate = sections[index]
        candidate_level = int(candidate.get('level', 5))
        if candidate_level <= root_level:
            break
        collected.append(candidate)

    return collected


def _format_pdf_sections_for_context(file_name: str, selected: list[dict[str, Any]]) -> str:
    lines = [
        f'Attachment retrieval result for {file_name}:',
        'Return answers using only the exact matched section content below.',
    ]

    consumed = 0
    for section in selected:
        heading = str(section.get('heading', 'Untitled Section'))
        level = int(section.get('level', 5))
        start_page = int(section.get('start_page', 0))
        end_page = int(section.get('end_page', start_page))
        body = str(section.get('body', '')).strip()

        lines.append(f"- Level {level} | {heading} (pages {start_page}-{end_page})")
        if body:
            remaining = _MAX_CONTEXT_CHARS_PER_FILE - consumed
            if remaining <= 0:
                break
            chunk = body[:remaining]
            consumed += len(chunk)
            lines.append(chunk)

    return '\n'.join(lines)


def _build_pdf_section_context(attachment: Attachment, user_query: str) -> str:
    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return ''

    sections = _build_pdf_section_index(path)
    if not sections:
        return ''

    exact_index = _find_exact_pdf_section_index(sections, user_query)
    query_targets = _extract_query_targets(user_query)

    if query_targets and exact_index is None:
        target_text = ', '.join(f'{label} {identifier}' for label, _, identifier in query_targets)
        return (
            f'Attachment retrieval result for {attachment.file_name}: '\
            f'Exact requested section was not found: {target_text}. '\
            'Do not infer from nearby sections.'
        )

    if exact_index is not None:
        if _is_title_lookup_query(user_query):
            heading = str(sections[exact_index].get('heading', '')).strip()
            exact_heading = _derive_exact_heading_for_title_query(heading, query_targets)
            return (
                f'Attachment retrieval result for {attachment.file_name}:\n'
                'Exact matched heading for the requested section:\n'
                f'{exact_heading}\n'
                'Respond with the exact heading text above.'
            )

        selected = _collect_section_with_children(sections, exact_index)
        return _format_pdf_sections_for_context(attachment.file_name, selected)

    # No exact target in query: provide top heading blocks with structure preserved.
    fallback = sections[:4]
    return _format_pdf_sections_for_context(attachment.file_name, fallback)


def _extract_attachment_excerpt(attachment: Attachment) -> str:
    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return ''

    suffix = Path(attachment.file_name).suffix.lower()
    mime = (attachment.mime_type or '').lower()

    # Do not attempt binary string scraping for videos. It yields container/header noise
    # that is not useful to the language model and causes confusing responses.
    if mime.startswith('video/') or suffix in _VIDEO_EXTENSIONS:
        return ''

    if suffix == '.pdf' or mime == 'application/pdf':
        return _read_pdf_excerpt(path)

    # Force image files through vision OCR path in async builder.
    # Binary string scanning for images produces noise like PNG headers.
    if mime.startswith('image/') or suffix in {
        '.png', '.jpg', '.jpeg', '.jfif', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif', '.svg'
    }:
        return ''

    if suffix in {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.epub'}:
        excerpt = _read_zip_text_excerpt(path)
        if excerpt:
            return excerpt

    if mime.startswith('text/') or suffix in {
        '.txt', '.md', '.csv', '.tsv', '.json', '.yaml', '.yml', '.sql', '.py', '.js', '.ts', '.tsx',
        '.jsx', '.java', '.cpp', '.c', '.cs', '.go', '.rs', '.html', '.css', '.tex', '.latex'
    }:
        return _read_text_excerpt(path)

    # Last fallback for unknown binary formats.
    return _read_binary_strings_excerpt(path)


def _build_entity_patterns(query: str) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []

    for label in ('demo', 'epic', 'user'):
        # Capture phrases like "Demo 2", "Epic #1", "User: John", "User-42".
        regex = re.compile(rf'\b{label}\s*[:#\-]?\s*([a-z0-9][a-z0-9_\-]*)\b', flags=re.IGNORECASE)
        for match in regex.finditer(query):
            identifier = re.escape(match.group(1))
            patterns.append(re.compile(rf'\b{label}\s*[:#\-]?\s*{identifier}\b', flags=re.IGNORECASE))

    return patterns


def _extract_query_keywords(query: str) -> set[str]:
    words = re.findall(r'[a-z0-9]{3,}', query.lower())
    return {word for word in words if word not in _QUERY_STOPWORDS}


def _segment_excerpt_text(excerpt: str) -> list[str]:
    raw_lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    if len(raw_lines) > 3:
        return raw_lines

    # PDFs often extract into very long lines. Build synthetic segments using
    # punctuation and entity heading boundaries to improve matching precision.
    normalized = re.sub(r'\s+', ' ', excerpt).strip()
    if not normalized:
        return []

    boundary_pattern = re.compile(
        r'(?i)(?=\b(?:demo|epic|user)\s*[:#\-]?\s*[a-z0-9][a-z0-9_\-]*\b)'
    )
    chunks = [chunk.strip() for chunk in boundary_pattern.split(normalized) if chunk.strip()]
    segments: list[str] = []

    for chunk in chunks:
        parts = re.split(r'(?<=[\.!?;])\s+', chunk)
        for part in parts:
            candidate = part.strip()
            if candidate:
                segments.append(candidate)

    if not segments:
        return [normalized]
    return segments


def _extract_exact_entity_targets(query: str) -> dict[str, str]:
    targets: dict[str, str] = {}
    for label in ('demo', 'epic', 'user', 'user story', 'story'):
        regex = re.compile(rf'\b{label}\s*[:#\-]?\s*([a-z0-9][a-z0-9_\-]*)\b', flags=re.IGNORECASE)
        match = regex.search(query)
        if match:
            targets[label] = match.group(1).lower()
    return targets


def _segment_entity_score(segment: str, *, exact_targets: dict[str, str], keyword_set: set[str]) -> int:
    lowered = segment.lower()
    score = 0

    for label, target in exact_targets.items():
        exact_pattern = re.compile(rf'\b{label}\s*[:#\-]?\s*{re.escape(target)}\b', flags=re.IGNORECASE)
        if exact_pattern.search(segment):
            score += 30
        elif re.search(rf'\b{label}\b', lowered):
            # Penalize mentions of same entity family with a different identifier.
            score -= 8

    if keyword_set:
        tokens = re.findall(r'[a-z0-9]{3,}', lowered)
        if tokens:
            token_counts = Counter(tokens)
            score += sum(token_counts[word] for word in keyword_set)

    return score


def _focus_excerpt_for_query(excerpt: str, query: str) -> str:
    if not excerpt or not query.strip():
        return excerpt

    lines = _segment_excerpt_text(excerpt)
    if len(lines) <= 1:
        return excerpt

    entity_patterns = _build_entity_patterns(query)
    keyword_set = _extract_query_keywords(query)
    exact_targets = _extract_exact_entity_targets(query)

    matched_indices: set[int] = set()
    exact_match_indices: set[int] = set()
    for idx, line in enumerate(lines):
        if any(pattern.search(line) for pattern in entity_patterns):
            matched_indices.add(idx)
            exact_match_indices.add(idx)

    scored: list[tuple[int, int]] = []
    for idx, line in enumerate(lines):
        score = _segment_entity_score(line, exact_targets=exact_targets, keyword_set=keyword_set)
        if score > 0:
            scored.append((idx, score))

    if scored:
        scored.sort(key=lambda item: item[1], reverse=True)
        top_indices = {idx for idx, _ in scored[:8]}
        matched_indices.update(top_indices)

    if exact_targets and not exact_match_indices:
        target_parts = [f"{label} {value}" for label, value in exact_targets.items()]
        target_text = ', '.join(target_parts)
        return (
            f"No exact match was found in extracted attachment text for requested identifiers: {target_text}. "
            'Do not substitute with similarly named items.'
        )

    if not matched_indices:
        return excerpt

    # Include neighboring lines to preserve local context around matched entities.
    expanded: list[int] = []
    for idx in sorted(matched_indices):
        for neighbor in (idx - 1, idx, idx + 1):
            if 0 <= neighbor < len(lines):
                expanded.append(neighbor)

    unique_indices = sorted(set(expanded))
    focused_lines = [lines[idx] for idx in unique_indices]
    focused_text = '\n'.join(focused_lines)
    if not focused_text:
        return excerpt

    return focused_text[:_MAX_CONTEXT_CHARS_PER_FILE]


def build_attachment_image_inputs(attachments: list[Attachment]) -> list[dict]:
    upload_root = _resolve_upload_root()
    parts: list[dict] = []

    for item in attachments:
        suffix = Path(item.file_name).suffix.lower()
        mime = (item.mime_type or '').lower()
        is_video = item.kind == 'video' or mime.startswith('video/') or suffix in _VIDEO_EXTENSIONS
        is_image = (
            item.kind == 'image'
            or mime.startswith('image/')
            or suffix in {'.png', '.jpg', '.jpeg', '.jfif', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif', '.svg'}
        )

        if is_video:
            parts.extend(_video_keyframe_image_parts(item, max_frames=_VIDEO_MAX_INLINE_FRAMES))
            continue

        if not is_image:
            continue

        path = upload_root / item.storage_path
        if not path.exists() or not path.is_file():
            continue

        if not mime.startswith('image/'):
            if suffix == '.png':
                mime = 'image/png'
            elif suffix in {'.jpg', '.jpeg', '.jfif'}:
                mime = 'image/jpeg'
            elif suffix == '.webp':
                mime = 'image/webp'
            elif suffix == '.gif':
                mime = 'image/gif'
            elif suffix == '.bmp':
                mime = 'image/bmp'
            elif suffix in {'.tif', '.tiff'}:
                mime = 'image/tiff'
            elif suffix in {'.svg'}:
                mime = 'image/svg+xml'
            else:
                continue

        try:
            raw = path.read_bytes()
        except Exception:  # noqa: BLE001
            continue

        if not raw:
            continue

        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        parts.append({'type': 'image_url', 'image_url': {'url': data_url}})

    return parts


async def _ocr_pdf_with_llm(attachment: Attachment) -> str:
    if fitz is None or not settings.llm_model:
        return ''

    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return ''

    try:
        doc = fitz.open(str(path))
    except Exception:  # noqa: BLE001
        return ''

    image_parts: list[dict] = []
    try:
        for index in range(min(len(doc), _OCR_MAX_PAGES)):
            page = doc[index]
            pix = page.get_pixmap(dpi=170)
            png_bytes = pix.tobytes('png')
            data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
            image_parts.append({'type': 'image_url', 'image_url': {'url': data_url}})
    finally:
        doc.close()

    if not image_parts:
        return ''

    try:
        client = get_async_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Extract readable text from the provided PDF page images. '
                        'Return plain text only. If no readable text exists, return empty output.'
                    ),
                },
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Transcribe all visible text from these PDF pages.'},
                        *image_parts,
                    ],
                },
            ],
            temperature=0,
        )
    except Exception:  # noqa: BLE001
        return ''

    content = (response.choices[0].message.content if response.choices else '') or ''
    return content.strip()[:_MAX_CONTEXT_CHARS_PER_FILE]


async def _ocr_image_with_llm(attachment: Attachment) -> str:
    if not settings.llm_model:
        return ''

    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return ''

    suffix = Path(attachment.file_name).suffix.lower()
    image_mime = (attachment.mime_type or '').lower() or 'application/octet-stream'
    if not image_mime.startswith('image/'):
        # Try to infer a common image mime when upload metadata is generic.
        if suffix in {'.png'}:
            image_mime = 'image/png'
        elif suffix in {'.jpg', '.jpeg', '.jfif'}:
            image_mime = 'image/jpeg'
        elif suffix in {'.webp'}:
            image_mime = 'image/webp'
        elif suffix in {'.gif'}:
            image_mime = 'image/gif'
        else:
            return ''

    try:
        image_bytes = path.read_bytes()
    except Exception:  # noqa: BLE001
        return ''

    if not image_bytes:
        return ''

    data_url = f"data:{image_mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    try:
        client = get_async_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Extract readable text and key factual details from the provided image. '
                        'Return plain text only. If no readable or meaningful content exists, return empty output.'
                    ),
                },
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Transcribe visible text and describe key details from this image.'},
                        {'type': 'image_url', 'image_url': {'url': data_url}},
                    ],
                },
            ],
            temperature=0,
        )
    except Exception:  # noqa: BLE001
        return ''

    content = (response.choices[0].message.content if response.choices else '') or ''
    return content.strip()[:_MAX_CONTEXT_CHARS_PER_FILE]


def _extract_video_keyframes(video_path: Path, *, max_frames: int) -> list[tuple[int, float | None, bytes]]:
    if cv2 is None:
        return []

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []

    encoded_frames: list[tuple[int, float | None, bytes]] = []
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count <= 0:
            sample_positions = [0]
        else:
            sample_count = max(1, min(max_frames, frame_count))
            if sample_count == 1:
                sample_positions = [0]
            else:
                sample_positions = [
                    int((frame_count - 1) * index / (sample_count - 1))
                    for index in range(sample_count)
                ]

        seen_prefixes: set[bytes] = set()
        for frame_index in sample_positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue

            height, width = frame.shape[:2]
            largest_side = max(height, width)
            if largest_side > _VIDEO_MAX_SIDE and largest_side > 0:
                scale = _VIDEO_MAX_SIDE / float(largest_side)
                frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            ok_encode, encoded = cv2.imencode(
                '.jpg',
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), _VIDEO_JPEG_QUALITY],
            )
            if not ok_encode:
                continue

            frame_bytes = encoded.tobytes()
            fingerprint = frame_bytes[:128]
            if fingerprint in seen_prefixes:
                continue
            seen_prefixes.add(fingerprint)

            timestamp_seconds: float | None = None
            if fps > 0:
                timestamp_seconds = frame_index / fps
            encoded_frames.append((frame_index, timestamp_seconds, frame_bytes))
    finally:
        capture.release()

    return encoded_frames


def _build_video_file_summary(attachment: Attachment) -> str:
    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file() or cv2 is None:
        return ''

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return ''

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_seconds = (frame_count / fps) if fps > 0 else 0.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        capture.release()

    parts: list[str] = [f'Video metadata for {attachment.file_name}:']
    if width > 0 and height > 0:
        parts.append(f'- Resolution: {width}x{height}')
    if frame_count > 0:
        parts.append(f'- Frame count: {frame_count}')
    if fps > 0:
        parts.append(f'- FPS: {fps:.2f}')
    if duration_seconds > 0:
        parts.append(f'- Duration: {duration_seconds:.1f} seconds')

    return '\n'.join(parts)


def _video_keyframe_image_parts(attachment: Attachment, *, max_frames: int) -> list[dict]:
    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return []

    keyframes = _extract_video_keyframes(path, max_frames=max_frames)
    if not keyframes:
        return []

    return [
        {'type': 'image_url', 'image_url': {'url': f"data:image/jpeg;base64,{base64.b64encode(frame_bytes).decode('ascii')}"}}
        for _, _, frame_bytes in keyframes
    ]


async def _analyze_video_with_llm(attachment: Attachment) -> str:
    if not settings.llm_model:
        return ''

    upload_root = _resolve_upload_root()
    path = upload_root / attachment.storage_path
    if not path.exists() or not path.is_file():
        return ''

    keyframes = _extract_video_keyframes(path, max_frames=_VIDEO_MAX_KEYFRAMES)
    if not keyframes:
        return ''

    timeline_parts: list[dict] = []
    for index, (frame_index, timestamp_seconds, frame_bytes) in enumerate(keyframes, start=1):
        if timestamp_seconds is None:
            label = f'Frame {index} (source frame index: {frame_index})'
        else:
            label = f'Frame {index} at ~{timestamp_seconds:.1f}s (source frame index: {frame_index})'

        timeline_parts.append({'type': 'text', 'text': label})
        timeline_parts.append(
            {'type': 'image_url', 'image_url': {'url': f"data:image/jpeg;base64,{base64.b64encode(frame_bytes).decode('ascii')}"}}
        )

    try:
        client = get_async_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are analyzing sampled frames from a user-attached video. '
                        'Prioritize the primary in-video content (application workflow, UI states, user actions, text in the app). '
                        'Ignore recording chrome such as browser tabs, address bars, recording toolbars, uploader UI, and filenames '
                        'unless they are directly relevant to the task being demonstrated. '
                        'Use OCR reasoning for visible in-frame text (labels, buttons, fields, headings, status messages). '
                        'Return plain text only.'
                    ),
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                f"Analyze this video attachment: {attachment.file_name}. "
                                'These are chronological keyframes. Provide: '
                                '1) step-by-step actions in temporal order, '
                                '2) key UI text/controls observed, '
                                '3) workflow context and user intent (what the user is trying to accomplish). '
                                'If something is uncertain because audio is unavailable, state that clearly without guessing.'
                            ),
                        },
                        *timeline_parts,
                    ],
                },
            ],
            temperature=0,
        )
    except Exception:  # noqa: BLE001
        return ''

    content = (response.choices[0].message.content if response.choices else '') or ''
    return content.strip()[:_MAX_CONTEXT_CHARS_PER_FILE]


def _validate_upload(file_name: str, size_bytes: int, kind: str | None) -> str:
    if not file_name:
        raise HTTPException(status_code=400, detail='Attachment file name is required.')
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail='Attachment is empty.')
    if size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f'Attachment exceeds {settings.max_upload_mb} MB limit.')
    resolved_kind = kind or 'file'
    if resolved_kind not in ALLOWED_KINDS:
        resolved_kind = 'file'
    return resolved_kind


async def create_attachment(
    db: AsyncSession,
    *,
    user_id: str,
    thread_id: str,
    upload: UploadFile,
) -> Attachment:
    upload_root = _resolve_upload_root()

    file_name = upload.filename or 'attachment'
    extension = Path(file_name).suffix
    mime_type = upload.content_type or 'application/octet-stream'

    content = await upload.read()
    size_bytes = len(content)
    kind = _validate_upload(file_name, size_bytes, _guess_kind(file_name, mime_type, content))

    relative_folder = Path(user_id) / thread_id
    target_folder = upload_root / relative_folder
    target_folder.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4()}{extension}"
    target_path = target_folder / stored_name
    with target_path.open('wb') as output:
        output.write(content)

    attachment = Attachment(
        user_id=user_id,
        thread_id=thread_id,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        kind=kind,
        storage_path=str((relative_folder / stored_name).as_posix()),
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


async def list_attachments(db: AsyncSession, *, user_id: str, thread_id: str) -> list[Attachment]:
    stmt = (
        select(Attachment)
        .where(Attachment.user_id == user_id, Attachment.thread_id == thread_id)
        .order_by(Attachment.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_attachments_by_ids(
    db: AsyncSession,
    *,
    user_id: str,
    thread_id: str,
    attachment_ids: list[str],
) -> list[Attachment]:
    if not attachment_ids:
        return []
    stmt = select(Attachment).where(
        Attachment.user_id == user_id,
        Attachment.thread_id == thread_id,
        Attachment.id.in_(attachment_ids),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_attachment(db: AsyncSession, *, user_id: str, attachment_id: str) -> bool:
    stmt = select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user_id)
    result = await db.execute(stmt)
    attachment = result.scalar_one_or_none()
    if not attachment:
        return False

    upload_root = _resolve_upload_root()
    target_path = upload_root / attachment.storage_path
    if target_path.exists() and target_path.is_file():
        target_path.unlink()

    await db.delete(attachment)
    await db.commit()
    return True


def to_attachment_out(attachment: Attachment) -> dict:
    return {
        'id': attachment.id,
        'file_name': attachment.file_name,
        'mime_type': attachment.mime_type,
        'size_bytes': attachment.size_bytes,
        'kind': attachment.kind,
        'url': _build_public_url(attachment.storage_path),
        'created_at': attachment.created_at,
    }


def build_attachment_context(attachments: list[Attachment], *, user_query: str | None = None) -> str:
    if not attachments:
        return ''

    lines = [
        'Attachment data for this user message (provided by the application):',
        'Use the extracted content below when the user asks about attached files.',
    ]
    consumed = 0
    for item in attachments:
        kb = max(1, item.size_bytes // 1024)
        lines.append(f"- {item.file_name} ({item.kind}, {item.mime_type}, {kb} KB)")

        item_mime = (item.mime_type or '').lower()
        item_suffix = Path(item.file_name).suffix.lower()
        is_pdf = item_mime == 'application/pdf' or item_suffix == '.pdf'
        is_video = item.kind == 'video' or item_mime.startswith('video/') or item_suffix in _VIDEO_EXTENSIONS

        if is_pdf and user_query:
            excerpt = _build_pdf_section_context(item, user_query)
        else:
            excerpt = _extract_attachment_excerpt(item)
        if not excerpt and is_video:
            excerpt = _build_video_file_summary(item)

        if excerpt and user_query and not is_pdf:
            excerpt = _focus_excerpt_for_query(excerpt, user_query)

        if excerpt and consumed < _MAX_TOTAL_CONTEXT_CHARS:
            remaining = _MAX_TOTAL_CONTEXT_CHARS - consumed
            snippet = excerpt[:remaining]
            consumed += len(snippet)
            lines.append(f"Content excerpt from {item.file_name}:\n{snippet}")
        else:
            lines.append(f"No extractable text was found for {item.file_name}.")

    return '\n'.join(lines)


async def build_attachment_context_async(attachments: list[Attachment], *, user_query: str | None = None) -> str:
    if not attachments:
        return ''

    lines = [
        'Attachment data for this user message (provided by the application):',
        'Use the extracted content below when the user asks about attached files.',
    ]
    consumed = 0

    for item in attachments:
        kb = max(1, item.size_bytes // 1024)
        lines.append(f"- {item.file_name} ({item.kind}, {item.mime_type}, {kb} KB)")

        item_mime = (item.mime_type or '').lower()
        item_suffix = Path(item.file_name).suffix.lower()
        is_pdf = item_mime == 'application/pdf' or item.file_name.lower().endswith('.pdf') or item_suffix == '.pdf'
        is_video = item.kind == 'video' or item_mime.startswith('video/') or item_suffix in _VIDEO_EXTENSIONS
        is_image = (
            item.kind == 'image'
            or item_mime.startswith('image/')
            or item_suffix in {
                '.png', '.jpg', '.jpeg', '.jfif', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif', '.svg'
            }
        )

        if is_pdf and user_query:
            excerpt = _build_pdf_section_context(item, user_query)
        else:
            excerpt = _extract_attachment_excerpt(item)

        if not excerpt and is_pdf:
            excerpt = await _ocr_pdf_with_llm(item)
        elif not excerpt and is_video:
            excerpt = await _analyze_video_with_llm(item)
            if not excerpt:
                excerpt = _build_video_file_summary(item)
        elif not excerpt and is_image:
            excerpt = await _ocr_image_with_llm(item)

        if excerpt and user_query and not is_pdf:
            excerpt = _focus_excerpt_for_query(excerpt, user_query)

        if excerpt and consumed < _MAX_TOTAL_CONTEXT_CHARS:
            remaining = _MAX_TOTAL_CONTEXT_CHARS - consumed
            snippet = excerpt[:remaining]
            consumed += len(snippet)
            lines.append(f"Relevant content excerpt from {item.file_name}:\n{snippet}")
        else:
            lines.append(f"No extractable text was found for {item.file_name}.")

    return '\n'.join(lines)
