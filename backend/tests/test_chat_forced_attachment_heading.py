from app.services.chat_service import _extract_forced_attachment_heading


def test_extract_forced_attachment_heading_for_title_query() -> None:
    attachment_context = (
        'Attachment retrieval result for sample.pdf:\n'
        'Exact matched heading for the requested section:\n'
        'Epic 1 : Player Ownership & Market Trading\n'
        'Respond with the exact heading text above.'
    )

    heading = _extract_forced_attachment_heading(
        attachment_context,
        'Provide me the title of Epic 1 in the Demo 3',
    )

    assert heading == 'Epic 1 : Player Ownership & Market Trading'


def test_extract_forced_attachment_heading_ignores_non_title_query() -> None:
    attachment_context = (
        'Attachment retrieval result for sample.pdf:\n'
        'Exact matched heading for the requested section:\n'
        'Epic 1 : Player Ownership & Market Trading\n'
        'Respond with the exact heading text above.'
    )

    heading = _extract_forced_attachment_heading(
        attachment_context,
        'Explain this epic in detail',
    )

    assert heading is None
