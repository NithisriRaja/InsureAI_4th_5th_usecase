"""Users + sessions (lightweight identity, not security).

- One user per case-insensitive name; picking an existing name with a new role updates it
  and ends that user's other open sessions.
- Sessions slide: each heartbeat pushes ``expires_at`` forward by the idle timeout.
- Heartbeat DB writes are throttled so many open tabs don't churn SQLite.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Session, User
from insurance_poc.utils.clock import utcnow
from insurance_poc.utils.ids import new_id, new_token

HEARTBEAT_WRITE_THROTTLE = timedelta(seconds=30)
ACTIVE_WINDOW = timedelta(minutes=5)
ENDED_RETENTION = timedelta(days=7)


def name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


async def upsert_user(s: AsyncSession, name: str, role: str) -> tuple[User, str | None]:
    """Returns (user, previous_role if it changed)."""
    key = name_key(name)
    user = (await s.execute(select(User).where(User.name_key == key))).scalar_one_or_none()
    if user is None:
        user = User(id=new_id("usr"), name=" ".join(name.split()), name_key=key, role=role)
        try:
            async with s.begin_nested():
                s.add(user)
        except IntegrityError:  # concurrent first login with same name
            user = (await s.execute(select(User).where(User.name_key == key))).scalar_one()
        else:
            return user, None
    previous = None
    if user.role != role:
        previous, user.role = user.role, role
        # Open sessions must not silently gain the new role: end them; the new one has it.
        now = utcnow()
        for sess in (
            await s.execute(
                select(Session).where(Session.user_id == user.id, Session.ended_at.is_(None))
            )
        ).scalars():
            sess.ended_at = now
    return user, previous


async def create_session(
    s: AsyncSession, *, user: User, idle_hours: float, user_agent: str | None
) -> Session:
    now = utcnow()
    sess = Session(
        id=new_token(),
        user_id=user.id,
        user_agent=(user_agent or "")[:255] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=idle_hours),
    )
    s.add(sess)
    return sess


async def get_active(s: AsyncSession, token: str | None) -> tuple[Session, User] | None:
    if not token:
        return None
    row = (
        await s.execute(
            select(Session, User).join(User, User.id == Session.user_id).where(Session.id == token)
        )
    ).first()
    if row is None:
        return None
    sess, user = row
    if sess.ended_at is not None or sess.expires_at <= utcnow():
        return None
    return sess, user


async def touch(s: AsyncSession, sess: Session, idle_hours: float) -> bool:
    """Slide expiry. Returns True if a write happened (throttled)."""
    now = utcnow()
    if now - sess.last_seen_at < HEARTBEAT_WRITE_THROTTLE:
        return False
    sess.last_seen_at = now
    sess.expires_at = now + timedelta(hours=idle_hours)
    return True


async def end(s: AsyncSession, sess: Session) -> None:
    sess.ended_at = utcnow()


async def active_users(s: AsyncSession) -> Sequence[tuple[User, Session]]:
    cutoff = utcnow() - ACTIVE_WINDOW
    q = (
        select(User, Session)
        .join(Session, Session.user_id == User.id)
        .where(Session.ended_at.is_(None), Session.last_seen_at >= cutoff)
        .order_by(Session.last_seen_at.desc())
    )
    seen: set[str] = set()
    out = []
    for user, sess in (await s.execute(q)).all():
        if user.id not in seen:
            seen.add(user.id)
            out.append((user, sess))
    return out


async def purge_expired_sessions(s: AsyncSession) -> int:
    now = utcnow()
    res = await s.execute(
        delete(Session).where(
            or_(
                Session.expires_at < now - ENDED_RETENTION, Session.ended_at < now - ENDED_RETENTION
            )
        )
    )
    return res.rowcount or 0
