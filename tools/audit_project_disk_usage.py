# -*- coding: utf-8 -*-
import os

root = '.'
total_bytes = 0
dir_sizes = {}
root_files_bytes = 0

for item in os.listdir(root):
    p = os.path.join(root, item)
    if os.path.isdir(p):
        d_sz = 0
        file_cnt = 0
        for r, dirs, files in os.walk(p):
            for f in files:
                fp = os.path.join(r, f)
                try:
                    s = os.path.getsize(fp)
                    d_sz += s
                    file_cnt += 1
                except:
                    pass
        dir_sizes[item] = (d_sz, file_cnt)
        total_bytes += d_sz
    else:
        try:
            s = os.path.getsize(p)
            root_files_bytes += s
            total_bytes += s
        except:
            pass

def fmt(b):
    if b >= 1024**3:
        return f"{b/(1024**3):.3f} GB"
    if b >= 1024**2:
        return f"{b/(1024**2):.2f} MB"
    if b >= 1024:
        return f"{b/1024:.2f} KB"
    return f"{b} B"

print(f"Total Project Disk Usage: {fmt(total_bytes)} ({total_bytes} bytes)\n")
print(f"Root Files Total: {fmt(root_files_bytes)}\n")
print(f"{'Directory':<28} | {'Size':<12} | {'Files':<8}")
print("-" * 55)
for d, (sz, cnt) in sorted(dir_sizes.items(), key=lambda x: x[1][0], reverse=True):
    print(f"{d:<28} | {fmt(sz):<12} | {cnt:<8}")
