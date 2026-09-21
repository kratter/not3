"""The anchoring gate is the app's central safety property, so it is tested
against adversarial input, not just happy paths: a model that invents a quote
must not be able to get it into the database.
"""

from __future__ import annotations

import pytest

from not3.llm.anchor import anchor_items, dedupe
from not3.llm.chunker import Chunk, ChunkSegment


def make_chunk() -> Chunk:
    return Chunk(
        index=0,
        segments=[
            ChunkSegment(id=10, start_ms=0, end_ms=3000,
                         text="I always ruin everything I touch.", speaker="Client"),
            ChunkSegment(id=11, start_ms=3000, end_ms=5000,
                         text="Always?", speaker="Therapist"),
            ChunkSegment(id=12, start_ms=5000, end_ms=9000,
                         text="Well, not always. Last week went fine.", speaker="Client"),
        ],
    )


def test_exact_quote_is_kept_with_real_timestamps():
    kept, stats = anchor_items(
        [{"segment_id": 10, "quote": "I always ruin everything", "confidence": 0.9}],
        make_chunk(),
    )
    assert stats.kept == 1 and stats.dropped == 0
    assert kept[0].segment_id == 10
    assert (kept[0].start_ms, kept[0].end_ms) == (0, 3000)
    assert kept[0].speaker == "Client"
    assert not kept[0].relocated


def test_repunctuated_quote_is_kept():
    """Models re-case and re-punctuate while reproducing words exactly.
    That is not hallucination."""
    kept, stats = anchor_items(
        [{"segment_id": 10, "quote": "i ALWAYS ruin everything, i touch!", "confidence": 0.8}],
        make_chunk(),
    )
    assert stats.kept == 1
    assert kept[0].segment_id == 10


def test_fabricated_quote_is_dropped():
    kept, stats = anchor_items(
        [{"segment_id": 10,
          "quote": "I have never been good enough for my father",
          "confidence": 0.99}],
        make_chunk(),
    )
    assert kept == []
    assert stats.dropped_no_quote == 1
    assert stats.drop_rate == 1.0


def test_high_confidence_does_not_rescue_a_fabrication():
    """Confidence is the model's opinion of itself and carries no evidential
    weight. Only the transcript decides."""
    _, stats = anchor_items(
        [{"segment_id": 10, "quote": "my mother never called me back", "confidence": 1.0}],
        make_chunk(),
    )
    assert stats.kept == 0


def test_quote_from_outside_the_chunk_is_dropped():
    kept, stats = anchor_items(
        [{"segment_id": 99, "quote": "something said in a different recording",
          "confidence": 0.9}],
        make_chunk(),
    )
    assert kept == []
    assert stats.dropped_no_segment == 1


def test_miscited_but_real_quote_is_relocated_not_dropped():
    """Real speech attributed to the wrong line: fix the citation, count it,
    keep the observation."""
    kept, stats = anchor_items(
        [{"segment_id": 11, "quote": "Last week went fine", "confidence": 0.7}],
        make_chunk(),
    )
    assert stats.kept == 1 and stats.relocated == 1
    assert kept[0].segment_id == 12
    assert kept[0].start_ms == 5000
    assert kept[0].relocated


def test_missing_segment_id_recovered_when_quote_is_real():
    kept, stats = anchor_items(
        [{"quote": "not always", "confidence": 0.6}], make_chunk()
    )
    assert stats.kept == 1
    assert kept[0].segment_id == 12


def test_low_confidence_is_dropped_against_threshold():
    _, stats = anchor_items(
        [{"segment_id": 10, "quote": "I always ruin everything", "confidence": 0.3}],
        make_chunk(),
        min_confidence=0.6,
    )
    assert stats.dropped_low_conf == 1


@pytest.mark.parametrize("quote", ["", "   ", "Always?"])
def test_trivial_quotes_are_dropped(quote):
    """A one-word quote is not evidence of anything and matches everything."""
    _, stats = anchor_items(
        [{"segment_id": 11, "quote": quote, "confidence": 0.9}], make_chunk()
    )
    assert stats.kept == 0


def test_extra_fields_survive_as_payload():
    kept, _ = anchor_items(
        [{"segment_id": 10, "quote": "I always ruin everything", "confidence": 0.9,
          "category": "overgeneralization", "rationale": "absolute framing"}],
        make_chunk(),
    )
    assert kept[0].payload["category"] == "overgeneralization"
    assert kept[0].payload["rationale"] == "absolute framing"


def test_stats_account_for_every_proposal():
    items = [
        {"segment_id": 10, "quote": "I always ruin everything", "confidence": 0.9},
        {"segment_id": 10, "quote": "a thing nobody ever said here", "confidence": 0.9},
        {"segment_id": 77, "quote": "also not present anywhere at all", "confidence": 0.9},
        {"segment_id": 12, "quote": "Last week went fine", "confidence": 0.1},
    ]
    _, stats = anchor_items(items, make_chunk(), min_confidence=0.5)
    assert stats.proposed == 4
    assert stats.kept + stats.dropped == 4


def test_dedupe_keeps_the_most_confident_duplicate():
    """Chunk overlap produces the same observation twice; that must not become
    two findings in the UI."""
    chunk = make_chunk()
    kept, _ = anchor_items(
        [
            {"segment_id": 10, "quote": "I always ruin everything",
             "confidence": 0.6, "category": "overgeneralization"},
            {"segment_id": 10, "quote": "always ruin everything I touch",
             "confidence": 0.9, "category": "overgeneralization"},
        ],
        chunk,
    )
    merged = dedupe(kept, key="category")
    assert len(merged) == 1
    assert merged[0].confidence == 0.9


def test_dedupe_keeps_distinct_categories_on_one_segment():
    chunk = make_chunk()
    kept, _ = anchor_items(
        [
            {"segment_id": 10, "quote": "I always ruin everything",
             "confidence": 0.8, "category": "overgeneralization"},
            {"segment_id": 10, "quote": "I always ruin everything",
             "confidence": 0.7, "category": "all_or_nothing"},
        ],
        chunk,
    )
    assert len(dedupe(kept, key="category")) == 2


# -- quotes that span ASR segment boundaries --------------------------------
#
# Real whisper.cpp output breaks wherever the decoder happened to stop, often
# mid-clause, and the median segment on a real recording is a fragment. These
# cases were rejected at roughly a 70% rate until anchoring stopped requiring
# a quote to sit inside one segment.


def asr_chunk() -> Chunk:
    """Segments split the way an ASR actually splits them, not by sentence."""
    return Chunk(
        index=0,
        segments=[
            ChunkSegment(id=20, start_ms=0, end_ms=4000,
                         text="how long have you been feeling down altogether? Quite a few"),
            ChunkSegment(id=21, start_ms=4000, end_ms=8000,
                         text="months before that as well actually but it's gotten pretty"),
            ChunkSegment(id=22, start_ms=8000, end_ms=12000,
                         text="bad these past few months. Right, and are you sleeping?"),
        ],
    )


def test_quote_spanning_two_segments_is_kept():
    kept, stats = anchor_items(
        [{"segment_id": 20,
          "quote": "Quite a few months before that as well actually",
          "confidence": 0.9}],
        asr_chunk(),
    )
    assert stats.kept == 1, "a verbatim quote must not be lost to a segment boundary"
    assert kept[0].segment_id == 20


def test_quote_spanning_three_segments_is_kept():
    kept, stats = anchor_items(
        [{"segment_id": 20,
          "quote": "Quite a few months before that as well actually but it's "
                   "gotten pretty bad these past few months",
          "confidence": 0.9}],
        asr_chunk(),
    )
    assert stats.kept == 1
    assert kept[0].segment_id == 20


def test_span_end_time_covers_the_whole_quote():
    """Clicking a quote must play all of it, not just its first fragment."""
    kept, _ = anchor_items(
        [{"segment_id": 20,
          "quote": "Quite a few months before that as well actually but it's "
                   "gotten pretty bad these past few months",
          "confidence": 0.9}],
        asr_chunk(),
    )
    assert kept[0].start_ms == 0
    assert kept[0].end_ms == 12000


def test_quote_is_attributed_to_where_it_starts():
    kept, _ = anchor_items(
        [{"segment_id": 20, "quote": "bad these past few months", "confidence": 0.9}],
        asr_chunk(),
    )
    assert kept[0].segment_id == 22
    assert kept[0].start_ms == 8000


def test_fabrication_is_still_dropped_across_boundaries():
    """The whole point of the gate survives the boundary fix."""
    _, stats = anchor_items(
        [{"segment_id": 20,
          "quote": "I have been feeling suicidal for months and told nobody",
          "confidence": 0.95}],
        asr_chunk(),
    )
    assert stats.kept == 0


def test_words_present_but_reordered_are_dropped():
    """Real words in an order nobody said is still a fabricated quote."""
    _, stats = anchor_items(
        [{"segment_id": 20,
          "quote": "sleeping months few pretty down altogether gotten bad you",
          "confidence": 0.9}],
        asr_chunk(),
    )
    assert stats.kept == 0


def test_quote_longer_than_everything_shown_is_dropped():
    long_quote = " ".join(s.text for s in asr_chunk().segments) + \
        " and then I decided to leave the country and never come back at all"
    _, stats = anchor_items(
        [{"segment_id": 20, "quote": long_quote, "confidence": 0.9}], asr_chunk()
    )
    assert stats.kept == 0


# -- stored quotes are the transcript's words, not the model's ---------------


def test_stored_quote_comes_from_the_transcript():
    """A model that tidies a disfluency must not have its cleaned-up version
    presented as verbatim. Observed on a real recording: the transcript said
    "I don't know I I don't really" and the model returned it with the stutter
    removed, scoring 97 and passing the threshold."""
    chunk = Chunk(index=0, segments=[
        ChunkSegment(id=30, start_ms=0, end_ms=4000,
                     text="any other thoughts before the lecture? I feel like I don't know I"),
        ChunkSegment(id=31, start_ms=4000, end_ms=8000,
                     text="I don't really even deserve to be here if I can't do well enough."),
    ])
    kept, stats = anchor_items(
        [{"segment_id": 30,
          "quote": "I feel like I don't know I don't really even deserve to be here",
          "confidence": 0.9}],
        chunk,
    )
    assert stats.kept == 1
    # The stutter the speaker actually produced is preserved.
    assert "I don't know I I don't really" in kept[0].quote


def test_stored_quote_keeps_original_case_and_inner_punctuation():
    """The span runs from the first matched word to the last, so punctuation
    inside the quote is kept and punctuation beyond it is not."""
    kept, _ = anchor_items(
        [{"segment_id": 10, "quote": "i ALWAYS ruin everything, i touch!", "confidence": 0.9}],
        make_chunk(),
    )
    assert kept[0].quote == "I always ruin everything I touch"

    spanning, _ = anchor_items(
        [{"segment_id": 12, "quote": "not always last week", "confidence": 0.9}],
        make_chunk(),
    )
    assert spanning[0].quote == "not always. Last week"


def test_every_stored_quote_is_a_substring_of_the_transcript():
    """The property the whole feature rests on, stated directly."""
    chunk = asr_chunk()
    transcript = " ".join(s.text for s in chunk.segments)
    proposals = [
        {"segment_id": 20, "quote": "Quite a few months before that as well actually",
         "confidence": 0.9},
        {"segment_id": 21, "quote": "its gotten pretty bad these past few months",
         "confidence": 0.9},
        {"segment_id": 22, "quote": "are you sleeping", "confidence": 0.9},
    ]
    kept, stats = anchor_items(proposals, chunk)
    assert stats.kept == 3
    for item in kept:
        assert item.quote in transcript, f"not verbatim: {item.quote!r}"
