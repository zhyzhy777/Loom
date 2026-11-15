# Loom

Loom 是一个 Python Agent 框架。串行 Graph 按节点信号调度，ReAct Agent 在图上交替调用模型和显式注册的本地工具。运费示例使用可控模型，无需 API 密钥。DeepSeek 适配器仍在计划中。见 [v0.1 范围](docs/01-scope.md)。

使用 Python 3.10 或以上版本，在项目根目录执行：

```sh
python -m examples.stock_graph
python -m examples.shipping_agent
python -m unittest discover -s tests -v
```

库存示例依次输出 `16` 和 `库存不足`，运费示例输出 `运费为20.00 元。`。如需从别的项目导入 `loom`，可在当前虚拟环境执行 `python -m pip install -e .`。运行只依赖 Python 标准库。

开发分阶段验收。每阶段验收通过后，将同一个 Git 提交同步到 GitHub 和 Gitee，以提交编号核对两个平台的版本。
