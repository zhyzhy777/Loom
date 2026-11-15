# Loom v0.1 基础协议

运行行为已确认。下面的模块接口与字段约定是供审阅的 v0.1 设计稿。一次 `run(task)` 对应一次独立任务。节点执行一步并报告结果，Graph 据此选择下一条边或结束任务。

## 模块交换的数据

| 数据 | 字段与含义 |
| --- | --- |
| ToolCall | `id: str`、`name: str`、`arguments: str`。保留模型提供的调用 ID 和 JSON 参数原文 |
| ToolResult | `tool_call_id: str`、`content: str`。ID 对应一次请求，同名工具可调用多次 |
| ModelReply | `finish_reason`、可空的 `text`、有序的 `calls: list[ToolCall]`。适配层保留连续调用模型时需要回传的原始助手消息字段 |
| AgentState | ReAct 模板的消息、待执行调用、模型调用计数和最终回答，由模板节点维护 |
| GraphRun[S] | `state: S` 是调用者提供的业务状态，另有 `status`、`current_node`、`steps` 和可空的 `error`，由执行器记录 |
| RunError | `code`、出错节点、可读原因。工具错误附调用 ID。调用者可按错误码区分模型错误、工具错误、无效回复或达到上限 |

## 消息字段

消息按发生顺序追加。下表写的是 Loom 内部字段，DeepSeek 适配器负责与 Chat Completions 字段互转。

| `role` | 字段 | 谁追加 |
| --- | --- | --- |
| `system` | `content: str`，任务指令 | Agent 初始化时 |
| `user` | `content: str`，本次任务 | Agent 初始化时 |
| `assistant` | `content: str 或 None`、`calls: list[ToolCall]`、`provider_fields: dict`。无调用时列表为空，适配器专属的回传字段默认为空字典 | 模型节点，每次有效回复追加一条 |
| `tool` | `tool_call_id: str`、`content: str`，由 ToolResult 转成消息 | 工具节点，每次函数成功后追加一条 |

`ModelReply` 也携带 `provider_fields`。模型节点原样存入助手消息，后续发送历史时由适配器恢复。序列化工具请求时，适配器将内部的 `calls` 转为 `tool_calls`，将名称和 JSON 参数原文放进各项的 `function`。工具结果始终按 ID 对应本批请求。

## 模块接口（Python 签名示意）

```python
from typing import Callable, Generic, Protocol, TypeVar

S = TypeVar("S")

class Model(Protocol):
    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply: ...

class ToolRegistry:
    def describe(self) -> list[ToolSpec]: ...
    def execute(self, call: ToolCall) -> ToolResult: ...

class Graph(Generic[S]):
    def add_node(self, name: str, fn: Callable[[S], str]) -> None: ...
    def set_entry(self, name: str) -> None: ...
    def add_edge(self, source: str, signal: str, target: str | EndMarker) -> None: ...
    def run(self, state: S, *, max_steps: int) -> GraphRun[S]: ...

class Agent:
    def run(self, task: str) -> RunResult: ...
```

`ToolSpec` 含 `name: str`、`description: str` 和 `parameters: dict`。注册表从当前 Agent 的显式工具列表构建，同名工具或不支持的函数签名在构建时抛出 `ValueError`。参数 schema 用 object 表示，各参数列入 required，额外字段不接受。执行前按同一规则校验，布尔值不能当整数，整数可以作为浮点参数传入。模型节点持有模型和注册表，工具节点持有同一个注册表。模板将两者都作为普通节点函数注册到图中。内置 DeepSeekModel 和用户提供的适配器遵循同一个 Model 接口。

## 通用 Graph 的执行约定

每个节点接收业务状态 S，按需就地更新并返回字符串信号。每张图自行命名信号。Graph 按 (当前节点, 信号) 唯一选边。目标为公开的结束标记 END 时成功返回，否则继续运行目标节点，允许回到已访问的节点。

运行前校验入口、节点名、边的两端、重复路由及正整数步数上限，配置错误抛出 ValueError。每次运行从入口、running 和零步开始，调用节点前占用一步。最后允许的一步若走到 END 则成功，若还需执行下一步则在调用前以 step_limit 失败。找不到匹配边、返回非法信号或节点抛出意外异常，以 graph_error 失败。已带原因的 RunError 原样保存。Graph 返回包含业务状态及终态的 GraphRun，保留最后执行节点及已执行步数。每次运行的调度记录独立，调用者为独立任务提供新的业务状态对象。

## ReAct 模板的状态及写入权限

Agent 为每次运行创建一个 AgentState。每个字段只有下表列出的写入者，节点通过返回信号交还控制权。

| 字段 | 初始值 | 运行时由谁写 |
| --- | --- | --- |
| `messages: list[Message]` | Agent 放入 system、user 消息 | 模型节点追加助手消息，工具节点追加工具结果 |
| `pending_calls: list[ToolCall]` | 空列表 | 模型节点按回复顺序填入。工具节点每成功处理一项便移除队首，失败时保留失败项及剩余项 |
| `model_calls: int`、`max_model_calls: int` | 0 和 Agent 配置的正整数 | 模型节点在发请求前将计数加一，额度只读 |
| `final_text: str 或 None` | None | 模型节点确认有效最终回答时写入 |

## Graph 怎样接收节点结果

默认图的入口是 `model`。Graph 每次调用注册的节点函数 `fn(state)`，再按下表处理。同一时间只会有一个正在执行的节点。

| 当前节点 | 节点返回或抛出 | 必须已经满足 | Graph 的动作 |
| --- | --- | --- | --- |
| model | `needs_tools` | 最新助手消息含调用，pending_calls 与这批调用一致，仍有下一轮模型额度 | 保持 running，前往 tools |
| tools | `tools_done` | 本批结果已全部回写，pending_calls 为空 | 保持 running，回到 model |
| model | `answered` | 最新助手消息为有效最终回答，pending_calls 为空 | 沿边走到 END，置 completed，返回终态 |
| 任一 | 抛出 `RunError` | 错误含原因 | 写入 error，置 failed，返回终态 |

表中消息及工具相关条件由模板节点验证。通用 Graph 只按注册的边调度。Agent 使用 max_steps = 2 × max_model_calls：每轮至多一次模型节点和一次工具节点。它读取 GraphRun，成功时从 AgentState.final_text 构造 RunResult，失败时抛出保存的 RunError。

## 错误如何穿过模块边界

`RunError` 是异常，字段为 `code: str`、`node: str`、`message: str`、`tool_call_id: str 或 None`。模型适配器将请求超时与服务错误分别转为 `model_timeout`、`model_error`，无法解码的回复转为 `invalid_reply`，节点名均为 model。模型节点检查结束原因、调用 ID、正文与额度，分别以 `invalid_reply` 或 `model_limit` 报告失败。注册表对未知工具、参数不合法、函数异常或返回非字符串，分别报告 `unknown_tool`、`invalid_arguments`、`tool_error`、`invalid_tool_result`，节点名为 tools 并附原调用 ID。节点向上传播这些异常，Graph 统一转为失败状态。失败后的消息历史仅用于本次诊断。

## 默认图的交互规则

1. 从模型节点开始。每次发出请求前检查并占用一次模型调用额度。请求超时或服务报错，任务失败。
2. 若模型以 `tool_calls` 结束并给出一项或多项请求，先检查本批调用 ID 非空且互不重复，记录整条助手消息。如果已无下一轮模型调用额度，此时直接失败，避免执行无法回传结果的工具。否则转到工具节点。
3. 工具节点按请求顺序查找函数、解析 JSON 对象、校验参数并执行。每次成功都追加一条工具消息，原样填入该请求的 `tool_call_id`。全部成功后清空待执行列表并回到模型节点。查无工具、参数错误、函数抛错或返回类型错误时，任务立即失败，本批剩余调用停止。先前执行过的函数可能已经产生效果。
4. 模型以 `stop` 正常结束、没有待执行请求且回答文本非空时，默认 Agent 判定本次运行完成。工具返回成功仅说明该步骤成功，仍需回到模型判断下一步。此默认标准表示模型已给出最终答复。若业务要求验证实际结果，例如订单确已生成，需要依据订单系统的查询结果另定完成条件。
5. 回复截断、空回复或结束原因与工具请求矛盾均视为无效回复，运行失败。完成和失败都是终态，图停止调度。本版默认图每次回边都经过模型节点，因此模型调用上限也限制了循环次数。

## 最小验收示例

以运费为例，设模型额度为 2。下面按节点返回时的状态核对一整次调用。

| 执行步骤 | 新增消息 | 待执行 ID | 模型调用数 | 交给 Graph 的结果 |
| --- | --- | --- | --- | --- |
| Agent 初始化 | system 指令、user 提问 | 空 | 0 | 从 model 开始 |
| model 请求运费工具 | assistant，含 `call_1`、`calculate_shipping`、参数原文 `{"weight_kg":2.5}` | call_1 | 1 | needs_tools |
| tools 调用本地函数 | tool，关联 `call_1`，内容为“20.00 元” | 空 | 1 | tools_done |
| model 给出最终答案 | assistant，内容为“运费为 20 元。” | 空 | 2 | answered → completed |

若第二次模型回复仍请求工具，模型节点在记录助手消息后抛出 `model_limit`。Graph 进入 failed，第二批工具执行次数为零。最后一次额度可以用于产生最终回答。

用可控的模型回复驱动同一张图。直接给出最终回答应产生零次工具调用。连续两轮分别请求查重量和算运费，应看到两次工具执行、三次模型调用、一次成功返回。同一轮请求两次同名工具，应按各自 ID 收到对应结果。若第二次工具执行失败，运行应在该处失败。若模型始终请求工具，应在调用额度用尽时失败，且最后一轮提出的工具请求不再执行。
