from nanobot.cron.session_turns import is_invalid_cron_response, sanitize_news_cron_response


def _title_list(url_for_section: dict[str, str]) -> str:
    lines = ["오늘 저녁 국내 주요 뉴스입니다.", "기준 시각: 2026-08-01 21:30 KST"]
    for section in ("정치", "경제", "사회", "국제", "스포츠", "IT", "AI", "과학"):
        lines.extend(["", section])
        lines.extend(
            f"{index}. [{section} 주요 기사 {index}]({url_for_section[section]}?item={index})"
            for index in range(1, 6)
        )
    return "\n".join(lines)


def test_domestic_top_news_requires_an_article_in_every_section():
    content = _title_list(
        {
            section: f"https://example.com/article/{100000 + index}"
            for index, section in enumerate(("정치", "경제", "사회", "국제", "스포츠", "IT", "AI", "과학"))
        }
    )

    sanitized = sanitize_news_cron_response(content)

    assert not is_invalid_cron_response(sanitized)


def test_domestic_top_news_rejects_duplicates_and_generic_links():
    content = _title_list(
        {
            "정치": "https://www.hankyung.com/article/2026072666261",
            "경제": "https://pulse.mk.co.kr/news/biz",
            "사회": "https://www.newsis.com/",
            "국제": "https://m-en.yna.co.kr/view/AEN20260729002400315",
            "스포츠": "https://m-en.yna.co.kr/view/AEN20260729002400315",
            "IT": "https://en.yna.co.kr/view/AEN20260730009700320",
            "AI": "https://en.yna.co.kr/view/AEN20260730009700320",
            "과학": "https://en.yna.co.kr/view/AEN20260730009700320",
        }
    )

    sanitized = sanitize_news_cron_response(content)

    assert "pulse.mk.co.kr/news/biz" not in sanitized
    assert is_invalid_cron_response(sanitized)


def test_domestic_top_news_preserves_sbs_rss_article_permalinks():
    content = _title_list(
        {
            section: (
                "https://news.sbs.co.kr/news/endPage.do"
                f"?news_id=N1008685{index:03d}&plink=RSSLINK&cooper=RSSREADER"
            )
            for index, section in enumerate(
                ("정치", "경제", "사회", "국제", "스포츠", "IT", "AI", "과학")
            )
        }
    )

    sanitized = sanitize_news_cron_response(content + "]")

    assert "news.sbs.co.kr/news/endPage.do?news_id=" in sanitized
    assert not sanitized.endswith("]")
    assert not is_invalid_cron_response(sanitized)
