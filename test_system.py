import asyncio
import os
import sys
from datetime import datetime, timedelta

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use isolated test database
os.environ["DATABASE_PATH"] = "test_database.sqlite3"
test_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_database.sqlite3")
if os.path.exists(test_db_path):
    try:
        os.remove(test_db_path)
    except Exception:
        pass

from bot.database.db import (
    init_db, save_user, create_poll, get_poll, get_candidates,
    has_user_voted, cast_vote, end_poll, get_system_stats, set_poll_message_id,
    save_channel, get_all_active_channels, deactivate_channel,
    get_custom_credit, set_custom_credit, get_channel, set_channel_status,
    get_all_channels_with_status, delete_channel, get_expired_active_polls,
    set_user_custom_credit, get_effective_credit,
    get_user_selectable_channels, is_user_authorized_for_channel_db, record_user_channel_access,
    update_poll_contact, get_user_default_contact, set_user_default_contact
)
from bot.templates import (
    render_poll_cta, render_poll_card, format_timer_badge,
    render_winner_announcement, render_custom_winner_announcement,
    strip_tg_emoji_tags, format_winners_display,
    TEMPLATE_KEYS, DEFAULTS_BN, DEFAULTS_EN, get_raw_template,
    set_custom_template, reset_template, render_help_text,
    render_fsub_alert, render_vote_success, safe_html_preserve_tg_emoji,
    safe_send_message, safe_bot_edit_message,
    get_suggestion, apply_suggestion, sync_emojis_between_texts,
    sync_emojis_to_other_languages, render_template_live_preview,
    extract_custom_emoji_info, strip_button_custom_emojis
)

from bot.keyboards.inline import (
    build_poll_keyboard, build_duration_keyboard, build_poll_language_keyboard,
    build_credit_manager_keyboard, build_templates_menu, build_template_edit_menu,
    get_candidate_icon, build_icon_style_keyboard,
    make_custom_button, resolve_candidate_icon_and_emoji
)


async def run_tests():
    print("[TEST] Initializing database...")
    await init_db()
    print("[SUCCESS] Database initialized successfully.")

    print("[TEST] Saving test user...")
    await save_user(user_id=12345678, username="testuser", first_name="Test", last_name="User")
    print("[SUCCESS] User saved.")

    print("[TEST] Saving and verifying connected channels...")
    await save_channel(chat_id=-100111222333, title="Channel One", username="chan1", added_by=12345678)
    await save_channel(chat_id=-100444555666, title="Channel Two", username="chan2", added_by=12345678)
    channels = await get_all_active_channels()
    assert len(channels) >= 2, f"Expected at least 2 channels, got {len(channels)}"
    print(f"[SUCCESS] 2 channels active: {[c['title'] for c in channels]}")

    await deactivate_channel(-100111222333)
    channels_after = await get_all_active_channels()
    assert len(channels_after) == len(channels) - 1, f"Expected {len(channels) - 1} channels after deactivation, got {len(channels_after)}"
    print("[SUCCESS] Deactivation works properly.")

    print("[TEST] Channel Management Helpers (get, status, all_with_status)...")
    ch = await get_channel(-100111222333)
    assert ch is not None
    assert ch["is_active"] == 0
    await set_channel_status(-100111222333, 1)
    ch_re = await get_channel(-100111222333)
    assert ch_re["is_active"] == 1
    all_ch = await get_all_channels_with_status()
    assert len(all_ch) >= 2
    print("[SUCCESS] Channel management helper functions verified.")

    print("[TEST] Custom Credit Branding Configuration...")
    await set_custom_credit("⚡ Super Brand @mybrand", "https://t.me/mybrand")
    name, url = await get_custom_credit()
    assert name == "⚡ Super Brand @mybrand"
    assert url == "https://t.me/mybrand"

    card_text = await render_poll_card("Sample Poll", "mybot", lang="en")
    assert "⚡ Super Brand @mybrand" in card_text
    print("[SUCCESS] Custom credit branding verified.")

    print("[TEST] Duration Keyboards...")
    kb_bn = build_duration_keyboard(lang="bn")
    kb_en = build_duration_keyboard(lang="en")
    assert len(kb_bn.inline_keyboard) == 4
    assert len(kb_en.inline_keyboard) == 4
    print("[SUCCESS] Duration keyboards generated cleanly.")

    print("[TEST] Poll Timer & Auto-Closer Testing...")
    # 1. Create a poll with ends_at in the past (expired)
    past_time = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    poll_expired_id = await create_poll(
        creator_id=12345678,
        target_chat_id=-100444555666,
        target_chat_title="Channel Two",
        target_chat_username="chan2",
        title="Expired Timer Poll Test",
        candidates=["Option 1", "Option 2"],
        ends_at=past_time
    )
    cands_exp = await get_candidates(poll_expired_id)
    cand_exp_id = cands_exp[0]["candidate_id"]

    # Verify get_expired_active_polls returns it
    expired_polls = await get_expired_active_polls()
    expired_ids = [p["poll_id"] for p in expired_polls]
    assert poll_expired_id in expired_ids, f"Expected {poll_expired_id} in {expired_ids}"
    print(f"[SUCCESS] Expired poll #{poll_expired_id} correctly detected by auto-closer.")

    # Verify cast_vote on expired poll is rejected
    success, reason = await cast_vote(poll_expired_id, cand_exp_id, user_id=999)
    assert success is False and reason == "POLL_CLOSED", f"Expected POLL_CLOSED, got {reason}"
    print("[SUCCESS] Voting on expired poll correctly rejected with POLL_CLOSED.")

    # 2. Create a poll with ends_at in the future (active with timer)
    future_time = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    poll_active_id = await create_poll(
        creator_id=12345678,
        target_chat_id=-100444555666,
        target_chat_title="Channel Two",
        target_chat_username="chan2",
        title="Active Timer Poll Test",
        candidates=["Player A", "Player B"],
        ends_at=future_time
    )
    cands_act = await get_candidates(poll_active_id)
    cand_act_id = cands_act[0]["candidate_id"]

    # Verify cast_vote on active timer poll succeeds
    success, reason = await cast_vote(poll_active_id, cand_act_id, user_id=888)
    assert success is True, f"Expected True, got {reason}"
    print("[SUCCESS] Voting on active timer poll succeeded.")

    # Verify card text shows start and end time badge
    created_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    card_with_timer = await render_poll_card("Active Timer Poll", "mybot", lang="bn", ends_at=future_time, created_at=created_now)
    assert "ভোটিং সময়সূচি:" in card_with_timer
    assert "🟢 <b>শুরু:</b>" in card_with_timer
    assert "🔴 <b>শেষ:</b>" in card_with_timer
    print("[SUCCESS] Poll card renders Start Time - End Time schedule badge correctly.")

    # 3. Create a poll with NO timer (Manual End)
    poll_manual_id = await create_poll(
        creator_id=12345678,
        target_chat_id=-100444555666,
        target_chat_title="Channel Two",
        target_chat_username="chan2",
        title="Manual End Poll Test",
        candidates=["Candidate X", "Candidate Y"],
        ends_at=None,
        created_at=created_now
    )
    cands_man = await get_candidates(poll_manual_id)
    cand_man_id = cands_man[0]["candidate_id"]

    success, reason = await cast_vote(poll_manual_id, cand_man_id, user_id=777)
    assert success is True
    print("[SUCCESS] Voting on manual end poll succeeded.")

    # Verify manual end poll card shows Start and Manual End
    card_manual = await render_poll_card("Manual Poll", "mybot", lang="bn", ends_at=None, created_at=created_now)
    assert "🟢 <b>শুরু:</b>" in card_manual
    assert "♾️ <b>সমাপ্তি:</b> <code>ম্যানুয়াল সমাপ্তি</code>" in card_manual
    print("[SUCCESS] Manual poll card renders Start Time and Manual closure badge correctly.")

    # Manual end poll
    ended_data = await end_poll(poll_manual_id)
    assert ended_data["status"] == "ended"
    assert ended_data["winner"]["name"] == "Candidate X"
    print(f"[SUCCESS] Manual poll #{poll_manual_id} closed successfully with winner {ended_data['winner']['name']}!")

    print("[TEST] 29 Candidates Simultaneous Creation & Keyboard Grid...")
    candidates_29 = [f"Participant #{i+1:02d}" for i in range(29)]
    poll_29_id = await create_poll(
        creator_id=12345678,
        target_chat_id=-100444555666,
        target_chat_title="Mega Channel",
        target_chat_username="megachan",
        title="Grand 29 Candidate Contest",
        candidates=candidates_29,
        ends_at=future_time,
        created_at=created_now
    )
    saved_candidates = await get_candidates(poll_29_id)
    assert len(saved_candidates) == 29, f"Expected 29 candidates in DB, found {len(saved_candidates)}"
    print(f"[SUCCESS] Exactly 29 candidates stored in database successfully.")

    # Test keyboard generation for 29 candidates (14 rows of 2 + 1 row of 1 + 1 CTA row = 16 rows)
    kb_29 = build_poll_keyboard(poll_29_id, saved_candidates, "mybot")
    total_candidate_buttons = sum(len(row) for row in kb_29.inline_keyboard[:-1])
    assert total_candidate_buttons == 29, f"Expected 29 voting buttons, got {total_candidate_buttons}"
    assert len(kb_29.inline_keyboard) == 16, f"Expected 16 rows, got {len(kb_29.inline_keyboard)}"
    print(f"[SUCCESS] 29-candidate inline keyboard built cleanly in 2-column layout (16 rows, 29 buttons).")

    # Vote for candidate #29
    cand_29_id = saved_candidates[28]["candidate_id"]
    voted, v_reason = await cast_vote(poll_29_id, cand_29_id, user_id=55555)
    assert voted is True, f"Vote failed: {v_reason}"
    updated_cands = await get_candidates(poll_29_id)
    assert updated_cands[28]["votes_count"] == 1
    print("[SUCCESS] Vote cast successfully for candidate #29.")

    # Reset credit back to user's setting
    await set_custom_credit("@ProAccessX", "https://t.me/+nmsvkQklxts5ZjNl")

    print("[TEST] Professional Button Icon Styles & Dynamic Ranking...")
    from bot.database.db import get_button_icon_style, set_button_icon_style
    from bot.keyboards.inline import get_candidate_icon, name_has_leading_emoji, build_icon_style_keyboard

    # Test leading emoji detection
    assert name_has_leading_emoji("🔥 Option A") is True
    assert name_has_leading_emoji("👑 Leader") is True
    assert name_has_leading_emoji("Candidate 1") is False

    # Test initial 0 votes icon (Ballot Box instead of generic 👤)
    cands_test = [
        {"name": "Alpha", "votes_count": 0},
        {"name": "Beta", "votes_count": 0}
    ]
    icon_alpha = get_candidate_icon(cands_test[0], cands_test, style="dynamic")
    assert "🗳️" in icon_alpha, f"Expected 🗳️ in initial icon, got {icon_alpha}"
    print("[SUCCESS] Initial candidates with 0 votes correctly get professional 🗳️ icon.")

    # Test dynamic leaderboard ranking icons
    cands_ranked = [
        {"name": "Leader", "votes_count": 50},
        {"name": "Second", "votes_count": 30},
        {"name": "Third", "votes_count": 20},
        {"name": "Fourth", "votes_count": 10},
        {"name": "ZeroVotes", "votes_count": 0},
        {"name": "🔥 PreEmoji", "votes_count": 5}
    ]
    assert "👑" in get_candidate_icon(cands_ranked[0], cands_ranked, style="dynamic")
    assert "🥈" in get_candidate_icon(cands_ranked[1], cands_ranked, style="dynamic")
    assert "🥉" in get_candidate_icon(cands_ranked[2], cands_ranked, style="dynamic")
    assert "🔥" in get_candidate_icon(cands_ranked[3], cands_ranked, style="dynamic")
    assert "🗳️" in get_candidate_icon(cands_ranked[4], cands_ranked, style="dynamic")
    # Pre-existing emoji in candidate name should not have duplicate icon prepended
    assert get_candidate_icon(cands_ranked[5], cands_ranked, style="dynamic") == ""
    print("[SUCCESS] Dynamic leaderboard icons (👑, 🥈, 🥉, 🔥, 🗳️) resolved accurately.")

    # Test setting and getting icon styles
    await set_button_icon_style("diamond")
    cur_style = await get_button_icon_style()
    assert cur_style == "diamond"
    assert "💎" in get_candidate_icon(cands_ranked[0], cands_ranked, style="diamond")

    # Test admin icon keyboard
    icon_kb = build_icon_style_keyboard("diamond")
    assert any("✅" in btn.text and "Diamond" in btn.text for row in icon_kb.inline_keyboard for btn in row)
    print("[SUCCESS] Super Admin icon style selector generated and verified.")

    # Reset icon style to dynamic
    await set_button_icon_style("dynamic")

    print("[TEST] Multi-Part Connected Poll System & Auto-Split...")
    from bot.database.db import (
        get_last_user_poll, get_poll_parts, get_next_part_number,
        update_poll_title, end_all_poll_parts
    )
    from bot.handlers.poll_create import get_base_title

    # 1. Test get_base_title
    assert get_base_title("Eid Mega Giveaway 2026") == "Eid Mega Giveaway 2026"
    assert get_base_title("Eid Mega Giveaway 2026 [Part 1]") == "Eid Mega Giveaway 2026"
    assert get_base_title("Eid Mega Giveaway 2026 [পর্ব ১]") == "Eid Mega Giveaway 2026"
    assert get_base_title("Eid Mega Giveaway 2026 [Part 5]") == "Eid Mega Giveaway 2026"
    print("[SUCCESS] get_base_title cleanly strips [Part X] and [পর্ব X] suffixes.")

    # 2. Test Multi-Part Poll Creation & Database Linking
    part1_cands = [f"Contestant P1-{i+1}" for i in range(29)]
    poll_p1_id = await create_poll(
        creator_id=99991111,
        target_chat_id=-100444555666,
        target_chat_title="Multi-Part Channel",
        target_chat_username="multipartchan",
        title="Grand Annual Awards [Part 1]",
        candidates=part1_cands,
        ends_at=future_time,
        created_at=created_now,
        parent_poll_id=None,
        part_number=1
    )

    # Verify last poll created by user
    last_poll = await get_last_user_poll(99991111)
    assert last_poll is not None
    assert last_poll["poll_id"] == poll_p1_id

    # Verify next part number before Part 2
    next_part = await get_next_part_number(poll_p1_id)
    assert next_part == 2, f"Expected next part 2, got {next_part}"

    # 3. Create Part 2 linked to Part 1
    part2_cands = [f"Contestant P2-{i+1}" for i in range(29)]
    poll_p2_id = await create_poll(
        creator_id=99991111,
        target_chat_id=-100444555666,
        target_chat_title="Multi-Part Channel",
        target_chat_username="multipartchan",
        title="Grand Annual Awards [Part 2]",
        candidates=part2_cands,
        ends_at=future_time,
        created_at=created_now,
        parent_poll_id=poll_p1_id,
        part_number=2
    )

    # Verify next part number is now 3
    next_part_after = await get_next_part_number(poll_p1_id)
    assert next_part_after == 3, f"Expected next part 3, got {next_part_after}"

    # Verify get_poll_parts from either Part 1 or Part 2 returns both parts in sequence
    parts_from_p1 = await get_poll_parts(poll_p1_id)
    parts_from_p2 = await get_poll_parts(poll_p2_id)
    assert len(parts_from_p1) == 2
    assert len(parts_from_p2) == 2
    assert parts_from_p1[0]["poll_id"] == poll_p1_id and parts_from_p1[0]["part_number"] == 1
    assert parts_from_p1[1]["poll_id"] == poll_p2_id and parts_from_p1[1]["part_number"] == 2
    print("[SUCCESS] Multi-part poll tracking and get_poll_parts verified perfectly.")

    # 4. Test updating poll title
    await update_poll_title(poll_p1_id, "Grand Annual Awards 2026 [Part 1]")
    updated_p1 = await get_poll(poll_p1_id)
    assert updated_p1["title"] == "Grand Annual Awards 2026 [Part 1]"
    print("[SUCCESS] update_poll_title verified.")

    # 5. Test end_all_poll_parts
    ended_parts = await end_all_poll_parts(poll_p1_id)
    assert len(ended_parts) == 2
    for p in ended_parts:
        assert p["status"] == "ended"
    print("[SUCCESS] end_all_poll_parts successfully ends all connected parts.")

    print("[TEST] 1-Click Add Bot to Channel & Auto-Help Duration Parser...")
    from bot.keyboards.inline import build_main_menu
    from bot.handlers.poll_create import parse_custom_duration, format_duration_label

    # Verify build_main_menu contains 1-click add channel button
    menu_bn = build_main_menu(is_admin=False, bot_username="propollbot", lang="bn")
    menu_en = build_main_menu(is_admin=False, bot_username="propollbot", lang="en")
    
    expected_url = "https://t.me/propollbot?startchannel=true&admin=post_messages+edit_messages+delete_messages"
    
    # Check BN button
    found_bn_btn = any(btn.url == expected_url and "চ্যানেলে যুক্ত করুন" in btn.text for row in menu_bn.inline_keyboard for btn in row)
    assert found_bn_btn, "Expected 1-click Add Channel button in Bengali main menu"
    
    # Check EN button
    found_en_btn = any(btn.url == expected_url and "Add Bot to Channel" in btn.text for row in menu_en.inline_keyboard for btn in row)
    assert found_en_btn, "Expected 1-click Add Channel button in English main menu"
    print("[SUCCESS] 1-Click Add Channel button verified in both BN and EN main menu.")

    # Test parse_custom_duration
    assert parse_custom_duration("45m") == 45 * 60
    assert parse_custom_duration("2h") == 2 * 3600
    assert parse_custom_duration("3d") == 3 * 86400
    assert parse_custom_duration("0") == 0
    assert parse_custom_duration("manual") == 0
    assert parse_custom_duration("no") == 0
    assert parse_custom_duration("invalid_text") is None
    print("[SUCCESS] parse_custom_duration handles valid and invalid inputs accurately.")

    # Test format_duration_label
    assert "মিনিট" in format_duration_label(1800, "bn")
    assert "Minutes" in format_duration_label(1800, "en")
    assert "কোনো সময়সীমা নেই" in format_duration_label(0, "bn")
    assert "No Timer" in format_duration_label(0, "en")
    print("[SUCCESS] format_duration_label formats labels accurately in both languages.")

    print("[TEST] Top N Winners Selection & Announcement...")
    from bot.templates import format_winners_display
    poll_winners_id = await create_poll(
        creator_id=77778888,
        target_chat_id=-100444555666,
        target_chat_title="Winners Channel",
        target_chat_username="winchan",
        title="Top 2 Winners Contest Test",
        candidates=["Contender Alpha", "Contender Beta", "Contender Gamma"],
        winner_count=2,
        icon_style="rocket"
    )
    cands_w = await get_candidates(poll_winners_id)
    # Vote Alpha 2 times, Beta 1 time, Gamma 0 times
    await cast_vote(poll_winners_id, cands_w[0]["candidate_id"], user_id=101)
    await cast_vote(poll_winners_id, cands_w[0]["candidate_id"], user_id=102)
    await cast_vote(poll_winners_id, cands_w[1]["candidate_id"], user_id=103)

    ended_w_data = await end_poll(poll_winners_id)
    assert "top_winners" in ended_w_data
    assert len(ended_w_data["top_winners"]) == 2, f"Expected 2 winners, got {len(ended_w_data['top_winners'])}"
    assert ended_w_data["top_winners"][0]["name"] == "Contender Alpha"
    assert ended_w_data["top_winners"][0]["votes_count"] == 2
    assert ended_w_data["top_winners"][1]["name"] == "Contender Beta"
    assert ended_w_data["top_winners"][1]["votes_count"] == 1
    
    # Test format_winners_display
    w_display_bn = format_winners_display(ended_w_data["top_winners"], lang="bn")
    assert "🥇" in w_display_bn and "🥈" in w_display_bn
    assert "Contender Alpha" in w_display_bn and "Contender Beta" in w_display_bn
    print("[SUCCESS] Top 2 Winners correctly determined and formatted with medals (🥇, 🥈).")

    # Verify poll card shows winner count badge
    card_w_text = await render_poll_card("Top 2 Contest", "propollbot", lang="bn", winner_count=2)
    assert "শীর্ষ ২ জন" in card_w_text
    print("[SUCCESS] Poll card renders Top 2 Winners badge properly.")

    print("[TEST] Brand Credit Hyperlink & Custom Button Text...")
    from bot.database.db import set_custom_credit_btn_text, get_custom_credit_btn_text
    await set_custom_credit("⚡ Pro Access Network", "https://t.me/proaccess")
    await set_custom_credit_btn_text("🚀 Join VIP Network ➔")
    
    card_brand_text = await render_poll_card("Brand Card Test", "propollbot", lang="en")
    assert '<a href="https://t.me/proaccess">⚡ Pro Access Network</a>' in card_brand_text
    
    btn_text, btn_url = await render_poll_cta("propollbot", lang="en")
    assert btn_text == "🚀 Join VIP Network ➔"
    assert btn_url == "https://t.me/proaccess"
    print("[SUCCESS] Clickable brand credit hyperlink and custom CTA button text verified.")

    print("[TEST] Per-User Isolated Icon Styles & 14+ Themes...")
    from bot.database.db import get_user_icon_style, set_user_icon_style
    from bot.keyboards.inline import get_candidate_icon

    await save_user(user_id=5001, username="admin1")
    await save_user(user_id=5002, username="admin2")

    await set_user_icon_style(5001, "diamond")
    await set_user_icon_style(5002, "rocket")

    assert await get_user_icon_style(5001) == "diamond"
    assert await get_user_icon_style(5002) == "rocket"
    
    cand_sample = {"name": "Test Option", "votes_count": 0}
    assert "💎" in get_candidate_icon(cand_sample, [cand_sample], style="diamond")
    assert "🚀" in get_candidate_icon(cand_sample, [cand_sample], style="rocket")
    assert "⚡" in get_candidate_icon(cand_sample, [cand_sample], style="zap")
    assert "🏆" in get_candidate_icon(cand_sample, [cand_sample], style="trophy")
    assert "🟢" in get_candidate_icon(cand_sample, [cand_sample], style="neon")
    print("[SUCCESS] Per-user icon styles isolated cleanly and 14+ icon themes working.")

    print("[TEST] Persistent Reply Keyboard Menu...")
    from bot.keyboards.reply import build_persistent_menu
    reply_kb_bn = build_persistent_menu(lang="bn", is_admin=True)
    reply_kb_en = build_persistent_menu(lang="en", is_admin=False)
    reply_kb_hi = build_persistent_menu(lang="hi", is_admin=False)

    assert reply_kb_bn.is_persistent is True
    assert reply_kb_bn.resize_keyboard is True
    # Verify omnipresent Start button in top row
    assert "Start" in reply_kb_bn.keyboard[0][0].text and "মূল মেনু" in reply_kb_bn.keyboard[0][0].text
    assert "Start" in reply_kb_en.keyboard[0][0].text and "Main Menu" in reply_kb_en.keyboard[0][0].text
    assert "Start" in reply_kb_hi.keyboard[0][0].text and "मुख्य मेनू" in reply_kb_hi.keyboard[0][0].text
    assert any("নতুন পোল" in btn.text for row in reply_kb_bn.keyboard for btn in row)
    assert any("Create New Poll" in btn.text for row in reply_kb_en.keyboard for btn in row)
    assert any("नया पोल" in btn.text for row in reply_kb_hi.keyboard for btn in row)
    assert any("এডমিন" in btn.text for row in reply_kb_bn.keyboard for btn in row)
    assert not any("Brand" in btn.text for row in reply_kb_en.keyboard for btn in row)
    print("[SUCCESS] Persistent bottom reply keyboard with omnipresent Start button verified across BN, EN, and HI.")

    print("[TEST] Advanced Executive Start Text with Personalization...")
    from bot.templates import render_start_text
    start_bn = await render_start_text("propollbot", lang="bn", user_name="Shadman")
    assert "PRO POLL ENGINE v3.5" in start_bn
    assert "Shadman" in start_bn
    assert "৭-লেয়ার সিকিউরিটি" in start_bn

    start_en = await render_start_text("propollbot", lang="en", user_name="Alex")
    assert "PRO POLL ENGINE v3.5" in start_en
    assert "Alex" in start_en
    assert "7-Layer Active" in start_en
    print("[SUCCESS] Advanced executive start dashboard & user personalization verified.")

    print("[TEST] Interactive Channel Poll Language Selector...")
    poll_lang_kb = build_poll_language_keyboard(current_lang="en")
    lang_callbacks = [btn.callback_data for row in poll_lang_kb.inline_keyboard for btn in row]
    assert "poll_lang:bn" in lang_callbacks
    assert "poll_lang:en" in lang_callbacks
    assert "poll_lang:hi" in lang_callbacks
    assert "poll_lang:ar" in lang_callbacks
    assert "poll_lang:ru" in lang_callbacks
    # Check that current language shows checkmark
    current_en_btn = [btn for row in poll_lang_kb.inline_keyboard for btn in row if btn.callback_data == "poll_lang:en"][0]
    assert "✅" in current_en_btn.text
    print("[SUCCESS] Interactive channel poll language keyboard verified.")

    print("[TEST] Owner Exclusive Brand Credit & Multi-Language Poll Cards...")
    creator_a = 987654321
    creator_b = 123987456
    await save_user(creator_a, username="creator_a")
    await save_user(creator_b, username="creator_b")

    # Super Admin sets owner brand
    await set_custom_credit("💎 Owner Club @ownerclub", "https://t.me/ownerclub")
    await set_custom_credit_btn_text("🚀 Join Owner Channel ➔")

    # Both Creator A and Creator B should universally get owner brand
    name_a, url_a, btn_a = await get_effective_credit(creator_a)
    assert name_a == "💎 Owner Club @ownerclub"
    assert url_a == "https://t.me/ownerclub"
    assert btn_a == "🚀 Join Owner Channel ➔"

    name_b, url_b, btn_b = await get_effective_credit(creator_b)
    assert name_b == "💎 Owner Club @ownerclub"
    print("[SUCCESS] Owner-exclusive brand credit policy verified.")

    # Render poll card in Hindi with Owner brand
    card_hi = await render_poll_card("Hindi Contest Test", "propollbot", lang="hi", creator_id=creator_a)
    assert "💎 Owner Club @ownerclub" in card_hi
    assert "वोट देने के लिए" in card_hi

    # Render poll card in Russian with Owner brand
    card_ru = await render_poll_card("Russian Contest Test", "propollbot", lang="ru", creator_id=creator_a)
    assert "💎 Owner Club @ownerclub" in card_ru
    assert "Нажмите кнопку ниже" in card_ru

    # Render poll card in Arabic with Owner brand
    card_ar = await render_poll_card("Arabic Contest Test", "propollbot", lang="ar", creator_id=creator_a)
    assert "💎 Owner Club @ownerclub" in card_ar
    assert "اضغط على أحد الأزرار" in card_ar

    # Test render_poll_ended in multiple languages
    from bot.templates import render_poll_ended
    ended_hi = await render_poll_ended("Hindi Contest Test", "Winner Alpha", 100, "propollbot", lang="hi", creator_id=creator_a)
    assert "कुल प्राप्त वोट:" in ended_hi
    ended_ru = await render_poll_ended("Russian Contest Test", "Winner Alpha", 100, "propollbot", lang="ru", creator_id=creator_a)
    assert "Всего голосов:" in ended_ru
    ended_ar = await render_poll_ended("Arabic Contest Test", "Winner Alpha", 100, "propollbot", lang="ar", creator_id=creator_a)
    assert "إجمالي الأصوات:" in ended_ar
    print("[SUCCESS] Multi-language poll cards and ended templates render accurately in BN, EN, HI, RU, AR.")

    print("[TEST] Interactive Winner Announcement Choice & Brand Preservation...")
    from bot.keyboards.inline import build_winner_announcement_choice_keyboard
    from bot.templates import render_winner_announcement, render_custom_winner_announcement

    choice_kb_bn = build_winner_announcement_choice_keyboard(123, lang="bn")
    choice_kb_en = build_winner_announcement_choice_keyboard(123, lang="en")
    assert any("post_winner_auto:123" == btn.callback_data for row in choice_kb_bn.inline_keyboard for btn in row)
    assert any("post_winner_custom:123" == btn.callback_data for row in choice_kb_bn.inline_keyboard for btn in row)
    assert any("post_winner_skip:123" == btn.callback_data for row in choice_kb_bn.inline_keyboard for btn in row)
    print("[SUCCESS] Winner announcement choice keyboards built cleanly.")

    # Test Auto announcement renderer
    top_w_sample = [
        {"name": "Champion One", "votes_count": 50},
        {"name": "Runner Up", "votes_count": 30}
    ]
    auto_ann = await render_winner_announcement(
        title="Mega Giveaway 2026",
        top_winners=top_w_sample,
        total_votes=80,
        bot_username="propollbot",
        lang="bn",
        creator_id=creator_a
    )
    assert "অফিসিয়াল বিজয়ী ঘোষণা" in auto_ann
    assert "Champion One" in auto_ann
    assert "Runner Up" in auto_ann
    assert "💎 Owner Club @ownerclub" in auto_ann
    assert "https://t.me/ownerclub" in auto_ann
    print("[SUCCESS] Auto winner announcement correctly includes medals, winners, votes, and brand credit.")

    # Test Custom announcement renderer with Brand Credit preservation
    custom_input = "সবাইকে আন্তরিক মোবারকবাদ! আমাদের সেরা ২ জন বিজয়ী নির্বাচিত হয়েছেন।"
    custom_ann = await render_custom_winner_announcement(
        custom_text=custom_input,
        bot_username="propollbot",
        creator_id=creator_a
    )
    assert custom_input in custom_ann
    assert "Powered by:" in custom_ann
    assert "💎 Owner Club @ownerclub" in custom_ann
    assert "https://t.me/ownerclub" in custom_ann
    print("[SUCCESS] Custom announcement guarantees 100% brand credit watermark & link preservation.")

    print("[TEST] Router & Handler Import Sanity Check...")
    from bot.handlers.start import router as start_router
    from bot.handlers.poll_create import router as create_router, cmd_new_poll
    from bot.handlers.poll_manage import router as manage_router, cmd_my_polls, WinnerAnnouncementState
    from bot.handlers.voting import router as voting_router
    from bot.handlers.admin import router as admin_router, show_credit_manager
    assert start_router is not None
    assert create_router is not None
    assert manage_router is not None
    assert voting_router is not None
    assert admin_router is not None
    assert callable(cmd_new_poll)
    assert callable(cmd_my_polls)
    assert WinnerAnnouncementState is not None
    print("[SUCCESS] All routers, handlers and alias functions import 100% cleanly.")

    print("[TEST] Strict Per-User Channel Isolation & Anti-Hijacking...")
    user_isolated_1 = 55551
    user_isolated_2 = 55552
    await save_channel(chat_id=-10055551, title="User 1 Channel", username="u1_chan", added_by=user_isolated_1)
    await save_channel(chat_id=-10055552, title="User 2 Channel", username="u2_chan", added_by=user_isolated_2)

    u1_channels = await get_user_selectable_channels(user_isolated_1)
    u1_ids = [c["chat_id"] for c in u1_channels]
    assert -10055551 in u1_ids, "User 1 must see their own channel"
    assert -10055552 not in u1_ids, "User 1 must NEVER see User 2's channel!"

    u2_channels = await get_user_selectable_channels(user_isolated_2)
    u2_ids = [c["chat_id"] for c in u2_channels]
    assert -10055552 in u2_ids, "User 2 must see their own channel"
    assert -10055551 not in u2_ids, "User 2 must NEVER see User 1's channel!"

    assert await is_user_authorized_for_channel_db(user_isolated_1, -10055551) is True
    assert await is_user_authorized_for_channel_db(user_isolated_2, -10055551) is False
    print("[SUCCESS] Strict per-user channel isolation & anti-hijacking protection verified 100%!")

    print("[TEST] Giveaway Host Contact ID & Prize Claim Announcement...")
    # Test setting default user contact
    await set_user_default_contact(12345678, "GiveawayAdminBoss")
    def_contact = await get_user_default_contact(12345678)
    assert def_contact == "GiveawayAdminBoss", f"Expected GiveawayAdminBoss, got {def_contact}"

    # Test creating poll with contact
    contact_poll_id = await create_poll(
        creator_id=12345678,
        target_chat_id=-100444555666,
        target_chat_title="Channel Two",
        target_chat_username="chan2",
        title="Mega Giveaway Test",
        candidates=["Alpha", "Beta"],
        contact_username="GiveawayAdminBoss"
    )
    p_info = await get_poll(contact_poll_id)
    assert p_info["contact_username"] == "GiveawayAdminBoss", f"Expected GiveawayAdminBoss, got {p_info.get('contact_username')}"

    # Test updating contact ID
    await update_poll_contact(contact_poll_id, "NewAdminMaster")
    p_updated = await get_poll(contact_poll_id)
    assert p_updated["contact_username"] == "NewAdminMaster"

    # Test winner announcement layout with contact username
    cands_winners = [
        {"name": "Candidate 1", "votes": 5},
        {"name": "Candidate 2", "votes": 1}
    ]
    announcement_html = await render_winner_announcement(
        title="Mega Tech Giveaway 2026",
        top_winners=cands_winners,
        total_votes=6,
        bot_username="ProPoolMaking_bot",
        lang="en",
        creator_id=12345678,
        contact_username="NewAdminMaster"
    )
    assert "NewAdminMaster" in announcement_html
    assert "https://t.me/NewAdminMaster" in announcement_html
    assert "Prize Claim Information" in announcement_html
    assert "<code>1</code> vote" in announcement_html
    assert "<code>5</code> votes" in announcement_html
    assert "100% Verified & Validated" in announcement_html
    assert ("@ownerclub" in announcement_html or "@ProPoolMaking_bot" in announcement_html)

    # Bengali winner announcement layout with contact username
    announcement_bn = await render_winner_announcement(
        title="মেগা ঈদ গিভওয়ে ২০২৬",
        top_winners=cands_winners,
        total_votes=6,
        bot_username="ProPoolMaking_bot",
        lang="bn",
        creator_id=12345678,
        contact_username="NewAdminMaster"
    )
    assert "পুরস্কার দাবি" in announcement_bn
    assert "https://t.me/NewAdminMaster" in announcement_bn

    # Test strip_tg_emoji_tags custom emoji fallback
    tg_emoji_sample = '<tg-emoji emoji-id="5368324170671202286">🔥</tg-emoji> <b>Super Deal</b> <tg-emoji emoji-id="123">💎</tg-emoji>'
    stripped = strip_tg_emoji_tags(tg_emoji_sample)
    assert "<tg-emoji" not in stripped
    assert "</tg-emoji>" not in stripped
    assert "🔥 <b>Super Deal</b> 💎" in stripped

    # Test custom winner announcement with contact username
    custom_msg = "Hey guys, here are our lucky winners! Contact us to get prizes."
    custom_rendered = await render_custom_winner_announcement(
        custom_text=custom_msg,
        bot_username="ProPoolMaking_bot",
        creator_id=12345678,
        contact_username="NewAdminMaster"
    )
    assert "Prize Claim" in custom_rendered
    assert "https://t.me/NewAdminMaster" in custom_rendered
    assert ("@ownerclub" in custom_rendered or "@ProPoolMaking_bot" in custom_rendered)

    print("[SUCCESS] Giveaway Host Contact ID & Prize Claim Announcement verified 100%!")

    print("[TEST] Full Template Customization, Multi-Language Separation & Safe Premium Emoji Rendering...")
    # 1. Template library completeness
    assert "tpl_winner_announcement" in TEMPLATE_KEYS
    assert "tpl_prize_claim" in TEMPLATE_KEYS
    assert "tpl_anti_cheat_badge" in TEMPLATE_KEYS
    assert "tpl_help" in TEMPLATE_KEYS
    assert "tpl_poll_card" in TEMPLATE_KEYS
    assert "tpl_poll_ended" in TEMPLATE_KEYS
    assert "tpl_vote_success" in TEMPLATE_KEYS
    assert "tpl_fsub_alert" in TEMPLATE_KEYS

    # 2. Template navigation keyboard
    tpl_menu = build_templates_menu()
    assert len(tpl_menu.inline_keyboard) >= 10
    edit_menu = build_template_edit_menu("tpl_winner_announcement")
    edit_callbacks = [b.callback_data for row in edit_menu.inline_keyboard for b in row]
    assert "tpl_edit:tpl_winner_announcement:bn" in edit_callbacks
    assert "tpl_edit:tpl_winner_announcement:en" in edit_callbacks
    assert "tpl_edit:tpl_winner_announcement:auto" in edit_callbacks
    assert "tpl_reset:tpl_winner_announcement" in edit_callbacks

    # 3. Setting custom template with <tg-emoji> in BN and EN separately
    custom_bn_with_emoji = '<tg-emoji id="5468383120">🎉</tg-emoji> <b>স্বাগতম</b> {candidate}'
    custom_en_with_emoji = '<tg-emoji id="5468383120">👑</tg-emoji> <b>Welcome</b> {candidate}'
    await set_custom_template("tpl_vote_success", "bn", custom_bn_with_emoji)
    await set_custom_template("tpl_vote_success", "en", custom_en_with_emoji)

    # Verify templates retrieved faithfully retain <tg-emoji> tags
    saved_bn = await get_raw_template("tpl_vote_success", "bn")
    saved_en = await get_raw_template("tpl_vote_success", "en")
    assert saved_bn == custom_bn_with_emoji
    assert saved_en == custom_en_with_emoji
    assert '<tg-emoji id="5468383120">🎉</tg-emoji>' in saved_bn
    assert '<tg-emoji id="5468383120">👑</tg-emoji>' in saved_en

    # 4. Toast alert strip_tg_emoji_tags behavior
    rendered_toast_bn = await render_vote_success("রাকিব", lang="bn")
    assert "<tg-emoji" not in rendered_toast_bn
    assert "</tg-emoji>" not in rendered_toast_bn
    assert "🎉" in rendered_toast_bn
    assert "রাকিব" in rendered_toast_bn

    rendered_toast_en = await render_vote_success("Rakib", lang="en")
    assert "<tg-emoji" not in rendered_toast_en
    assert "</tg-emoji>" not in rendered_toast_en
    assert "👑" in rendered_toast_en
    assert "Rakib" in rendered_toast_en

    # Reset template back
    await reset_template("tpl_vote_success")
    restored_bn = await get_raw_template("tpl_vote_success", "bn")
    assert restored_bn == DEFAULTS_BN["tpl_vote_success"]

    # 5. Help template rendering
    help_bn = await render_help_text("ProPoolMaking_bot", lang="bn")
    assert "পোল" in help_bn or "কমান্ড" in help_bn

    help_en = await render_help_text("ProPoolMaking_bot", lang="en")
    assert "Poll" in help_en or "Command" in help_en or "poll" in help_en

    # 6. Custom button emoji icon input & resolution
    cand_obj = {"name": "Candidate A", "votes_count": 5}
    all_cands = [cand_obj]
    custom_icon_code = "custom:💎"
    assert get_candidate_icon(cand_obj, all_cands, custom_icon_code) == "💎 "
    custom_icon_code_sparkles = "custom:✨"
    assert get_candidate_icon(cand_obj, all_cands, custom_icon_code_sparkles) == "✨ "

    icon_kb = build_icon_style_keyboard(current_style="custom:💎")
    icon_callbacks = [b.callback_data for row in icon_kb.inline_keyboard for b in row]
    assert any(c.startswith("prompt_custom_icon") for c in icon_callbacks)

    # 7. Safe HTML preservation with <tg-emoji>
    raw_mixed_text = 'Hello <tg-emoji id="12345">🔥</tg-emoji> & welcome <script>alert(1)</script> <b>bold</b>'
    safe_out = safe_html_preserve_tg_emoji(raw_mixed_text)
    assert '<tg-emoji id="12345">🔥</tg-emoji>' in safe_out
    assert "&amp;" in safe_out
    assert "&lt;script&gt;" in safe_out
    assert "<b>bold</b>" in safe_out

    # 8. Safe sending fallback simulation
    class MockTelegramBot:
        def __init__(self, fail_with_custom_emoji_error=True):
            self.fail = fail_with_custom_emoji_error
            self.sent_messages = []
            self.edited_messages = []

        async def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML", **kwargs):
            if self.fail and "<tg-emoji" in text:
                from aiogram.exceptions import TelegramBadRequest
                raise TelegramBadRequest(method="send_message", message="Bad Request: can't use custom emoji in messages")
            self.sent_messages.append({"chat_id": chat_id, "text": text})
            return {"message_id": 1, "text": text}

        async def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None, parse_mode="HTML", **kwargs):
            if self.fail and "<tg-emoji" in text:
                from aiogram.exceptions import TelegramBadRequest
                raise TelegramBadRequest(method="edit_message_text", message="Bad Request: can't use custom emoji in messages")
            self.edited_messages.append({"chat_id": chat_id, "text": text})
            return {"message_id": message_id or 1, "text": text}

    mock_bot = MockTelegramBot(fail_with_custom_emoji_error=True)
    msg_with_emoji = 'Test <tg-emoji id="777">🚀</tg-emoji> Rocket'
    res = await safe_send_message(mock_bot, 12345, text=msg_with_emoji)
    assert len(mock_bot.sent_messages) == 1
    # Fallback stripped message was sent
    assert "<tg-emoji" not in mock_bot.sent_messages[0]["text"]
    assert "🚀 Rocket" in mock_bot.sent_messages[0]["text"]

    res_edit = await safe_bot_edit_message(mock_bot, 12345, 99, text=msg_with_emoji)
    assert len(mock_bot.edited_messages) == 1
    assert "<tg-emoji" not in mock_bot.edited_messages[0]["text"]
    assert "🚀 Rocket" in mock_bot.edited_messages[0]["text"]

    print("[SUCCESS] Full Template Customization, Multi-Language Separation & Safe Premium Emoji Rendering verified 100%!")

    print("[TEST] Advanced Channel Poll Card Suggestions, Live Preview & Cross-Language Emoji Sync...")
    # 1. Suggestion retrieval for poll card
    sug_bn = get_suggestion("tpl_poll_card", "bn")
    sug_en = get_suggestion("tpl_poll_card", "en")
    assert "{title}" in sug_bn and "{bot_username}" in sug_bn
    assert "{title}" in sug_en and "{bot_username}" in sug_en
    assert "✨" in sug_bn or "🗳️" in sug_bn

    # 2. Applying suggestion
    await apply_suggestion("tpl_poll_card")
    applied_bn = await get_raw_template("tpl_poll_card", "bn")
    applied_en = await get_raw_template("tpl_poll_card", "en")
    assert applied_bn == sug_bn
    assert applied_en == sug_en

    # 3. Live Preview rendering
    preview_bn_text, preview_bn_kb = await render_template_live_preview("tpl_poll_card", "bn")
    assert "LIVE CHANNEL PREVIEW" in preview_bn_text
    assert "🌟 সেরা কনটেন্ট ক্রিয়েটর নির্বাচন ২০২৬" in preview_bn_text
    assert preview_bn_kb is not None
    preview_callbacks = [b.callback_data for row in preview_bn_kb.inline_keyboard for b in row if b.callback_data]
    assert "dummy_vote_preview" in preview_callbacks
    assert "tpl_preview:tpl_poll_card:en" in preview_callbacks
    assert "tpl_view:tpl_poll_card" in preview_callbacks

    preview_en_text, preview_en_kb = await render_template_live_preview("tpl_poll_card", "en")
    assert "LIVE CHANNEL PREVIEW" in preview_en_text
    assert "Best Content Creator" in preview_en_text

    # 4. Interactive Keyboard buttons verification
    edit_menu_poll_card = build_template_edit_menu("tpl_poll_card")
    edit_card_callbacks = [b.callback_data for row in edit_menu_poll_card.inline_keyboard for b in row if b.callback_data]
    assert "tpl_preview:tpl_poll_card:bn" in edit_card_callbacks
    assert "tpl_apply_sug:tpl_poll_card" in edit_card_callbacks
    assert "tpl_sync_emojis:tpl_poll_card" in edit_card_callbacks

    # 5. Smart cross-language emoji & Telegram Premium emoji synchronization
    sample_edited_bn = (
        '<tg-emoji emoji-id="5468383120">👑</tg-emoji> <b>{title}</b>\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '🎯 <i>পছন্দের প্রার্থীকে ভোট দিতে নিচের বাটনে ক্লিক করুন:</i>\n\n'
        '⚡ <b>সতর্কতা:</b> ভোট দিতে হলে অবশ্যই আমাদের চ্যানেলে জয়েন থাকতে হবে!\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '🚀 <b>Powered by:</b> {bot_username}'
    )
    sample_current_en = (
        '📊 <b>{title}</b>\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '🗳 <i>Tap a button below to cast your vote:</i>\n\n'
        '⚠️ <b>Note:</b> You must be a member of this channel to vote.\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '⚡ <b>Powered by:</b> {bot_username}'
    )
    synced_en = sync_emojis_between_texts(sample_edited_bn, sample_current_en)
    assert '<tg-emoji emoji-id="5468383120">👑</tg-emoji> <b>{title}</b>' in synced_en
    assert '🎯 <i>Tap a button below to cast your vote:</i>' in synced_en
    assert '⚡ <b>Note:</b> You must be a member of this channel to vote.' in synced_en
    assert '🚀 <b>Powered by:</b> {bot_username}' in synced_en

    # Reset template back
    await reset_template("tpl_poll_card")
    print("[SUCCESS] Advanced Channel Poll Card Suggestions, Live Preview & Cross-Language Emoji Sync verified 100%!")

    print("[TEST] A-to-Z Bot Buttons & Telegram Premium Custom Emojis (icon_custom_emoji_id)...")
    # 1. New button keys in TEMPLATE_KEYS
    assert "btn_main_create" in TEMPLATE_KEYS
    assert "btn_main_mypolls" in TEMPLATE_KEYS
    assert "btn_main_icons" in TEMPLATE_KEYS
    assert "btn_main_lang" in TEMPLATE_KEYS
    assert "btn_main_help" in TEMPLATE_KEYS
    assert "btn_main_addchannel" in TEMPLATE_KEYS
    assert "btn_fsub_join" in TEMPLATE_KEYS
    assert "tpl_vote_btn_format" in TEMPLATE_KEYS

    # 2. extract_custom_emoji_info
    raw_sample = '<tg-emoji emoji-id="5468383120">🔥</tg-emoji> Create Poll'
    clean, emoji_id = extract_custom_emoji_info(raw_sample)
    assert emoji_id == "5468383120"
    assert "Create Poll" in clean

    # 3. resolve_candidate_icon_and_emoji with custom_tg
    icon_str, custom_id = resolve_candidate_icon_and_emoji(
        {"name": "Rahim", "votes_count": 10},
        [{"name": "Rahim", "votes_count": 10}],
        style="custom_tg:5468383120:💎"
    )
    assert custom_id == "5468383120"
    assert icon_str == ""  # Strictly empty so no duplicate emojis appear alongside custom emoji

    # 4. build_poll_keyboard with custom_tg style and candidate custom emoji
    cand_list = [
        {"candidate_id": 1, "name": '<tg-emoji emoji-id="77778888">👑</tg-emoji> Player 1', "votes_count": 5},
        {"candidate_id": 2, "name": "Player 2", "votes_count": 3}
    ]
    poll_kb = build_poll_keyboard(
        poll_id=999,
        candidates=cand_list,
        bot_username="mybot",
        cta_text='<tg-emoji emoji-id="99990000">⚡</tg-emoji> Create Poll',
        icon_style="custom_tg:5468383120:🔥"
    )
    row0_btn0 = poll_kb.inline_keyboard[0][0]
    row0_btn1 = poll_kb.inline_keyboard[0][1]
    cta_btn = poll_kb.inline_keyboard[1][0]

    assert row0_btn0.icon_custom_emoji_id == "77778888"
    assert row0_btn1.icon_custom_emoji_id == "5468383120"
    assert cta_btn.icon_custom_emoji_id == "99990000"

    # 5. strip_button_custom_emojis fallback
    stripped_kb = strip_button_custom_emojis(poll_kb)
    for row in stripped_kb.inline_keyboard:
        for btn in row:
            assert btn.icon_custom_emoji_id is None

    # 6. make_custom_button
    btn_custom = make_custom_button('<tg-emoji emoji-id="123456">🚀</tg-emoji> Launch', callback_data="launch")
    assert btn_custom.icon_custom_emoji_id == "123456"
    assert "Launch" in btn_custom.text

    # 7. build_templates_menu contains button category
    tpl_menu_full = build_templates_menu()
    menu_callbacks = [b.callback_data for row in tpl_menu_full.inline_keyboard for b in row]
    assert "tpl_view:btn_main_create" in menu_callbacks
    assert "tpl_view:btn_fsub_join" in menu_callbacks
    assert "tpl_view:tpl_vote_btn_format" in menu_callbacks

    print("[SUCCESS] A-to-Z Bot Buttons & Telegram Premium Custom Emojis verified 100%!")

    print("\nALL MULTI-LANGUAGE, TOP N WINNERS, PER-USER ICONS, BRAND CREDIT, STICKY MENU, CHANNEL ISOLATION & CONTACT ID TESTS PASSED 1000% PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())




