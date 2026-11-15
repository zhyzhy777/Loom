# Loom

Loom 是一个 Python Agent 框架。串行 Graph 按节点信号调度，ReAct Agent 在图上交替调用模型和显式注册的本地工具。运费示例通过 DeepSeekModel 接入 DeepSeek，配置及调用示例见[使用方式](docs/02-usage.md)。

使用 Python 3.10 或以上版本，在项目根目录执行：

```sh
python -m examples.stock_graph
python -m unittest discover -s tests -v
```

库存示例依次输出 `16` 和 `库存不足`。运行真实运费示例前，在本地环境中设置 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`，再执行 `python -m examples.shipping_agent`。示例打印本地工具实际收到的重量、算出的金额以及模型的最终回答。

如需从别的项目导入 `loom`，在 Loom 仓库根目录执行 `python -m pip install .`，即可将它安装到当前 Python 环境。开发时可使用 `python -m pip install -e .`，让源码修改直接生效。运行只依赖 Python 标准库。

每次推送和提交拉取请求时，GitHub Actions 会在 Python 3.10、3.12 和 3.14 上安装 Loom，然后从仓库外运行单元测试和库存示例。真实运费示例使用本地提供的 DeepSeek 配置单独运行。

开发分阶段验收。每阶段验收通过后，将同一个 Git 提交同步到 GitHub 和 Gitee，以提交编号核对两个平台的版本。
