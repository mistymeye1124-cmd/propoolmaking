import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_anti_cheat_strict.sqlite3"
os.environ["ADMIN_IDS"] = "99999999"

from aiogram.types import User, CallbackQuery
from bot.database.db import (
    init_db, cast_vote, create_poll, get_candidates, has_user_voted, end_poll
)
from bot.handlers.voting import check_membership, handle_vote


class TestAntiCheatStrict(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists("test_anti_cheat_strict.sqlite3"):
            try:
                os.remove("test_anti_cheat_strict.sqlite3")
            except Exception:
                pass
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_anti_cheat_strict.sqlite3"):
            try:
                os.remove("test_anti_cheat_strict.sqlite3")
            except Exception:
                pass

    async def test_invalid_candidate_rejected(self):
        """Verify that voting for a candidate not belonging to the poll is strictly rejected."""
        poll1_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Channel 1",
            target_chat_username="chan1",
            title="Poll 1",
            candidates=["Alpha", "Beta"]
        )
        poll2_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Channel 1",
            target_chat_username="chan1",
            title="Poll 2",
            candidates=["Gamma", "Delta"]
        )

        cands2 = await get_candidates(poll2_id)
        foreign_candidate_id = cands2[0]["candidate_id"]

        # Attempt to vote in Poll 1 with a candidate from Poll 2
        success, reason = await cast_vote(poll1_id, foreign_candidate_id, user_id=5001)
        self.assertFalse(success)
        self.assertEqual(reason, "INVALID_CANDIDATE")

        # Attempt to vote with non-existent candidate ID
        success_fake, reason_fake = await cast_vote(poll1_id, 999999, user_id=5001)
        self.assertFalse(success_fake)
        self.assertEqual(reason_fake, "INVALID_CANDIDATE")

    async def test_multi_part_contest_single_vote_anti_cheat(self):
        """Verify that a user who votes in Part 1 is strictly prevented from voting in Part 2 of the same contest."""
        part1_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Mega Channel",
            target_chat_username="megachan",
            title="Mega Contest [Part 1]",
            candidates=["Option 1", "Option 2"],
            part_number=1
        )
        part2_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Mega Channel",
            target_chat_username="megachan",
            title="Mega Contest [Part 2]",
            candidates=["Option 3", "Option 4"],
            part_number=2,
            parent_poll_id=part1_id
        )

        cands1 = await get_candidates(part1_id)
        cands2 = await get_candidates(part2_id)

        user_voter_id = 7001

        # Vote in Part 1
        success1, reason1 = await cast_vote(part1_id, cands1[0]["candidate_id"], user_voter_id)
        self.assertTrue(success1)
        self.assertEqual(reason1, "VOTE_CAST")

        # has_user_voted must return True for Part 2 as well!
        already_voted_part2 = await has_user_voted(part2_id, user_voter_id)
        self.assertTrue(already_voted_part2)

        # Attempt to vote in Part 2 must be rejected with ALREADY_VOTED!
        success2, reason2 = await cast_vote(part2_id, cands2[0]["candidate_id"], user_voter_id)
        self.assertFalse(success2)
        self.assertEqual(reason2, "ALREADY_VOTED")

    async def test_invalid_user_id_rejected(self):
        """Verify negative or 0 user IDs are rejected as invalid."""
        poll_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Standard Channel",
            target_chat_username="stdchan",
            title="Standard Poll",
            candidates=["A", "B"]
        )
        cands = await get_candidates(poll_id)
        cid = cands[0]["candidate_id"]

        success0, reason0 = await cast_vote(poll_id, cid, user_id=0)
        self.assertFalse(success0)
        self.assertEqual(reason0, "INVALID_USER")

        success_neg, reason_neg = await cast_vote(poll_id, cid, user_id=-999)
        self.assertFalse(success_neg)
        self.assertEqual(reason_neg, "INVALID_USER")

    async def test_cannot_vote_on_ended_poll(self):
        """Verify that voting on an ended poll is strictly rejected."""
        poll_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Ended Channel",
            target_chat_username="endchan",
            title="Ended Poll Test",
            candidates=["A", "B"]
        )
        cands = await get_candidates(poll_id)
        cid = cands[0]["candidate_id"]

        # Close poll
        await end_poll(poll_id)

        success, reason = await cast_vote(poll_id, cid, user_id=8888)
        self.assertFalse(success)
        self.assertEqual(reason, "POLL_CLOSED")

    async def test_bot_account_handler_rejection(self):
        """Verify that handle_vote rejects any bot accounts immediately."""
        poll_id = await create_poll(
            creator_id=1001,
            target_chat_id=-100111,
            target_chat_title="Bot Channel",
            target_chat_username="botchan",
            title="Bot Shield Poll",
            candidates=["A", "B"]
        )
        cands = await get_candidates(poll_id)
        cid = cands[0]["candidate_id"]

        fake_bot_user = MagicMock(spec=User)
        fake_bot_user.id = 12345
        fake_bot_user.is_bot = True

        cb = AsyncMock(spec=CallbackQuery)
        cb.from_user = fake_bot_user
        cb.data = f"vote:{poll_id}:{cid}"
        cb.answer = AsyncMock()

        await handle_vote(cb)
        cb.answer.assert_called_once()
        self.assertIn("বট", cb.answer.call_args[0][0])

        # Verify 0 votes cast
        cands_after = await get_candidates(poll_id)
        self.assertEqual(cands_after[0]["votes_count"], 0)


if __name__ == "__main__":
    unittest.main()
