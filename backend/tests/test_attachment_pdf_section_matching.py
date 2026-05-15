from app.services.attachment_service import _derive_exact_heading_for_title_query, _find_exact_pdf_section_index


def test_exact_match_respects_parent_demo_scope() -> None:
    sections = [
        {
            'heading': 'Demo 1: Payments',
            'normalized_heading': 'demo 1: payments',
            'level': 1,
            'start_page': 1,
            'end_page': 1,
            'body': '',
        },
        {
            'heading': 'Epic 1: Legacy Checkout',
            'normalized_heading': 'epic 1: legacy checkout',
            'level': 2,
            'start_page': 1,
            'end_page': 1,
            'body': '',
        },
        {
            'heading': 'Demo 3: Marketplace',
            'normalized_heading': 'demo 3: marketplace',
            'level': 1,
            'start_page': 2,
            'end_page': 2,
            'body': '',
        },
        {
            'heading': 'Epic 1: Player Ownership & Market Trading',
            'normalized_heading': 'epic 1: player ownership & market trading',
            'level': 2,
            'start_page': 2,
            'end_page': 2,
            'body': '',
        },
    ]

    selected_index = _find_exact_pdf_section_index(
        sections,
        'Provide me the title of Epic 1 in the Demo 3',
    )

    assert selected_index == 3


def test_exact_match_returns_none_when_demo_not_present() -> None:
    sections = [
        {
            'heading': 'Demo 2: Questing',
            'normalized_heading': 'demo 2: questing',
            'level': 1,
            'start_page': 1,
            'end_page': 1,
            'body': '',
        },
        {
            'heading': 'Epic 1: Narrative Progression',
            'normalized_heading': 'epic 1: narrative progression',
            'level': 2,
            'start_page': 1,
            'end_page': 1,
            'body': '',
        },
    ]

    selected_index = _find_exact_pdf_section_index(
        sections,
        'Provide me the title of Epic 1 in the Demo 3',
    )

    assert selected_index is None


def test_title_query_heading_strips_trailing_audience_noise() -> None:
    heading = 'Epic 1 : Player Ownership & Market Trading Mobile Users'
    query_targets = [('epic', 'epic', '1'), ('demo', 'demo', '3')]

    exact_heading = _derive_exact_heading_for_title_query(heading, query_targets)

    assert exact_heading == 'Epic 1 : Player Ownership & Market Trading'
