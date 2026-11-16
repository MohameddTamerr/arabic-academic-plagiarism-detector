# -*- coding: utf-8 -*-
"""
قياس الأداء واستخدام الذاكرة الحقيقي والشامل (Complete 8GB RAM Benchmark & Scalability):
يقيس استهلاك الذاكرة وسرعة المعالجة على كامل صفحات الوثائق دون أي اقتطاع (10، 50، 100 صفحة كاملة)
مع الفصل الواضح بين التحميل البارد (Cold Start) والاستدلال الدافئ (Warm Inference).
"""

import json
import logging
import os
import platform
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from plagiarism_detector.ai_detection.analysis import analyze_document_ai_research, get_research_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Benchmark")

SAMPLE_PARAGRAPHS = [
    "تعتبر حماية الآثار والتحف القديمة من أهم الواجبات القانونية التي تقع على عاتق الدولة للحفاظ على التراث الثقافي والتاريخي للأمة، وقد نص المشرع على عقوبات رادعة لكل من تسول له نفسه سرقة أو تهريب تلك المقتنيات.",
    "إن التطور التاريخي لمفهوم حقوق الإنسان يؤكد أن العدالة والمساواة بين الأفراد ليست وليدة العصر الحديث، بل هي نتاج تراكمي عبر الحضارات الإنسانية المتتابعة والتي أكدت على كرامة النفس البشرية وحمايتها من التعسف.",
    "يقوم النظام الدبلوماسي المعاصر على مجموعة من القواعد والاتفاقيات الدولية التي تنظم العلاقات بين الدول، وفي مقدمتها اتفاقية فيينا للعلاقات الدبلوماسية لعام 1961 التي حددت الحصانات والامتيازات الممنوحة للمبعوثين.",
    "تعد المسؤولية المدنية عن الأضرار الناشئة عن المنتجات المعيبة ركيزة أساسية في حماية المستهلك، حيث يلتزم المنتج بتعويض المضرور عن كافة الأضرار التي تلحق به جراء وجود عيب خفي في المنتج المصنع يخل بالسلامة.",
    "أكدت المحكمة الإدارية العليا في العديد من أحكامها أن القرار الإداري يجب أن يستند إلى سبب يبرره صدقاً وحقاً في الواقع والقانون، وأن انعدام السبب يؤدي بالضرورة إلى إلغاء القرار لعيب مخالفة القانون الجسيم."
]


def generate_academic_pages(num_pages: int, words_per_page: int = 250) -> tuple[str, list[dict]]:
    """Generate realistic academic multi-page text and pages_data."""
    pages_data = []
    full_text_parts = []
    para_idx = 0

    for page_num in range(1, num_pages + 1):
        page_paras = []
        page_words = 0
        while page_words < words_per_page:
            p = SAMPLE_PARAGRAPHS[para_idx % len(SAMPLE_PARAGRAPHS)]
            para_idx += 1
            page_paras.append(p)
            page_words += len(p.split())

        page_text = "\n\n".join(page_paras)
        pages_data.append({
            "page_number": page_num,
            "text": page_text
        })
        full_text_parts.append(page_text)

    return "\n\n".join(full_text_parts), pages_data


def get_current_process_ram_mb():
    """Return total resident memory in MB of current process tree."""
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            mem += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return round(mem / (1024 * 1024), 2)


def run_comprehensive_benchmark():
    app = create_app()
    with app.app_context():
        # 1. First measure Cold-Start Time of Nawaf INT8 Research Model
        logger.info("--- Measuring Cold-Start Model Loading Time ---")
        t_cold_0 = time.perf_counter()
        adapter = get_research_adapter(model_variant='nawaf_int8')
        if adapter is not None:
            adapter.load()
        cold_load_seconds = round(time.perf_counter() - t_cold_0, 3)
        ram_after_model_load = get_current_process_ram_mb()
        logger.info(f"Model Cold-Start: {cold_load_seconds}s | RAM after load: {ram_after_model_load} MB")

        results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "environment": {
                "os": platform.platform(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "host_total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "host_available_ram_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "target_specification": "Windows 10/11 64-bit, 8GB RAM, CPU-only, 100% Offline"
            },
            "cold_start": {
                "model_name": "Nawaf-AraBERT-INT8-ONNX" if getattr(adapter, "mode", None) == "onnx" else "Nawaf-AraBERT-INT8-TorchScript",
                "load_time_seconds": cold_load_seconds,
                "ram_after_load_mb": ram_after_model_load
            },
            "benchmarks": []
        }

        test_sizes = [10, 50, 100]

        for num_pages in test_sizes:
            logger.info(f"=== Running Full Benchmark for {num_pages} Pages (NO TRUNCATION) ===")
            raw_text, pages_data = generate_academic_pages(num_pages)
            total_words = len(raw_text.split())

            # 1. Plagiarism Engine Baseline (Lexical)
            t0 = time.perf_counter()
            plag_report = analyze_academic_document(
                raw_text,
                pages_data=pages_data,
                settings_override={
                    "enable_ai_research_mode": False,
                    "enable_semantic_model": False
                }
            )
            t_plag = time.perf_counter() - t0
            ram_plag = get_current_process_ram_mb()

            # 2. Plagiarism Engine with Semantic E5 (ONNX INT8)
            t0 = time.perf_counter()
            semantic_report = analyze_academic_document(
                raw_text,
                pages_data=pages_data,
                settings_override={
                    "enable_ai_research_mode": False,
                    "enable_semantic_model": True
                }
            )
            t_semantic = time.perf_counter() - t0
            ram_semantic = get_current_process_ram_mb()

            # 3. AI Writing Research (AraBERT INT8) on ALL pages without truncation
            t0 = time.perf_counter()
            ai_res = analyze_document_ai_research(raw_text, pages_data=pages_data)
            t_ai = time.perf_counter() - t0
            ram_ai = get_current_process_ram_mb()

            # Detailed paragraph accounting
            paragraphs_list = ai_res.get("paragraphs", [])
            total_paragraphs = len(paragraphs_list)
            analyzed_paragraphs = sum(1 for p in paragraphs_list if p.get("status") == "experimental_score")
            untrun_count = sum(1 for p in paragraphs_list if not p.get("truncated", False))
            trunc_count = sum(1 for p in paragraphs_list if p.get("truncated", False))
            excluded_count = sum(1 for p in paragraphs_list if p.get("status") == "not_analyzed")

            entry = {
                "pages_extracted": num_pages,
                "words_extracted": total_words,
                "paragraphs_eligible": total_paragraphs,
                "paragraphs_analyzed": analyzed_paragraphs,
                "paragraphs_truncated_512_tokens": trunc_count,
                "paragraphs_excluded": excluded_count,
                "plagiarism_baseline": {
                    "time_seconds": round(t_plag, 2),
                    "throughput_pages_per_sec": round(num_pages / max(t_plag, 0.001), 2),
                    "throughput_words_per_sec": round(total_words / max(t_plag, 0.001), 2),
                    "ram_mb": ram_plag
                },
                "plagiarism_with_semantic": {
                    "time_seconds": round(t_semantic, 2),
                    "throughput_pages_per_sec": round(num_pages / max(t_semantic, 0.001), 2),
                    "ram_mb": ram_semantic
                },
                "ai_research_mode": {
                    "time_seconds": round(t_ai, 2),
                    "time_per_paragraph_ms": round((t_ai / max(analyzed_paragraphs, 1)) * 1000, 2),
                    "throughput_paragraphs_per_sec": round(analyzed_paragraphs / max(t_ai, 0.001), 2),
                    "ram_mb": ram_ai,
                    "estimated_ai_pct": ai_res.get("estimated_ai_percentage")
                },
                "peak_ram_mb": max(ram_plag, ram_semantic, ram_ai),
                "ram_budget_8gb_pct": round((max(ram_plag, ram_semantic, ram_ai) / (8 * 1024)) * 100, 2)
            }
            results["benchmarks"].append(entry)
            logger.info(
                f"Done {num_pages} pages ({analyzed_paragraphs} paras): "
                f"Plag={entry['plagiarism_baseline']['time_seconds']}s | "
                f"Semantic={entry['plagiarism_with_semantic']['time_seconds']}s | "
                f"AI={entry['ai_research_mode']['time_seconds']}s ({entry['ai_research_mode']['time_per_paragraph_ms']} ms/para) | "
                f"Peak RAM={entry['peak_ram_mb']} MB ({entry['ram_budget_8gb_pct']}% of 8GB)"
            )

        # Save JSON Report
        json_path = ROOT / "docs" / "WINDOWS_8GB_PERFORMANCE_REPORT.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Save Markdown Report
        md_path = ROOT / "docs" / "WINDOWS_8GB_PERFORMANCE_REPORT.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# تقرير قياس الأداء والذاكرة الشامل لنظام كشف الاستلال والذكاء الاصطناعي\n\n")
            f.write("## 1. مواصفات بيئة القياس والتحميل البارد (Cold Start)\n\n")
            f.write(f"- **تاريخ الاختبار:** `{results['timestamp']}`\n")
            f.write(f"- **نظام التشغيل:** `{results['environment']['os']}`\n")
            f.write(f"- **المعالج:** `{results['environment']['processor']}`\n")
            f.write(f"- **إجمالي ذاكرة جهاز التطوير:** `{results['environment']['host_total_ram_gb']} GB`\n")
            f.write(f"- **زمن التحميل البارد لأوزان ومعجم الذكاء الاصطناعي (Cold Start):** `{cold_load_seconds} ثانية`\n")
            f.write(f"- **استهلاك الذاكرة بعد تحميل النموذج:** `{ram_after_model_load} MB`\n\n")
            f.write("> ⚠️ **إيضاح منهجي:** شملت القياسات فحص كامل صفحات الوثائق دون أي اقتصار على عينات جزئية (10، 50، 100 صفحة كاملة). أُجريت الاختبارات على جهاز التطوير (Intel Core i5-12500H / 32GB RAM)، وتعتبر جاهزية العتاد الفعلي 8GB معلقة لحين التجربة على الجهاز المستهدف مباشرة.\n\n")
            f.write("## 2. جدول القياسات الشاملة (Full Document Scalability)\n\n")
            f.write("| حجم المستند | الكلمات | الفقرات المفحوصة بالكامل | زمن الاستلال اللفظي | زمن الاستلال + الدلالي | زمن فحص الذكاء الاصطناعي | سرعة الاستدلال (مللي ث/فقرة) | ذروة الذاكرة RAM | نسبة ميزانية 8GB |\n")
            f.write("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n")
            for b in results["benchmarks"]:
                f.write(
                    f"| **{b['pages_extracted']} صفحة** | {b['words_extracted']:,} | **{b['paragraphs_analyzed']} فقرة** | "
                    f"{b['plagiarism_baseline']['time_seconds']} ث | {b['plagiarism_with_semantic']['time_seconds']} ث | "
                    f"**{b['ai_research_mode']['time_seconds']} ث** | **{b['ai_research_mode']['time_per_paragraph_ms']} ms** | "
                    f"**{b['peak_ram_mb']} MB** | **%{b['ram_budget_8gb_pct']}** |\n"
                )
            f.write("\n## 3. تفاصيل المعالجة وحصر الفقرات (Accounting & Exclusions)\n\n")
            for b in results["benchmarks"]:
                f.write(f"### مستند {b['pages_extracted']} صفحة:\n")
                f.write(f"- عدد الصفحات المستخرجة: {b['pages_extracted']}\n")
                f.write(f"- إجمالي الفقرات المؤهلة: {b['paragraphs_eligible']}\n")
                f.write(f"- الفقرات المفحوصة بنجاح: {b['paragraphs_analyzed']}\n")
                f.write(f"- الفقرات التي تجاوزت 512 رمز وخضعت للاقتطاع المعياري (Truncated): {b['paragraphs_truncated_512_tokens']}\n")
                f.write(f"- الفقرات المستبعدة (لأسباب الطول المفرط > 32KB أو الفراغ): {b['paragraphs_excluded']}\n\n")
        logger.info(f"Updated benchmark markdown at {md_path}")

if __name__ == "__main__":
    run_comprehensive_benchmark()
