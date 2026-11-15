import os

from loom import Agent, DeepSeekModel, tool


@tool
def calculate_shipping(weight_kg: float) -> str:
    """按每千克 8 元计算包裹运费。"""
    if weight_kg <= 0:
        raise ValueError("重量必须大于零")
    amount = f"{weight_kg * 8:.2f} 元"
    print(f"calculate_shipping({weight_kg} kg) → {amount}")
    return amount


if __name__ == "__main__":
    try:
        model = DeepSeekModel(api_key=os.environ["DEEPSEEK_API_KEY"], model=os.environ["DEEPSEEK_MODEL"])
    except KeyError as error:
        raise SystemExit(f"请在运行前设置环境变量 {error.args[0]}") from None
    agent = Agent(model=model, instructions="必须调用 calculate_shipping 计算运费，根据工具结果用中文回答。",
                  tools=[calculate_shipping], max_model_calls=3)
    print(agent.run("一个 2.5 千克的包裹，运费是多少？").text)
