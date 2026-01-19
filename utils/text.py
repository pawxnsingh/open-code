import tiktoken


def get_tokenizer(model: str):
    try:
        enc = tiktoken.encoding_for_model(model)
        return enc.encode
    except Exception:
        enc = tiktoken.get_encoding("o200k_base")
        return enc.encode


def count_token(text: str, model: str) -> int:
    tokenizer = get_tokenizer(model=model)
    if tokenizer:
        return len(tokenizer(text))

    return estimate_token(text=text)


def estimate_token(text: str) -> int:
    return max(1, len(text) // 4)
