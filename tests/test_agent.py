from pathlib import Path

from zxf_agent.agent import ConversationAgent, build_system_prompt
from zxf_agent.providers import OfflineDemoProvider
from zxf_agent.skill_loader import load_skill


ROOT = Path(__file__).resolve().parents[1]


def test_load_skill_frontmatter() -> None:
    skill = load_skill(ROOT / "SKILL.md")

    assert skill.name == "zhangxuefeng-perspective"
    assert "张雪峰" in skill.description
    assert "核心心智模型" in skill.body


def test_system_prompt_includes_first_disclaimer_rule() -> None:
    skill = load_skill(ROOT / "SKILL.md")
    prompt = build_system_prompt(skill, in_character=True, disclaimer_sent=False)

    assert "第一次以该视角回答" in prompt
    assert "非本人观点" in prompt
    assert "不要凭空编数据" in prompt


def test_exit_switches_out_of_character() -> None:
    agent = ConversationAgent.from_skill_path(ROOT / "SKILL.md", OfflineDemoProvider())
    answer = agent.reply("退出")

    assert "切回正常模式" in answer
    assert agent.in_character is False
