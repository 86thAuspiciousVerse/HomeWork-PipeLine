# HomeWork-PipeLine

> Claude Code 全局插件。把你的课程要求 docx 扔进去，全自动产出可交付的数据科学课程设计作业。

## 安装

```bash
# 添加 marketplace
claude plugin marketplace add 86thAuspiciousVerse/HomeWork-PipeLine

# 安装插件
claude plugin install homework-pipeline@homework-dev
```

## 使用

把课程要求的 `.docx` 或 `.md` 文件放在你的作业目录里，然后：

```
cd ~/my-homework/
/hw doc/课程要求.docx
```

管线会自动推进：抽取课程约束 → 裁决哪些可自动验证 → 规划技术方案 → 生成代码 → 真实执行 → 机器校验 → 打包交付。最终产物在 `delivery/` 目录下。

## 更新

```bash
claude plugin update homework-pipeline@homework-dev
```
