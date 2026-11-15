"""Run from the project root: python -m examples.stock_graph."""

from loom import END, Graph


def check_stock(order):
    return "available" if order["stock"] >= order["quantity"] else "short"


def quote(order):
    order["total"] = order["unit_price"] * order["quantity"]
    return "done"


if __name__ == "__main__":
    graph = Graph()
    graph.add_node("check", check_stock)
    graph.add_node("quote", quote)
    graph.set_entry("check")
    graph.add_edge("check", "available", "quote")
    graph.add_edge("check", "short", END)
    graph.add_edge("quote", "done", END)

    for stock in (3, 0):
        run = graph.run({"stock": stock, "quantity": 2, "unit_price": 8}, max_steps=2)
        if run.error is not None:
            raise run.error
        print(run.state.get("total", "库存不足"))
