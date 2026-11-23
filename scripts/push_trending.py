#!/usr/bin/env python3
"""Fetch GitHub's official weekly Trending page and push it to a WeCom group bot."""

from __future__ import annotations

import argparse
import html
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo

TRENDING_URL = "https://github.com/trending"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PERIOD_LABEL = {"day": "今日", "week": "本周", "month": "本月"}
MESSAGE_LIMIT = 3800
SHANGHAI = ZoneInfo("Asia/Shanghai")

ARTICLE_RE = re.compile(
    r'<article\b[^>]*\bclass="[^"]*\bBox-row\b[^"]*"[^>]*>([\s\S]*?)</article>',
    re.IGNORECASE,
)
DESC_RE = re.compile(
    r'<p\b[^>]*\bclass="[^"]*\bcol-9\b[^"]*"[^>]*>\s*([\s\S]*?)\s*</p>',
    re.IGNORECASE,
)
LANG_RE = re.compile(
    r'itemprop="programmingLanguage">\s*([^<]+?)\s*<',
    re.IGNORECASE,
)
STARS_RE = re.compile(
    r'href="/[^"]+/stargazers"[^>]*>[\s\S]*?([\d,]+)\s*</a>',
    re.IGNORECASE,
)
FORKS_RE = re.compile(
    r'href="/[^"]+/forks"[^>]*>[\s\S]*?([\d,]+)\s*</a>',
    re.IGNORECASE,
)
GAINED_RE = re.compile(
    r'([\d,]+)\s+stars this (day|week|month)',
    re.IGNORECASE,
)


@dataclass
class Repo:
    name: str
    url: str
    description: str
    language: str
    stars: int | None
    forks: int | None
    gained: int | None
    period: str


def clean_text(value: str, limit: int = 160) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", value))
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("<", "＜").replace(">", "＞")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_count(value: str | None) -> int | None:
    if not value:
        return None
    return int(value.replace(",", ""))


def format_count(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def parse_repos(page: str) -> list[Repo]:
    repos: list[Repo] = []
    for block in ARTICLE_RE.findall(page):
        full_name = ""
        for href in re.findall(r'href="(/[^"]+)"', block):
            if href.startswith("/login"):
                continue
            parts = [part for part in href.split("/") if part]
            if len(parts) == 2 and parts[0] not in {"topics", "features", "sponsors"}:
                full_name = f"{parts[0]}/{parts[1]}"
                break
        if not full_name:
            continue

        description = ""
        desc_match = DESC_RE.search(block)
        if desc_match:
            description = clean_text(desc_match.group(1), limit=500)

        language = ""
        lang_match = LANG_RE.search(block)
        if lang_match:
            language = clean_text(lang_match.group(1), limit=40)

        gained_match = GAINED_RE.search(block)
        repos.append(
            Repo(
                name=full_name,
                url=f"https://github.com/{full_name}",
                description=description,
                language=language,
                stars=parse_count(STARS_RE.search(block).group(1) if STARS_RE.search(block) else None),
                forks=parse_count(FORKS_RE.search(block).group(1) if FORKS_RE.search(block) else None),
                gained=parse_count(gained_match.group(1) if gained_match else None),
                period=gained_match.group(2).lower() if gained_match else "week",
            )
        )
    return repos


def fetch_trending(language: str, retries: int = 3) -> str:
    path = ""
    if language:
        path = "/" + urllib.parse.quote(language.strip(), safe="+")
    url = f"{TRENDING_URL}{path}?since=weekly"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
            if "Box-row" not in body:
                raise RuntimeError(f"GitHub Trending 页面没有仓库列表：{url}")
            return body
        except (
            OSError,
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            RuntimeError,
        ) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 2)
    raise RuntimeError(f"抓取失败 {url}：{last_error}")


def board_title(language: str) -> str:
    return language.strip() if language.strip() else "全语言"


def trending_link(language: str) -> str:
    path = ""
    if language.strip():
        path = "/" + urllib.parse.quote(language.strip(), safe="+")
    return f"{TRENDING_URL}{path}?since=weekly"


def needs_translation(text: str) -> bool:
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    letters = sum(1 for char in text if char.isascii() and char.isalpha())
    return letters > 0 and cjk < letters


def parse_gtx(payload: str) -> str:
    data = json.loads(payload)
    if not data or not isinstance(data[0], list):
        raise RuntimeError("翻译结果为空")
    parts = [item[0] for item in data[0] if item and item[0]]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("翻译结果为空")
    return text


def http_get(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def translate_gtx(text: str) -> str:
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text}
    )
    return parse_gtx(
        http_get("https://translate.googleapis.com/translate_a/single?" + query)
    )


def translate_mymemory(text: str) -> str:
    query = urllib.parse.urlencode({"q": text[:500], "langpair": "en|zh-CN"})
    data = json.loads(http_get("https://api.mymemory.translated.net/get?" + query))
    translated = html.unescape(str(data.get("responseData", {}).get("translatedText", "")))
    status = data.get("responseStatus")
    if status not in (200, "200") or not translated.strip():
        detail = data.get("responseDetails") or "MyMemory 翻译失败"
        raise RuntimeError(str(detail))
    if "MYMEMORY WARNING" in translated.upper():
        raise RuntimeError(translated)
    return translated.strip()


def translate_to_zh(text: str) -> str:
    text = text.strip()
    if not text or not needs_translation(text):
        return text
    errors: list[str] = []
    for attempt in range(1, 3):
        try:
            return translate_gtx(text)
        except (
            OSError,
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            RuntimeError,
            json.JSONDecodeError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            errors.append(str(exc))
            if attempt == 1:
                time.sleep(1)
    try:
        return translate_mymemory(text)
    except (
        OSError,
        urllib.error.URLError,
        http.client.HTTPException,
        TimeoutError,
        RuntimeError,
        json.JSONDecodeError,
        IndexError,
        TypeError,
        ValueError,
    ) as exc:
        errors.append(str(exc))
        print(f"介绍翻译失败，这条保留原文：{errors[-1]}", file=sys.stderr)
        return text


def localize_repos(repos: list[Repo]) -> list[Repo]:
    localized: list[Repo] = []
    for repo in repos:
        description = translate_to_zh(repo.description) if repo.description else ""
        localized.append(replace(repo, description=description))
    return localized


def render_repo(index: int, repo: Repo) -> str:
    period = PERIOD_LABEL.get(repo.period, "本周")
    description = repo.description or "暂无介绍"
    return "\n".join(
        [
            f"**第 {index} 名 · [{repo.name}]({repo.url})**",
            f"总星数 {format_count(repo.stars)} · {period}新增 {format_count(repo.gained)}",
            f"介绍：{description}",
        ]
    )


def render_messages(language: str, repos: list[Repo], when: datetime) -> list[str]:
    title = board_title(language)
    stamp = when.strftime("%Y-%m-%d %H:%M")
    header = "\n".join(
        [
            f"## GitHub 本周热榜 · {title}",
            (
                f"<font color=\"comment\">{stamp}（北京时间）· "
                f"[Trending]({trending_link(language)})</font>"
            ),
        ]
    )
    blocks = [render_repo(index, repo) for index, repo in enumerate(repos, start=1)]
    if not blocks:
        return [header + "\n\n本周没有抓到仓库。"]

    messages: list[str] = []
    current = header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate.encode("utf-8")) <= MESSAGE_LIMIT:
            current = candidate
            continue
        messages.append(current)
        current = header.replace("## GitHub 本周热榜", "## GitHub 本周热榜（续）", 1)
        current = current + "\n\n" + block
    messages.append(current)
    return messages


def post_wecom(webhook: str, content: str) -> None:
    payload = json.dumps(
        {"msgtype": "markdown", "markdown": {"content": content}},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("errcode") != 0:
        raise RuntimeError(f"企微返回错误：{data}")


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y"}


def positive_int(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    number = int(str(value).strip())
    if number < 1 or number > 25:
        raise ValueError("TOP_N 需要在 1 到 25 之间")
    return number


def language_list(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return [""]
    return [item.strip() for item in raw.split(",") if item.strip()] or [""]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把 GitHub 官方 Trending 周榜推到企微群")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息，不推送")
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--languages", default=None, help="逗号分隔，例如 python,go。留空表示全语言")
    parser.add_argument("--html", help="解析本地 HTML，不请求 GitHub")
    parser.add_argument("--webhook", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = args.dry_run or env_flag("DRY_RUN")
    top_n = positive_int(
        str(args.top) if args.top is not None else os.environ.get("TOP_N"),
        10,
    )
    languages = language_list(
        args.languages if args.languages is not None else os.environ.get("LANGUAGES")
    )
    webhook = (args.webhook or os.environ.get("WECOM_WEBHOOK") or "").strip()
    when = datetime.now(SHANGHAI)

    if not dry_run and not webhook:
        print("缺少 WECOM_WEBHOOK。先在仓库 Secrets 里配置，或本地加 --dry-run。", file=sys.stderr)
        return 2
    if webhook and not webhook.startswith("https://qyapi.weixin.qq.com/"):
        print("WECOM_WEBHOOK 不是企微群机器人地址。", file=sys.stderr)
        return 2

    messages: list[str] = []
    if args.html:
        page = open(args.html, encoding="utf-8").read()
        repos = localize_repos(parse_repos(page)[:top_n])
        if not repos:
            print(f"没有解析到仓库：{args.html}", file=sys.stderr)
            return 1
        messages.extend(render_messages(languages[0], repos, when))
    else:
        for language in languages:
            page = fetch_trending(language)
            repos = localize_repos(parse_repos(page)[:top_n])
            if not repos:
                print(f"没有解析到仓库：{trending_link(language)}", file=sys.stderr)
                return 1
            messages.extend(render_messages(language, repos, when))

    for index, content in enumerate(messages):
        if dry_run:
            print(content)
            if index < len(messages) - 1:
                print("\n----- message -----\n")
            continue
        post_wecom(webhook, content)
        if index < len(messages) - 1:
            time.sleep(0.4)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, urllib.error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
