# -*- coding: utf-8 -*-
"""
واجهة التوافق العكسي لموديول تحليل مؤشرات أسلوب الذكاء الاصطناعي.
"""

from plagiarism_detector.ai_analysis.stylistic_indicators import analyze_stylistic_ai_indicators

def analyze_ai_generation(text: str) -> dict:
    """استدعاء الموديول المحدث للمؤشرات الأسلوبية."""
    return analyze_stylistic_ai_indicators(text)

__all__ = ['analyze_ai_generation', 'analyze_stylistic_ai_indicators']
