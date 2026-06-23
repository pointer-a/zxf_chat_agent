from __future__ import annotations

import argparse
from pathlib import Path

from .agent import ConversationAgent
from .providers import OfflineDemoProvider, OpenAICompatibleProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Zhang Xuefeng perspective dialogue agent.")
    parser.add_argument("--skill", default="SKILL.md", help="Path to the skill markdown file.")
    parser.add_argument("--model", default=None, help="OpenAI-compatible chat model name.")
    parser.add_argument("--offline", action="store_true", help="Use deterministic offline demo mode.")
    args = parser.parse_args()

    provider = None if args.offline else OpenAICompatibleProvider.from_env(args.model)
    if provider is None:
        provider = OfflineDemoProvider()
        print("未检测到 OPENAI_API_KEY，已进入离线演示模式。配置 API key 后可使用真实模型。")

    agent = ConversationAgent.from_skill_path(Path(args.skill), provider)
    print("张雪峰视角对话 agent 已启动。输入“退出”可切回正常，输入 Ctrl+C 结束。")

    while True:
        try:
            user_text = input("\n你 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n已结束。")
            break
        if not user_text:
            continue
        print(f"\nAgent > {agent.reply(user_text)}")


if __name__ == "__main__":
    main()
