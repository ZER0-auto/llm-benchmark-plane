# -*- coding: utf-8 -*-
"""下载致知（llm2014/llm_benchmark）的月榜 CSV 到 data/zhizhi/

**为什么要多入口**：2026-10-28 真实周抓取时，`raw.githubusercontent.com` 在这台机器上
先 TLS 握手超时、再连接被重置（WinError 10054），重试 3 次也救不回来——一次网络策略就
让 logic / code_v3 两个计分源整周没有新数据。同一份文件在项目自己的 GitHub Pages
（`llm2014.github.io/llm_benchmark/data/...`，docs/ 就是 Pages 根）和 jsDelivr CDN 上都取得到，
内容一致（实测同为 4624 字节）。所以按"清单 + 文件"两级做多入口：

- 清单：api.github.com（权威，含最新月份）→ jsDelivr 的 packages API（可能滞后一个月，会告警）
- 文件：raw.githubusercontent → GitHub Pages → jsDelivr（先探一次，按可用性排序，之后粘住）

文件**只增不改**：本地已有的月份不会被删除，所以兜底清单滞后也不会丢历史。
"""
import json, os

from fetchlib import get

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "zhizhi")
API = "https://api.github.com/repos/llm2014/llm_benchmark/contents/docs/data/{sub}"
JSD_LIST = "https://data.jsdelivr.com/v1/packages/gh/llm2014/llm_benchmark@main?structure=flat"
SUBS = ["logic", "code_v3"]
BASES = [
    ("github-raw", "https://raw.githubusercontent.com/llm2014/llm_benchmark/main/docs/data/{sub}/{name}"),
    ("github-pages", "https://llm2014.github.io/llm_benchmark/data/{sub}/{name}"),
    ("jsdelivr", "https://cdn.jsdelivr.net/gh/llm2014/llm_benchmark@main/docs/data/{sub}/{name}"),
]


def listing(sub):
    """返回该子目录下的 CSV 文件名列表；主清单失败时退回镜像清单并告警。"""
    try:
        return [x["name"] for x in json.loads(get(API.format(sub=sub))) if x["name"].endswith(".csv")]
    except Exception as e:
        print(f"  {sub}: 主清单不可用（{e.__class__.__name__}: {e}），改用 jsDelivr 镜像清单"
              f"（可能滞后一个月；本地已有月份保留，不会删）", flush=True)
        d = json.loads(get(JSD_LIST))
        pre = f"/docs/data/{sub}/"
        return [x["name"][len(pre):] for x in d.get("files", [])
                if x["name"].startswith(pre) and x["name"].endswith(".csv")]


def probe_order(sub, files):
    """用第一个文件探一遍各入口，返回可用入口（按成功顺序）；全不通就抛错。"""
    order = []
    for label, tpl in BASES:
        url = tpl.format(sub=sub, name=files[0])
        try:
            get(url, timeout=20, tries=1, encoding=None)
            order.append((label, tpl))
            print(f"  {sub}: 入口 {label} 可用", flush=True)
        except Exception as e:
            print(f"  {sub}: 入口 {label} 不可用（{e.__class__.__name__}: {e}）", flush=True)
    if not order:
        raise SystemExit(f"{sub}: 三个入口都取不到 {files[0]}，本周该源没有新数据")
    return order


def main():
    for sub in SUBS:
        out = os.path.join(DATA, sub)
        os.makedirs(out, exist_ok=True)
        files = [n for n in listing(sub) if "-lang" not in n]
        order = probe_order(sub, files)
        updated = unchanged = 0
        for name in files:
            path = os.path.join(out, name)
            last = None
            for label, tpl in order:
                try:
                    blob = get(tpl.format(sub=sub, name=name), timeout=45, tries=2, encoding=None)
                except Exception as e:
                    last = e
                    print(f"  {sub}/{name}: {label} 失败（{e.__class__.__name__}），换下一个入口", flush=True)
                    continue
                old = open(path, "rb").read() if os.path.exists(path) else None
                if blob == old:
                    unchanged += 1
                else:
                    open(path, "wb").write(blob)
                    updated += 1
                    print(f"  {sub}/{name}: {label} {len(blob)} bytes（已更新）", flush=True)
                break
            else:
                raise SystemExit(f"{sub}/{name}: 所有可用入口都失败（最后一次 {last}）；"
                                 f"不静默跳过，否则下游会把'抓不到'当成'没有数据'")
        print(f"{sub}: {len(files)} 个文件，更新 {updated}、未变 {unchanged}")
    print("done")


if __name__ == "__main__":
    main()
