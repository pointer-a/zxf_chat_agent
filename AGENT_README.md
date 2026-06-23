# 张雪峰视角对话 Agent

这是一个基于本仓库 `SKILL.md` 的本地对话 agent。它会把 skill 内容作为系统提示加载进会话，并维护“首次免责声明”“退出角色”“需要事实先查数据/追问背景”等对话状态。

## 运行

离线演示模式，不需要依赖：

```bash
python -m zxf_agent.cli --offline
```

使用 OpenAI 兼容接口：

```bash
$env:OPENAI_API_KEY="你的 key"
$env:OPENAI_MODEL="gpt-4.1-mini"
python -m zxf_agent.cli
```

如果使用兼容服务，可额外设置：

```bash
$env:OPENAI_BASE_URL="https://你的服务/v1"
```

## 设计

- `zxf_agent/skill_loader.py`：读取 `SKILL.md` 和 frontmatter。
- `zxf_agent/agent.py`：组装系统提示、维护对话历史和角色状态。
- `zxf_agent/providers.py`：提供 OpenAI 兼容模型调用和离线演示 provider。
- `zxf_agent/cli.py`：终端对话入口。

## 注意

这个 agent 会按 skill 要求模拟“张雪峰视角”，并在首次回答中标明“基于公开言论推断，非本人观点”。涉及专业、院校、行业、薪资、录取政策等事实问题时，真实模型也被要求先追问或查数据，不凭空编造。
