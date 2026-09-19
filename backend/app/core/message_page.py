"""Shared paging for the chat history endpoints.

The chat views open on the newest messages and pull older ones in as the reader
scrolls up, so the history endpoints hand back one page plus a `has_more` flag
instead of every row in the chat.

Rows are paged by primary key, not by `created_at`: timestamps are not unique
(bulk inserts share one), which makes them useless as a cursor. `id` follows
insertion order, and for every chat in the database the two orders agree.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.message import Message

# Rows that only mean something while debugging a run. The conversation view
# hides them, so a normal read of a chat has no use for them.
DEBUG_MESSAGE_TYPES = ("tool", "flow")


def paginate_messages(
    db: Session,
    chat_id: int,
    limit: Optional[int] = None,
    before_id: Optional[int] = None,
    include_debug: bool = True,
) -> dict:
    """Return one page of a chat history, oldest row first.

    `before_id` walks backwards: the caller passes the id of the oldest row it
    already holds and gets the `limit` rows directly before it. Without it the
    newest page comes back. `limit=None` keeps the old "give me everything"
    behaviour for callers that genuinely need the whole chat.

    One row more than asked for is read: its presence is what tells the caller
    there is more history, which avoids a second COUNT query.
    """
    query = db.query(Message).filter(Message.chat_id == chat_id)
    if before_id is not None:
        query = query.filter(Message.id < before_id)
    if not include_debug:
        # message_type is nullable, and `not in` silently drops NULL rows even
        # though they are ordinary messages, so they are matched explicitly.
        query = query.filter(
            (Message.message_type.is_(None))
            | (Message.message_type.notin_(DEBUG_MESSAGE_TYPES))
        )

    if limit is None:
        return {"messages": query.order_by(Message.id).all(), "has_more": False}

    rows = query.order_by(Message.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    page.reverse()
    return {"messages": page, "has_more": has_more}
