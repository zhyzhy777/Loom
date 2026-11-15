# Loom v0.1 使用方式

使用方式已确认。工具采用 `@tool` 和显式工具列表。以下为计划提供的 Python API。

## 使用者需要做的事

配置 DeepSeek 模型，编写并注册工具，创建 Agent，调用 `run()` 并读取结果。Agent 内置一张串行执行的 ReAct 图。

## 最小调用示例

```python
import os

from loom import Agent, DeepSeekModel, tool


@tool
def calculate_shipping(weight_kg: float) -> str:
    """按固定费率计算运费，返回人民币金额；weight_kg 是包裹重量，单位为千克。"""
    if weight_kg <= 0:
        raise ValueError("包裹重量必须大于 0")
    return f"{weight_kg * 8:.2f} 元"


model = DeepSeekModel(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    model=os.environ["DEEPSEEK_MODEL"],
    timeout_seconds=30,
)

agent = Agent(
    model=model,
    instructions="你是运费助手。涉及运费计算时使用工具，根据工具结果用中文回答。",
    tools=[calculate_shipping],
    max_model_calls=8,
)

result = agent.run("一个 2.5 千克的包裹，运费是多少？")
print(result.text)
```

这里采用示例费率，每千克 8 元；期望回答包含运费 20 元，最终措辞由模型生成。需要真实配置支持工具调用的 DeepSeek 模型才能运行。

`DeepSeekModel` 默认连接 DeepSeek 官方地址 `https://api.deepseek.com`。`DEEPSEEK_API_KEY` 填写 DeepSeek 密钥，`DEEPSEEK_MODEL` 填写服务实际支持的模型标识；模型名以 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/) 为准。环境变量由使用者的代码读取，框架不隐式读取上述名称。具体模型模式及供应商参数在后续适配设计时明确。

## 工具是什么意思

工具就是允许模型请求调用的函数。例如，上面的 `calculate_shipping` 原本只是一个 Python 函数；加上 `@tool` 并放入 `tools` 后，框架会把它的名称、用途和参数说明提供给模型。

本次任务中，模型可以请求“调用 calculate_shipping，weight_kg 为 2.5”。框架找到已注册函数，在本地执行 `calculate_shipping(weight_kg=2.5)`，再把返回的 `20.00 元` 交给模型，模型据此组织最终回答。模型本身不直接运行这个 Python 函数。

使用者写函数实现和说明；框架负责生成工具描述、注册、参数校验与执行、回传结果。具体交互和失败规则见[基础协议](03-protocol.md)。

工具也可以是查询订单、访问数据库或调用天气 API 的函数。“本地”描述的是函数执行位置，不限制它访问外部服务。第一版先提供通用的函数工具机制，不内置这些业务工具。

## 使用体验约定

- `DeepSeekModel` 使用 DeepSeek 连接配置，按 OpenAI Chat Completions 格式发送消息和工具说明，接收回答或工具调用请求。
- `@tool` 将带类型注解和文档字符串的同步函数注册为工具，不要求使用者编写 JSON Schema；参数含义写在文档字符串中。
- `Agent` 保存可复用的运行配置。`instructions` 是系统指令，`tools` 是显式允许模型调用的工具集合；可传入空列表。
- `run()` 接收一个任务字符串，同步执行整个任务，成功时返回可读取 `.text` 的结果对象。
- `max_model_calls=8` 表示一次任务最多向模型发出 8 次请求，包括首次请求和工具执行后的后续请求；它不是工具调用次数限制。
- 同一个 Agent 可以重复使用，但每次 `run()` 都从新任务开始；第二次调用不会记得第一次调用。

## 一次 `run()` 怎样经过默认图

模型节点是入口。它收到任务后调用 DeepSeek。图根据模型回复选择下一步，每次只执行一个节点。

| 模型回复 | 图的走向 | 运费示例 |
| --- | --- | --- |
| 请求调用工具 | 从模型节点进入工具节点，再沿回边返回模型节点 | 工具节点调用已注册的 `calculate_shipping(weight_kg=2.5)`，把 `20.00 元` 写入本次任务上下文 |
| 给出最终回答 | 从模型节点结束本次运行 | `agent.run(...)` 返回结果，使用者从 `result.text` 读取回答 |

`tools=[calculate_shipping]` 给同一个工具节点提供可调用的函数。使用者可以按任务更换这个列表，继续使用同一张默认图。并行分支和分支结果合并留到后续版本。

## 暂不在示例中承诺的内容

本轮不提供 `messages`、`memory`、`stream`、回调、完整执行轨迹。同一轮的多个工具请求按顺序执行，失败行为见[基础协议](03-protocol.md)。

## 运行结果

调用者用 `agent.run(task).text` 取得成功结果。按[基础协议](03-protocol.md)，运行失败会抛出带原因的 `RunError`。

## 独立运行一张业务图

下例用库存数量选择分支。每个节点都是可单独调用的 Python 函数。图负责串行调度，业务字典在本次运行中由节点就地更新。

```python
from loom import END, Graph

def check_stock(order):
    return "available" if order["stock"] >= order["quantity"] else "short"

def quote(order):
    order["total"] = order["unit_price"] * order["quantity"]
    return "done"

graph = Graph()
graph.add_node("check", check_stock)
graph.add_node("quote", quote)
graph.set_entry("check")
graph.add_edge("check", "available", "quote")
graph.add_edge("check", "short", END)
graph.add_edge("quote", "done", END)

run = graph.run({"stock": 3, "quantity": 2, "unit_price": 8}, max_steps=4)
if run.status == "failed":
    raise run.error
print(run.state.get("total", "库存不足"))  # 16
```

## 替换 Agent 的模型

自定义适配器提供 `complete(messages, tools)`。例如，本地测试可以用固定回复验证 Agent 的完成分支。

```python
from loom import Agent, ModelReply

class FixedModel:
    def complete(self, messages, tools):
        return ModelReply(finish_reason="stop", text="已收到任务", calls=[], provider_fields={})

agent = Agent(model=FixedModel(), instructions="用中文回答", tools=[], max_model_calls=2)
print(agent.run("你好").text)  # 已收到任务
```
