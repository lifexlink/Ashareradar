import shutil, pathlib

src_candidates = [
    pathlib.Path("../ashare_oneclick_v2/data/latest_signals.json"),
    pathlib.Path("../ashare_oneclick_v3/data/latest_signals.json"),
    pathlib.Path("./data/latest_signals.json"),
]

dst = pathlib.Path("./data/latest_signals.json")
for src in src_candidates:
    if src.exists() and src.resolve() != dst.resolve():
        shutil.copy(src, dst)
        print(f"已复制信号文件: {src} -> {dst}")
        break
else:
    print("未找到旧版信号文件，请手动替换 data/latest_signals.json")
