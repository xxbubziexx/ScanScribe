"""add_chat_tables

Revision ID: a0c81eb53031
Revises: a95e5b291054
Create Date: 2026-10-14 16:23:14.225779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0c81eb53031'
down_revision: Union[str, Sequence[str], None] = 'a95e5b291054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add chat_threads and chat_messages."""
    op.create_table(
        'chat_threads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='New Query'),
        sa.Column('time_scope_preset', sa.String(length=50), nullable=False, server_default='today'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('talkgroups', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chat_threads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_threads_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_threads_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_threads_updated_at'), ['updated_at'], unique=False)

    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('cited_log_ids', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_messages_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_messages_thread_id'), ['thread_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_messages_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema: remove chat_messages and chat_threads."""
    op.drop_table('chat_messages')
    op.drop_table('chat_threads')
