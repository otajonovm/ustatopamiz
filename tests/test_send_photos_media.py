"""Regression: multi-photo portfolio submit must not mutate frozen InputMediaPhoto."""

from aiogram.types import InputMediaPhoto

from bot.services.telegram_helpers import build_photo_media_group


def test_frozen_caption_assignment_fails():
    media = [InputMediaPhoto(media="a"), InputMediaPhoto(media="b")]
    try:
        media[0].caption = "x"
        raised = False
    except Exception:
        raised = True
    assert raised, "aiogram InputMediaPhoto must stay frozen"


def test_media_group_caption_at_construction():
    media = build_photo_media_group(["p1", "p2", "p3"], "🖼 Usta ishlaridan namunalar")
    assert len(media) == 3
    assert media[0].caption == "🖼 Usta ishlaridan namunalar"
    assert media[1].caption is None
    assert media[2].media == "p3"
