# -*- coding: utf-8 -*-
"""抓取用的 HTTP 客户端：带重试的 GET（四个 fetch_*.py 共用）。

为什么单独抽出来：2026-10-28 第一次真实周抓取，致知第 2 个文件撞上 TLS 握手超时
（`ssl.c:1063: The handshake operation timed out`），一次失败就让整个源丢掉一周的数据。
周任务必须分清两件事：**这周榜单没变化**（是观测）与**这周没抓成**（是缺失）。
重试解决前者被误报成后者的概率；后者由 `fetch_week.py` 的 `fetch_status` 记录。

`fetch_bl.py` 不用这里：它自带线程池与 `--workers/--timeout` 参数，重试写在抓取循环里
（理由是 BL 站点单源 200 KB+、约 8 KB/s，超时要比别的源长得多）。
"""
import http.client, socket, time, urllib.error, urllib.request

TRIES = 3          # 总共试几次（含第一次）
BACKOFF = 2.0      # 秒；第 n 次失败后等 BACKOFF × n


def get(url, timeout=90, tries=TRIES, headers=None, encoding="utf-8"):
    """GET 一个 URL，失败重试；`encoding=None` 时返回 bytes（下载文件用）。

    重试的边界：5xx / 429 / 连接与超时类错误重试；其它 4xx 直接放弃
    （404 重试三次只是多等 6 秒，而且会把"这个 slug 不存在"伪装成网络问题）。
    全部失败就抛出最后一次异常——调用方必须失败退出，不许静默跳过，
    否则"抓不到"会被下游当成"没有数据"。
    """
    hdr = {"User-Agent": "Mozilla/5.0"}
    hdr.update(headers or {})
    last = None
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                blob = r.read()
            return blob if encoding is None else blob.decode(encoding, "ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                raise
        except (urllib.error.URLError, http.client.HTTPException,
                socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            last = e
        if i < tries:
            wait = BACKOFF * i
            print(f"  第 {i} 次失败（{last.__class__.__name__}: {last}），{wait:.0f}s 后重试",
                  flush=True)
            time.sleep(wait)
    raise last
