from prompts.system import get_system_prompt
from dataclasses import dataclass
from utils.text import count_token
from typing import Literal, Any


@dataclass
class MessageItem:
    role: Literal["user", "system", "assistant"]
    content: str
    token_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}

        if self.content:
            result["content"] = self.content

        return result


class ContextManager:
    def __init__(self) -> None:
        self._system_prompt = get_system_prompt()
        self._messages: list[MessageItem] = []
        self._model_name = "minimax.minimax-m2"

    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role="user",
            content=content,
            token_count=count_token(
                content,
                model=self._model_name,
            ),
        )

        self._messages.append(item)

    def add_assistant_message(self, content: str) -> None:
        item = MessageItem(
            role="assistant",
            content=content or "",
            token_count=count_token(
                content,
                model=self._model_name,
            ),
        )

        self._messages.append(item)

    def get_message(self) -> list[dict[str, Any]]:
        messages = []

        # appending a system message
        messages.append(
            {
                "role": "system",
                "content": self._system_prompt,
            }
        )

        for item in self._messages:
            messages.append(item.to_dict())

        return messages
