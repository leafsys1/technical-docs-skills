# 中文专业技术文档技能

这组 Agent Skills 用于编写和审查专业中文技术文档，适用于模型部署手册、测试手册、运维操作规程和最佳实践指南。重点是可追溯的事实、可执行的步骤、明确的验收条件和复现边界。

## 技能

- [professional-technical-docs](professional-technical-docs/SKILL.md)：编写或实质改写技术文档，按任务读取写作规范、操作契约和文档类型参考资料。
- [technical-docs-review](technical-docs-review/SKILL.md)：审查事实、依赖、步骤、验收及恢复路径，按影响程度报告问题。

两个技能通过相对路径关联，建议一起安装。它们不保证实际环境已验证，也不代表通过厂商认证或 AI 检测。

## 安装

将仓库克隆到本地，然后从仓库根目录复制两个目录到 `~/.agents/skills/`：

```bash
mkdir -p "$HOME/.agents/skills"
cp -R professional-technical-docs technical-docs-review "$HOME/.agents/skills/"
```

如果目标目录已经存在，先检查已有内容，避免覆盖个人修改。支持该共享目录的客户端可在新会话中发现这些技能；具体加载行为取决于客户端配置。也可在请求中明确指定技能名称。

## 离线检查

写作技能自带的检查脚本只检查 Markdown 结构和部分工件引用，不执行文档中的命令，也不能替代事实核对、渲染检查或实际复现：

```bash
python3 professional-technical-docs/scripts/check_manual.py --help
python3 professional-technical-docs/scripts/check_manual.py path/to/manual.md --json
```

## 参考来源

整合方法、来源版本和适用边界见 [来源与整合说明](professional-technical-docs/references/sources.md)，上游署名和许可见 [来源声明](professional-technical-docs/references/source-notices.txt)。
