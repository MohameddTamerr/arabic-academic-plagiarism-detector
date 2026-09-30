# -*- coding: utf-8 -*-
"""مرشحات النصوص الشائعة والديباجات الأكاديمية (Text Filters Package)."""
from .common_phrases import (
    classify_non_substantive_academic_text,
    filter_common_spans,
    is_common_institutional_text,
    EXPANDED_COMMON_INSTITUTIONAL_MARKERS
)
