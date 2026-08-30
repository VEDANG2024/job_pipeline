"""
latex_compile.py — compiles resume .tex to .pdf via pdflatex.

Requires a TeX Live install with fontawesome5 (texlive-fonts-extra).
On Debian/Ubuntu:
    sudo apt-get install texlive-latex-base texlive-latex-extra \\
        texlive-fonts-recommended texlive-fonts-extra
"""
import os
import shutil
import subprocess
import tempfile


class CompileError(RuntimeError):
    pass


def compile_tex(tex_source: str, output_pdf_path: str) -> str:
    """Writes tex_source to a scratch dir, compiles it, and copies the
    resulting PDF to output_pdf_path. Returns output_pdf_path on success.
    Raises CompileError with the pdflatex log tail on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        tex_path = os.path.join(tmp, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)

        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
            cwd=tmp, capture_output=True, text=True, timeout=60,
        )

        pdf_path = os.path.join(tmp, "resume.pdf")
        if not os.path.exists(pdf_path):
            log_tail = (result.stdout or "")[-2000:]
            raise CompileError(f"pdflatex failed:\n{log_tail}")

        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        shutil.copy(pdf_path, output_pdf_path)
        return output_pdf_path
