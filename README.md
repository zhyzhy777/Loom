# Loom

Loom 是一个 Python Agent 框架。当前可运行的部分是串行 Graph：节点读写调用方传入的状态，返回字符串信号，由边决定下一步或结束。ReAct Agent、模型适配器和工具注册的设计见 [v0.1 范围](docs/01-scope.md)。

使用 Python 3.10 或以上版本，在项目根目录执行：

```sh
python -m examples.stock_graph
python -m unittest discover -s tests -v
```

示例依次输出 `16` 和 `库存不足`。如需从别的项目导入 `loom`，可在当前虚拟环境执行 `python -m pip install -e .`。Graph 运行只依赖 Python 标准库。

开发分阶段验收。每阶段验收通过后，将同一个 Git 提交同步到 GitHub 和 Gitee，以提交编号核对两个平台的版本。
