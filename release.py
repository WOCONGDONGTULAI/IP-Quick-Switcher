#!/usr/bin/env python3
"""自动发布下一个版本。

版本号规则：纯数字递增 —— 1、2、3 …… 数字最大即最新版。

用法：
    python release.py              # 发布 <当前最大版本 + 1>
    python release.py --dry-run    # 只打印将要做什么，不实际发布
    python release.py --notes 文本  # 自定义一句话说明

依赖：GitHub CLI（https://cli.github.com），需先执行 gh auth login
说明：本脚本只通过 API 操作远端仓库，不需要本地 clone。
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "WOCONGDONGTULAI/IP-Quick-Switcher"
API = "https://api.github.com"


def gh_token():
    """向 gh CLI 索取当前登录凭据。"""
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        sys.exit("未找到 gh。请先安装 GitHub CLI（https://cli.github.com）")
    except subprocess.CalledProcessError:
        sys.exit("gh 尚未登录，请先执行 gh auth login")

    token = proc.stdout.strip()
    if not token:
        sys.exit("gh 未返回有效令牌，请先执行 gh auth login")
    return token


def request(method, path, token, payload=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ip-switcher-release")

    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, body or None) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit("GitHub API %s %s 失败（HTTP %s）:\n%s" % (method, path, exc.code, detail))


def latest_version(token):
    """取现有标签里最大的纯数字版本号，没有则返回 0。"""
    data = request("GET", "/repos/%s/tags?per_page=100" % REPO, token) or []
    numbers = []
    for tag in data:
        name = str(tag.get("name", "")).strip()
        if name.isdigit():
            numbers.append(int(name))
    return max(numbers) if numbers else 0


def head_sha(token):
    commits = request("GET", "/repos/%s/commits?per_page=1" % REPO, token)
    if not commits:
        sys.exit("仓库还没有任何提交")
    return commits[0]["sha"]


def changed_commits(token, base, head):
    """自上一个版本以来的提交，用于生成更新说明。"""
    if base is None:
        data = request("GET", "/repos/%s/commits?per_page=100" % REPO, token) or []
        return list(reversed(data))

    data = request("GET", "/repos/%s/compare/%s...%s" % (REPO, base, head), token)
    return list(reversed(data.get("commits", [])))


def build_body(commits, current, note):
    lines = []
    if note:
        lines.append(note.strip())
        lines.append("")
    else:
        lines.append("IP 快速切换器 **版本 %d**。" % current)
        lines.append("")

    if commits:
        lines.append("## 本次更新")
        lines.append("")
        for item in commits:
            message = item["commit"]["message"].strip().splitlines()[0]
            lines.append("- %s" % message)
        lines.append("")
    lines.append(
        "完整源码见本页下方的 **Source code** 附件（zip / tar.gz）。"
        "exe 需在 Windows 上运行 `build.bat` 生成。"
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="发布下一个版本")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不实际发布")
    parser.add_argument("--notes", default="", help="自定义一句话更新说明")
    parser.add_argument("--repo", default=REPO, help="目标仓库，默认 %s" % REPO)
    args = parser.parse_args()

    globals()["REPO"] = args.repo
    token = gh_token()

    current = latest_version(token)
    nxt = current + 1
    sha = head_sha(token)
    commits = changed_commits(token, str(current) if current else None, sha)

    print("仓库        : %s" % REPO)
    print("当前最新版  : %s" % (current or "（无）"))
    print("即将发布    : %s" % nxt)
    print("目标提交    : %s" % sha[:7])
    print("包含提交    : %d 个" % len(commits))
    for item in commits:
        print("   - %s" % item["commit"]["message"].strip().splitlines()[0])

    if args.dry_run:
        print("\n[dry-run] 未实际发布。")
        return

    release = request(
        "POST", "/repos/%s/releases" % REPO, token,
        {
            "tag_name": str(nxt),
            "target_commitish": sha,
            "name": "版本 %d" % nxt,
            "body": build_body(commits, nxt, args.notes),
            "draft": False,
            "prerelease": False,
        },
    )
    print("\n发布成功：%s" % release.get("html_url", ""))


if __name__ == "__main__":
    main()
