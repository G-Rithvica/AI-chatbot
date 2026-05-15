from typing import TypedDict


class ChatTurn(TypedDict):
    role: str
    content: str


def build_memory_window(messages: list[ChatTurn], max_previous_conversations: int = 5) -> list[ChatTurn]:
    """Return system + dialog messages constrained to previous-N conversations.

    The input is expected to include the latest user prompt already persisted.
    The returned window includes that latest prompt plus up to N previous user turns.
    """
    if max_previous_conversations < 0:
        max_previous_conversations = 0

    normalized = [
        {'role': item['role'], 'content': item['content']}
        for item in messages
        if item.get('role') in {'system', 'user', 'assistant'} and bool(item.get('content'))
    ]

    if not normalized:
        return []

    system_messages = [item for item in normalized if item['role'] == 'system']
    dialog_messages = [item for item in normalized if item['role'] in {'user', 'assistant'}]

    user_indexes = [index for index, item in enumerate(dialog_messages) if item['role'] == 'user']
    allowed_user_turns = max_previous_conversations + 1

    if not user_indexes or len(user_indexes) <= allowed_user_turns:
        return [*system_messages, *dialog_messages]

    start_dialog_index = user_indexes[-allowed_user_turns]
    return [*system_messages, *dialog_messages[start_dialog_index:]]
