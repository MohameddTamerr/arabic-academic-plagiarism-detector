# -*- coding: utf-8 -*-
"""
أداة بناء ملفات التشغيل التنفيذية لنظام ويندوز (.EXE Launchers Builder):
- تُنشئ 8 ملفات تنفيذية PE أصلية ومستقلة تماماً (Windows Native Executables).
- لا تعتمد على أي بايثون مثبت على نظام التشغيل، بل تستخدم بيئة Runtime المحمولة المدمجة فقط.
- تدمج الأيقونة المؤسسية الرسمية (Police-Academy logo / app.ico) داخل كل ملف EXE.
- تدعم المسارات ذات المسافات الطويلة واللغة العربية وترميز UTF-8 بشكل كامل.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from PIL import Image

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
SCRATCH_DIR = ROOT_DIR / "scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

# قائمة المشغلات التنفيذية والأوامر المقابلة لها في portable_cli.py
LAUNCHERS = [
    ("Start-System.exe", "start", "Arabic Academic Plagiarism Detector - Start System"),
    ("Stop-System.exe", "stop", "Arabic Academic Plagiarism Detector - Stop System"),
    ("Setup-System.exe", "setup", "Arabic Academic Plagiarism Detector - Setup System"),
    ("Check-System.exe", "check", "Arabic Academic Plagiarism Detector - Check System"),
    ("Backup-System.exe", "backup", "Arabic Academic Plagiarism Detector - Backup System"),
    ("Restore-System.exe", "restore", "Arabic Academic Plagiarism Detector - Restore System"),
    ("View-Logs.exe", "logs", "Arabic Academic Plagiarism Detector - View Logs"),
    ("Create-Diagnostic-Package.exe", "diagnostic", "Arabic Academic Plagiarism Detector - Create Diagnostic Package")
]


def generate_application_icon() -> Path:
    """توليد أيقونة ويندوز .ico من شعار المنظومة المؤسسي."""
    ico_path = SCRATCH_DIR / "app.ico"
    logo_path = ROOT_DIR / "static" / "logo.png"
    if not logo_path.exists():
        logo_path = ROOT_DIR / "Police-Academy-College-of-Graduate-Studies.png"

    if logo_path.exists():
        try:
            img = Image.open(logo_path)
            img.save(
                ico_path,
                format='ICO',
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            )
            return ico_path
        except Exception as e:
            print(f"   [!] Note on icon generation: {e}")
    return None


def get_csharp_source(command: str, title: str) -> str:
    """توليد كود C# نظيف ومحكم لكل مشغل تنفيذي."""
    template = r'''using System;
using System.IO;
using System.Diagnostics;
using System.Text;

namespace ArabicPlagiarismDetector {
    class Launcher {
        static int Main(string[] args) {
            try {
                Console.Title = "__TITLE__";
            } catch {}

            try {
                Console.OutputEncoding = Encoding.UTF8;
                Console.InputEncoding = Encoding.UTF8;
            } catch {}

            string rootDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
            string pythonExe = Path.Combine(rootDir, "Runtime", "python.exe");

            // في حال عدم وجود Runtime\\python.exe يتم الرفض القاطع
            if (!File.Exists(pythonExe)) {
                Console.WriteLine("======================================================================");
                Console.WriteLine("RUNTIME NOT FOUND");
                Console.WriteLine("======================================================================");
                Console.WriteLine("Python executable was not found in:");
                Console.WriteLine("  " + pythonExe);
                Console.WriteLine();
                Console.WriteLine("This portable package requires the bundled Runtime.");
                Console.WriteLine("System Python fallback is disabled in production portable mode.");
                Console.WriteLine("======================================================================");
                if (Environment.UserInteractive && !Console.IsInputRedirected) {
                    Console.WriteLine();
                    Console.WriteLine("Press Enter to exit...");
                    Console.ReadLine();
                }
                return 1;
            }

            string cliPath = Path.Combine(rootDir, "Tools", "portable_cli.py");
            if (!File.Exists(cliPath)) {
                cliPath = Path.Combine(rootDir, "tools", "portable_cli.py");
            }

            if (!File.Exists(cliPath)) {
                Console.WriteLine("======================================================================");
                Console.WriteLine("PORTABLE CLI NOT FOUND");
                Console.WriteLine("======================================================================");
                Console.WriteLine("Could not locate portable_cli.py in:");
                Console.WriteLine("  " + cliPath);
                Console.WriteLine("======================================================================");
                if (Environment.UserInteractive && !Console.IsInputRedirected) {
                    Console.WriteLine();
                    Console.WriteLine("Press Enter to exit...");
                    Console.ReadLine();
                }
                return 1;
            }

            StringBuilder argBuilder = new StringBuilder();
            argBuilder.Append("\"" + cliPath + "\" __COMMAND__");

            if (args != null && args.Length > 0) {
                foreach (string a in args) {
                    argBuilder.Append(" \"" + a.Replace("\"", "\\\"") + "\"");
                }
            }

            ProcessStartInfo psi = new ProcessStartInfo {
                FileName = pythonExe,
                Arguments = argBuilder.ToString(),
                WorkingDirectory = rootDir,
                UseShellExecute = false,
                CreateNoWindow = false
            };

            psi.EnvironmentVariables["PORTABLE_MODE"] = "1";
            psi.EnvironmentVariables["PORTABLE_ROOT"] = rootDir;

            try {
                using (Process proc = Process.Start(psi)) {
                    proc.WaitForExit();
                    int exitCode = proc.ExitCode;

                    // إذا كان المشغل دُبل كليك تفاعلي وأمر غير البدء، نترك رسالة واضحة
                    if (Environment.UserInteractive && !Console.IsInputRedirected && args.Length == 0) {
                        if ("__COMMAND__" == "setup" || "__COMMAND__" == "backup" || "__COMMAND__" == "restore" || "__COMMAND__" == "check" || "__COMMAND__" == "diagnostic") {
                            Console.WriteLine();
                            Console.WriteLine("Press Enter to exit...");
                            Console.ReadLine();
                        }
                    }
                    return exitCode;
                }
            } catch (Exception ex) {
                Console.WriteLine("======================================================================");
                Console.WriteLine("LAUNCH ERROR");
                Console.WriteLine("======================================================================");
                Console.WriteLine(ex.Message);
                Console.WriteLine("======================================================================");
                if (Environment.UserInteractive && !Console.IsInputRedirected) {
                    Console.WriteLine();
                    Console.WriteLine("Press Enter to exit...");
                    Console.ReadLine();
                }
                return 1;
            }
        }
    }
}
'''
    return template.replace("__TITLE__", title).replace("__COMMAND__", command)


def build_launchers(output_dir: Path) -> dict:
    """بناء وتجميع كافة ملفات الـ EXE في المجلد المحدد."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ico_path = generate_application_icon()
    
    csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not os.path.exists(csc_path):
        csc_path = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
    if not os.path.exists(csc_path):
        csc_path = shutil.which("csc")

    if not csc_path:
        raise RuntimeError("Windows C# compiler (csc.exe) not found on system.")

    print("=" * 70)
    print("   Building Windows Native EXE Launchers...")
    print(f"   Target Directory: {output_dir}")
    print("=" * 70)

    built_exes = {}
    for exe_name, cmd, title in LAUNCHERS:
        src_file = SCRATCH_DIR / f"{exe_name}.cs"
        out_file = output_dir / exe_name
        src_file.write_text(get_csharp_source(cmd, title), encoding='utf-8')

        cmd_args = [csc_path, "/nologo", "/optimize+", "/target:exe"]
        if ico_path and ico_path.exists():
            cmd_args.append(f"/win32icon:{ico_path.resolve()}")
        cmd_args.append(f"/out:{out_file.resolve()}")
        cmd_args.append(str(src_file.resolve()))

        res = subprocess.run(cmd_args, capture_output=True, text=True)
        if res.returncode != 0 or not out_file.exists():
            raise RuntimeError(f"Failed to build {exe_name}: {res.stderr or res.stdout}")

        size_kb = out_file.stat().st_size / 1024.0
        built_exes[exe_name] = {
            "path": str(out_file),
            "size_bytes": out_file.stat().st_size,
            "size_kb": round(size_kb, 2),
            "command": cmd
        }
        print(f"   [✓] {exe_name:<30} -> {size_kb:.1f} KB (Command: '{cmd}')")

    print("=" * 70)
    print(f"   Successfully compiled {len(built_exes)} Windows native EXE launchers!")
    print("=" * 70)
    return built_exes


if __name__ == "__main__":
    target = ROOT_DIR / "dist" / "Arabic-Academic-Plagiarism-System"
    build_launchers(target)
