"""回归测试：ASR token 拼接对英文要保留空格，对中文要去掉空格，
对标点要正确黏附。来自 v0.2.1 修 bug：英文转写全部挤在一起。"""

from liasse.asr import _join_qwen_tokens, _segments_from_time_marks


def test_english_words_get_spaces():
    tokens = ["This", "design", "process", "is", "broken"]
    assert _join_qwen_tokens(tokens) == "This design process is broken"


def test_chinese_chars_no_spaces():
    tokens = ["试", "图", "去", "联", "系", "一", "些", "地", "方"]
    assert _join_qwen_tokens(tokens) == "试图去联系一些地方"


def test_mixed_cjk_and_latin_inserts_space_between():
    # 中文段落里夹英文词应该两侧加空格
    tokens = ["我", "用", "ChatGPT", "做", "实", "验"]
    assert _join_qwen_tokens(tokens) == "我用 ChatGPT 做实验"


def test_punctuation_attaches_to_previous_word():
    # 英文标点不能跟前面有空格
    tokens = ["Hello", ",", "world", "!"]
    assert _join_qwen_tokens(tokens) == "Hello, world!"


def test_apostrophe_stays_glued():
    # "what 's" → "what's"
    tokens = ["what", "'s", "next"]
    assert _join_qwen_tokens(tokens) == "what's next"


def test_chinese_punctuation_attaches():
    tokens = ["你", "好", "，", "世", "界", "。"]
    assert _join_qwen_tokens(tokens) == "你好，世界。"


def test_empty_tokens_skipped():
    tokens = ["This", "", "is", "  ", "fine"]
    # 空字符串/纯空白都不参与拼接
    assert _join_qwen_tokens(tokens) == "This is fine"


def test_segments_from_marks_preserves_english_spacing():
    """端到端：原始 mark 列表（English）→ TranscriptSegment 文本不挤在一起。"""
    marks = [
        {"text": "This", "start": 0.0, "end": 0.3},
        {"text": "design", "start": 0.3, "end": 0.7},
        {"text": "process", "start": 0.7, "end": 1.2},
        {"text": ".", "start": 1.2, "end": 1.3},
    ]
    segments = _segments_from_time_marks(marks, source="mlx-qwen3-asr")
    assert len(segments) == 1
    assert segments[0].text == "This design process."
