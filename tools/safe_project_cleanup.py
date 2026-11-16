# -*- coding: utf-8 -*-
"""
Safe Project Cleanup & Organization Script:
- Preserves all critical application code, UI, models, datasets, and release assets.
- Archives obsolete development snapshots and duplicate test builds OUTSIDE the project.
- Cleans safe regenerable build caches (__pycache__, .pytest_cache, PyInstaller build temp).
- Generates a full SHA-256 inventory manifest.
"""
import os
import sys
import shutil
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(r"C:\Users\user\Downloads\Baba").resolve()
ARCHIVE_DIR = Path(r"C:\Users\user\Downloads\Baba_Archive_20261116").resolve()

# 1. Obsolete items in scratch/ to archive
SCRATCH_ARCHIVE_DIRS = [
    "windows-release-scoped-20261116",
    "windows-release-20261116",
    "windows-final-20261116",
    "win8-rc2",
    "stage8m_deadline",
    "stage8m_shutdown",
    "stage8l",
    "windows-accepted-20261116",
    "win8-rc1",
    "final-win-20261116",
    "final-acceptance-20261116",
    "Arabic Academic Plagiarism System",
    "source-runtime-isolated",
    "old-exe-reproduction",
    "recovery-20260916",
    "windows-release-scoped-validation-20261116",
    "windows-release-validation-20261116",
    "acceptance-preflight5",
    "windows-native-preflight-20261116",
    "acceptance-preflight4",
    "acceptance-preflight3",
    "acceptance-preflight2",
    "acceptance-preflight",
    "final-ui-source",
    "video-review-20260910-184032",
    "exe-smoke-20260926",
    "exe-smoke-evidence",
]

SCRATCH_ARCHIVE_FILES = [
    "Arabic-Plagiarism-System.failed-build-20260910.exe",
    "win8-rc2-build.log",
    "windows-final-build.log",
    "windows-release-build.log",
    "windows-release-scoped-build.log",
    "win8-rc1-build.log",
    "windows-accepted-build.log",
    "final-win-build.log",
    "final-acceptance-build.log",
]

# 2. Obsolete executables in dist/ to archive (PRESERVING active RC4 Arabic-Plagiarism-System.exe, manifest, and Arabic-Academic-Plagiarism-System)
DIST_ARCHIVE_FILES = [
    "Arabic-Plagiarism-System.rc2-preserved-20261116.exe",
    "Arabic-Plagiarism-System.stable-before-semantic-batch-20261002.exe",
    "Arabic-Plagiarism-System.bak.exe",
    "Arabic-Plagiarism-System.pre-superadmin-fix-20260914.exe",
    "Arabic-Plagiarism-System.pre-responsive-fix-20260914.exe",
    "Arabic-Plagiarism-System.pre-layout-fix-20260914.exe",
    "Arabic-Plagiarism-System-RC2.exe",
    "ArabicPlagiarismDetector.exe",
]

DIST_ARCHIVE_DIRS = [
    "fresh_acceptance_rc3",
]

# 3. Obsolete top-level directories to archive
TOP_ARCHIVE_DIRS = [
    "dist-staged",
    "dist-staged-e5",
    ".venv-stage8d",
    ".venv-stage8m",
    ".venv-stage8m53",
    ".venv-stage8m13",
]

# 4. Obsolete top-level files to archive
TOP_ARCHIVE_FILES = [
    "UI_AUDIT_SCREENSHOTS.zip",
    "UI_AFTER_SCREENSHOTS.zip",
    "UI_FINAL_REVIEW.zip",
]

# 5. Obsolete tmp/ subdirectories to archive
TMP_ARCHIVE_DIRS = [
    "pdfs",
    "employee-fix-smoke-20260915",
    "exe-first-login-smoke",
    "exe-responsive-localappdata",
    "exe-responsive-smoke",
    "exe-smoke-20261004",
    "exe-smoke-e90a967ec4784729bd4e3c9cd7b350a3",
    "responsive-visual-qa",
    "stage01_pytest",
    "stage02_final_pytest",
    "stage02_pytest",
    "stage02_pytest2",
    "stage02_pytest3",
    "stage03_final_pytest",
    "stage03_initial_pytest",
    "stage03_pytest1",
    "stage03_pytest2",
    "stage03_release_pytest",
    "stage04_e5_baseline",
    "stage04_final_pytest",
    "stage04_pytest1",
    "stage04_semantic_fix",
    "stage05_final_pytest",
    "stage05_pytest1",
    "stage05_pytest2",
]

# 6. Proven REGENERABLE build caches to safely remove
REGENERABLE_DIRS = [
    ROOT / "build",
    ROOT / "tmp" / "responsive-shell-build",
    ROOT / "tmp" / "superadmin-fixed-build",
]

REGENERABLE_FILES = [
    ROOT / "build_log.txt",
    ROOT / "rc2_run_log.txt",
    ROOT / "exe_run_log.txt",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_tree_stats(path: Path):
    total_bytes = 0
    file_count = 0
    if not path.exists():
        return 0, 0
    if path.is_file():
        return path.stat().st_size, 1
    for dp, dn, fn in os.walk(path):
        for f in fn:
            try:
                total_bytes += (Path(dp) / f).stat().st_size
                file_count += 1
            except Exception:
                pass
    return total_bytes, file_count


def run_inventory_and_cleanup(execute: bool = False):
    print("=" * 70)
    print(f"SAFE CLEANUP AND ARCHIVE PLAN {'(EXECUTE MODE)' if execute else '(DRY RUN)'}")
    print("=" * 70)

    initial_bytes, initial_files = get_tree_stats(ROOT)
    print(f"Baseline Project Size: {initial_bytes:,} bytes ({initial_bytes / (1024**3):.2f} GB)")
    print(f"Baseline Project Files: {initial_files:,}")

    archive_plan = []  # list of (src_path, rel_path, category)
    remove_plan = []   # list of paths to remove

    # 1. Scratch items
    for d in SCRATCH_ARCHIVE_DIRS:
        p = ROOT / "scratch" / d
        if p.exists():
            archive_plan.append((p, f"scratch/{d}", "Obsolete Test Snapshot in scratch/"))
    for f in SCRATCH_ARCHIVE_FILES:
        p = ROOT / "scratch" / f
        if p.exists():
            archive_plan.append((p, f"scratch/{f}", "Obsolete Build Log in scratch/"))

    # 2. Dist items
    for f in DIST_ARCHIVE_FILES:
        p = ROOT / "dist" / f
        if p.exists():
            archive_plan.append((p, f"dist/{f}", "Historical Windows Executable Backup"))
    for d in DIST_ARCHIVE_DIRS:
        p = ROOT / "dist" / d
        if p.exists():
            archive_plan.append((p, f"dist/{d}", "Previous RC3 Test Build Directory"))

    # 3. Top-level directories
    for d in TOP_ARCHIVE_DIRS:
        p = ROOT / d
        if p.exists():
            archive_plan.append((p, d, "Historical Staged Build / Stage Venv"))

    # 4. Top-level files
    for f in TOP_ARCHIVE_FILES:
        p = ROOT / f
        if p.exists():
            archive_plan.append((p, f, "Historical UI Screenshot Archive"))

    # 5. Tmp subdirs
    for d in TMP_ARCHIVE_DIRS:
        p = ROOT / "tmp" / d
        if p.exists():
            archive_plan.append((p, f"tmp/{d}", "Old Smoke / Stage Trial Directory"))

    # 6. Regenerable caches
    for p in REGENERABLE_DIRS:
        if p.exists():
            remove_plan.append((p, str(p.relative_to(ROOT)), "Regenerable PyInstaller Build Cache"))
    for p in REGENERABLE_FILES:
        if p.exists():
            remove_plan.append((p, str(p.relative_to(ROOT)), "Regenerable Transient Log"))

    # Calculate Archive totals
    total_archive_bytes = 0
    total_archive_files = 0
    print("\n--- Items to Archive OUTSIDE Project Directory ---")
    for src, rel, desc in archive_plan:
        sz, fc = get_tree_stats(src)
        total_archive_bytes += sz
        total_archive_files += fc
        kind = "DIR " if src.is_dir() else "FILE"
        print(f"[{kind}] {rel:<50} | {sz / (1024*1024):>8.2f} MB | {fc:>5} files | {desc}")

    # Calculate Remove totals
    total_remove_bytes = 0
    total_remove_files = 0
    print("\n--- Regenerable Items to Clean ---")
    for src, rel, desc in remove_plan:
        sz, fc = get_tree_stats(src)
        total_remove_bytes += sz
        total_remove_files += fc
        kind = "DIR " if src.is_dir() else "FILE"
        print(f"[{kind}] {rel:<50} | {sz / (1024*1024):>8.2f} MB | {fc:>5} files | {desc}")

    # Also count __pycache__ and .pytest_cache
    pycache_paths = []
    pycache_bytes = 0
    pycache_files = 0
    for dp, dn, fn in os.walk(ROOT):
        # Don't walk inside items already in archive plan or remove plan
        if any(str(src) in dp for src, _, _ in archive_plan + remove_plan):
            continue
        if "__pycache__" in Path(dp).parts or ".pytest_cache" in Path(dp).parts:
            for f in fn:
                fp = Path(dp) / f
                try:
                    pycache_bytes += fp.stat().st_size
                    pycache_files += 1
                except Exception:
                    pass
            if Path(dp) not in pycache_paths:
                pycache_paths.append(Path(dp))

    print(f"\n[CACHE] __pycache__ & .pytest_cache directories: {len(pycache_paths)} dirs | {pycache_bytes / (1024*1024):.2f} MB | {pycache_files} files")

    estimated_recovery_bytes = total_archive_bytes + total_remove_bytes + pycache_bytes
    estimated_recovery_files = total_archive_files + total_remove_files + pycache_files

    print("\n" + "=" * 70)
    print("ESTIMATED CLEANUP IMPACT:")
    print(f"  To Archive:   {total_archive_bytes / (1024**3):.2f} GB ({total_archive_files:,} files)")
    print(f"  To Remove:    {(total_remove_bytes + pycache_bytes) / (1024**3):.2f} GB ({total_remove_files + pycache_files:,} files)")
    print(f"  Total Saving: {estimated_recovery_bytes / (1024**3):.2f} GB ({estimated_recovery_files:,} files)")
    print(f"  Projected Project Size: {(initial_bytes - estimated_recovery_bytes) / (1024**3):.2f} GB")
    print(f"  Projected Project Files: {initial_files - estimated_recovery_files:,}")
    print("=" * 70)

    if not execute:
        print("\n[DRY RUN COMPLETE] To execute this plan, run with --execute.")
        return

    # EXECUTION
    print("\nExecuting Safe Archival...")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest_records = []

    for src, rel, desc in archive_plan:
        dest = ARCHIVE_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Archiving: {rel} -> {dest}")

        # If it's a file, compute hash and move
        if src.is_file():
            h = sha256_file(src)
            sz = src.stat().st_size
            shutil.move(str(src), str(dest))
            manifest_records.append({
                "relative_path": rel,
                "type": "file",
                "size_bytes": sz,
                "sha256": h,
                "category": desc,
                "archived_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            # Directory: compute hashes of contained files then move
            dir_files = []
            for dp, dn, fn in os.walk(src):
                for f in fn:
                    fp = Path(dp) / f
                    try:
                        h = sha256_file(fp)
                        sz = fp.stat().st_size
                        contained_rel = str(fp.relative_to(ROOT)).replace("\\", "/")
                        dir_files.append((contained_rel, sz, h))
                    except Exception:
                        pass
            shutil.move(str(src), str(dest))
            for contained_rel, sz, h in dir_files:
                manifest_records.append({
                    "relative_path": contained_rel,
                    "type": "file",
                    "size_bytes": sz,
                    "sha256": h,
                    "category": desc,
                    "archived_at": time.strftime("%Y-%m-%d %H:%M:%S")
                })

    # Save Archive Manifest in both Archive Dir and Project Docs
    archive_manifest_file = ARCHIVE_DIR / "ARCHIVE_MANIFEST.json"
    with open(archive_manifest_file, "w", encoding="utf-8") as f:
        json.dump({
            "archive_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "archive_destination": str(ARCHIVE_DIR),
            "total_archived_entries": len(manifest_records),
            "total_archived_bytes": total_archive_bytes,
            "manifest": manifest_records
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved archive manifest to: {archive_manifest_file}")

    project_manifest_file = ROOT / "docs" / "CLEANUP_AND_ARCHIVE_MANIFEST.json"
    with open(project_manifest_file, "w", encoding="utf-8") as f:
        json.dump({
            "archive_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "archive_destination": str(ARCHIVE_DIR),
            "total_archived_entries": len(manifest_records),
            "total_archived_bytes": total_archive_bytes,
            "manifest": manifest_records
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved project archive record to: {project_manifest_file}")

    # Remove regenerable build caches
    print("\nCleaning Regenerable Build Caches...")
    for src, rel, desc in remove_plan:
        if src.is_file():
            try:
                src.unlink()
                print(f"Removed file: {rel}")
            except Exception as e:
                print(f"Error removing {rel}: {e}")
        elif src.is_dir():
            try:
                shutil.rmtree(src)
                print(f"Removed dir: {rel}")
            except Exception as e:
                print(f"Error removing {rel}: {e}")

    # Remove __pycache__ and .pytest_cache
    for p in pycache_paths:
        if p.exists():
            try:
                shutil.rmtree(p)
            except Exception:
                pass
    print("Cleaned __pycache__ and .pytest_cache directories.")

    # Clean empty tmp dir if empty
    tmp_dir = ROOT / "tmp"
    if tmp_dir.exists() and not any(tmp_dir.iterdir()):
        try:
            tmp_dir.rmdir()
        except Exception:
            pass

    # Final measurements
    final_bytes, final_files = get_tree_stats(ROOT)
    recovered_bytes = initial_bytes - final_bytes
    print("\n" + "=" * 70)
    print("CLEANUP COMPLETED SUCCESSFULLY:")
    print(f"  Original Size:    {initial_bytes:,} bytes ({initial_bytes / (1024**3):.2f} GB)")
    print(f"  Final Size:       {final_bytes:,} bytes ({final_bytes / (1024**3):.2f} GB)")
    print(f"  Space Recovered:  {recovered_bytes:,} bytes ({recovered_bytes / (1024**3):.2f} GB / {recovered_bytes / (1024**2):.2f} MB)")
    print(f"  Retained Files:   {final_files:,}")
    print(f"  Archived Files:   {total_archive_files:,}")
    print(f"  Removed Caches:   {total_remove_files + pycache_files:,}")
    print(f"  Archive Location: {ARCHIVE_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    is_execute = "--execute" in sys.argv
    run_inventory_and_cleanup(execute=is_execute)
