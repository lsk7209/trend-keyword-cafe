from keybert import KeyBERT
from sentence_transformers import SentenceTransformer


class KeywordExtractor:
    """KeyBERT 다국어 임베딩 기반 키워드 추출기."""

    def __init__(self) -> None:
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.kw_model = KeyBERT(model=model)

    def extract(
        self,
        text: str,
        candidates: list[str] | None = None,
        top_n: int = 5,
    ) -> list[tuple[str, float]]:
        if not text or len(text) < 50:
            return []

        try:
            keywords = self.kw_model.extract_keywords(
                text,
                candidates=candidates,
                keyphrase_ngram_range=(1, 2),
                stop_words=None,
                top_n=top_n,
                use_mmr=True,
                diversity=0.5,
            )
            return [(str(keyword), float(score)) for keyword, score in keywords]
        except Exception as exc:
            print(f"[keyword_extractor] 실패: {exc}")
            return []
