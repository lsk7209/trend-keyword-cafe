from kiwipiepy import Kiwi


class KoreanNLP:
    """Kiwi 기반 한국어 명사 후보 추출기."""

    def __init__(self) -> None:
        self.kiwi = Kiwi()
        self.stopwords = {
            "기자",
            "뉴스",
            "일보",
            "신문",
            "방송",
            "오늘",
            "어제",
            "내일",
            "지난",
            "관련",
            "해당",
            "이번",
            "지난번",
            "사진",
            "제공",
            "무단",
            "전재",
            "배포",
            "금지",
        }

    def extract_nouns(self, text: str, min_length: int = 2) -> list[str]:
        if not text:
            return []

        nouns: list[str] = []
        for token in self.kiwi.tokenize(text):
            if (
                token.tag in {"NNG", "NNP"}
                and len(token.form) >= min_length
                and token.form not in self.stopwords
            ):
                nouns.append(token.form)
        return nouns
