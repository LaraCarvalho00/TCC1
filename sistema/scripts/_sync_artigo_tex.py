import os
import shutil
import re

root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src = os.path.join(root, "artigo.md")
dst = os.path.join(root, "artigo.tex")
with open(src, encoding="utf-8") as handle:
    text = handle.read()
shutil.copyfile(src, dst)
print("copied", dst, "bytes", len(text.encode("utf-8")))

# Structural checks
errors = []
if text.count("\\begin{document}") != 1:
    errors.append("begin document")
if text.count("\\end{document}") != 1:
    errors.append("end document")
if "\\cite{---}" in text:
    errors.append("placeholder cite")
cites = set(re.findall(r"\\cite\{([^}]+)\}", text))
bibs = set(re.findall(r"\\bibitem\[[^\]]+\]\{([^}]+)\}", text))
missing = sorted(cites - bibs)
unused = sorted(bibs - cites)
labels = set(re.findall(r"\\label\{([^}]+)\}", text))
refs = set(re.findall(r"\\ref\{([^}]+)\}", text))
dangling = sorted(refs - labels)
dup_labels = [l for l in labels if text.count("\\label{" + l + "}") > 1]
begins = re.findall(r"\\begin\{([a-zA-Z*]+)\}", text)
ends = re.findall(r"\\end\{([a-zA-Z*]+)\}", text)
from collections import Counter
if Counter(begins) != Counter(ends):
    errors.append(f"env mismatch {Counter(begins)-Counter(ends)} {Counter(ends)-Counter(begins)}")
figs = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text)
missing_figs = [p for p in figs if not os.path.isfile(os.path.join(root, p.replace("/", os.sep)))]
print("cites missing bib", missing)
print("bib unused", unused)
print("dangling refs", dangling)
print("dup labels", dup_labels)
print("missing figs", missing_figs)
print("errors", errors)
print("eq", re.findall(r"\\label\{eq:[^}]+\}", text))
print("tabs", re.findall(r"\\label\{tab:[^}]+\}", text))
print("figs labels", re.findall(r"\\label\{fig:[^}]+\}", text))
