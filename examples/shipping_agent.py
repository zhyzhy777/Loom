from loom import Agent, ModelReply, ToolCall, tool


@tool
def calculate_shipping(weight_kg: float) -> str:
    """按每千克 8 元计算包裹运费。"""
    if weight_kg <= 0:
        raise ValueError("重量必须大于零")
    return f"{weight_kg * 8:.2f} 元"


class ShippingDemoModel:
    """用固定的 2.5 千克请求演示一次工具往返。"""

    def complete(self, messages, tools):
        last = messages[-1]
        if last["role"] == "user":
            call = ToolCall("shipping_1", "calculate_shipping", '{"weight_kg": 2.5}')
            return ModelReply("tool_calls", calls=[call])
        return ModelReply("stop", text=f"运费为{last['content']}。")


if __name__ == "__main__":
    agent = Agent(model=ShippingDemoModel(), instructions="根据工具结果回答。",
                  tools=[calculate_shipping], max_model_calls=2)
    print(agent.run("一个 2.5 千克的包裹，运费是多少？").text)
