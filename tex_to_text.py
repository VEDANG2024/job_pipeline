"""
tex_to_text.py — flattens a .tex resume into plain lowercase text for
keyword-overlap matching. This is deliberately crude: it doesn't need
to produce readable prose, just a bag of words that ATS-style keyword
matching can search. Tailoring itself (tailor.py) sends the real .tex
to the LLM, which reads LaTeX fine — this flattener is only for
scoring.
"""
import re


def flatten(tex: str) -> str:
    # Only look at the document body.
    if r"\begin{document}" in tex:
        tex = tex.split(r"\begin{document}", 1)[1]

    # Strip comments (a % not preceded by a backslash).
    tex = re.sub(r"(?<!\\)%.*", "", tex)

    # Drop command names + any optional [..] args, keep the braced content
    # (braces themselves get stripped next, so nested content survives as
    # plain words even though nesting isn't tracked precisely).
    tex = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", tex)

    tex = tex.replace("{", " ").replace("}", " ")
    tex = tex.replace("\\", " ")
    tex = re.sub(r"\s+", " ", tex).strip()
    return tex.lower()


def flatten_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return flatten(f.read())
