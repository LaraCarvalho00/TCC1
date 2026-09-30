import os
import shutil

root = os.path.join(os.path.dirname(__file__), "..", "..")
src = os.path.join(root, "sistema", "results", "harness_progressao", "figuras")
n50 = os.path.join(src, "n50_50rodadas")
dst = os.path.join(root, "figuras", "artigo")
os.makedirs(dst, exist_ok=True)

pairs = [
    (os.path.join(src, "figura1_acuracia_vs_N.pdf"), "acuracia_vs_N.pdf"),
    (os.path.join(src, "figura2_acuracia_vs_maliciosos_percentual.pdf"), "acuracia_vs_percentual.pdf"),
    (os.path.join(src, "figura3_reputacao_N30_p50.pdf"), "reputacao_N30_p50.pdf"),
    (os.path.join(src, "sem_conluio", "sem_conluio_acuracia_vs_N.pdf"), "acuracia_N_sem_conluio.pdf"),
    (os.path.join(src, "com_conluio", "com_conluio_acuracia_vs_N.pdf"), "acuracia_N_com_conluio.pdf"),
    (os.path.join(n50, "panorama_7_cenarios.pdf"), "n50_panorama.pdf"),
    (os.path.join(n50, "cenario_5_50pct", "acuracia_4configs.pdf"), "n50_p50_acuracia.pdf"),
    (os.path.join(n50, "cenario_5_50pct", "reputacao_por_rodada.pdf"), "n50_p50_reputacao.pdf"),
    (os.path.join(n50, "cenario_7_80pct", "acuracia_4configs.pdf"), "n50_p80_acuracia.pdf"),
    (os.path.join(n50, "cenario_7_80pct", "reputacao_por_rodada.pdf"), "n50_p80_reputacao.pdf"),
    (os.path.join(n50, "cenario_2_5pct", "acuracia_4configs.pdf"), "n50_p5_acuracia.pdf"),
]
copied = []
missing = []
for src_path, name in pairs:
    if os.path.isfile(src_path):
        shutil.copy2(src_path, os.path.join(dst, name))
        copied.append(name)
    else:
        missing.append(src_path)
print("copied", copied)
print("missing", missing)
print("dst", os.path.abspath(dst))
