from app.services.token_counter import count_tokens


class Chunker:
    def chunk_text(self, text: str, max_tokens: int = 800, overlap_tokens: int = 100) -> list[str]:
        words = (text or '').split()
        if not words:
            return []

        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for word in words:
            token_count = count_tokens(word)
            if current_tokens + token_count > max_tokens and current:
                chunks.append(' '.join(current))
                overlap_words = current[-min(len(current), overlap_tokens):]
                current = overlap_words.copy()
                current_tokens = count_tokens(' '.join(current))
            current.append(word)
            current_tokens += token_count

        if current:
            chunks.append(' '.join(current))
        return chunks
