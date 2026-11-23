import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import push_trending  # noqa: E402
from push_trending import (  # noqa: E402
    Repo,
    language_list,
    localize_repos,
    needs_translation,
    parse_gtx,
    parse_repos,
    render_messages,
    scenario_source,
    trending_link,
)


class ParseTrendingTest(unittest.TestCase):
    def test_fixture(self) -> None:
        page = (ROOT / "tests" / "fixture.html").read_text(encoding="utf-8")
        repos = parse_repos(page)
        self.assertEqual([repo.name for repo in repos], ["acme/widgets", "beta/tool"])
        first = repos[0]
        self.assertEqual(first.description, "Build widgets & ship faster.")
        self.assertEqual(first.language, "Python")
        self.assertEqual(first.stars, 12345)
        self.assertEqual(first.forks, 678)
        self.assertEqual(first.gained, 901)
        self.assertEqual(first.period, "week")
        self.assertEqual(repos[1].stars, 10)
        self.assertIsNone(repos[1].forks)

    def test_message_contains_weekly_fields(self) -> None:
        page = (ROOT / "tests" / "fixture.html").read_text(encoding="utf-8")
        when = datetime(2026, 11, 23, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        messages = render_messages("", parse_repos(page), when)
        text = "\n".join(messages)
        self.assertIn("GitHub 本周热榜 · 全语言", text)
        self.assertIn("第 1 名 · [acme/widgets](https://github.com/acme/widgets)", text)
        self.assertIn("总星数 12,345 · 本周新增 901", text)
        self.assertIn("介绍：Build widgets & ship faster.", text)
        self.assertIn("2026-11-23 09:00", text)
        self.assertLess(len(text.encode("utf-8")), 4096)

    def test_translation_helpers(self) -> None:
        self.assertTrue(needs_translation("Build widgets and ship faster."))
        self.assertFalse(needs_translation("一个用来管理任务的工具"))
        payload = '[[["用来做小组件。","Build widgets.",null,null,1]],null,"en"]'
        self.assertEqual(parse_gtx(payload), "用来做小组件。")

        original = push_trending.translate_to_zh
        original_readme = push_trending.fetch_readme
        push_trending.translate_to_zh = lambda text: "中文介绍"
        push_trending.fetch_readme = lambda name: ""
        try:
            page = (ROOT / "tests" / "fixture.html").read_text(encoding="utf-8")
            repos = localize_repos(parse_repos(page)[:1])
        finally:
            push_trending.translate_to_zh = original
            push_trending.fetch_readme = original_readme
        self.assertEqual(repos[0].description, "中文介绍")
        self.assertEqual(repos[0].name, "acme/widgets")
        self.assertEqual(repos[0].scenario, "")

    def test_scenario_comes_from_use_cases(self) -> None:
        readme = """
# Widgets

Build widgets and ship faster.

## Use cases

Review a pull request before merging it into the main branch.
Share a release checklist with the team when shipping.

## Install

```bash
pip install widgets
```
"""
        source = scenario_source(readme, "Build widgets and ship faster.")
        self.assertIn("pull request", source)
        self.assertNotIn("pip install", source)

        when = datetime(2026, 11, 23, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        repo = Repo(
            name="acme/widgets",
            url="https://github.com/acme/widgets",
            description="做小组件。",
            language="Python",
            stars=10,
            forks=1,
            gained=2,
            period="week",
            scenario="合并代码前先检查改动，并发给同事一起看。",
        )
        text = "\n".join(render_messages("", [repo], when))
        self.assertIn("场景：合并代码前先检查改动，并发给同事一起看。", text)

    def test_language_helpers(self) -> None:
        self.assertEqual(language_list(None), [""])
        self.assertEqual(language_list(" python, go "), ["python", "go"])
        self.assertEqual(
            trending_link("c#"),
            "https://github.com/trending/c%23?since=weekly",
        )
        self.assertEqual(
            trending_link("c++"),
            "https://github.com/trending/c++?since=weekly",
        )


if __name__ == "__main__":
    unittest.main()
