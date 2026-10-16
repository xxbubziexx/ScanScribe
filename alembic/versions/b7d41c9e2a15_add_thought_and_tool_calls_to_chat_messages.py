"""add_thought_and_tool_calls_to_chat_messages

Revision ID: b7d41c9e2a15
Revises: a0c81eb53031
Create Date: 2026-10-15 19:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d41c9e2a15'
down_revision: Union[str, Sequence[str], None] = 'a0c81eb53031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: persist agent reasoning trace and tool execution records."""
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thought', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('tool_calls', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: remove thought and tool_calls columns."""
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_column('tool_calls')
        batch_op.drop_column('thought')
