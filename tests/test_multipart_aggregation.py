import asyncio
import unittest
from datetime import datetime
from bot.database.db import (
    init_db, create_poll, add_candidates_to_poll, get_poll, get_poll_parts,
    get_multi_part_aggregated_results, end_poll
)
from bot.templates import format_winners_display, render_winner_announcement
from bot.database.db import get_db

class TestMultiPartAggregation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def test_multipart_creation_and_aggregation(self):
        creator_id = 99887766
        # Create Part 1
        part1_id = await create_poll(
            creator_id=creator_id,
            target_chat_id=-1001234567,
            target_chat_title="Test Giveaway Channel",
            target_chat_username="testchannel",
            title="Mega Giveaway 2026 [Part 1]",
            candidates=["Candidate A (P1)", "Candidate B (P1)"],
            winner_count=3,
            part_number=1
        )

        # Create Part 2 linked to Part 1
        part2_id = await create_poll(
            creator_id=creator_id,
            target_chat_id=-1001234567,
            target_chat_title="Test Giveaway Channel",
            target_chat_username="testchannel",
            title="Mega Giveaway 2026 [Part 2]",
            candidates=["Candidate C (P2)", "Candidate D (P2)"],
            winner_count=3,
            parent_poll_id=part1_id,
            part_number=2
        )

        # Create Part 3 linked to Part 1
        part3_id = await create_poll(
            creator_id=creator_id,
            target_chat_id=-1001234567,
            target_chat_title="Test Giveaway Channel",
            target_chat_username="testchannel",
            title="Mega Giveaway 2026 [Part 3]",
            candidates=["Candidate E (P3)", "Candidate F (P3)"],
            winner_count=3,
            parent_poll_id=part1_id,
            part_number=3
        )

        # Verify get_poll_parts from any part returns all 3 parts
        parts_from_1 = await get_poll_parts(part1_id)
        parts_from_2 = await get_poll_parts(part2_id)
        parts_from_3 = await get_poll_parts(part3_id)
        self.assertEqual(len(parts_from_1), 3)
        self.assertEqual(len(parts_from_2), 3)
        self.assertEqual(len(parts_from_3), 3)

        # Inject vote counts directly for testing
        async with get_db() as db:
            await db.execute("UPDATE candidates SET votes_count = 10 WHERE poll_id = ? AND name = 'Candidate A (P1)'", (part1_id,))
            await db.execute("UPDATE candidates SET votes_count = 5 WHERE poll_id = ? AND name = 'Candidate B (P1)'", (part1_id,))
            await db.execute("UPDATE candidates SET votes_count = 50 WHERE poll_id = ? AND name = 'Candidate C (P2)'", (part2_id,))
            await db.execute("UPDATE candidates SET votes_count = 12 WHERE poll_id = ? AND name = 'Candidate D (P2)'", (part2_id,))
            await db.execute("UPDATE candidates SET votes_count = 35 WHERE poll_id = ? AND name = 'Candidate E (P3)'", (part3_id,))
            await db.execute("UPDATE candidates SET votes_count = 2 WHERE poll_id = ? AND name = 'Candidate F (P3)'", (part3_id,))
            await db.commit()

        # Query aggregated results from Part 2 (should find all connected parts)
        agg = await get_multi_part_aggregated_results(part2_id)
        self.assertTrue(agg["is_multi_part"])
        self.assertEqual(agg["total_votes"], 10 + 5 + 50 + 12 + 35 + 2)  # 114 votes
        self.assertEqual(len(agg["all_candidates"]), 6)

        # Winner count is 3: Top 3 should be:
        # #1: Candidate C (50 votes, Part 2)
        # #2: Candidate E (35 votes, Part 3)
        # #3: Candidate D (12 votes, Part 2)
        top_winners = agg["top_winners"]
        self.assertEqual(len(top_winners), 3)
        self.assertIn("Candidate C", top_winners[0]["name"])
        self.assertEqual(top_winners[0]["votes_count"], 50)
        self.assertEqual(top_winners[0]["part_number"], 2)

        self.assertIn("Candidate E", top_winners[1]["name"])
        self.assertEqual(top_winners[1]["votes_count"], 35)
        self.assertEqual(top_winners[1]["part_number"], 3)

        self.assertIn("Candidate D", top_winners[2]["name"])
        self.assertEqual(top_winners[2]["votes_count"], 12)
        self.assertEqual(top_winners[2]["part_number"], 2)

        # Test format_winners_display in Bengali
        text_bn = format_winners_display(top_winners, lang="bn", is_multi_part=True)
        self.assertIn("সকল পর্ব মিলিয়ে", text_bn)
        self.assertIn("পর্ব ২", text_bn)
        self.assertIn("পর্ব ৩", text_bn)
        self.assertIn("50", text_bn)

        # Test format_winners_display in English
        text_en = format_winners_display(top_winners, lang="en", is_multi_part=True)
        self.assertIn("Across All Connected Parts", text_en)
        self.assertIn("Part 2", text_en)
        self.assertIn("Part 3", text_en)
        self.assertIn("50", text_en)

        # Test simultaneous closing: Ending connected parts
        parts = await get_poll_parts(part2_id)
        for p in parts:
            if p["status"] == "active":
                await end_poll(p["poll_id"])

        p1_after = await get_poll(part1_id)
        p2_after = await get_poll(part2_id)
        p3_after = await get_poll(part3_id)
        self.assertEqual(p1_after["status"], "ended")
        self.assertEqual(p2_after["status"], "ended")
        self.assertEqual(p3_after["status"], "ended")

if __name__ == "__main__":
    unittest.main()
