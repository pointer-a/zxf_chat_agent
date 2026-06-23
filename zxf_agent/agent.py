from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .providers import ChatProvider, Message
from .skill_loader import Skill, load_skill


EXIT_TRIGGERS = ("退出", "切回正常", "不用扮演了", "不用扮演")


@dataclass
class ConversationAgent:
    skill: Skill
    provider: ChatProvider
    history: list[Message] = field(default_factory=list)
    in_character: bool = True
    disclaimer_sent: bool = False

    @classmethod
    def from_skill_path(cls, skill_path: str | Path, provider: ChatProvider) -> "ConversationAgent":
        return cls(skill=load_skill(skill_path), provider=provider)

    def reply(self, user_text: str) -> str:
        if any(trigger in user_text for trigger in EXIT_TRIGGERS):
            self.in_character = False

        messages = self._build_messages(user_text)
        answer = self.provider.complete(messages)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})

        if self.in_character and not self.disclaimer_sent:
            self.disclaimer_sent = True
        return answer

    def _build_messages(self, user_text: str) -> list[Message]:
        system_prompt = build_system_prompt(self.skill, self.in_character, self.disclaimer_sent)
        return [{"role": "system", "content": system_prompt}, *self.history[-16:], {"role": "user", "content": user_text}]


def build_system_prompt(skill: Skill, in_character: bool, disclaimer_sent: bool) -> str:
    if not in_character:
        return (
            "你是一个中文对话助手。用户已经要求退出张雪峰视角，后续不要继续角色扮演。"
            "可以在需要时引用该 skill 的框架，但必须明确这是分析工具，而不是继续扮演。"
        )

    disclaimer_rule = (
        "本轮如果是本会话第一次以该视角回答，开头只说一次："
        "「我以张雪峰视角和你聊，基于公开言论推断，非本人观点。」"
        if not disclaimer_sent
        else "本会话免责声明已经说过，后续不要重复。"
    )

    return f"""
你是一个对话 agent，必须严格基于下面的 Agent Skill 运作。

运行规则：
1. {disclaimer_rule}
2. 用户说“退出”“切回正常”“不用扮演了”时，停止角色扮演。
3. 涉及具体分数、专业、院校、行业、就业、薪资、录取、政策等事实问题时，不要凭空编数据，如果没查到就说没查到。
4. 如果运行环境没有提供实时搜索结果，你必须先追问必要背景，或明确说需要先查就业率、薪资中位数、录取线、毕业去向等数据。
5. 回答要先给判断，再解释；短句、高密度、中文口语；避免“可能、或许、这取决于”等模糊套话。
6. 给教育和职业建议时，优先追问分数/学历、省份、家庭资源、目标城市、风险承受能力。
7. 不要输出内部分类过程，不要写“Step 1/Step 2”，直接像一个真实对话 agent 一样回答。

以下是必须遵循的 skill 内容：

{skill.raw}
""".strip()
