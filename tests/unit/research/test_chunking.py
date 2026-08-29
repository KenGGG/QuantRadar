def test_short_report_uses_one_whole_report_chunk() -> None:
    from quantradar.research.llm.chunking import plan_chunks

    chunks = plan_chunks("# 标题\n正文", max_chars=100)

    assert [(chunk.chunk_id, chunk.text) for chunk in chunks] == [("chunk-0001", "# 标题\n正文")]


def test_long_report_preserves_the_tail_in_stable_chunks() -> None:
    from quantradar.research.llm.chunking import plan_chunks

    source = "# 第一节\n" + "甲" * 20 + "\n# 第二节\n" + "乙" * 20 + "\n尾部结论"
    chunks = plan_chunks(source, max_chars=32)

    assert [chunk.chunk_id for chunk in chunks] == ["chunk-0001", "chunk-0002"]
    assert "尾部结论" in chunks[-1].text
    assert "".join(chunk.text for chunk in chunks).replace("\n", "") == source.replace("\n", "")
