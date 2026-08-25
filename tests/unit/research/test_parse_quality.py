def test_quality_marks_nonempty_chinese_markdown_parse_ok() -> None:
    from quantradar.research.parser.quality import assess_markdown

    quality = assess_markdown("# 标题\n这是中文研报正文。\n\n|A|B|\n|-|-|\n|1|2|")

    assert quality.status == "PARSE_OK"
    assert quality.char_count > 0
    assert quality.table_count == 1
